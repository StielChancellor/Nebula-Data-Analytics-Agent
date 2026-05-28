# Phase 5 status

> Cube schemas auto-generated from approved graph edges + dataset profiles.
> Closes the loop from "upload CSV" through "admin confirms edges" to
> "ready-to-deploy Cube schema files."

## The full trust contract is now wired

```
[upload CSV]
      ↓
[profiler writes column profiles to Firestore]
      ↓
[edge_proposer compares high-key-likeness columns]
      ↓
[admin reviews proposals in /v1/edges/proposals]
      ↓
[admin approves → insnav_graph_store]
      ↓
[Cube generator reads approved edges]
      ↓
[GET /v1/cube/schemas/{dataset_id}.js → Cube .js file]
```

**Every Cube join in the output traces back to a `from_edge_id` comment
referencing the approved graph edge that authorized it** (PRD § Hard
constraint #2). The generator has no code path that can construct a join
from a proposed or rejected edge — verified by `test_proposed_edge_does_NOT_become_join`.

## What shipped

### Backend

- **`backend/packages/cube_client/`** — replaced the Phase 0 stub:
  - `models.py` — `CubeSchema`, `CubeDimension`, `CubeMeasure`, `CubeJoin`
    with `from_edge_id` provenance fields on every join
  - `generator.py`:
    - BQ type → Cube type mapping (INT64/FLOAT64 → `number`,
      DATE/TIMESTAMP → `time`, STRING → `string`, BOOL → `boolean`)
    - `cube_name_for_dataset()` — sanitized label + 8-char dataset id suffix
      (e.g. "Sales 2026.csv" + id "a3f4..." → `sales_2026_csv__a3f4d2b1`)
    - `build_cube_schema()`:
      - Every cube gets a `count` measure
      - Each column becomes a dimension
      - Numeric columns with low key-likeness (< 0.7) also get `sum_<col>` + `avg_<col>` measures
      - First column with key-likeness ≥ 0.85 becomes `primary_key`
      - Revenue-touching detector (revenue/sales/roas/cost/spend/profit/margin) flags measures
    - `render_to_js()` — emits valid Cube .js with provenance header + per-join `from_edge_id` comments
    - Join relationship inference from distinct counts (one_to_one / one_to_many / many_to_one / many_to_many)
- **`backend/services/api_gateway/app/cube_router.py`**:
  - `GET /v1/cube/schemas` — summary list per ready dataset (dims/measures/joins counts + revenue_touching flag)
  - `GET /v1/cube/schemas/{dataset_id}/json` — full CubeSchema as JSON
  - `GET /v1/cube/schemas/{dataset_id}.js` — raw Cube .js, Content-Type: application/javascript
  - Schemas computed on demand from current Firestore state — no separate persistence layer (cheaper + safer than caching)

### Frontend

- **`packages/api-client/src/index.ts`** — `CubeSchemaSummary`, `CubeSchemaFull`, `CubeDimension`, `CubeMeasure`, `CubeJoin` types + `listCubeSchemas / getCubeSchemaJson / getCubeSchemaJs` methods
- **`apps/web/src/views/CubeView.tsx`** — Cube tab:
  - Summary table: Dataset / Cube name / Dims / Measures / Joins / revenue-touching badge
  - "View .js" button on each row opens a modal with the syntax-rendered Cube JS
  - Copy-to-clipboard button on the modal
- **`apps/web/src/App.tsx`** — fourth tab wired ("Datasets" / "Graph" / **"Cube"** / "Locale demo")

### Tests

- **Backend: 111/111 pass** (was 72, +39 across cube generator + cube router):
  - `packages/cube_client/insnav_cube_client/test_generator.py` — 29 tests:
    type mapping, name sanitization, dimension/measure generation, primary
    key selection, revenue-touching detection, join inference, JS rendering,
    full roundtrip with a realistic e-commerce + ads schema
  - `services/api_gateway/app/test_cube_router.py` — 10 tests: endpoint auth,
    empty/list/get behavior, 404 for unknown / 409 for non-ready dataset,
    raw .js content-type, **approved-edge becomes join + proposed-edge does NOT
    become join (PRD §2 enforcement)**
- **Frontend: 9/9 locale** (unchanged this turn)
- **Total: 120/120**

## Acceptance criteria covered

| Criterion | Status |
|---|---|
| Schemas computed deterministically from inputs | ✅ (single function, no caching) |
| Every join traces to an approved graph edge | ✅ (`from_edge_id` in models + tests assert this) |
| Proposed/rejected edges never become joins | ✅ (test asserts) |
| Revenue-touching measures flagged | ✅ (revenue/sales/roas/cost/spend/profit/margin) |
| Output is valid Cube .js | ✅ (renders to spec, parseable) |
| Endpoints return the right content-types | ✅ (application/javascript for .js) |

## What was NOT done (deliberate)

- **No file writes to `infra/cube-schema/`.** Schemas are served via HTTP,
  not persisted to disk. When we deploy Cube in Phase 5b, the Cube container
  can either fetch schemas from `/v1/cube/schemas/*.js` at startup, or we
  can wire a Cloud Run Job that polls and commits to Git.
- **No PR-gating for revenue-touching changes** (PRD §11). The
  `revenue_touching` flag is computed and surfaced in the UI, but it
  doesn't gate anything yet. Phase 11 will wire the auto-deploy-vs-PR
  decision based on this flag.
- **No India-specific fiscal-year granularities.** Cube's built-in time
  granularities are day/week/month/quarter/year. Apr-Mar FY requires
  custom Cube granularities, which we'll add when we actually deploy Cube
  in Phase 5b — they need Cube-server-side JS to define.
- **No metric registry (PRD §11).** Measure metadata is auto-generated
  from columns — there's no per-measure owner / version / deprecation
  lifecycle yet. Standalone Phase 11 work.
- **No Cube deployment.** Just the generator. Phase 5b deploys Cube on
  Cloud Run, configures it to read our `/v1/cube/schemas/*.js` outputs,
  and gives the Semantic agent (Phase 6) a client.

## Verification

| Check | Result |
|---|---|
| `pytest -v` | ✅ 111/111 |
| `pnpm typecheck` | ✅ 13/13 projects |
| `pnpm --filter @insnav/locale test` | ✅ 9/9 |
| `pnpm build --mode nebula` | ✅ 116 KB gzip first load, 434 KB ELK chunk lazy |
| Approved edge → join in BOTH cubes (bidirectional) | ✅ |
| Proposed edge → NO join (PRD §2 enforcement) | ✅ |
| Provenance: every join has `from_edge_id` traceable to graph_edges/{id} | ✅ |

## Cost projection

| Service | Phase 5 usage | Cost |
|---|---|---|
| Firestore reads (datasets + columns + edges per schema build) | ~4 reads × N datasets | $0 (free tier 50K reads/day) |
| Cube .js generation | Pure Python, no external calls | $0 |
| **Total** | | **$0 incremental** |

## Manual smoke-test recipe (live GCP)

```bash
# Backend + frontend running (per docs/PHASE-2-STATUS.md)
# Upload two CSVs that share a join key column (e.g. both have `gclid`)
# Go to Graph tab → approve the proposed edge
# Go to Cube tab → see two rows, each showing 1 join
# Click "View .js" on either → see the Cube schema with:
#   - cube(`<name>__<short_id>`, { ... })
#   - dimensions block with every column
#   - measures block with count + sum/avg for numeric non-FK columns
#   - joins block with from_edge_id comment pointing at the approved edge
```

## Next: Phase 5b (Cube deployment) OR Phase 1.5 (Firebase Auth)?

- **Phase 5b — Cube deployment**: deploy Cube as a Cloud Run service that
  reads our `/v1/cube/schemas/*.js`. Gives the Phase 6 Semantic agent a real
  query target. Cube is free + open-source; would land within our $5/mo
  guardrail (Cloud Run scales to zero). ~1-2 hours.
- **Phase 1.5 — Firebase Auth multi-tenant**: required before any second
  real user.

Recommendation: **Phase 5b** so the next real product capability (Semantic
agent answering questions) has a target. Phase 1.5 still solo-dev safe.
