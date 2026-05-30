# Phase 9 status — Stats/Maths specialist agents

> The "PhD-level analyst" depth: inferential analysis on top of the governed
> Cube result. The LLM SELECTS the method + the fields; **deterministic
> numpy/scipy code computes** the numbers (PRD constraint #1). Predictive answers
> ship with stated assumptions + an uncertainty band, never as fact (PRD §8).

## What shipped

### Stats library — `packages/agents/insnav_agents/stats.py`
Deterministic methods, each returning a uniform envelope
`{method_used, result, assumptions_checked, confidence, caveats}`:

| Method | What it does |
|---|---|
| `summary_stats` | n, mean, median, std, min/max, quartiles |
| `significance_test` | Welch t-test or Mann-Whitney (auto by sample size); p-value, significance @ α=0.05, Cohen's d effect size |
| `correlation` | Pearson r + p-value; always caveats "correlation ≠ causation" |
| `detect_anomalies` | z-score outliers (\|z\| > 3) |
| `forecast` | Holt linear (level+trend) exponential smoothing in numpy; 95% band from residual std |

Built-in mitigations (PRD §6 #6): small-sample caveats (n < 30), uncertainty
bands on forecasts, "correlation ≠ causation", graceful "numerical libs
unavailable" envelope (numpy/scipy lazy-imported, so the module imports without
the `[stats]` extra).

### Orchestrator routing (the swarm picks up a specialist)
- `Interpretation.analysis` — an optional directive the LLM fills for inferential
  questions, e.g. `{"method":"forecast","value_field":"c.m","periods":3}` or
  `{"method":"significance","value_field":"c.m","group_field":"c.d","group_a":"X","group_b":"Y"}`.
- `run_specialist_analysis()` maps the directive onto the Cube result columns and
  runs the deterministic method. Graceful on any field-mapping gap.
- `answer_question()` attaches the result as `ChatAnswer.analysis`.
- System prompt updated so the LLM emits the directive only for inferential
  questions (forecast/trend/significance/correlation/anomaly).

### Frontend
- `api-client`: `AnalysisResult` type on `ChatAnswer.analysis`.
- ChatView renders an **Analysis** block (method, key result JSON, confidence,
  assumptions, caveats) above the "show your work" query.

### Tests — 187/187 backend (was 164, +23)
- `test_stats.py` (18): known-answer checks — perfect correlation r=1, clearly-
  different groups significant, identical groups not, linear series → trend
  forecast with band, obvious outlier detected, dispatch + graceful failures.
- `test_swarm.py` (+5): `run_specialist_analysis` routing (forecast/significance/
  correlation/missing-field) + an end-to-end `answer_question` attaching a
  forecast analysis.
- CI installs `.[dev,stats]`; backend image installs `.[gcp,llm,stats]`.

## Determinism guarantee held

The LLM never emits a number — it picks `{method, fields}`; fixed, audited
numpy/scipy functions compute everything. This is a **stricter** subset of the
PRD vision (LLM-generated code in a sandbox): the methods are reviewed once and
can't be prompt-injected into running arbitrary code.

## What was NOT done (deliberate — the sandbox + heavier methods)

- **Compute sandbox** (Cloud Run Job per invocation, no-egress). The PRD's full
  vision is the LLM *generating* Python that runs in an isolated sandbox. We ship
  fixed methods that run in-process — safe because the code is audited, not
  generated. The sandbox is the next step **when** we let agents author code
  (ARIMA tuning, custom MMM, causal IV, etc.).
- **Heavier methods** — ARIMA/SARIMA, causal inference (diff-in-diff, RDD, IV,
  propensity), survival (Kaplan-Meier/Cox), CLV (BG/NBD), clustering (k-means/
  RFM), marketing-mix (adstock+saturation). These want statsmodels/lifelines/
  scikit-learn (the `[stats]` extra can grow). Forecast here is Holt-linear, not
  full ARIMA.
- **Graph/path agent** (journeys, multi-touch attribution over the knowledge
  graph) — the NetworkX path store exists (Phase 4); the agent that walks it for
  attribution is a separate build.
- **Critic re-deriving assumptions** against a corpus — the Critic still does the
  grounding check (Phase 6); statistical-assumption auditing (normality,
  stationarity) is a Phase 9.5 add.

## Live note

The committed backend image installs `[gcp,llm,stats]`, so once redeployed the
live `/v1/chat` runs real forecasts/significance tests. Until a redeploy, a
deployed backend without numpy returns the graceful "numerical libraries not
installed" caveat instead of crashing.

## Cost

$0 incremental (numpy/scipy run in the api_gateway; no new infra). The sandbox,
when built, would be a Cloud Run Job (pay-per-invocation, scale-to-zero).
