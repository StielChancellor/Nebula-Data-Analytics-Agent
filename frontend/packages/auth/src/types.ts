/**
 * Auth shapes. Mirror of backend insnav_contracts + auth.py.
 * Keep these in sync; codegen from OpenAPI replaces this hand-written file in Phase 1.5.
 */

export interface Principal {
  sub: string;
  email: string;
  tenant_id: string;
  brand: string;
  roles: Array<"admin" | "user">;
}

export type AuthStatus = "idle" | "loading" | "authenticated" | "unauthenticated" | "error";

export interface AuthState {
  status: AuthStatus;
  principal: Principal | null;
  token: string | null;
  error: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface AuthContextValue extends AuthState {
  login: (req: LoginRequest) => Promise<void>;
  logout: () => void;
  /** Refresh the principal from /v1/auth/me (e.g. after token restore on boot) */
  refresh: () => Promise<void>;
  /**
   * Returns the freshest bearer token (Firebase auto-refreshes; bootstrap
   * returns the stored JWT). Pass this to the ApiClient instead of `token`
   * so Firebase ID tokens never go stale.
   */
  getToken: () => Promise<string | null>;
  /** True when the app is using Firebase Auth (vs bootstrap admin login). */
  firebaseMode: boolean;
}
