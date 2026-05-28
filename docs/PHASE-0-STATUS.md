# Phase 0 status

> Scaffolding complete. Repo is runnable. Architecture is wired and verified.
> This file is the handoff for the next phase.

## What's in this commit

### Frontend (`frontend/`)
- pnpm workspace, 11 packages + 2 apps (`web` runnable, `embed` placeholder)
- **Fully implemented**: `@insnav/locale` (US + IN, Lakh/Crore, Apr-Mar FY, Asia/Kolkata — 9 tests pass), `@insnav/brand-runtime` (runtime token loader, applies before React mounts)
- **Stubs with TODOs**: ui-kit, api-client, charts, pivot, dashboards, chat, share-embed, auth
- Vite + React 18 + Tailwind + custom **Aurora theme** (electric teal on deep navy, Inter + JetBrains Mono)
- Runnable: `pnpm install && pnpm dev` from `frontend/`

### Backend (`backend/`)
- 10 Python packages + 6 services
- **Fully implemented**: `insnav_contracts` (agent message + result envelope + determinism hash — 3 tests), `insnav_llm_router` (Gemini 3.0 Preview default + Claude fallback + Stub provider for tests — 4 tests), `insnav_locale` (mirrors frontend — 7 tests), `services/api_gateway` (FastAPI with `/healthz`, `/v1/me/brand`, `/v1/me/datasets`, `/v1/openapi.json`, `/v1/events-schema.json` — 5 tests)
- **Stubs with TODOs**: agents (7), graph_store, cube_client, identity, audit, verification_corpus, metric_registry, services/{orchestrator, ingestion, graph_builder, cube_gen, compute_sandbox}
- Runnable: `pip install -e .[dev] && uvicorn services.api_gateway.app.main:app`

### Infra (`infra/`)
- Terraform skeleton with cost guardrails: scales-to-zero only, no Spanner Graph, no Cloud SQL, no Memorystore
- Feature-toggle vars (`enable_cloud_run`, `enable_firebase_hosting`, etc.) so you stand up resources incrementally
- `enable-apis.sh` for one-shot API enablement
- **Not applied yet** — review `terraform plan` before any apply

## Verification (the round-robin you asked for)

| Step | Status |
|---|---|
| Frontend `pnpm install` | ✅ 242 packages, 10s |
| Frontend `pnpm typecheck` | ✅ all 13 projects green |
| Frontend `pnpm test` (locale, India non-negotiables) | ✅ 9/9 pass |
| Frontend `pnpm build --mode nebula` | ✅ `dist-nebula/`, 48 KB gzip |
| Backend `pip install -e .[dev]` | ✅ on Python 3.14 |
| Backend `pytest -v` | ✅ 19/19 pass |
| **Total tests** | **✅ 28/28** |
| Terraform `validate` | ⚠️ skipped (CLI not installed locally; CI workflow runs it on PR) |

## Hard constraints honored

| Constraint | How |
|---|---|
| LLM doesn't compute (PRD #1) | `llm_router` is the only module importing Gemini/Claude SDKs; agents call `router.generate(...)` not SDKs |
| Provenance on every answer (PRD #4) | `AgentResult` envelope requires `method_used`, `confidence`, `assumptions_checked`, `inputs_hash`, optional `interpretation_echo` + `data_health` |
| Determinism (PRD #5 + Cube hash) | `compute_inputs_hash` canonicalizes inputs (sorted keys, no whitespace) and returns SHA256; test asserts identical inputs → identical hash |
| India non-negotiables (PRD #8) | LocalePreset enforced; 6 dedicated tests per side (frontend + backend) |
| Gemini 3.0 Preview default (PRD #9) | `get_default_router()` returns Gemini primary unless `INSNAV_LLM_PRIMARY` overrides |
| $5/mo cost guardrail (PRD #10) | Terraform deliberately excludes Spanner Graph, Cloud SQL, Memorystore; NetworkX + Firestore replaces graph engine |
| Monorepo deployable template (PRD #11) | Single repo with `frontend/`, `backend/`, `infra/`; README explains fork-→-new-GCP-→-deploy flow |

## Next phases (per PRD build order)

1. **Foundations (Phase 1)** — Firebase Auth multi-tenant, bootstrap admin env vars, run `terraform apply` for the always-free resources (`enable_cloud_run=false` still)
2. **CSV ingestion (Phase 2)** — Build out `services/ingestion`: GCS resumable upload, profiler, BQ raw load, schema catalog writer
3. **Brand contract end-to-end (Phase 3)** — Wire `/v1/me/brand` to real Firestore-backed brand configs; verify a second brand can deploy with new tokens but same backend
4. **Knowledge graph (Phase 4)** — Implement `insnav_graph_store` with NetworkX + Firestore; ship admin edge-approval UI (embeddings + key-overlap % both shown)
5. **Cube auto-gen (Phase 5)** — Wire `services/cube_gen` to emit `infra/cube-schema/*.js` from approved edges
6. **Single-source MVP through swarm (Phase 6)** — Orchestrator + Semantic + Critic + Data-Quality agents wired in-process; first answer with interpretation echo + data-health badge

See `PRD.md` for the full 13-step build order.
