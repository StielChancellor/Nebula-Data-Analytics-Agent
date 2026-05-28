# Project Insights Navigator V2.0 — Master PRD & Build Plan

## Context

We are building a brand-new GCP-native analytics platform that combines three things:

1. **Nebula / Insights Navigator's UX patterns** (Excel-style drag-drop pivot, pinnable dashboards, region-aware locales for India + US, multi-brand skinning) — distilled in `C:\Users\hi\Desktop\Qubit Projects\Project Nebula AI - Apr 2026\HANDOFF.md`.
2. **The Intelligent Business Analyst's determinism architecture** (5-layer stack: raw BQ → identity → human-confirmed knowledge graph → Cube semantic layer → agent swarm; LLMs select and narrate but never compute) — distilled in `C:\Users\AI-GiG\Desktop\intelligent_analyst_handoff.md`.
3. **Metabase-inspired BI primitives** (dashboard-level parameter linking, public share links, embedding SDK, x-ray-style auto-exploration, multi-database connector ecosystem) — researched via Metabase docs + GitHub.

The current local directory `C:\Users\AI-GiG\Desktop\eRC\Agent\InsightsNavigator-v2.0` is **empty**. The destination repo is `https://github.com/StielChancellor/Nebula-Data-Analytics-Agent` and the destination GCP project is `insights-navigator-v2`.

**The non-negotiable line:** LLMs orchestrate, select, and narrate. **Deterministic code computes.** Every cross-dataset join traces to a human-confirmed graph edge compiled into a Cube join. Every answer carries provenance: definition version, snapshot, coverage, the exact query that ran. The platform must be able to say "I don't know."

**The plug-and-play frontend goal:** spin up a new GCP project, deploy a different brand build of the frontend, point it at an existing backend Cloud Run URL, and it just works. The backend is a single source of truth; many frontends consume it.

## Locked decisions

| # | Decision | Notes |
|---|---|---|
| D1 | Name: **Project Insights Navigator V2.0** | Used throughout |
| D2 | **Single monorepo as deployable template** | One git repo (`StielChancellor/Nebula-Data-Analytics-Agent`) with `frontend/` + `backend/` + `infra/` subtrees. Fork the repo → new GCP project → configure brand env → terraform apply → build → deploy. The repo IS the white-label platform-in-a-box. Backend ↔ frontend seam is still versioned OpenAPI + SSE event schema |
| D3 | **Frontend swap = multi-brand build + runtime brand tokens** | `vite build --mode <brand>` for the static brand bundle (logo, favicon); but **theme tokens, locale, and feature flags load at runtime** from `GET /v1/me/brand`. Avoids build explosion as brand count grows |
| D4 | **Cube is the only semantic layer** | No Metabase Models/Metrics. Every Cube join traces to a human-confirmed graph edge. Cube schema is generated, not hand-edited |
| D5 | **Agent swarm v1 = single Cloud Run service** hosting all 7 agents as in-process Python modules behind the same envelope they'd use over RPC | Avoids 7× cold starts; designed for later extraction without refactor |
| D6 | **Brain = Gemini 3.0 Preview** by default; **Claude (Anthropic API) as configurable fallback** | LLM choice lives in `llm-router` package; never imported directly by agents |
| D7 | **Regions v1 = US + India** | Full `LocalePreset` abstraction; INR ₹ / Lakh / Crore / Apr-Mar FY / Asia/Kolkata / en-IN grouping is non-negotiable for IN |
| D8 | **Auth = Firebase Auth multi-tenant** | One Firebase project per backend, one tenant per brand. JWT carries `tenant_id` + `brand` claims. Backend maps `(tenant_id, user_id)` → allowed datasets |
| D9 | **Compute sandbox = Cloud Run job per invocation** | Pinned image (numpy/pandas/scipy/statsmodels/prophet/lifelines/pymc), 60s timeout, no network egress except BQ via SA, results to GCS scratch bucket |
| D10 | **Knowledge graph v1 = NetworkX in-process + Firestore persistence** ($0) | Cost guardrail (D11) ruled out Spanner Graph (~$650/mo). NetworkX covers our expected scale (< 5k edges/customer) for years. `packages/graph-store` abstraction makes Neo4j Aura swap a one-file port if we ever outgrow it. Mitigations for the two real losses (multi-instance write consistency, cold-start load time): pin orchestrator to 1 instance for v1; cache serialized graph in GCS |
| D11 | **$5/month cost guardrail per service** (hard constraint) | No new GCP service costing more than $5/month without explicit user approval. Every infra addition must flag estimated monthly cost in the PR/plan. Forces every architecture call to consider cost-vs-value |
| D12 | **MIT license** | Permissive; matches the "deployable template" intent. Anyone can fork, white-label, deploy commercially |

## The 5-layer architecture (load-bearing)

```
L0  Raw landing                BigQuery raw_<source> datasets, partitioned by load date
                               Never queried by agents directly
       ↓
L1  Identity + modeling        Conformed facts + cookie_journey + COVERAGE RATE
                               Deterministic stitching (gclid, fbclid, utm, cookie_id, confirmation_no)
       ↓
L2  Knowledge graph            Spanner Graph. Nodes = entities; edges = CONFIRMED relationships
                               Human-in-the-loop confirmation required for revenue/ROAS-feeding edges
       ↓
L3  Semantic layer (Cube)      Auto-generated from confirmed edges. Cubes ↔ entities, joins ↔ edges
                               Versioned, immutable metric definitions tagged with effective dates
       ↓
L4  Agent swarm                Orchestrator + Semantic + Graph + Stats + Maths + Critic + Data-Quality
                               Single Cloud Run service v1; in-process modules behind shared envelope
                               All math runs in the Python compute sandbox; LLMs never emit numbers
```

## Module map

### Frontend repo (`Nebula-Data-Analytics-Agent`, pnpm workspace)

```
apps/
  web/                  Vite SPA entry. Brand mode at build time, theme tokens at runtime
  embed/                Smaller iframe-embed bundle for public share + customer embedding
packages/
  ui-kit/               Headless components consuming brand tokens via CSS vars
  brand-static/         Per-brand static assets (logo, favicon, build-time copy)
  brand-runtime/        Runtime token loader + applyBrand() (writes --accent CSS vars before mount)
  locale/               LocalePreset {US, IN} — INR/USD, Lakh-Crore vs M-B, FY calendars, formatters
  api-client/           Codegen'd from /v1/openapi.json + SSE wrapper for streaming agent responses
  pivot/                Drag-drop pivot panel (Nebula §2.1 + §2.2 — all features, in ONE PR)
  dashboards/           Pinning, parameter linking, layout grid, snapshot viewer
  chat/                 Agent chat UI, streaming narration, interpretation echo, data-health badge, citations
  charts/               Smart chart-type selector + ECharts adapters, region-aware color palettes
  share-embed/          Public link viewer + embed SDK consumer
  auth/                 Firebase Auth + token refresh + brand-scoped login + bootstrap-admin override
tools/
  openapi-codegen/      Pulls /v1/openapi.json on prebuild; emits api-client types
  brand-build/          Orchestrates vite build --mode <brand> + Firebase Hosting target wiring
```

### Backend repo (new, e.g. `insights-navigator-backend`)

```
services/
  api-gateway/          Cloud Run. REST + SSE. OpenAPI source of truth. Auth middleware. /api prefix stripper
  orchestrator/         Cloud Run. Hosts all 7 agents in-process v1. Owns the swarm protocol
  ingestion/            Cloud Run JOB. GCS → BQ raw load. Profiler. Schema catalog writer
  graph-builder/        Cloud Run JOB. Embedding-based edge proposals + key-overlap scoring. Writes proposals for admin review
  cube-gen/             Cloud Run JOB. Reads approved edges → emits Cube .js schema files → PR or auto-deploys
  compute-sandbox/      Cloud Run JOB invoked per stats/maths computation
packages/
  agents/               7 agent modules: orchestrator_logic, semantic, graph, stats, maths, critic, data_quality
  contracts/            Pydantic models. OpenAPI export. Inter-agent envelope. Result envelope
  graph-store/          Spanner Graph client + edge-proposal/approval API
  cube-client/          Cube REST/SQL client + securityContext builder + canonical-query hashing
  identity/             L1 stitching primitives
  locale/               Backend FY/currency helpers (mirrors FE; canonical source for absolute-date resolution)
  audit/                Append-only audit log writer (BQ audit dataset)
  llm-router/           Gemini 3.0 Preview default; Claude fallback; prompt versioning; per-model retry policy
  verification-corpus/  Critic's golden queries + assumption-checklist DSL
  metric-registry/      Owner, definition history, effective dates, deprecation lifecycle for every Cube metric
infra/
  terraform/            GCP project, Cloud Run, BQ datasets, Firestore, GCS, Secret Manager, Firebase Hosting targets
  cube-schema/          Generated Cube .js files (PR-reviewed for revenue-touching changes)
```

## Backend ↔ frontend contract

- **`GET /v1/openapi.json`** — single source of REST shape, served by api-gateway.
- **`GET /v1/events-schema.json`** — sibling JSON Schema document for SSE event payloads (agent narration stream, computation progress, partial chart specs). OpenAPI doesn't cleanly model this; we publish it separately so the api-client can validate streamed events.
- **Auth:** Firebase Auth multi-tenant. JWT contains `tenant_id` + `brand`. Backend validates, then resolves `(tenant_id, user_id) → allowed_datasets` via a `tenant_access` table. Same token format across all brand frontends.
- **Dataset discovery:** `GET /v1/me/datasets` returns `[{id, label, locale_hint, last_refreshed, row_count, scopes}]`. Frontend never hardcodes. Pivot + chat + dashboards all call this on mount. **Multi-dataset selection** is just multi-select on this list; the orchestrator resolves cross-dataset queries via confirmed graph edges.
- **Theme + locale at runtime:** `GET /v1/me/brand` returns `{tokens, logo_url, currency_default, region_default, feature_flags}`. The frontend's brand-static bundle is just the entry point; everything visual after first paint is server-driven.

## Agent swarm wiring

**v1 deployment:** ONE Cloud Run service (`orchestrator/`) hosting all 7 agents as Python modules. They communicate via function calls using the same envelope they would use over RPC. **Extraction trigger:** any agent exceeding p95 latency budget or needing independent scaling — Stats and Maths are the likely first candidates.

**Inter-agent message envelope:**
```python
{
  "trace_id": str,
  "parent_span": str,
  "agent_from": str,
  "agent_to": str,
  "intent": "interpret" | "compute" | "verify" | "narrate",
  "payload": dict,
  "context_refs": list[str],   # conversation_id + prior result ids
  "deadline_ms": int,
}
```

**Mandatory result envelope (every agent, every call):**
```python
{
  "result": Any,                       # the actual output
  "method_used": str,                  # "cube_query" | "diff_in_diff" | "prophet" | ...
  "assumptions_checked": list[str],    # ["sample_size>=30", "no_seasonality_break"]
  "confidence": float,                 # 0.0-1.0
  "caveats": list[str],
  "inputs_hash": str,                  # SHA of normalized inputs for drift detection
}
```

**Critic agent** does **not** re-run computation (tautological). It loads the Orchestrator's stored interpretation from Firestore via `context_refs`, runs an assumption-checklist DSL against the verification corpus, and emits a verdict envelope. Below-threshold confidence → Orchestrator asks the user a clarifying question instead of answering.

**Compute sandbox** is a Cloud Run **job** (not service) per invocation. Pinned image, 60s timeout, no network egress except BQ via service account, results to GCS scratch bucket. Stats/Maths agents submit jobs and fetch results — they never compute in-process.

## Features lifted, verbatim

### From Nebula (must-haves; ship as ONE PR each)
- **Pivot panel**: drag-drop Filters/Rows/Columns/Values; debounced preview vs full Compute; Table↕Chart toggle; row-number gutter; sticky dim columns with cumulative offsets; aggregation glyphs (Σ Ø # ↑↓ μ); active-sort arrows; drag-to-reorder; Excel-style group expand/collapse; per-metric heatmap; keyboard nav + Ctrl+C as TSV; right-click context menu; in-table search; **all of it, no skipping**.
- **Pinnable dashboards**: chart spec is the unit of pinning. POST `/v1/dashboards` with the spec; server persists + saves a refresh recipe; dashboards re-run on each visit against fresh data.
- **Region-aware locale**: full `LocalePreset` (region, currency, currencySymbol, timezone, fyStartMonth, locale string). India defaults: ₹, en-IN grouping (1,24,00,000), Apr-Mar FY default on every date dim, Asia/Kolkata, Lakh/Crore in compact format. GST-aware column detection. Fortnight (15-day) bucketing.
- **Multi-brand skin layer**: `--accent`, `--accent-glow`, `--accent-soft`, `--accent-foreground` CSS vars. Build-time brand bundle + runtime token loader. `.firebaserc` with multi-target hosting.
- **Bootstrap admin**: env-based admin override for pre-user-management shipping. **Rotate before any real customer.**
- **Resumable CSV upload via signed URLs**: GCS resumable upload session → direct PUT → `/uploads/complete` triggers BQ load. CORS configured for `Location` + `x-goog-resumable`.
- **Snapshot model**: `{columns, rows, preview, computed_at, row_count}` — same shape preview vs compute. Table↕Chart toggle reads same in-memory snapshot.

### From Metabase (adapted, not copied — AGPL license keeps us at "inspiration" distance)
- **Dashboard-level parameter linking**: one filter changes N cards on a dashboard.
- **Public share links + embedding SDK**: read-only share tokens; iframe embed for customers' sites. Chart spec stays portable.
- **X-ray-style proactive insights**: on a new dataset, agent auto-generates a starter dashboard (anomalies, top movers, segment breakdowns) without being asked.
- **Audit log + usage analytics**: every query (agent or user) writes to BQ `audit.queries` with `(user, tenant, query, snapshot, definition_version, sandbox_job_id, cost_bytes)`.
- **Multi-dataset selection**: user picks N datasets in the chat header; orchestrator resolves cross-dataset queries via confirmed graph edges. If the requested join has no confirmed edge → refuse with the missing edge surfaced for admin approval.
- **Smart chart-type auto-selection**: agent emits chart spec, but spec generation is rule-based on result shape (1 measure × 1 time dim → line; N measures × 1 dim → grouped bar; 1 measure × 2 dims → heatmap or stacked; single number → KPI tile; 2 measures of same units → scatter). Rule table in `charts/auto-select.ts`. LLM proposes only when rules tie.

## Features anticipated (no source doc had them; PhD-level differentiators)

1. **Column-level lineage UI** — click any number, trace back through Cube → graph edges → L1 tables → raw BQ columns. Without this, "deterministic" is unprovable to a skeptic. Ship as a slide-over on every chart.
2. **Cohort builder with set algebra** — named saved filters, then `(A ∩ B) \ C` in chat. Trivial on top of the graph layer; killer for retention/funnel work.
3. **Snapshot diffing** — "What changed in metric X between yesterday's and today's snapshot?" Requires versioned L2 + BQ time-travel.
4. **Query-plan + cost preview** — before any cross-dataset join, show BQ slot estimate and gate on user approval if > N GB. Prevents cost surprises in multi-dataset mode.
5. **Assumption-violation alerts on pinned dashboards** — Critic re-runs nightly against pinned dashboards; if a previously-valid assumption (normality, no seasonality break) now fails, tile shows a warning badge. **This is what separates a BI tool from an analyst.**
6. **Reproducible notebook export** — any chat session exports as a Python notebook with the exact Cube queries, sandbox code, and locale settings. Auditors and analysts will demand this.
7. **Causal-inference guardrails** — "did X cause Y?" routes to a dedicated path that requires a stated identification strategy (DiD, RDD, IV) or refuses with explanation. Prevents the #1 BI-LLM embarrassment.
8. **Metric-definition registry with deprecation** — every Cube metric has an owner, definition history, effective dates, deprecation lifecycle. Surfaces in UI. Stops "revenue means three different things" drift.

## Seven failure-mode mitigations (from the intelligent-analyst handoff — ALL implemented)

1. **Why-questions** → driver/decomposition module (contribution waterfall); narrate causes grounded only in the decomposition.
2. **Wrong-question (existential)** → interpretation echo in plain English before/with every answer; Critic re-derives interpretation independently; below-threshold confidence → clarifying question instead of guess.
3. **Silent data-quality (existential)** → data contracts + freshness/completeness/coverage badge on every answer; if a source feeding the answer failed to load, block or visibly flag.
4. **Definition drift** → versioned immutable definitions; warn + offer recompute when a query spans a change.
5. **Late-arriving data** → recent windows marked provisional with stabilization note; snapshot versions stored so any past answer is reproducible.
6. **Statistical misreads** → Stats agent auto-annotates small-sample, normalizes unequal periods, adds seasonality/YoY context, runs significance tests, checks Simpson's paradox.
7. **Attribution = value choice** → never one "true" ROAS; ROAS shown under multiple named models side-by-side; platform-claimed vs warehouse-reconciled always paired.

## Build order

1. **Foundations.** GCP project (`insights-navigator-v2`) wiring per intelligent-analyst handoff §10 step 3. Repos initialized. Terraform in place. Bootstrap admin env vars. Firebase multi-tenant Auth.
2. **CSV ingestion + profiler + schema catalog.** Cloud Run job, GCS staging bucket with correct CORS, BQ raw load. `GET /v1/me/datasets` working.
3. **LocalePreset + brand-runtime + theme contract.** `GET /v1/me/brand` returns tokens; frontend applies before mount. US + IN both work end-to-end with formatting tests.
4. **Knowledge graph + edge proposal/confirmation UX.** Embedding-proposed edges + actual key-overlap %. Admin UI to approve. Spanner Graph storage. L1 identity stitching + published coverage rate.
5. **Cube auto-generation pipeline.** Approved edges → generated `cube-schema/*.js` → PR (or auto-deploy for non-revenue). Metric registry alongside.
6. **Single-source MVP through the agent swarm.** Orchestrator + Semantic + Critic + Data-Quality in one Cloud Run service. Chat answers "highest-revenue city last 30 days" with interpretation echo, data-health badge, and the Cube query shown. **No charts yet.**
7. **Pivot panel.** All of Nebula §2.1 + §2.2 in one PR.
8. **Pinnable dashboards + smart chart selection + share/embed.** Chart spec portable. Public share tokens. Embed SDK.
9. **Stats + Maths + Graph agents in-process.** Compute sandbox (Cloud Run job per invocation) wired. Verification corpus seeded. All 7 mitigations enforced.
10. **Multi-dataset selection + cross-dataset graph resolution.** Refuse cleanly when no confirmed edge exists.
11. **PhD differentiators**: lineage UI → cohort builder → snapshot diffing → cost preview → assumption-violation alerts → notebook export → causal guardrails → metric registry deprecation. In that order.
12. **X-ray proactive insights.** Auto-generated starter dashboard on new dataset upload.
13. **Ship to one real customer.** Iterate. No new features for two weeks after first customer.

## Highest-risk decisions (flag for revisit post-MVP)

| Risk | When to revisit | What to watch |
|---|---|---|
| Single-service agent swarm | After first paying customer / when p95 chat latency > 12s | Stats agent contention is the canary; extract it first |
| OpenAPI as sole REST contract (SSE handled via sibling schema) | Before public launch / before third frontend brand | Schema drift between SSE events doc and actual emissions |
| Build-time brand-static bundle (even with runtime tokens) | Before fifth brand ships | Build matrix explosion; if real, move logo/favicon to runtime too |

## Hard constraints (do not violate)

1. LLMs orchestrate and select. **Deterministic code computes.** No LLM-authored joins. No LLM-emitted final numbers.
2. Every Cube join traces to a human-confirmed graph edge.
3. Human-in-the-loop confirmation is **mandatory** for any edge feeding revenue or ROAS.
4. Every answer carries provenance: definition version, snapshot, coverage, the exact query that ran, attribution model label where applicable.
5. The platform must be able to say "I don't know." Calibrated uncertainty over confident wrongness, always.
6. Frontend and backend communicate **only** via versioned OpenAPI + the SSE events schema. No shared package imports.
7. Each module in the module map is independently deployable (or, for v1 in-process agents, independently extractable without refactor).
8. India defaults are **non-negotiable** when region = IN: ₹, en-IN grouping, Lakh/Crore, Apr-Mar FY default on every date dimension, Asia/Kolkata timezone.
9. Default brain is Gemini 3.0 Preview, accessed only through `llm-router`. No agent imports the LLM SDK directly.
10. **$5/month cost guardrail per GCP service.** Any new service expected to exceed $5/month requires explicit user approval before being added to Terraform. Every infra PR must flag estimated monthly cost.
11. Monorepo layout (D2): one repo for everything. The repo is a deployable template — fork → new GCP → new brand → deploy.

## Acceptance criteria (definition of done for v1)

- [ ] Admin can upload CSVs and they land profiled in BQ raw with row counts visible.
- [ ] Graph edge proposals include both embedding similarity AND actual key-overlap %; admin confirms; confirmed edges appear as Cube joins; rejected proposals are remembered.
- [ ] No agent can join two datasets lacking a confirmed edge (verified by integration test).
- [ ] All metrics use Cube nomenclature; each is versioned + immutable; every answer reports the version used.
- [ ] Identical question over the same snapshot returns byte-identical cached answer (canonical-query hash test passes).
- [ ] Every answer includes: interpretation echo + data-health badge + Cube query shown + (where applicable) coverage rate + attribution-model label + confidence interval.
- [ ] All 7 failure-mode mitigations implemented; #2 and #3 verified by Critic and Data-Quality agents.
- [ ] Orchestrator routes by analysis level (descriptive/diagnostic/path/predictive/prescriptive); Stats/Maths agents invoked only when needed; their math runs in the sandbox job.
- [ ] System refuses or hedges when data is insufficient or a metric is undefined.
- [ ] Golden-question regression suite runs in CI on every prompt/model/definition change.
- [ ] Pivot panel ships with EVERY Nebula §2.1 + §2.2 feature.
- [ ] India defaults verified end-to-end (₹ symbol, en-IN grouping, Apr-Mar FY default, Asia/Kolkata timezone, Lakh/Crore compact format).
- [ ] Multi-brand build deploys at least 2 brands (default + one other) to different Firebase Hosting targets in different GCP projects, both pointing at the same backend Cloud Run URL.
- [ ] `GET /v1/me/brand` returns runtime theme tokens; frontend applies before mount; brand swap requires no rebuild for theme-only changes.

## Verification plan

- **Determinism test**: ask the same chat question twice over the same snapshot; assert byte-identical responses including the inputs_hash in each agent envelope.
- **Edge enforcement test**: attempt a cross-dataset Cube query whose join has no confirmed edge; assert refusal with the missing edge named in the error.
- **Locale test**: switch a dataset to IN; verify all numbers re-render with Lakh/Crore + en-IN grouping, all dates default to Apr-Mar FY, timezone is Asia/Kolkata.
- **Brand swap test**: deploy brand `nebula` and brand `secondary` to two Firebase targets in two GCP projects; both consume the same backend; verify themes differ and auth works.
- **Critic effectiveness test**: feed Orchestrator a deliberately ambiguous question ("how's our funnel?"); assert it asks a clarifying question instead of guessing.
- **Data-quality block test**: simulate a failed load of one source; verify any answer touching that source either blocks or carries a red badge with the failure named.
- **Sandbox isolation test**: submit a stats job that attempts network egress to a non-BQ endpoint; assert failure.
- **Cost-preview gate test**: trigger a multi-dataset join estimated > 5 GB; assert the user is prompted to approve before execution.

## Critical files (the load-bearing seams)

- `packages/contracts/agent_envelope.py` (backend) — inter-agent message + result envelope. Touch this carefully; every agent depends on it.
- `services/api-gateway/openapi/v1/openapi.yaml` + `events-schema.json` — the frontend↔backend seam.
- `packages/agents/orchestrator.py` — in-process swarm coordinator for v1; the extraction boundary lives here.
- `packages/cube-client/schema_generator.py` — graph-edge → Cube schema pipeline; gates revenue-affecting changes through PR review.
- `packages/llm-router/router.py` — Gemini 3.0 Preview default; Claude fallback; the only file that imports an LLM SDK.
- `apps/web/src/brand-runtime/applyBrand.ts` — runtime theme loader; runs before React mounts.
- `packages/locale/src/index.ts` (frontend) + `packages/locale/__init__.py` (backend) — LocalePreset; both sides must stay in sync, enforced by a CI consistency test.
