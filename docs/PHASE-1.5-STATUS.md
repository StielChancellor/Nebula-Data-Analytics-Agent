# Phase 1.5 status — Firebase Auth multi-tenant

> Dual-mode auth: the backend verifies BOTH our bootstrap HS256 tokens
> (break-glass) AND Firebase RS256 ID tokens (real users), auto-detecting by
> algorithm. The frontend uses Firebase when configured, else falls back to the
> bootstrap login. Identity Platform is provisioned + live.

## What shipped

### Backend (dual-mode, fully offline-testable)
- `services/api_gateway/app/firebase.py` — verifies Firebase ID tokens against
  Google's JWKS: RS256, issuer `https://securetoken.google.com/<project>`,
  audience `<project>`, tenant from `claims.firebase.tenant`. Injectable signing
  key resolver so the whole path is testable with a local RSA keypair.
- `auth.py` `decode_token()` now routes by JWT `alg`:
  - HS256 → bootstrap admin (break-glass, unchanged)
  - RS256 → Firebase / Identity Platform
- `settings.py` — `firebase_project` (defaults to gcp_project) + `firebase_jwks_url`.
- **9 new tests** (`test_firebase_auth.py`): valid token → principal+tenant,
  default tenant, custom claims (brand/roles), wrong audience/issuer/expiry/key
  all rejected, bootstrap HS256 still works alongside, garbage rejected.

### Frontend (Firebase-or-bootstrap, same useAuth surface)
- `@insnav/auth` `firebase.ts` — lazy, optional. Reads `VITE_FIREBASE_*`; if
  present, uses Firebase Auth (email/password, tenant-aware, ID token
  auto-refresh); else the app falls back to bootstrap login. The firebase SDK
  is dynamically imported, so it splits into a lazy chunk (~37 KB gzip) and is
  absent from brands that don't configure it.
- `AuthProvider` branches on `firebaseMode`; exposes `getToken()` (async, always
  fresh) — the ApiClient now uses it so Firebase ID tokens never go stale.
- `LoginScreen` footer reflects the active mode. `firebase@^11` added to
  `@insnav/auth`.

### Infra — Identity Platform LIVE
- APIs enabled: `identitytoolkit`, `apikeys`.
- `infra/terraform/identity_platform.tf` (gated `enable_identity_platform`):
  `google_identity_platform_config` (email/password sign-in),
  `google_apikeys_key` (browser web key), and a named-tenant resource gated
  separately (`enable_identity_platform_tenant`).
- Provider fix: `user_project_override = true` + `billing_project` (the apikeys
  + Identity Platform APIs reject user ADC without a quota project).
- **Live on insights-navigator-v2:** Identity Platform config initialized
  (self-initialized, no console click needed), multi-tenancy enabled via the
  Admin API (`multiTenant.allowTenants=true`), browser web API key created.

## Live config values (for wiring a frontend brand)

```
VITE_FIREBASE_API_KEY      = <terraform output -raw firebase_web_api_key>   # AIzaSyCf0oyg…
VITE_FIREBASE_AUTH_DOMAIN  = insights-navigator-v2.firebaseapp.com
VITE_FIREBASE_PROJECT_ID   = insights-navigator-v2
# VITE_FIREBASE_TENANT_ID  = <tenant-id>   # only when using a named tenant
```

Backend: set `INSNAV_FIREBASE_PROJECT=insights-navigator-v2` (or leave unset —
it defaults to the gcp project).

## What was NOT done (deliberate / deferred)

- **Named per-brand tenants.** Single-tenant works for the MVP (users land in
  the default tenant; backend maps to `"default"`). The Terraform
  `google_identity_platform_tenant` resource hit a provider `INVALID_PROJECT_ID`
  quirk; gated behind `enable_identity_platform_tenant=false`. Create named
  tenants (console or a fixed provider call) when onboarding a second brand.
- **Creating a test user.** Do it via the Firebase console or the Admin SDK:
  ```python
  import firebase_admin
  from firebase_admin import auth
  firebase_admin.initialize_app()
  auth.create_user(email="you@example.com", password="…")
  # custom claims (brand/roles): auth.set_custom_user_claims(uid, {"brand":"nebula","roles":["admin","user"]})
  ```
- **tenant_access ACLs.** Datasets are already tenant-scoped via the token's
  tenant. Finer per-dataset sharing within a tenant is deferred until needed.
- **Wiring Firebase into a deployed frontend.** The frontend isn't deployed yet
  (Firebase Hosting still gated). When it is, set the VITE_FIREBASE_* env above
  for the brand build and users can sign in with Firebase. Until then, the app
  runs in bootstrap-admin mode.

## Verification

| Check | Result |
|---|---|
| Backend `pytest` | ✅ 139/139 (+9 Firebase) |
| Firebase RS256 verify (local RSA keypair) | ✅ valid + all rejection paths |
| Bootstrap HS256 still works (dual-mode) | ✅ |
| Frontend `pnpm typecheck` (13 projects) | ✅ |
| Frontend `pnpm build` | ✅ firebase split into lazy chunk (~37 KB gzip) |
| `terraform validate` | ✅ |
| Identity Platform config + web API key | ✅ live |
| Multi-tenancy enabled | ✅ (Admin API) |

## Cost

$0 incremental. Identity Platform free tier covers 50K MAU; the API key + config
are free.

---

Next in the requested sequence: **Phase 5c (Cube Store for production)** →
**Phase 6 (agent swarm)**.
