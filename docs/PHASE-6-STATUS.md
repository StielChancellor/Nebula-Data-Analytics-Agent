# Phase 6 status — the agent swarm

> Natural-language question → governed answer. The brain SELECTS measures /
> dimensions / filters; **Cube compiles the SQL** (PRD § Hard constraint #1).
> Every answer carries an interpretation echo, a data-health badge, and the
> exact Cube query that ran. Below-confidence or hallucinated selections →
> clarify, not a confident wrong answer.

## The swarm (MVP subset: Orchestrator + Semantic + Critic + Data-Quality)

```
question
   │
   ▼  Orchestrator (insnav_agents.answer_question — pure, injectable)
   ├─ Semantic.interpret: LLM → structured Interpretation (measures/dims/filters)
   │                       grounded against the REAL catalog (built from the
   │                       tenant's Cube schemas)
   ├─ Critic.critic_check: every selected field must EXIST in the catalog
   │                       (a hallucinated measure can never reach Cube);
   │                       low confidence → clarify
   ├─ Data-Quality.data_health: freshness + completeness badge; blocked source → refuse
   ├─ Semantic.to_cube_query → CubeQueryClient.load()  (Cube compiles + runs SQL)
   └─ synthesize ChatAnswer: echo + confidence + health + cube_query + rows + inputs_hash
```

Stats / Maths / Graph specialists + the Python compute sandbox are Phase 9.

## What shipped

### Backend
- `packages/agents/insnav_agents/`:
  - `schemas.py` — `Interpretation`, `ChatAnswer`, `DataHealthBadge`.
  - `swarm.py` — `build_catalog`, `interpret` (LLM→JSON, robust extraction),
    `critic_check` (grounding), `to_cube_query`, `data_health`, and the
    `answer_question` orchestrator. **Pure + injectable** (LLM router + Cube
    client) → fully testable offline; swaps to Gemini + deployed Cube in prod.
- `services/api_gateway/app/chat_router.py` — `POST /v1/chat` (tenant-scoped):
  builds the catalog + dataset health from Firestore, runs the swarm, returns
  the `ChatAnswer`. **Canonical-hash cache** (identical tenant+question+datasets
  → identical answer) + structured audit log.
- LLM via `get_default_router()` (Gemini when `[llm]` + creds present; else a
  stub → the orchestrator clarifies, honestly, because the stub can't interpret).
  Cube via `CubeQueryClient` (deployed service when `INSNAV_CUBE_API_URL` is set,
  else offline stub with an "illustrative" caveat).

### Frontend
- `api-client`: `chat()` + `ChatAnswer` / `DataHealthBadge` types.
- `apps/web/src/views/ChatView.tsx` — the **"Ask"** tab (now the default):
  question box (⌘/Ctrl+Enter to send), answer card with the interpretation echo,
  confidence + data-health + analysis-level badges, warnings/caveats, the result
  table, and a collapsible **"Cube query (show your work)"**. Clarify/refuse
  answers render their message.

### Tests — 158/158 backend (was 139, +19)
- `test_swarm.py` (14): catalog + grounding, critic catches hallucinated +
  empty selections, query mapping, data-health ok/warn, and end-to-end
  happy-path / hallucination→clarify / low-confidence→clarify / no-schemas→refuse
  / deterministic inputs_hash / unparseable-LLM→clarify.
- `test_chat.py` (5): endpoint auth, happy path (echo+health+query+rows+caveat),
  hallucination→clarify, canonical cache serves identical answer, no-datasets→refuse.
- Frontend: typecheck (13 projects) + build green; locale 9/9.

## PRD guarantees demonstrated

| Guarantee | How |
|---|---|
| LLM selects, code computes (#1) | LLM returns a structured `Interpretation`; `to_cube_query` + Cube do the SQL. No LLM-authored SQL anywhere. |
| Interpretation echo (#2) | `interpretation_echo` on every answer; low confidence → clarify instead of guessing. |
| Grounding (no hallucinated metrics) | Critic rejects any field not in the real catalog before Cube is touched. |
| Data-health badge (#3) | `data_health` (freshness/completeness/warnings); blocked source → refuse. |
| Show-your-work + provenance (#4) | `cube_query` returned + shown in the UI; `inputs_hash` for determinism. |
| "I don't know" (#5) | `kind: clarify | refuse` paths. |
| Determinism | Canonical-hash cache + `compute_inputs_hash`; test asserts identical answers. |

## What was NOT done (deliberate)

- **Streaming (SSE).** The endpoint is request/response for the MVP; the SSE
  event schema is stubbed (PRD § Backend↔frontend contract) for Phase 7+.
- **Multi-dataset cross-cube joins in chat.** The catalog includes joins from
  approved edges, but the MVP prompt is single-cube-leaning; cross-cube
  selection hardening is a follow-up.
- **Stats/Maths/Graph agents + compute sandbox** — Phase 9.
- **Live LLM.** No Gemini key/`[llm]` extra wired into a deployed backend yet,
  and the backend isn't deployed. With the stub LLM the swarm honestly
  clarifies. To see real answers: install `[llm]`, set `INSNAV_LLM_PRIMARY` +
  creds, set `INSNAV_CUBE_API_URL`, and ask. The whole path is proven offline
  with a fake LLM returning a canned interpretation.

## Cost

$0 incremental (no new infra; chat runs in the api_gateway). A live Gemini
brain would add per-query LLM cost when configured.
