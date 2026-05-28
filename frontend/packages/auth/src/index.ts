/**
 * @insnav/auth
 *
 * Firebase Auth multi-tenant. One Firebase project per backend; one Firebase
 * tenant per brand. JWT carries `tenant_id` + `brand` claims; same token
 * format across all brand frontends (PRD D8).
 *
 * Also: bootstrap-admin override via env vars for MVP shipping pre-user-mgmt
 * (Nebula §5.3). Rotate before any real customer.
 *
 * TODO Phase 1.
 */

export interface AuthState {
  user: { id: string; email: string; tenantId: string; brand: string } | null;
  token: string | null;
}

export const AUTH_VERSION = "0.1.0";
