# Phase 4 status

> Knowledge graph live end-to-end. Edge proposals auto-generated on upload,
> admin approves/rejects in the UI, approved edges become the ground truth
> for Cube join generation in Phase 5.

## The trust contract this turn enforces

PRD § Hard constraint #2 (the load-bearing rule): every Cube join MUST trace
to a human-confirmed graph edge. If a relationship is not a confirmed edge,
it cannot become a join, and the agents physically cannot connect those
datasets.

Phase 4 ships the proposal + confirmation half of that contract. Phase 5
will wire the approved edges into Cube schema generation (the join half).

## Architecture summary

Two-signal proposer → human review → approved-only graph.

```
[upload completes]                 │
        │                          │
        ▼                          │
[edge_proposer.propose_for_dataset]│  Triggered inline in /uploads/complete
        │                          │  (wrapped in try/except so it can't
        │                          │   fail the upload itself)
        ▼                          │
[BQ key-overlap query per pair] ◄──┘
        │  for pairs where both columns have profile.key_likeness >= 0.7
        ▼
[proposed edges in Firestore]
        │
        ▼
[GET /v1/edges/proposals] ←── frontend Graph tab
        │
   admin clicks approve/reject
        ▼
[POST /v1/edges/{id}/approve|reject]
        │
        ▼
[approved edges in Firestore]
        │
        ▼
[GET /v1/edges] ←── available to Cube generator (Phase 5)
                    + NetworkX path queries for multi-dataset (Phase 10)
```

## What shipped

### Backend (new + edits)

- `backend/packages/graph_store/insnav_graph_store/` — fully replaced the
  Phase 0 stub:
  - `models.py` — `GraphEdge` with state machine + directionless_key for dedup
  - `store.py` — propose/approve/reject + NetworkX path queries; offline
    in-memory + Firestore prod modes
- `backend/services/api_gateway/app/edge_proposer.py` — generates proposals
  via BQ key-overlap. Two thresholds (PR-only to change):
  - `KEY_LIKENESS_MIN = 0.7` — only consider columns the profiler flagged
    as high-cardinality + low-null
  - `MIN_OVERLAP_PCT = 0.5` — only emit a proposal if actual value overlap
    is above this
  Builds SQL via `build_overlap_sql()` using `SAFE_DIVIDE` + `CAST AS STRING`
  on both sides (handles inferred type mismatch like int↔string foreign keys).
- `backend/services/api_gateway/app/edges_router.py` — REST endpoints
  (list approved, list proposals, approve, reject, manual re-discover).
- `backend/services/api_gateway/app/uploads.py` — `/v1/uploads/complete` now
  auto-runs `propose_for_dataset()` after the profile finishes. New field
  `new_edge_proposals: int` on `CompleteUploadResponse`. Failure is logged
  but never undoes the upload.

### Frontend
- `packages/api-client/src/index.ts` — typed methods + `GraphEdge` model
- `apps/web/src/views/GraphView.tsx` — Graph tab with two sections:
  - **Proposed** — per-edge card showing `from_ds.col ↔ to_ds.col`, overlap %,
    distinct counts, shared sample values, Approve/Reject buttons
  - **Approved** — read-only table of confirmed edges with reviewer + when
- `apps/web/src/App.tsx` — third tab wired ("Datasets" / "Graph" / "Locale demo")

### Tests

- **Backend: 72/72** (was 45, +27 new):
  - `packages/graph_store/insnav_graph_store/test_store.py` — 10 tests:
    propose/approve/reject, sticky-reject, tenant isolation, directionless
    idempotency, single-hop + two-hop path queries, neighbors
  - `services/api_gateway/app/test_edge_proposer.py` — 8 tests: SQL
    construction (SAFE_DIVIDE, CAST AS STRING, ARRAY samples), threshold
    behavior, idempotency, tenant isolation, peer requirement
  - `services/api_gateway/app/test_edges.py` — 9 tests: endpoint auth,
    approve flow flips lists, reject flow, cross-tenant 404, auto-discover
    on second upload
- **Frontend: 9/9 locale** (unchanged — Phase 4 has no FE tests yet; that's
  a Phase 3.5 backfill)
- **Total: 81/81.**

## What was NOT done (deliberate)

- **No embedding similarity yet.** The PRD has a two-signal proposer
  (embedding cosine + key overlap). v1 ships key overlap only. Reasons:
  - Cost: Vertex AI embeddings would burn ~$0.0001 per column per dataset
    — under $1/mo at MVP scale but worth gating on user value
  - Most join keys (gclid, transaction_id, cookie_id) are caught by key
    overlap alone since they're literally the same values across systems
  - Embedding adds value mostly for semantically-similar-but-differently-
    named columns (`billing_city` ↔ `geo_city`). Add when a real user wants it.
- **No subgraph visualization.** The frontend lists edges; no canvas/graph
  visualization yet. NetworkX-on-the-frontend or a viz library (D3, vis-network,
  cytoscape) is Phase 4.5.
- **No edge editing.** Approve/Reject only. PRD §4.3 mentions Approve/Reject/
  Edit. Edit would be useful when the proposer picks the wrong columns of a
  multi-column composite key. Phase 4.5 or when a user asks.
- **Discovery runs synchronously on upload-complete.** Fine at v1 scale
  (one upload at a time, ~50 BQ queries each, <30s combined). Phase 4.5
  can dispatch to a Cloud Run Job if it ever exceeds Cloud Run's 60-min
  request timeout.

## Verification

| Check | Result |
|---|---|
| `pytest -v` | ✅ 72/72 |
| `pnpm typecheck` | ✅ 13/13 projects |
| `pnpm --filter @insnav/locale test` | ✅ 9/9 |
| `pnpm build --mode nebula` | ✅ 52 KB gzip (39 modules) |
| Edge state machine (proposed → approved/rejected, sticky) | ✅ |
| Tenant isolation (cross-tenant 404, not empty list) | ✅ |
| Directionless idempotency (A↔B == B↔A) | ✅ |
| NetworkX path queries (single-hop, two-hop) | ✅ |
| SAFE_DIVIDE + CAST AS STRING in overlap SQL | ✅ |
| Auto-discover triggers on upload complete | ✅ |

## Cost projection (still inside $5/mo guardrail)

| Service | Phase 4 usage | Cost |
|---|---|---|
| BQ overlap queries | ~50 queries per upload, small DISTINCT scans | $0 under 1 TB/month |
| Firestore edges collection | KB per edge | $0 (free tier 1 GiB) |
| **Total** | | **$0 incremental** |

## Manual smoke-test recipe (live GCP)

```bash
# Start backend + frontend per docs/PHASE-2-STATUS.md
# Then:

# 1. Upload first CSV — Datasets tab, drag-drop, watch status → ready
#    Notice the response shows new_edge_proposals=0 (no peers).

# 2. Upload a second CSV that shares a key column with the first
#    (e.g. both have a `customer_id` or `gclid` column).
#    Response will show new_edge_proposals=1.

# 3. Go to Graph tab → see the proposal with:
#    - from_ds.col ↔ to_ds.col
#    - overlap % (e.g. 92%)
#    - distinct counts
#    - 5 shared sample values
#    - Approve / Reject buttons

# 4. Click Approve → edge moves to the Approved section below.

# 5. Verify in Firestore (gcloud or console):
#    gcloud firestore documents list --project=insights-navigator-v2 \
#      --collection-path=graph_edges
```

## Next: Phase 5 (Cube auto-generation) or Phase 1.5 (Firebase Auth)?

- **Phase 5 — Cube auto-generation** uses the approved edges to emit
  `infra/cube-schema/*.js` files. Closes the loop from upload → approval →
  queryable cube. Most product value. ~2 hours.
- **Phase 1.5 — Firebase Auth multi-tenant** — required before any second
  real user. Bootstrap admin is fine for solo dev.

I'd recommend **Phase 5** so we get to a "ask a chat question, get a real answer"
state. Phase 1.5 is a prerequisite for users, but you can use the platform
yourself for weeks before it matters.
