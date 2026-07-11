// Session state: restores the account from the stored refresh token on boot,
// exposes sign-in / register / sign-out, and keeps /v1/me in sync.

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, clearSession, getApiUrl, refreshSession, storedRefreshToken, storeSession } from "./api";
import type { AuthResponse, User } from "./types";

interface RegisterPayload {
  email: string;
  password: string;
  displayName: string;
  role: "user" | "guardian";
  birthYear: number;
  birthMonth: number;
}

interface AuthContextValue {
  ready: boolean;
  hasServer: boolean;
  user: User | null;
  signIn: (email: string, password: string) => Promise<User>;
  register: (payload: RegisterPayload) => Promise<AuthResponse>;
  signOut: () => Promise<void>;
  reloadUser: () => Promise<User | null>;
  markServerConfigured: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [hasServer, setHasServer] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    (async () => {
      const url = await getApiUrl();
      setHasServer(Boolean(url));
      if (url) {
        const auth = await refreshSession();
        if (auth) setUser(auth.user);
      }
      setReady(true);
    })();
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const auth = await api<AuthResponse>("/v1/auth/login", {
      method: "POST",
      body: { email: email.trim().toLowerCase(), password },
    });
    await storeSession(auth);
    setUser(auth.user);
    return auth.user;
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    const auth = await api<AuthResponse>("/v1/auth/register", {
      method: "POST",
      body: { ...payload, email: payload.email.trim().toLowerCase() },
    });
    await storeSession(auth);
    setUser(auth.user);
    return auth;
  }, []);

  const signOut = useCallback(async () => {
    const refreshToken = await storedRefreshToken();
    if (refreshToken) {
      try {
        await api("/v1/auth/logout", { method: "POST", body: { refreshToken } });
      } catch {
        // Signing out locally is enough for the prototype.
      }
    }
    await clearSession();
    setUser(null);
  }, []);

  const reloadUser = useCallback(async () => {
    try {
      const me = await api<User>("/v1/me");
      setUser(me);
      return me;
    } catch {
      return null;
    }
  }, []);

  const value = useMemo(() => ({
    ready, hasServer, user, signIn, register, signOut, reloadUser,
    markServerConfigured: () => setHasServer(true),
  }), [ready, hasServer, user, signIn, register, signOut, reloadUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
