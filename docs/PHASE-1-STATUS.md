# Phase 1 status

> Foundations: code-side complete. Terraform apply deferred to the next session
> (blocked on `gcloud auth application-default login` being run interactively).

## What's in this phase

### Backend
- **New module** `services/api_gateway/app/auth.py`
  - `BootstrapAdminConfig.from_env()` — `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` (Nebula §5.3 pattern)
  - `issue_token()` / `decode_token()` — HS256 JWT, 12h TTL
  - `current_principal()` — FastAPI dependency for protected endpoints
  - JWT claim shape (`sub`, `email`, `tenant_id`, `brand`, `roles`, `iss`, `aud`, `exp`, `iat`) **mirrors Firebase Auth multi-tenant tokens** so Phase 1.5 swap is a verify-side change only (HS256→RS256, issuer string)
- **api_gateway/app/main.py**: new endpoints `/v1/auth/login` (bootstrap), `/v1/auth/me`. `/v1/me/datasets` now requires bearer token. `/healthz`, `/v1/me/brand`, `/v1/openapi.json`, `/v1/events-schema.json` stay public.
- **pyproject.toml**: `pyjwt>=2.9` added to core (pure Python, no compile on 3.14). Heavy crypto (`pyjwt[crypto]`, `argon2-cffi`, `google-cloud-secret-manager`) stay behind `[secrets]` extra for Phase 1.5.
- **Tests added**: 8 auth tests covering login success, wrong password / unknown user (identical 401 — no user enumeration), token-required endpoints, garbage tokens, bootstrap-not-configured.
- **Result**: 27/27 backend tests pass (was 19).

### Frontend
- **packages/auth fleshed out from stub**:
  - `types.ts` — `Principal`, `AuthState`, `LoginRequest`, `LoginResponse`, `AuthContextValue`
  - `AuthProvider.tsx` — React context, localStorage-backed token persistence, validates stored token on mount via `/v1/auth/me`, exposes `login` / `logout` / `refresh`
  - `LoginScreen.tsx` — Email/password form styled with the Aurora theme + brand-runtime CSS vars
  - `index.ts` — public surface
- **apps/web**: `main.tsx` wraps `<App/>` in `<AuthProvider apiBase={...}/>`. `App.tsx` renders `<LoginScreen/>` when unauth'd, the demo shell + Sign Out when auth'd. Calls `/v1/me/datasets` with the bearer token and shows the row count, proving the end-to-end flow works.
- **.env.nebula**: `VITE_API_BASE=/api` so the Vite dev proxy forwards to `http://localhost:8000`.

### Infra
- **Terraform 1.15.5 installed** via winget.
- **GCP APIs enabled** on `insights-navigator-v2`: cloudbuild, run, artifactregistry, bigquery, aiplatform, secretmanager, firestore, storage, firebase, firebasehosting, iamcredentials, cloudresourcemanager. Idempotent, $0.
- **Active project switched** to `insights-navigator-v2` (billing confirmed enabled).
- **`terraform apply` deferred** — needs `gcloud auth application-default login` (interactive). Run it, then resume Task #9.

## Verification

| Check | Result |
|---|---|
| Frontend `pnpm install` | ✅ no new packages needed |
| Frontend `pnpm typecheck` | ✅ all 13 workspace projects |
| Frontend `pnpm --filter @insnav/locale test` | ✅ 9/9 (India non-negotiables) |
| Frontend `pnpm build --mode nebula` | ✅ 49 KB gzipped (was 48) |
| Backend `pytest -v` | ✅ 27/27 (was 19) |
| **Total tests** | **✅ 36/36** |
| GCP APIs enabled | ✅ 12 APIs |
| GCP project switched | ✅ insights-navigator-v2 |
| Terraform install | ✅ 1.15.5 |
| ADC for Terraform | ⏳ pending user interactive step |
| `terraform apply` | ⏳ deferred |

## Manual setup notes (for the next deploy)

Set these env vars on the backend Cloud Run service when you deploy:

```
BOOTSTRAP_ADMIN_EMAIL=<your-admin-email>
BOOTSTRAP_ADMIN_PASSWORD=<strong-password>     # rotate before any real customer
INSNAV_JWT_SECRET=<48-byte-random-secret>      # read from Secret Manager
INSNAV_CORS_ORIGINS=https://<your-firebase-hosting-url>
```

For local dev:
```bash
export BOOTSTRAP_ADMIN_EMAIL=admin@local.dev
export BOOTSTRAP_ADMIN_PASSWORD=changeme
export INSNAV_JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(24))")
make dev-backend
```

## Next phase (1.5 — Firebase Auth multi-tenant upgrade)

1. `gcloud auth application-default login` (interactive, you)
2. `cd infra/terraform && terraform init && terraform plan && terraform apply` for free-tier resources (Artifact Registry, GCS staging, BQ datasets, Firestore, Secret Manager, service accounts + IAM)
3. Firebase Console: add Firebase to the GCP project, enable Identity Platform with multi-tenancy
4. Backend: install `[secrets]` extra (`pyjwt[crypto]`, Firebase Admin SDK), swap HS256 → RS256 verify against Firebase JWKS, keep bootstrap admin as fallback for break-glass
5. Frontend: install `firebase` SDK, swap email/password form for the Firebase Auth UI (tenant-aware), keep token shape unchanged so nothing else has to change
6. Add `tenant_access` Firestore collection + first real user
