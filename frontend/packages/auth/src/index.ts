/**
 * @insnav/auth — frontend auth surface.
 *
 * Phase 1: bootstrap admin login flow (HS256 JWT from backend).
 * Phase 1.5: swap to Firebase Auth multi-tenant SDK. The shapes here mirror
 *            what Firebase returns so the AuthProvider stays unchanged.
 *
 * Exports:
 *   AuthProvider           — wrap your <App/> with this
 *   useAuth()              — { principal, token, login, logout, status }
 *   AuthState              — type shape
 *   loadStoredToken()      — read token from localStorage on bootstrap
 */
export type {
  AuthState,
  Principal,
  AuthStatus,
  AuthContextValue,
  LoginRequest,
  LoginResponse,
} from "./types";

export { AuthProvider, useAuth, loadStoredToken } from "./AuthProvider";
export { LoginScreen } from "./LoginScreen";
export { isFirebaseConfigured, readFirebaseEnv } from "./firebase";

export const AUTH_VERSION = "0.3.0";
