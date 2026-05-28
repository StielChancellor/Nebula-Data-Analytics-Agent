/**
 * AuthProvider — React context that owns the auth state.
 *
 * Phase 1 token storage: localStorage keyed by `insnav.token`. Fine for
 * single-domain MVP. Phase 1.5 with Firebase will swap this for the SDK's
 * built-in IndexedDB-backed persistence.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type {
  AuthContextValue,
  AuthState,
  LoginRequest,
  LoginResponse,
  Principal,
} from "./types";

const STORAGE_KEY = "insnav.token";

const AuthContext = createContext<AuthContextValue | null>(null);

interface ProviderProps {
  /** Absolute or relative base for API calls. e.g. "/api" in dev (Vite proxy) or "https://api.example.com" */
  apiBase: string;
  children: ReactNode;
}

export function AuthProvider({ apiBase, children }: ProviderProps) {
  const [state, setState] = useState<AuthState>(() => ({
    status: loadStoredToken() ? "loading" : "unauthenticated",
    principal: null,
    token: loadStoredToken(),
    error: null,
  }));

  const refresh = useCallback(async () => {
    const token = state.token;
    if (!token) {
      setState((s) => ({ ...s, status: "unauthenticated", principal: null }));
      return;
    }
    try {
      const res = await fetch(`${apiBase}/v1/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const principal = (await res.json()) as Principal;
      setState({ status: "authenticated", principal, token, error: null });
    } catch {
      localStorage.removeItem(STORAGE_KEY);
      setState({ status: "unauthenticated", principal: null, token: null, error: null });
    }
  }, [apiBase, state.token]);

  // On mount: if we have a token in storage, validate it
  useEffect(() => {
    if (state.token && state.status === "loading") {
      void refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (req: LoginRequest) => {
      setState((s) => ({ ...s, status: "loading", error: null }));
      try {
        const res = await fetch(`${apiBase}/v1/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(req),
        });
        if (!res.ok) {
          const body = (await res.json().catch(() => ({}))) as { detail?: string };
          throw new Error(body.detail || `HTTP ${res.status}`);
        }
        const data = (await res.json()) as LoginResponse;
        localStorage.setItem(STORAGE_KEY, data.access_token);
        // Get the principal next
        const meRes = await fetch(`${apiBase}/v1/auth/me`, {
          headers: { Authorization: `Bearer ${data.access_token}` },
        });
        const principal = (await meRes.json()) as Principal;
        setState({
          status: "authenticated",
          principal,
          token: data.access_token,
          error: null,
        });
      } catch (e) {
        setState({
          status: "error",
          principal: null,
          token: null,
          error: e instanceof Error ? e.message : "Login failed",
        });
      }
    },
    [apiBase],
  );

  const logout = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setState({ status: "unauthenticated", principal: null, token: null, error: null });
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, logout, refresh }),
    [state, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider/>");
  return ctx;
}

export function loadStoredToken(): string | null {
  if (typeof localStorage === "undefined") return null;
  return localStorage.getItem(STORAGE_KEY);
}
