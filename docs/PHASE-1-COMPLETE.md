# Phase 1 complete

> Foundations fully landed: GCP infra applied + bootstrap admin auth wired
> end-to-end. Ready for Phase 2 (CSV ingestion).

## GCP resources live in `insights-navigator-v2`

All scale-to-zero / free-tier. Honors the $5/mo cost guardrail.

| Resource | Identifier | Notes |
|---|---|---|
| Artifact Registry repo | `us-central1-docker.pkg.dev/insights-navigator-v2/insnav` | Push backend Docker images here |
| GCS staging bucket | `insights-navigator-v2-staging` | CORS configured for resumable uploads; 30-day TTL on contents |
| BQ dataset (data) | `insights-navigator-v2.datasets` | Cleaned, modeled datasets (L1+) |
| BQ dataset (audit) | `insights-navigator-v2.audit` | Append-only query log |
| Firestore | `(default)` native, us-central1 | Will hold knowledge graph, dashboards, brand configs |
| Secret: JWT | `insnav-jwt-secret` (version 1 loaded) | 48-byte random; read by api_gateway at boot |
| Secret: Anthropic key | `anthropic-api-key` (empty) | Add when wiring Claude fallback |
| SA: api_gateway | `insnav-api-gateway@insights-navigator-v2.iam.gserviceaccount.com` | `datastore.user`, `secretmanager.secretAccessor` |
| SA: orchestrator | `insnav-orchestrator@insights-navigator-v2.iam.gserviceaccount.com` | `bigquery.dataEditor`, `bigquery.jobUser`, `datastore.user`, `secretmanager.secretAccessor`, `aiplatform.user`, `storage.objectUser` |
| SA: compute_sandbox | `insnav-compute-sandbox@insights-navigator-v2.iam.gserviceaccount.com` | Roles added when Phase 9 sandbox lands |
| APIs enabled | 12 | cloudbuild, run, artifactregistry, bigquery, aiplatform, secretmanager, firestore, storage, firebase, firebasehosting, iamcredentials, cloudresourcemanager |

**Total resources:** 30 (Terraform-managed) + 1 secret version (out-of-band)
**Estimated monthly cost at idle:** $0

## Pending (deferred, won't move forward without explicit ask)

- `enable_cloud_run = false` until first backend image is built and pushed
- `enable_firebase_hosting = false` until you run `firebase init` interactively in the Firebase Console
- Anthropic API key value not loaded (placeholder secret only)

## Verification

```bash
gcloud bq ls --project=insights-navigator-v2                # datasets, audit
gcloud secrets list --project=insights-navigator-v2         # jwt + anthropic-api-key
gcloud iam service-accounts list --project=insights-navigator-v2
gsutil ls gs://insights-navigator-v2-staging
```

## What changed in the repo this session

- `infra/terraform/main.tf` — fixed HCL syntax (nested `replication { auto {} }` blocks)
- `infra/terraform/terraform.tfvars` — created from `.example` (gitignored)
- `infra/terraform/.terraform.lock.hcl` — committed (provider version pin)
- `.gitignore` — stopped ignoring the lock file
- `docs/PHASE-1-COMPLETE.md` — this file

## Next: Phase 1.5 (Firebase Auth multi-tenant)

The bootstrap admin we shipped in `47e5b1c` is the break-glass path. Phase 1.5
swaps it for the real Firebase Auth multi-tenant flow:

1. Firebase Console → Add Firebase to GCP project → enable Identity Platform with multi-tenancy
2. Backend: `pip install '.[secrets]'`, swap HS256 → RS256 verify against Firebase JWKS, keep bootstrap admin as fallback
3. Frontend: add `firebase` SDK, swap email/password form for Firebase Auth UI (tenant-aware), token shape unchanged
4. Add `tenant_access` Firestore collection + first real user

Or skip to **Phase 2 (CSV ingestion)** — that's the next big product capability
per the PRD build order. Auth is good enough for now.
