# Phase 10 — Project Workspaces + Agent-Led Ingestion

> Ingestion becomes an **agent-led conversation** inside a **project workspace**.
> The agent reads the file, asks for a project name + context, drafts how to read
> every column, you review/correct it, and that human-confirmed semantic model
> builds the project's Cube + graph. Plus a robust ingestion backbone underneath.

## The shape

```
Tenant (brand)
  └─ Project (workspace)         ← NEW first-class scope
       ├─ Datasets (project_id)
       ├─ Graph edges (project_id)
       ├─ Cube model  → GCS cube-model/<tenant>/<project>/
       ├─ Locale default (US|IN)
       ├─ Onboarding sessions
       └─ Members + settings
```

Two UI surfaces: **Admin** (projects → Datasets · Onboarding · Graph · Cube ·
Settings) and **Explore** (Ask + Pivots/Dashboards placeholders), both scoped to
a selected project.

## What shipped (A–F)

**A — Project foundation.** `projects.py` (Project + ProjectMember, Firestore/
offline CRUD) + `/v1/projects` CRUD. `project_id` threaded through Dataset,
GraphEdge, uploads, edge scoping/proposer. Back-compat: defaults to None.

**B — Robust ingestion.** `DELETE /v1/datasets/{id}` (edges → BQ → GCS →
Firestore → project detach → cube re-sync, idempotent). `sniffer.py` — pure,
India-aware type inference (DD-MM-YYYY, ₹/"1,24,000" → NUMERIC, encoding/
delimiter/header). `POST /v1/uploads/preview` (read-before-commit). Explicit
type/locale override on load via `build_normalize_sql` (SAFE.PARSE_DATE /
regex-strip + SAFE_CAST; bad cells → NULL). Structured `IngestError`
(stage/reason/message/hint). Idempotent profiles (delete-then-write).

**C — Agent-led onboarding.** `insnav_agents/onboarding{,_models}.py` — pure
state machine (`project_name → grain → draft_review → joins → confirm → done`).
"Agent drafts, you review": `heuristic_semantics` auto-classifies all columns;
the LLM only authors questions + parses free-text corrections (reuses the
`interpret()` prompt/parse pattern); offline → stub → deterministic heuristics.
`ingest_router.py` (stateful sessions). Completion stamps `confirmed_by`, saves
semantics onto the columns subcollection, approves confirmed joins, activates the
project, re-syncs the cube.

**D — Per-project Cube + graph.** `build_cube_schema` prefers confirmed
`ColumnSemantics` over heuristics (role/aggregation/title/description) and gates
`revenue_touching` on `is_revenue AND confirmed_by` (PRD #3). `sync_project` +
`cube-model/<tenant>/<project>/` path. `cube.js` keys context/version/repo off
(tenant, project) with a transition-safe fallback. Cube security context carries
`project_id`; chat + `/v1/cube/sync` + edge-approve scope to the project.

**E — Frontend.** Two-surface `App.tsx` (Admin/Explore + project selector).
`ProjectsView` (list/create), `OnboardingView` (conversation + editable
draft-review table), project-scoped `DatasetsView` (delete + onboard) + ChatView.
api-client: projects/ingest/preview/delete + project_id everywhere + Phase 10 types.

**F — Migration + deploy.** `infra/scripts/migrate_default_projects.py` wraps
pre-projects datasets into a per-tenant Default project + re-syncs per-project.

## Determinism held (PRD #1/#3)

The LLM only drafts question text + parses corrections. Deterministic code
computes the Cube from human-**confirmed** semantics. A `revenue`-named column
stays `revenue_touching=False` until a human confirms — proven by test.

## Tests

241 backend tests (+ ~53 for Phase 10: projects, delete, sniffer, onboarding
state machine + scripted interview + revenue-gate, ingest sessions, generator
semantics, per-project sync). Frontend typecheck + production build green.

## Cost ($5/mo guardrail — D11)

$0 new always-on cost. Per-project Cube models share the single Cube service
(project = GCS path + security-context key). Preview = partial GCS read.
India-normalize transform ≈ $0.03 worst-case per 5 GB, only when India formats
are present. LLM interview calls via `insnav_llm_router` (Gemini), negligible.

## Not yet (deliberate)

- Member **invitations** (model carries owner + members; real multi-user needs
  Identity Platform user management — a later slice).
- Pivots + Dashboards (PRD Phase 7/8 — placeholders wired to the project).
- Async ingestion Job (inline load handled 2.37M rows; add only if files time out).
