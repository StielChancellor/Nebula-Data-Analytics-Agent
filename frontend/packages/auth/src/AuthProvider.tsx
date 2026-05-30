/**
 * AuthProvider — React context that owns the auth state. Phase 1.5 dual-mode:
 *
 *  - Firebase mode (VITE_FIREBASE_* configured): email/password via the
 *    Firebase SDK, tenant-aware, ID token auto-refreshed. Session persistence
 *    is handled by the SDK (IndexedDB).
 *  - Bootstrap mode (no Firebase env): the Phase 1 flow — POST /v1/auth/login
 *    for an HS256 admin token kept in localStorage.
 *
 * Both expose the same useAuth() surface. Components should call `getToken()`
 * (async) for the freshest bearer rather than reading `token` directly.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
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
import {
  firebaseSignIn,
  firebaseSignOut,
  getFirebaseIdToken,
  isFirebaseConfigured,
  onFirebaseAuthChanged,
} from "./firebase";

const STORAGE_KEY = "insnav.token";

const AuthContext = createContext<AuthContextValue | null>(null);

interface ProviderProps {
  /** Absolute or relative base for API calls. e.g. "/api" in dev (Vite proxy). */
  apiBase: string;
  children: ReactNode;
}

export function AuthProvider({ apiBase, children }: ProviderProps) {
  const firebaseMode = isFirebaseConfigured();

  const [state, setState] = useState<AuthState>(() => ({
    status: firebaseMode || loadStoredToken() ? "loading" : "unauthenticated",
    principal: null,
    token: firebaseMode ? null : loadStoredToken(),
    error: null,
  }));

  // Keep a ref to the latest token so getToken() (passed to ApiClient) is stable.
  const tokenRef = useRef<string | null>(state.token);
  tokenRef.current = state.token;

  const getToken = useCallback(async (): Promise<string | null> => {
    if (firebaseMode) return getFirebaseIdToken();
    return tokenRef.current;
  }, [firebaseMode]);

  // ---- Bootstrap-mode bootstrap (validate stored token on mount) ----
  const refresh = useCallback(async () => {
    if (firebaseMode) return; // Firebase drives state via the listener below
    const token = tokenRef.current;
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
  }, [apiBase, firebaseMode]);

  useEffect(() => {
    if (firebaseMode) {
      let unsub: (() => void) | undefined;
      void onFirebaseAuthChanged((principal) => {
        if (principal) {
          setState({ status: "authenticated", principal, token: null, error: null });
        } else {
          setState({ status: "unauthenticated", principal: null, token: null, error: null });
        }
      }).then((u) => {
        unsub = u;
      });
      return () => unsub?.();
    }
    if (tokenRef.current) void refresh();
    else setState((s) => ({ ...s, status: "unauthenticated" }));
    return undefined;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = useCallback(
    async (req: LoginRequest) => {
      setState((s) => ({ ...s, status: "loading", error: null }));
      try {
        if (firebaseMode) {
          const principal = await firebaseSignIn(req.email, req.password);
          setState({ status: "authenticated", principal, token: null, error: null });
          return;
        }
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
        tokenRef.current = data.access_token;
        const meRes = await fetch(`${apiBase}/v1/auth/me`, {
          headers: { Authorization: `Bearer ${data.access_token}` },
        });
        const principal = (await meRes.json()) as Principal;
        setState({ status: "authenticated", principal, token: data.access_token, error: null });
      } catch (e) {
        setState({
          status: "error",
          principal: null,
          token: null,
          error: e instanceof Error ? e.message : "Login failed",
        });
      }
    },
    [apiBase, firebaseMode],
  );

  const logout = useCallback(() => {
    if (firebaseMode) {
      void firebaseSignOut();
    } else {
      localStorage.removeItem(STORAGE_KEY);
      tokenRef.current = null;
    }
    setState({ status: "unauthenticated", principal: null, token: null, error: null });
  }, [firebaseMode]);

  const value = useMemo<AuthContextValue>(
    () => ({ ...state, login, logout, refresh, getToken, firebaseMode }),
    [state, login, logout, refresh, getToken, firebaseMode],
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
