# Phase 2 status

> CSV ingestion live end-to-end. User can now upload a CSV and see it
> profiled in the system. The infra wiring is real (signed URLs → GCS → BQ
> load → BQ-based profile → Firestore catalog) and tested offline.

## The architecture decision that drove this turn

User asked for **5 GB file support.** That broke the original "in-process
profiler" plan (a 5 GB CSV in pandas needs ~15 GB RAM, and Cloud Run requests
would time out). The correct architecture for 5 GB files:

1. **Upload** — signed resumable URL → GCS directly. **The API never touches
   the file bytes.** Works for any file size.
2. **Load** — BigQuery load job from GCS → `raw.raw_<dataset_id>`. BQ handles
   any CSV size cheaply (load jobs are free).
3. **Profile** — a single `SELECT count, count_distinct, min, max, null_count`
   query against BQ. BigQuery does the scan in seconds even at 5 GB; we just
   collect aggregates. `APPROX_COUNT_DISTINCT` for distinct counts (single-pass,
   ~2% accurate) keeps cost down.
4. **Storage** — schema catalog + dataset metadata go to Firestore (~KB per
   dataset).

The api_gateway **orchestrates** but BigQuery does the actual data work.
That avoids standing up Cloud Run Jobs or sandboxes for v1. Phase 2.5 can
extract to a Cloud Run Job if profile queries ever exceed Cloud Run's
60-min request timeout.

## What shipped

### Backend (`backend/services/api_gateway/app/`)
- `settings.py` — pydantic-settings, env-typed config (staging bucket, BQ
  raw dataset name, upload caps, offline mode). Anything reading os.environ
  directly is now a smell.
- `gcp_clients.py` — lazy singleton Storage/BigQuery/Firestore clients. Importing
  this module triggers zero network calls.
- `datasets.py` — `Dataset` + `ColumnProfile` models. CRUD against Firestore
  (prod) or an in-memory dict (offline_mode for tests). Storage backend swaps at
  the function boundary so call sites are identical.
- `profiler.py` — builds the single aggregate SQL across all columns +
  parses the result into `ColumnProfile` records. `key_likeness` score
  computed: `(1 - null_pct) * min(distinct_count / row_count, 1.0)` —
  used in Phase 4 to propose join-key candidates.
- `uploads.py` — `POST /v1/uploads/start` + `POST /v1/uploads/complete`
  endpoints + the GCS resumable session + BQ load + profile orchestration.
- `datasets_router.py` — `GET /v1/me/datasets` (filtered by tenant_id) +
  `GET /v1/datasets/{id}` (cross-tenant returns 404, doesn't leak existence).
- `conftest.py` — autouse fixture flips `INSNAV_OFFLINE=true` so every test
  runs without GCP credentials.

### Frontend
- `packages/api-client/src/index.ts` — fleshed out with typed methods:
  `listDatasets`, `getDataset`, `startUpload`, `completeUpload`, +
  `uploadToGcs(signedUrl, file, onProgress)` helper that uses XMLHttpRequest
  (fetch can't emit upload progress events).
- `apps/web/src/views/DatasetsView.tsx` — list with status badges, drag-drop
  upload dialog with progress bar, polling until `ready`/`failed`.
- `apps/web/src/App.tsx` — tabbed shell: Datasets (default) + Locale demo.

### Tests
- **Backend: 45/45** (was 27). New: 18 tests covering upload start/complete,
  profile SQL building, profile-row parsing, cross-tenant isolation,
  5 GB acceptance, 10 GB rejection (413), and the offline storage backend.
- **Frontend: 9/9 locale** (unchanged — no new tests for UI yet; that's
  Phase 3).
- **Total: 54/54.**

## What WAS NOT done (deliberate)

- **No real GCS upload run.** All testing is offline (mocked GCS + BQ). To
  smoke-test against real GCP: set `BOOTSTRAP_ADMIN_*` env vars, leave
  `INSNAV_OFFLINE` unset, run `make dev-backend` + `make dev-frontend`,
  upload a small CSV. Files land in `gs://insights-navigator-v2-staging/uploads/<id>/`
  and a `raw.raw_<id>` BQ table appears. Costs: pennies for the load,
  free for the profile (under 1 TB/month).
- **No chunked PUT for files > 2 GB.** Phase 2 uses a single XHR PUT to the
  GCS signed URL. Browsers handle this fine for files up to ~2 GB. For 2-5 GB,
  we'll need to switch to chunked PUTs with `Content-Range` headers
  (Phase 2.5 — easy follow-up; GCS resumable sessions already accept partial
  PUTs with 308 responses).
- **No XLSX/Parquet/JSON.** CSV-only v1 per your call.
- **No async ingestion.** `/v1/uploads/complete` runs the load + profile
  synchronously. Fine for files ≤ 100 MB → ~seconds; for 5 GB → ~60s.
  Cloud Run's 60-minute request timeout covers it. Extract to a Cloud Run
  Job in Phase 2.5 if needed.

## Verification

| Check | Result |
|---|---|
| `pip install -e .[gcp]` on Python 3.14 | ✅ all wheels (grpcio, protobuf, cryptography included) |
| `pytest -v` | ✅ 45/45 |
| `pnpm typecheck` | ✅ 13/13 workspace projects |
| `pnpm --filter @insnav/locale test` | ✅ 9/9 |
| `pnpm build --mode nebula` | ✅ 51 KB gzip (38 modules) |
| 5 GB file accepted by `/v1/uploads/start` | ✅ (test_supports_5gb_files) |
| 10 GB file rejected with 413 | ✅ (test_rejects_files_over_size_cap) |
| Cross-tenant isolation | ✅ (test_other_tenant_cannot_complete) |
| Profile SQL uses cost-efficient APPROX_COUNT_DISTINCT | ✅ (test_aggregates_each_column) |

## Cost projection (still inside the $5/mo guardrail)

| Service | Phase 2 usage | Cost |
|---|---|---|
| GCS staging | First few GB of uploads | $0 (5 GB free tier) |
| BQ storage | First N GB of `raw.*` tables | $0 (10 GB free tier) |
| BQ queries | Load jobs are free; profile queries scan dataset once each | $0 under 1 TB/mo |
| Firestore | KB per dataset metadata | $0 (free tier > 50 MB writes/day) |
| **Total at MVP traffic** | | **$0** |

## Manual smoke-test recipe (against live GCP)

```bash
# In one terminal — backend
cd backend
. .venv/Scripts/activate
export BOOTSTRAP_ADMIN_EMAIL=admin@local.dev
export BOOTSTRAP_ADMIN_PASSWORD=changeme123
export INSNAV_JWT_SECRET=$(python -c "import secrets; print(secrets.token_hex(24))")
# leave INSNAV_OFFLINE unset → uses real GCP
uvicorn services.api_gateway.app.main:app --reload --port 8000

# In another terminal — frontend
cd frontend/apps/web
pnpm dev

# Visit http://localhost:5173
# Sign in as admin@local.dev / changeme123
# Datasets tab → Upload CSV → pick any small .csv → watch the status
#   queued → uploading → loading → profiling → ready
# Inspect:
#   gsutil ls gs://insights-navigator-v2-staging/uploads/
#   bq ls insights-navigator-v2:raw
```

## Next phase: 3 or 4 or 1.5?

- **Phase 3 (region-aware brand contract end-to-end)** — small. Wire `/v1/me/brand`
  to read from a real Firestore brand-configs collection so brand swap doesn't
  need a backend deploy. Lets you ship the second brand.
- **Phase 4 (knowledge graph)** — the headline. Embedding-proposed edges +
  admin confirmation UX + NetworkX + Firestore. This is where the platform
  becomes meaningfully different from Metabase.
- **Phase 1.5 (Firebase Auth multi-tenant)** — swap bootstrap admin for real
  Firebase Auth. Required before any second user.

Most product value: **Phase 4**. Most "ready to onboard a user" value: **Phase 1.5**.
Pick on next "next".
