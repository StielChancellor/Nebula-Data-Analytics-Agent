# Backend — Insights Navigator V2.0

FastAPI + Python services running on Cloud Run, plus shared Python packages.

## Layout

```
services/
  api_gateway/        Cloud Run service. REST + SSE. OpenAPI source of truth.
  orchestrator/       Cloud Run service. Hosts all 7 agents in-process v1.
  ingestion/          Cloud Run job. GCS → BQ raw load. Profiler.
  graph_builder/      Cloud Run job. Edge proposals + key-overlap scoring.
  cube_gen/           Cloud Run job. Approved edges → Cube .js schema.
  compute_sandbox/    Cloud Run job per invocation. Stats/Maths sandbox.
packages/
  contracts/          Agent envelope + result envelope (load-bearing)
  llm_router/         Gemini 3.0 Preview default; Claude fallback
  locale/             Python mirror of frontend locale (CI test enforces sync)
  agents/             7 agent modules
  graph_store/        NetworkX + Firestore (v1; swappable for Neo4j/Spanner)
  cube_client/        Cube REST/SQL client + canonical-query hashing
  identity/           L1 stitching
  audit/              Append-only audit log → BQ
  verification_corpus/  Critic's golden queries + assumption-checklist DSL
  metric_registry/    Versioned metric definitions w/ effective dates
```

## Local dev

```bash
python -m venv .venv
source .venv/Scripts/activate    # Git Bash / WSL on Windows
# or .\.venv\Scripts\activate    # PowerShell
pip install -e .[dev]
uvicorn services.api_gateway.app.main:app --reload --port 8000
```

Health check: http://localhost:8000/healthz
OpenAPI: http://localhost:8000/openapi.json
Swagger: http://localhost:8000/docs

## Tests

```bash
pytest
```

## Architecture notes

**Agent swarm v1 runs in-process inside `services/api_gateway/`** — the
`POST /v1/chat` handler calls `insnav_agents.swarm.answer_question`, which
orchestrates the Semantic/Critic/Data-Quality/Stats agents as Python modules
(per PRD D5). Likewise ingestion (uploads.py), edge discovery (edge_proposer.py),
and onboarding (insnav_agents.onboarding) all run in-process in api_gateway.

The `services/{orchestrator,graph_builder,ingestion,compute_sandbox}/` packages
are **Phase-0 scaffolds that are NOT deployed** — they exist as extraction
boundaries for when an agent/job needs to scale independently. Only
`services/cube_gen/` (the Cube model rebuild job) and `services/api_gateway/`
are real, deployed workloads. The extraction boundary is the agent envelope —
swap function calls for HTTP calls without rewriting the agent itself.

See `../PRD.md` for the full architecture, build order, and acceptance criteria.
