/**
 * Firebase Auth integration (Phase 1.5).
 *
 * Optional + lazy. When VITE_FIREBASE_* env is present, the AuthProvider uses
 * Firebase / Identity Platform (email/password, tenant-aware) and sends the
 * Firebase ID token as the bearer. When absent, the app falls back to the
 * bootstrap-admin login (Phase 1 behavior) and none of the firebase SDK is
 * loaded — the imports below are dynamic so the SDK stays out of the bundle
 * for brands that don't use it.
 */
import type { Principal } from "./types";

export interface FirebaseEnv {
  apiKey: string;
  authDomain: string;
  projectId: string;
  tenantId?: string;
}

export function readFirebaseEnv(): FirebaseEnv | null {
  const apiKey = import.meta.env.VITE_FIREBASE_API_KEY;
  const authDomain = import.meta.env.VITE_FIREBASE_AUTH_DOMAIN;
  const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID;
  if (!apiKey || !authDomain || !projectId) return null;
  return {
    apiKey,
    authDomain,
    projectId,
    tenantId: import.meta.env.VITE_FIREBASE_TENANT_ID || undefined,
  };
}

export function isFirebaseConfigured(): boolean {
  return readFirebaseEnv() !== null;
}

// We hold the firebase auth instance once initialized.
// `any` here avoids a hard type dependency on the firebase SDK for brands
// that don't install/use it.
let _auth: any = null;

async function getAuth(): Promise<any> {
  if (_auth) return _auth;
  const env = readFirebaseEnv();
  if (!env) throw new Error("Firebase is not configured");
  const { initializeApp, getApps } = await import("firebase/app");
  const { getAuth: fbGetAuth } = await import("firebase/auth");
  const app = getApps().length ? getApps()[0] : initializeApp({
    apiKey: env.apiKey,
    authDomain: env.authDomain,
    projectId: env.projectId,
  });
  _auth = fbGetAuth(app);
  if (env.tenantId) _auth.tenantId = env.tenantId;
  return _auth;
}

export async function firebaseSignIn(email: string, password: string): Promise<Principal> {
  const auth = await getAuth();
  const { signInWithEmailAndPassword } = await import("firebase/auth");
  const cred = await signInWithEmailAndPassword(auth, email, password);
  const tokenResult = await cred.user.getIdTokenResult();
  const claims = tokenResult.claims as Record<string, unknown>;
  const fb = (claims.firebase as { tenant?: string } | undefined) ?? {};
  return {
    sub: cred.user.uid,
    email: cred.user.email ?? email,
    tenant_id: (fb.tenant as string) || "default",
    brand: (claims.brand as string) || "nebula",
    roles: (claims.roles as Array<"admin" | "user">) || ["user"],
  };
}

export async function firebaseSignOut(): Promise<void> {
  if (!isFirebaseConfigured()) return;
  const auth = await getAuth();
  const { signOut } = await import("firebase/auth");
  await signOut(auth);
}

/** Current Firebase ID token (auto-refreshes). null if not signed in. */
export async function getFirebaseIdToken(): Promise<string | null> {
  if (!isFirebaseConfigured()) return null;
  const auth = await getAuth();
  const user = auth.currentUser;
  if (!user) return null;
  return user.getIdToken();
}

/** Subscribe to auth-state changes; returns an unsubscribe fn. */
export async function onFirebaseAuthChanged(
  cb: (principal: Principal | null) => void,
): Promise<() => void> {
  const auth = await getAuth();
  const { onAuthStateChanged } = await import("firebase/auth");
  return onAuthStateChanged(auth, async (user: any) => {
    if (!user) {
      cb(null);
      return;
    }
    const tokenResult = await user.getIdTokenResult();
    const claims = tokenResult.claims as Record<string, unknown>;
    const fb = (claims.firebase as { tenant?: string } | undefined) ?? {};
    cb({
      sub: user.uid,
      email: user.email ?? "",
      tenant_id: (fb.tenant as string) || "default",
      brand: (claims.brand as string) || "nebula",
      roles: (claims.roles as Array<"admin" | "user">) || ["user"],
    });
  });
}
