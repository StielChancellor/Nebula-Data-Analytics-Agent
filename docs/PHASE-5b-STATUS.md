# Phase 5b status

> The deployment stack for Cube: a container that reads the generated model
> from GCS, a backend sync that publishes it, a REST query client for the
> Phase 6 Semantic agent, and gated Terraform. **Built and verified locally;
> NOT deployed yet** — the live deploy is the checkpoint below.

## Architecture

```
[backend] insnav_cube_client.sync.sync_cube_model()
      writes per-tenant model → gs://<bucket>/cube-model/<tenant>/<cube>.js
                                gs://<bucket>/cube-model/<tenant>/__version__
      triggers: POST /v1/cube/sync, on edge-approve, or the cube_gen job
                      │
                      ▼
[Cube container]  infra/cube/cube.js
      repositoryFactory reads the tenant's *.js from GCS at compile time
      schemaVersion reads __version__ → recompiles when the model changes
      contextToAppId namespaces the model per tenant (isolation)
      BigQuery driver runs the compiled SQL via the runtime SA's ADC
                      │
                      ▼
[Phase 6 agent]  insnav_cube_client.CubeQueryClient
      mints a Cube API JWT carrying {tenant_id} as the security context
      load()/sql() → governed results. LLM selects; Cube compiles the SQL.
```

## What shipped

### Backend
- `insnav_cube_client.sync` — `sync_cube_model()` renders a tenant's schemas
  and writes them to GCS (offline in-memory store for tests). `model_version()`
  is a content hash so identical data → identical version (no Cube recompile
  churn). **Determinism fix**: `render_to_js()` no longer embeds a timestamp,
  so re-syncing unchanged data is byte-identical.
- `insnav_cube_client.client.CubeQueryClient` — REST client (`load`, `sql`,
  `meta`) + `mint_cube_token()` (HS256, payload = security context). Offline
  stub returns deterministic fixtures so Phase 6 + tests run without a live Cube.
- `generator.build_tenant_schemas()` — builds all of a tenant's schemas in one
  call (shared by the cube router and the sync).
- `cube_sync_service.py` — `sync_tenant()` / `sync_all_tenants()` bridge
  Firestore state → the sync.
- `datasets.py` — `list_all_ready_datasets()` + `get_column_profiles()` helpers.
- Endpoints: `POST /v1/cube/sync` (publish caller's tenant). Edge-approve now
  re-syncs automatically (wrapped so a sync hiccup can't roll back the approve).
- `services/cube_gen/app/main.py` — real Cloud Run Job: `sync_all_tenants()`.

### Cube container (`infra/cube/`)
- `Dockerfile` on `cubejs/cube:v1.6.52` (verified current tag) + `@google-cloud/storage`.
- `cube.js` — GCS `repositoryFactory` + `schemaVersion` + per-tenant
  `contextToAppId` + `queryRewrite` tenant guard. Syntax-checked with `node --check`.
- `README.md` — build/push + required env + local smoke-test recipe.

### Frontend
- `api-client` — `syncCubeModel()` + `CubeSyncResult`.
- Cube tab — **"Publish to Cube"** button → calls `/v1/cube/sync`, shows the
  published version.

### Infra (Terraform, gated)
- `enable_cube` var (default **false**).
- Cube Cloud Run service (scales to zero), `cube-gen` Cloud Run Job, `insnav-cube`
  runtime SA (`bigquery.dataViewer`/`jobUser`, `storage.objectViewer`,
  `secretmanager.secretAccessor`), `cube-api-secret` Secret Manager secret.
- api_gateway SA gains `storage.objectUser` + `bigquery.dataViewer`/`jobUser`
  (it runs the sync + profiler + edge-overlap queries).
- `terraform fmt` + `validate` pass; `terraform plan` = **9 to add, 0 change,
  0 destroy** (all $0: SAs, IAM bindings, empty secret). Not applied.

## Tests

- **Backend: 128/128** (was 111, +17): sync (8), client (8 incl. token tamper),
  sync endpoint + approve-hook + cube_gen job (5), minus overlap. Determinism
  fix verified by `test_resync_with_same_inputs_is_stable`.
- **Frontend: 9/9 locale**; typecheck across 13 projects; build green.
- **Total: 137/137.**

## Verification

| Check | Result |
|---|---|
| `pytest -q` | ✅ 128/128 |
| `pnpm typecheck` | ✅ 13/13 |
| `pnpm build` | ✅ 116 KB gzip |
| `node --check cube.js` | ✅ syntax OK |
| `terraform fmt -check` + `validate` | ✅ |
| `terraform plan` (read-only) | ✅ 9 add / 0 change / 0 destroy, all $0 |
| Re-sync identical data → identical version | ✅ |
| Approve edge → model version changes | ✅ |
| Cube token tamper detectable | ✅ |

## LIVE DEPLOY — COMPLETE ✅

Cube is deployed and verified end-to-end on `insights-navigator-v2`.

| Thing | Value |
|---|---|
| Cube service | `insnav-cube` (Cloud Run, us-central1) — **private** (no public invoker) |
| URL | `https://insnav-cube-q3rm3dw2tq-uc.a.run.app` |
| cube-gen job | `insnav-cube-gen` (Cloud Run Job, backend image) |
| Images | `…/insnav/cube:latest` + `…/insnav/api:latest` (built via Cloud Build) |
| Secret | `cube-api-secret` v2 (v1 had a trailing newline — see bugs) |
| Mode | dev mode (embedded Cube Store) via `cube_dev_mode=true` in local tfvars |

**End-to-end smoke test passed.** Seeded `raw.smoke` (3 rows) + published a
model to GCS, then queried the live Cube REST API:

- `GET /cubejs-api/v1/meta` → `cubes: ['smoke__smoke']` (model loaded from GCS,
  compiled, JWT verified)
- `GET /cubejs-api/v1/load` (`sum_revenue by city`) →
  `[{city: Mumbai, sum_revenue: 125}, {city: Pune, sum_revenue: 50}]`
  — **correct aggregation, computed by Cube → BigQuery.**

Proven live: image build → deploy → boot → read model from GCS
(repositoryFactory + schemaVersion) → compile schema → JWT auth + tenant
guard → deterministic SQL → BigQuery → correct rows.

### Two bugs found + fixed during deploy

1. **Secret trailing newline.** `python -c "print(...)"` wrote the secret with
   a Windows `\r\n`, so the Cube container's `CUBEJS_API_SECRET` (50 bytes)
   didn't match the locally-signed token (newline stripped by `$()`) → every
   call was `{"error":"Invalid token"}`. Fixed: store with `sys.stdout.write`
   (no newline) as v2.
2. **Nested-backtick compile error (the important one).** The generator wraps
   column names in BQ backticks; `render_to_js` wrapped the whole `sql:` value
   in a JS template literal (also backticks) WITHOUT escaping, so
   `` sql: `\`city\`` `` closed the template early → Cube failed with a
   `DataCloneError: … could not be cloned` (the worker-thread error masked the
   real parse error). Fixed: `_escape()` the backticks in dimension/measure/join
   `sql` fields while keeping `${CUBE}` interpolation live. **Locked in by two
   regression tests** (`test_sql_backticks_are_escaped_*`) — these would have
   caught it pre-deploy.

### Production-hardening notes (deferred, documented)

- **dev mode** bundles the embedded Cube Store so one container can execute
  queries. It also relaxes JWT verification + exposes the Playground, so the
  service is kept **private** (IAM-gated). Committed Terraform defaults
  `cube_dev_mode=false` (secure); the live deploy overrides via gitignored
  `terraform.tfvars`. For public/prod, deploy a real **Cube Store** cluster and
  leave dev mode off — that's Phase 5c.
- **Backend → Cube** auth (header collision between Cloud Run ID token and the
  Cube JWT) is a Phase 6 concern; the Semantic agent uses `CubeQueryClient`,
  which works against the offline stub until that's wired.

### Reproducibility additions (for forks)

- `infra/cube/cloudbuild.yaml` + `backend/cloudbuild.yaml` — Cloud Build configs
  (the backend Dockerfile is at a non-default path).
- `backend/.gcloudignore` — keeps the build upload small (excludes `.venv`).
- Terraform `google_project_iam_member.cloudbuild_builder` — grants the Compute
  Engine default SA the builder role (forks hit a 403 without it).
- `infra/scripts/cube_smoke.py` — reusable smoke-test seeder.

### Cost of the live deploy

| Resource | Cost |
|---|---|
| Cube Cloud Run (scales to zero) | $0 idle |
| cube-gen job | $0 (pay per run) |
| Artifact Registry (cube ~1.5 GB + api image) | ~$0.15–0.30/mo |
| Cloud Build (2 builds) | $0 (free tier) |
| **Total recurring** | **< $0.50/mo** — inside the $5 guardrail |

---

## What was NOT done (deliberate)

- **Production Cube Store** (Phase 5c) — running prod mode publicly requires a
  separate Cube Store cluster. dev mode + private service is the MVP stand-in.
- **No real Cube query yet** — the query client returns stubs until Cube is
  deployed and `INSNAV_CUBE_API_URL` is set. Phase 6 wires the Semantic agent.
- **India fiscal-year custom granularities** — need Cube-side JS; add when the
  first IN dataset needs them.
- **Per-tenant pre-aggregations / caching** — Cube defaults; tune later.

## Live-deploy checkpoint (when you say go)

Cost: **$0 at idle** (Cloud Run scales to zero; BQ/GCS/Firestore free tier).
The only non-zero risk is a brief build/push. Steps:

```bash
# 1. Apply the $0 prerequisites (Cube SA, IAM, secret) — the 9-resource plan
cd infra/terraform && terraform apply        # review first

# 2. Generate the Cube API secret (shared by backend + Cube)
python -c "import secrets;print(secrets.token_hex(24))" | \
  gcloud secrets versions add cube-api-secret --data-file=- --project=insights-navigator-v2

# 3. Build + push the Cube image
REG=us-central1-docker.pkg.dev/insights-navigator-v2/insnav
docker build -t $REG/cube:latest infra/cube/ && docker push $REG/cube:latest

# 4. Build + push the backend image (also needed for the cube-gen job + api)
docker build -t $REG/api:latest -f backend/services/api_gateway/Dockerfile backend/
docker push $REG/api:latest

# 5. Flip enable_cube=true (and enable_cloud_run=true for the backend), apply
#    set INSNAV_CUBE_API_URL on the backend to the Cube service URL output
terraform apply -var="enable_cube=true"

# 6. Publish a model + smoke-test
#    UI → Cube tab → Publish to Cube, then the Phase 6 agent (or curl the
#    Cube REST API with a minted token) returns real rows.
```

## Next: Phase 6 (Semantic agent) or Phase 1.5 (Firebase Auth)?

- **Phase 6 — Orchestrator + Semantic + Critic + Data-Quality agents**: the
  first natural-language-question → governed answer, using `CubeQueryClient`.
  This is the headline product capability. Works against the offline Cube stub
  immediately; against real Cube once 5b is deployed.
- **Phase 1.5 — Firebase Auth multi-tenant**: prerequisite for a second user.
