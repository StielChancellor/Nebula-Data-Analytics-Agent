# Live deployment — end-to-end proven

The whole platform is deployed and answering questions on `insights-navigator-v2`.

## Live services (all Cloud Run, us-central1, scale-to-zero / $0 idle)

| Service | URL | Notes |
|---|---|---|
| **Frontend (SPA)** | **`https://insnav-frontend-q3rm3dw2tq-uc.a.run.app`** | **Open this.** nginx static, public. Calls the api_gateway cross-origin (CORS). |
| API gateway | `https://insnav-api-gateway-q3rm3dw2tq-uc.a.run.app` | Public; does its own JWT auth. Brain: Gemini via Vertex ADC. |
| Cube semantic layer | `https://insnav-cube-q3rm3dw2tq-uc.a.run.app` | Prod mode + Cube Store sidecar; JWT-enforced. |
| cube-gen job | `insnav-cube-gen` | Full Cube-model rebuild. |

**Open the frontend URL** → sign in (`admin@insnav.local` + the bootstrap
password from Secret Manager) → **Ask** tab → pick a brain → "total revenue by
city". The frontend is its own Cloud Run service (nginx), built with
`VITE_API_BASE` baked to the api_gateway URL; bearer-token auth (no cookies), so
plain `*` CORS works. Firebase Hosting remains the production CDN option (config
scaffolded; one `firebase login && firebase deploy` away).

## The proof — a real chat answer, live

`POST /v1/chat {"question":"total revenue by city"}` →
```json
{
  "kind": "answer",
  "interpretation_echo": "I will show the total revenue for each city, ordered from highest to lowest revenue.",
  "confidence": 1.0,
  "cube_query": {"measures":["smoke__smoke.sum_revenue"],"dimensions":["smoke__smoke.city"],"order":{"smoke__smoke.sum_revenue":"desc"}},
  "rows": [["125","Mumbai"],["50","Pune"]],
  "data_health": {"status":"ok","completeness":[{"source":"Smoke","row_count":3}]},
  "caveats": []
}
```
The echo was written by **Gemini**; it selected the governed measures/dimensions
(not SQL); the **live Cube** compiled + ran the SQL against **BigQuery** →
correct answer. No "illustrative" caveat = the real Cube. Every PRD guarantee
shown live: LLM-selects/code-computes, interpretation echo, grounding,
data-health badge, show-your-work, determinism (`inputs_hash`).

## Config that made it live

- Backend image built with `.[gcp,llm]` (google-genai + anthropic).
- api_gateway Cloud Run env (Terraform): `BOOTSTRAP_ADMIN_EMAIL`,
  `BOOTSTRAP_ADMIN_PASSWORD` (secret `insnav-bootstrap-admin-password`),
  `INSNAV_JWT_SECRET` (secret), `INSNAV_CUBE_API_URL` (live Cube),
  `INSNAV_CUBE_API_SECRET` (secret), `INSNAV_LLM_PRIMARY=gemini`,
  `INSNAV_LLM_MODEL=gemini-2.5-pro`, `INSNAV_CORS_ORIGINS=*`.
- api_gateway SA granted `roles/aiplatform.user` (Gemini via Vertex).
- `enable_cloud_run=true`; the separate `orchestrator` service stays gated
  (`enable_orchestrator=false`) — the swarm runs in-process.

## The bug the live deploy caught

The Firestore client rejects `.where(filter=("field","==",v))` (a tuple) — it
needs `FieldFilter("field","==",v)`. Offline tests skip the Firestore branch, so
this only surfaced against real Firestore (a 500 on `/v1/chat`). Fixed in
`datasets.py` + `graph_store/store.py` (5 call sites). **A class of bug that only
a live deploy can find.**

## Operating it

- **Admin login:** email `admin@insnav.local`; password in Secret Manager:
  `gcloud secrets versions access latest --secret=insnav-bootstrap-admin-password`.
- **Switch the brain:** the chat UI dropdown, or `"llm"` in the `/v1/chat` body
  (`gemini-3.0-preview`, `gemini-2.5-pro`, `claude-sonnet-4-5`, `stub`). Claude
  shows once `ANTHROPIC_API_KEY` is set.
- **Frontend:** not deployed yet. Set `VITE_API_BASE` to the api_gateway URL and
  `pnpm dev` (or deploy to Firebase Hosting) to drive it from the UI.
- **First request is slow** (~30-40s cold start: api_gateway + Gemini + Cube
  cold start); the canonical cache makes repeats instant; idle = $0.

## Cost

Everything scales to zero. Recurring: Artifact Registry image storage (< $1/mo).
Per-query: Gemini tokens only when you ask. Inside the $5/mo guardrail (the only
thing that would exceed it is an always-on Cube Store — still off).
