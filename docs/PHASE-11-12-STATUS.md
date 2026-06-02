# Phases 7, 8, 11, 12 + Tier B — Status

All remaining PRD phases are built, tested, deployed, and verified end-to-end
(UI / UX / functionality / OODA / feature + live UAT as an end user).

## What shipped

### Phase 7 — Pivot panel
Drag-drop Rows/Columns/Values shelves → governed Cube crosstab. Table↕Chart,
Copy-as-TSV, Pin-to-dashboard. `GET /v1/pivot/fields`, `POST /v1/pivot/query`.

### Phase 8 — Dashboards + smart charts + share/embed
Pin tiles (chart specs); tiles re-run on visit. Rule-based chart-type auto-select
(KPI / bar / line / table, CSS+SVG, no charting lib). Read-only public share
tokens (`GET /v1/public/dashboards/{token}`, no auth).

### Phase 11 — PhD differentiators (all deterministic, $0, offline-tested)
| # | Feature | Surface |
|---|---------|---------|
| 1 | **Column-level lineage** | `GET /v1/lineage` → cube member → SQL → raw cols → who-confirmed → join edges. Slide-over on any field. |
| 2 | **Cohort builder + set algebra** | `(A & B) - C` parsed + compiled to a Cube boolean filter tree (De Morgan negation), per-cube, every leaf validated. `/v1/cohorts*`. |
| 3 | **Snapshot diffing** | Capture governed results, diff two by dimension key with per-measure deltas. `/v1/snapshots*`. |
| 4 | **Query cost preview** | `POST /v1/pivot/estimate` — table-metadata upper bound, gate at 5 GB. Live ≈/⚠ badge in pivot. |
| 5 | **Assumption-violation alerts** | `POST /v1/assumptions/check` — small-sample, recent-anomaly. On-demand per-tile badges (no cron → $0). |
| 6 | **Reproducible notebook export** | `POST /v1/notebook` → runnable `.ipynb` of the governed query. Download button in pivot. |
| 7 | **Causal-inference guardrails** | Orchestrator refuses causal *claims* without a stated identification strategy (DiD / RDD / IV / randomized). LLM-free detection. |
| 8 | **Metric registry** | `GET /v1/metrics` — every measure + provenance + human-confirmed owner/effective date. Admin "Metrics" tab. |

### Phase 12 — X-ray proactive insights
`POST /v1/xray/suggest` + `/v1/xray/dashboard` — rule-based starter tiles (KPI
totals, top-N breakdowns, trends) from the cube, revenue-first, capped at 8.
"✨ Auto-generate" button in Dashboards.

### Tier B
- **Heavier stats**: OLS `linear_regression` (slope/intercept/R²/p-value) + 2×2
  `diff_in_differences`; `regression` wired into chat analysis routing.
- **Multi-turn chat**: ChatView keeps a running Q&A transcript + Clear.
- **Onboarding resume-on-reload**: sessionId persisted in `localStorage` per
  dataset; refresh resumes the interview (cleared on completion). Re-onboard =
  click Onboard again.

## Determinism & governance (held throughout)
LLMs orchestrate/select; deterministic code computes. Every cube join traces to
a human-confirmed edge. `revenue_touching` requires human confirmation. Causal
claims refused without an identification strategy. Cost-gated cross-dataset
queries. Tenant + project IDOR checks on every endpoint.

## Tests
- Backend: **235 passed** (api_gateway + agents), offline. New suites:
  `test_phase11`, `test_cohorts`, `test_snapshots`, `test_xray`, causal in
  `test_swarm`, regression + DiD in `test_stats`.
- Frontend: `tsc -b` + `vite build` clean.

## Live deployment (insights-navigator-v2, us-central1)
- api-gateway revision `00009-vm8` (image `insnav/api:latest`)
- frontend revision `00005-596` (image `insnav/frontend:latest`)
- URLs: api `https://insnav-api-gateway-q3rm3dw2tq-uc.a.run.app` ·
  app `https://insnav-frontend-q3rm3dw2tq-uc.a.run.app`

## Live UAT (as an end user) — 23/23 passed
`backend/uat_live.py` against the live deployment with the real marriott India
dataset: health, login, pivot, cost estimate, metrics, lineage, notebook,
dashboard (create/pin/run/share/public), cohorts (create/resolve), snapshots
(capture/diff), assumptions, x-ray (suggest/dashboard), causal guardrail
(refuse without strategy, proceed with strategy).

## Browser UI/UX pass (live backend)
Login → Admin/Projects → Explore (Ask · Pivots · Dashboards · Cohorts ·
Snapshots) → Pivot loaded all live cube fields with ₹ India-locale marking →
Cohort builder rendered with live field dropdowns + set-algebra input. No
console errors.

## Two live findings fixed mid-UAT
1. Snapshot capture 500 — Firestore rejects nested arrays; rows now JSON-
   serialized on write / parsed on read (+ regression test).
2. `/healthz` shadowed by Google Front End on `*.run.app` — added `/health`
   alias.

## Notes / follow-ups
- Bootstrap admin password must be rotated before real external users.
- `.claude/launch.json` is a local dev-preview convenience (untracked).
