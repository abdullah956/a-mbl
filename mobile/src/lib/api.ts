// Small fetch wrapper: base-URL storage, bearer tokens, single-flight refresh.
// The refresh token lives in SecureStore; the access token stays in memory.

import * as FileSystem from "expo-file-system/legacy";
import * as SecureStore from "expo-secure-store";

import type { AuthResponse, Health } from "./types";

const URL_KEY = "ambl.apiUrl";
const REFRESH_KEY = "ambl.refreshToken";
const DEFAULT_TIMEOUT_MS = 12_000;

// Development-only default (roadmap §9.3): EXPO_PUBLIC_API_URL is inlined at
// build time and seeds the address until one is saved on the connect screen.
const ENV_URL = process.env.EXPO_PUBLIC_API_URL?.replace(/\/+$/, "") ?? null;

let baseUrl: string | null = null;
let accessToken: string | null = null;
let refreshing: Promise<AuthResponse | null> | null = null;

export class ApiError extends Error {
  code: string;
  status: number;
  fieldErrors?: Record<string, string>;

  constructor(status: number, code: string, message: string,
              fieldErrors?: Record<string, string>) {
    super(message);
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }
}

async function safeGet(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

async function safeSet(key: string, value: string | null): Promise<void> {
  try {
    if (value === null) await SecureStore.deleteItemAsync(key);
    else await SecureStore.setItemAsync(key, value);
  } catch {
    // Storage is best-effort on unsupported platforms (e.g. web preview).
  }
}

export async function getApiUrl(): Promise<string | null> {
  if (!baseUrl) baseUrl = (await safeGet(URL_KEY)) ?? ENV_URL;
  return baseUrl;
}

export async function setApiUrl(url: string): Promise<void> {
  baseUrl = url.replace(/\/+$/, "");
  await safeSet(URL_KEY, baseUrl);
}

export function currentAccessToken(): string | null {
  return accessToken;
}

export async function storeSession(auth: AuthResponse): Promise<void> {
  accessToken = auth.accessToken;
  await safeSet(REFRESH_KEY, auth.refreshToken);
}

export async function clearSession(): Promise<void> {
  accessToken = null;
  await safeSet(REFRESH_KEY, null);
}

export async function storedRefreshToken(): Promise<string | null> {
  return safeGet(REFRESH_KEY);
}

function withTimeout(ms: number): { signal: AbortSignal; done: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  return { signal: controller.signal, done: () => clearTimeout(timer) };
}

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    return new ApiError(response.status, body.code ?? "error",
                        body.message ?? "The request failed.", body.fieldErrors);
  } catch {
    return new ApiError(response.status, "error", "The request failed.");
  }
}

async function rawRequest(path: string, options: RequestInit,
                          timeoutMs: number): Promise<Response> {
  const url = await getApiUrl();
  if (!url) throw new ApiError(0, "no_server", "Set the server address first.");
  const timeout = withTimeout(timeoutMs);
  try {
    return await fetch(`${url}${path}`, { ...options, signal: timeout.signal });
  } catch {
    throw new ApiError(0, "unreachable",
                       "Could not reach the server. Check that the phone and the server's computer share the same Wi-Fi.");
  } finally {
    timeout.done();
  }
}

export function refreshSession(): Promise<AuthResponse | null> {
  // Single-flight: the backend rotates refresh tokens and treats reuse as
  // theft (revoking ALL of the user's sessions), so every caller — boot,
  // 401 retry, evidence reload — must share one in-flight request.
  if (!refreshing) {
    refreshing = (async () => {
      const token = await storedRefreshToken();
      if (!token) return null;
      try {
        const response = await rawRequest("/v1/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refreshToken: token }),
        }, DEFAULT_TIMEOUT_MS);
        if (!response.ok) {
          // Only a 401 means the token itself is dead; keep it on
          // transient server errors so the session can recover.
          if (response.status === 401) await clearSession();
          return null;
        }
        const auth = await response.json() as AuthResponse;
        await storeSession(auth);
        return auth;
      } catch {
        return null;
      } finally {
        refreshing = null;
      }
    })();
  }
  return refreshing;
}

export async function api<T>(path: string, options: {
  method?: string;
  body?: unknown;
  formData?: FormData;
  timeoutMs?: number;
  retryOn401?: boolean;
} = {}): Promise<T> {
  const { method = "GET", body, formData, timeoutMs = DEFAULT_TIMEOUT_MS,
          retryOn401 = true } = options;

  const headers: Record<string, string> = {};
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  const response = await rawRequest(path, {
    method,
    headers,
    body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
  }, timeoutMs);

  if (response.status === 401 && retryOn401 && await refreshSession()) {
    return api<T>(path, { ...options, retryOn401: false });
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export async function apiUpload<T>(path: string, fileUri: string,
                                   mimeType: string, retryOn401 = true): Promise<T> {
  // fetch + FormData{uri} silently fails to send on current React Native, so
  // uploads go through expo-file-system's native multipart uploader instead.
  const url = await getApiUrl();
  if (!url) throw new ApiError(0, "no_server", "Set the server address first.");

  let result: FileSystem.FileSystemUploadResult;
  try {
    result = await FileSystem.uploadAsync(`${url}${path}`, fileUri, {
      httpMethod: "POST",
      uploadType: FileSystem.FileSystemUploadType.MULTIPART,
      fieldName: "file",
      mimeType,
      headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {},
    });
  } catch {
    throw new ApiError(0, "unreachable",
                       "Could not reach the server. Check that the phone and the server's computer share the same Wi-Fi.");
  }

  if (result.status === 401 && retryOn401 && await refreshSession()) {
    return apiUpload<T>(path, fileUri, mimeType, false);
  }
  if (result.status < 200 || result.status >= 300) {
    try {
      const body = JSON.parse(result.body);
      throw new ApiError(result.status, body.code ?? "error",
                         body.message ?? "The upload failed.", body.fieldErrors);
    } catch (err) {
      if (err instanceof ApiError) throw err;
      throw new ApiError(result.status, "error", "The upload failed.");
    }
  }
  return JSON.parse(result.body) as T;
}

export async function checkHealth(url: string): Promise<Health> {
  const timeout = withTimeout(5_000);
  try {
    const response = await fetch(`${url.replace(/\/+$/, "")}/v1/health`,
                                 { signal: timeout.signal });
    if (!response.ok) throw new Error();
    return await response.json() as Health;
  } catch {
    throw new ApiError(0, "unreachable",
                       "No a-mbl server answered at this address. Check the address, the Wi-Fi network, and the computer's firewall.");
  } finally {
    timeout.done();
  }
}
