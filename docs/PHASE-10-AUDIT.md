# Phase 10 — Security / UX / Functional Audit + Hardening (OODA)

A full review of the deployed platform after the Phase-10 build, run as an OODA
loop: three parallel audit agents (OWASP security, UX best-practices, functional
completeness) → prioritize → fix the essentials → redeploy.

## Observe — what the audits found

**Confirmed healthy:** tenant-ownership (IDOR) checks on every id-bearing
endpoint, Firebase RS256 verification, the determinism + revenue gate (a
`revenue`-named column stays ungoverned until a human confirms), server-generated
BQ table names, sanitized GCS object paths.

**Security (OWASP):** SQL injection via CSV headers (C1), JWT dev-fallback secret
(C2), no RBAC (H1), unvalidated chat `project_id` (H2), hardcoded cube secret
(H3), raw exception leak in 500s (H4), wildcard CORS + credentials (M1),
unbounded BQ cost (M4).

**UX:** preview/type-override step unwired (C2), onboarding "joins" step broken
(C1), silent failures (C5), onboarding hard to follow (no legend/progress),
modal a11y gaps, low-contrast text.

**Functional:** Graph/Cube views showed tenant-wide (not project) data
(cross-project leak); no project-management UI; 4 Phase-0 stub services not
deployed; stale README.

## Orient → Decide — priority

Security criticals/highs > functional correctness (project isolation, the two
unwired ingestion steps) > UX-essential (errors, legibility, a11y) > cleanup.

## Act — what was fixed

### Security
- **C1** `sql_safety.quote_bq_identifier()` escapes every interpolated identifier
  in `build_normalize_sql` / profiler / edge-overlap SQL; date-format + bq_type
  validated against allowlists. → BQ injection closed.
- **C2** `_jwt_secret()` fails closed (no baked-in fallback; requires the env var
  in prod; deterministic offline secret for tests).
- **H1** `require_admin` RBAC dependency gates edge approve/reject, cube sync,
  project PATCH/DELETE, dataset DELETE.
- **H2** `/v1/chat` validates `project_id` tenant ownership before minting the cube token.
- **H3** `cube_api_secret` no longer defaults to a known value.
- **H4** 500 body is generic; curated detail stays on the dataset for the owner.
- **M1** CORS `allow_credentials=False` (bearer API).
- **M4** `maximum_bytes_billed` cap on every BQ query (the $5 guardrail, enforced).
- +6 security regression tests.

### Functional correctness
- Graph/Cube views project-scoped (`?project_id` on `/v1/edges`,
  `/v1/edges/proposals`, `/v1/cube/schemas`, `/v1/cube/sync`). → cross-project
  leak closed.
- **Preview/type-override** wired into the upload dialog (read-before-commit,
  India-aware, editable types → `completeUpload(overrides)`).
- **Onboarding joins** step renders candidate edges as a checklist and sends
  `confirmed_edge_ids`.

### UX / a11y
- Onboarding: column-role legend, step progress indicator, transcript autoscroll,
  free-text correction box on draft review.
- Project-management UI (rename / status / delete with cascade warning).
- Dataset-list error states (no silent empty state); upload-modal `role=dialog` /
  `aria-modal` / Escape + backdrop close / labelled close button; contrast floor
  raised; cold-start hint.

## Verify

248 backend tests pass (incl. the 6 security regressions). Frontend typecheck +
production build green. Re-deployed and live-verified end-to-end (India preview →
onboarding → per-project cube; project-scoped chat).

## Deferred (non-essential, flagged)

- Member invitations (needs Identity-Platform user management).
- Pivots/Dashboards (PRD Phase 7/8 placeholders).
- Removing the 4 Phase-0 stub services + fixing the stale `backend/README.md`
  ("swarm lives in services/orchestrator" — it's in-process in api_gateway).
- Onboarding resume-on-reload (session id persistence + `GET /sessions/{id}`
  re-deriving the question).
- Multi-turn chat history; per-CSV re-onboarding/edit of confirmed semantics.

## Cost

$0 new always-on. The `maximum_bytes_billed` cap makes the $5/mo guardrail
enforceable rather than advisory.
