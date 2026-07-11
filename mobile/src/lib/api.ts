// Small fetch wrapper: base-URL storage, bearer tokens, single-flight refresh.
// The refresh token lives in SecureStore; the access token stays in memory.

import * as SecureStore from "expo-secure-store";

import type { AuthResponse, Health } from "./types";

const URL_KEY = "ambl.apiUrl";
const REFRESH_KEY = "ambl.refreshToken";
const DEFAULT_TIMEOUT_MS = 12_000;

let baseUrl: string | null = null;
let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;

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
  if (!baseUrl) baseUrl = await safeGet(URL_KEY);
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
                       "Could not reach the server. Check that the phone and the Mac share the same Wi-Fi.");
  } finally {
    timeout.done();
  }
}

async function tryRefresh(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      const token = await storedRefreshToken();
      if (!token) return false;
      try {
        const response = await rawRequest("/v1/auth/refresh", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refreshToken: token }),
        }, DEFAULT_TIMEOUT_MS);
        if (!response.ok) return false;
        await storeSession(await response.json() as AuthResponse);
        return true;
      } catch {
        return false;
      } finally {
        refreshing = null;
      }
    })();
  }
  return refreshing;
}

export async function refreshSession(): Promise<AuthResponse | null> {
  const token = await storedRefreshToken();
  if (!token) return null;
  try {
    const response = await rawRequest("/v1/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refreshToken: token }),
    }, DEFAULT_TIMEOUT_MS);
    if (!response.ok) {
      await clearSession();
      return null;
    }
    const auth = await response.json() as AuthResponse;
    await storeSession(auth);
    return auth;
  } catch {
    return null;
  }
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

  if (response.status === 401 && retryOn401 && await tryRefresh()) {
    return api<T>(path, { ...options, retryOn401: false });
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
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
                       "No a-mbl server answered at this address. Check the address, the Wi-Fi network, and the Mac firewall.");
  } finally {
    timeout.done();
  }
}
