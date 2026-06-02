"""
The agent swarm (Phase 6 MVP): Orchestrator + Semantic + Critic + Data-Quality.

PRD § Hard constraint #1: LLMs orchestrate and SELECT; deterministic code
computes. The LLM produces a structured `Interpretation` (which governed
measures/dimensions/filters); Cube compiles + runs the SQL. The Critic grounds
the selection against the REAL catalog (so a hallucinated measure can never
reach Cube). Every answer carries an interpretation echo + data-health badge +
the Cube query that ran.

`answer_question` is a pure async function — inject the LLM router and the Cube
client. That makes the whole swarm testable offline (stub LLM + stub Cube) and
swappable in prod (Gemini + the deployed Cube).
"""
from __future__ import annotations

import json
import re
from typing import Any

from insnav_cube_client import CubeQueryClient, CubeSchema
from insnav_cube_client.client import mint_cube_token  # noqa: F401  (re-exported convenience)
from insnav_llm_router import LLMRouter

from .schemas import ChatAnswer, DataHealthBadge, Interpretation

# Confidence below this → ask a clarifying question instead of answering
# (PRD mitigation #2: prefer a clarifying question over a confident wrong one).
_CLARIFY_THRESHOLD = 0.45

# ---------- causal-inference guardrail (PRD §11.7) ----------
# Explicit causal-CLAIM connectors. Plain "why did X drop" is diagnostic and
# routes to decomposition — it is NOT trapped here. Only assertions that one
# thing *caused* another are gated, because asserting causation from
# observational warehouse data without an identification strategy is the #1
# BI-LLM embarrassment.
_CAUSAL_TRIGGERS = (
    "cause", "caused", "causes", "causal", "causation",
    "effect of", "effect on", "impact of", "impact on",
    "because of", "due to", "result of", "as a result of",
    "led to", "lead to", "drove", "driven by", "thanks to",
    "attribut", "responsible for", "contributed to", "knock-on",
)
# A stated identification strategy lets the request through (with a caveat).
_STRATEGY_TERMS = (
    "difference-in-difference", "difference in difference", "differences-in-difference",
    "diff-in-diff", "diff in diff",
    "regression discontinuity", "rdd",
    "instrumental variable", "instrumented", "instrument variable",
    "randomized", "randomised", "randomized controlled", "rct",
    "a/b test", "ab test", "split test", "holdout", "hold-out",
    "control group", "treatment group", "counterfactual", "synthetic control",
    "natural experiment", "propensity", "fixed effects", "event study",
)


def detect_causal_request(question: str) -> tuple[bool, bool]:
    """Return (is_causal_claim, identification_strategy_stated). Deterministic —
    no LLM, so the guardrail holds even when the brain is offline/stubbed."""
    q = question.lower()
    is_causal = any(t in q for t in _CAUSAL_TRIGGERS)
    has_strategy = any(t in q for t in _STRATEGY_TERMS)
    return is_causal, has_strategy


_CAUSAL_REFUSAL = (
    "That asks whether one thing *caused* another. Establishing causation from "
    "observational data needs a stated identification strategy — otherwise the "
    "honest answer is correlation, not cause. Re-ask with one of: a "
    "difference-in-differences design (a comparable control group over the same "
    "period), a regression discontinuity (a threshold that splits treated vs "
    "untreated), an instrumental variable, or a randomized/holdout experiment. "
    "Or ask me descriptively — e.g. \"break down the change in Y by segment\" or "
    "\"show X and Y over time\" — and I'll give you the decomposition without "
    "claiming causation."
)


# ---------- catalog (the grounding surface) ----------

def build_catalog(schemas: list[CubeSchema]) -> tuple[str, set[str]]:
    """
    Returns (human-readable catalog text for the LLM prompt, set of valid
    fully-qualified measure+dimension names for the Critic's grounding check).
    """
    lines: list[str] = []
    valid: set[str] = set()
    for s in schemas:
        lines.append(f"Cube `{s.name}` (from dataset {s.dataset_id[:8]}):")
        for m in s.measures:
            fq = f"{s.name}.{m.name}"
            valid.add(fq)
            lines.append(f"  measure {fq} ({m.type})")
        for d in s.dimensions:
            fq = f"{s.name}.{d.name}"
            valid.add(fq)
            kind = "time" if d.type == "time" else d.type
            lines.append(f"  dimension {fq} ({kind})")
    return "\n".join(lines), valid


_SYSTEM_PROMPT = """You are the interpreter for a governed BI platform. The user
asks a question; you SELECT from the catalog below — you never write SQL.

Return ONLY a JSON object with these keys:
  measures: string[]        (fully-qualified, e.g. "cube.measure" — only from the catalog)
  dimensions: string[]      (fully-qualified — only from the catalog)
  time_dimension: string|null
  granularity: string|null  (day|week|month|quarter|year)
  filters: object[]         (Cube filter format: {member, operator, values})
  order: object             ({"field": "asc"|"desc"})
  limit: number|null
  plain_english: string     (one sentence restating what you will answer)
  analysis_level: string    (descriptive|diagnostic|path|predictive|prescriptive)
  confidence: number        (0..1 — how sure you are this matches the question)

Only use measures/dimensions that appear EXACTLY in the catalog. If the question
cannot be answered from the catalog, return confidence below 0.4.

If (and only if) the question is INFERENTIAL — forecast, trend, "is X
significantly different", correlation, or anomaly/outlier detection — also add an
"analysis" object, choosing fields from the query you built:
  forecast:     {"method":"forecast","value_field":"<measure>","periods":3}
  significance: {"method":"significance","value_field":"<measure>","group_field":"<dimension>","group_a":"<value>","group_b":"<value>"}
  correlation:  {"method":"correlation","x_field":"<measure>","y_field":"<measure>"}
  anomaly:      {"method":"anomaly","value_field":"<measure>"}
  summary:      {"method":"summary","value_field":"<measure>"}
Otherwise omit "analysis". The numbers are computed by deterministic code, not you.
"""


# ---------- Semantic agent: interpret ----------

async def interpret(question: str, catalog_text: str, router: LLMRouter) -> Interpretation:
    prompt = f"{_SYSTEM_PROMPT}\n\nCATALOG:\n{catalog_text}\n\nQUESTION: {question}\n\nJSON:"
    try:
        resp = await router.generate(prompt=prompt, system=_SYSTEM_PROMPT, max_tokens=2048)
    except Exception:  # noqa: BLE001 — LLM outage/model-unavailable → clarify, never 500
        return Interpretation(plain_english="(the language model is unavailable)", confidence=0.0)
    data = _extract_json(resp.text)
    if data is None:
        return Interpretation(plain_english="(could not parse interpretation)", confidence=0.0)
    try:
        return Interpretation.model_validate(data)
    except Exception:  # noqa: BLE001 — malformed model → low confidence, handled upstream
        return Interpretation(plain_english="(invalid interpretation)", confidence=0.0)


def _extract_json(text: str) -> dict[str, Any] | None:
    # Strip ```json fences if present, then grab the outermost {...}.
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    raw = fenced.group(1) if fenced else None
    if raw is None:
        brace = re.search(r"\{.*\}", text, re.DOTALL)
        raw = brace.group(0) if brace else None
    if raw is None:
        return None
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None


# ---------- Critic agent: ground the selection ----------

def critic_check(interp: Interpretation, valid_names: set[str]) -> list[str]:
    """
    Returns a list of grounding issues. The Critic does NOT re-run computation;
    it verifies the LLM only selected fields that actually exist (no
    hallucinated measures reach Cube) + sanity checks.
    """
    issues: list[str] = []
    selected = list(interp.measures) + list(interp.dimensions)
    if interp.time_dimension:
        selected.append(interp.time_dimension)
    for name in selected:
        if name not in valid_names:
            issues.append(f"'{name}' is not a known measure/dimension")
    if not interp.measures and not interp.dimensions:
        issues.append("no measures or dimensions selected")
    return issues


# ---------- Semantic agent: build + run the Cube query ----------

def to_cube_query(interp: Interpretation) -> dict[str, Any]:
    q: dict[str, Any] = {}
    if interp.measures:
        q["measures"] = interp.measures
    if interp.dimensions:
        q["dimensions"] = interp.dimensions
    if interp.time_dimension:
        td: dict[str, Any] = {"dimension": interp.time_dimension}
        if interp.granularity:
            td["granularity"] = interp.granularity
        q["timeDimensions"] = [td]
    if interp.filters:
        q["filters"] = interp.filters
    if interp.order:
        q["order"] = interp.order
    if interp.limit:
        q["limit"] = interp.limit
    return q


def _rows_from_cube(result: dict[str, Any], query: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    data = result.get("data", [])
    cols = list(query.get("measures", [])) + list(query.get("dimensions", []))
    for td in query.get("timeDimensions", []):
        cols.append(td["dimension"])
    if not cols and data:
        cols = list(data[0].keys())
    rows = [[row.get(c) for c in cols] for row in data]
    return cols, rows


# ---------- Stats/Maths specialist (Phase 9) ----------

def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def run_specialist_analysis(
    directive: dict[str, Any], columns: list[str], rows: list[list[Any]]
) -> dict[str, Any]:
    """
    Map an LLM-chosen analysis directive onto the Cube result columns and run the
    deterministic stats method. Graceful on any mapping gap.
    """
    from . import stats

    method = (directive or {}).get("method")
    col_index = {c: i for i, c in enumerate(columns)}

    def column(field: str | None) -> list[float] | None:
        i = col_index.get(field) if field else None
        if i is None:
            return None
        return [v for v in (_to_float(r[i]) for r in rows) if v is not None]

    if method in ("forecast", "summary", "anomaly"):
        series = column(directive.get("value_field"))
        if not series:
            return stats._envelope(method, {}, confidence=0.0,
                                   caveats=[f"value_field '{directive.get('value_field')}' not in result"])
        if method == "forecast":
            return stats.run_analysis("forecast", series=series, periods=int(directive.get("periods", 3)))
        return stats.run_analysis(method, values=series)

    if method in ("correlation", "regression"):
        x, y = column(directive.get("x_field")), column(directive.get("y_field"))
        if not x or not y:
            return stats._envelope(method, {}, confidence=0.0, caveats=["x_field/y_field not in result"])
        return stats.run_analysis(method, x=x, y=y)

    if method == "significance":
        vi = col_index.get(directive.get("value_field"))
        gi = col_index.get(directive.get("group_field"))
        if vi is None or gi is None:
            return stats._envelope("significance", {}, confidence=0.0,
                                   caveats=["value_field/group_field not in result"])
        ga, gb = str(directive.get("group_a")), str(directive.get("group_b"))
        a = [v for v in (_to_float(r[vi]) for r in rows if str(r[gi]) == ga) if v is not None]
        b = [v for v in (_to_float(r[vi]) for r in rows if str(r[gi]) == gb) if v is not None]
        return stats.run_analysis("significance", group_a=a, group_b=b)

    return stats.run_analysis(method or "unknown")


# ---------- Data-Quality agent: health badge ----------

def data_health(dataset_health: list[dict[str, Any]]) -> DataHealthBadge:
    """
    dataset_health: [{id, label, last_refreshed, row_count, status}, ...] for the
    datasets that feed the answer. PRD mitigation #3: surface freshness +
    completeness; block/warn if a source is unhealthy.
    """
    freshness = [{"source": d.get("label", d.get("id")), "last_refreshed": d.get("last_refreshed")} for d in dataset_health]
    completeness = [{"source": d.get("label", d.get("id")), "row_count": d.get("row_count")} for d in dataset_health]
    warnings: list[str] = []
    status = "ok"
    for d in dataset_health:
        if d.get("status") not in (None, "ready"):
            status = "warn"
            warnings.append(f"dataset {d.get('label', d.get('id'))} is {d.get('status')}")
        if d.get("row_count") == 0:
            status = "warn"
            warnings.append(f"dataset {d.get('label', d.get('id'))} has 0 rows")
    return DataHealthBadge(status=status, freshness=freshness, completeness=completeness, warnings=warnings)


# ---------- Orchestrator ----------

async def answer_question(
    question: str,
    *,
    tenant_id: str,
    schemas: list[CubeSchema],
    dataset_health: list[dict[str, Any]],
    router: LLMRouter,
    cube_client: CubeQueryClient,
) -> ChatAnswer:
    """
    The Lead Data Scientist. Interpret → ground (Critic) → run (Cube) → stamp
    health → synthesize. Refuses/clarifies rather than guessing when unsure.
    """
    from insnav_contracts.envelope import compute_inputs_hash

    if not schemas:
        return ChatAnswer(
            kind="refuse",
            message="No ready datasets / cube schemas are available to answer questions yet.",
            interpretation_echo="",
        )

    # Causal-inference guardrail (PRD §11.7) — refuse a causal CLAIM that has no
    # stated identification strategy, before we ever touch the LLM or Cube.
    is_causal, has_strategy = detect_causal_request(question)
    if is_causal and not has_strategy:
        return ChatAnswer(
            kind="refuse",
            message=_CAUSAL_REFUSAL,
            interpretation_echo="Causal question detected — identification strategy required.",
            analysis_level="diagnostic",
            confidence=0.0,
            caveats=["No identification strategy (DiD / RDD / IV / randomized) was stated."],
        )

    catalog_text, valid_names = build_catalog(schemas)
    interp = await interpret(question, catalog_text, router)

    # Critic grounding — a hallucinated field can never reach Cube.
    issues = critic_check(interp, valid_names)
    if issues or interp.confidence < _CLARIFY_THRESHOLD:
        msg = (
            "I'm not confident I can answer that from the available data. "
            + ("Issues: " + "; ".join(issues) + ". " if issues else "")
            + "Could you rephrase or pick a specific metric?"
        )
        return ChatAnswer(
            kind="clarify",
            message=msg,
            interpretation_echo=interp.plain_english,
            confidence=interp.confidence,
            analysis_level=interp.analysis_level,
            caveats=issues,
        )

    query = to_cube_query(interp)
    health = data_health(dataset_health)

    # Data-quality veto (PRD mitigation #3): never serve over a blocked source.
    if health.status == "block":
        return ChatAnswer(
            kind="refuse",
            message="A data source feeding this answer is unavailable; refusing to serve partial data.",
            interpretation_echo=interp.plain_english,
            data_health=health,
        )

    result = cube_client.load(query, tenant_id=tenant_id)
    columns, rows = _rows_from_cube(result, query)

    caveats: list[str] = []
    if result.get("_stub"):
        caveats.append("Cube is not deployed in this environment — results are illustrative (stub).")
    if is_causal and has_strategy:
        caveats.append(
            "Causal framing accepted (identification strategy stated). v1 returns the "
            "descriptive decomposition for that design; treat the estimate as the "
            "design-conditioned association, not a fully adjusted causal effect."
        )

    # Phase 9: if the LLM requested an inferential analysis, run the
    # deterministic specialist method on the result (Stats/Maths agent).
    analysis: dict[str, Any] | None = None
    if interp.analysis and interp.analysis.get("method") and rows:
        analysis = run_specialist_analysis(interp.analysis, columns, rows)

    return ChatAnswer(
        kind="answer",
        interpretation_echo=interp.plain_english,
        confidence=interp.confidence,
        analysis_level=interp.analysis_level,
        cube_query=query,
        columns=columns,
        rows=rows,
        data_health=health,
        method_used="cube_query",
        caveats=caveats,
        inputs_hash=compute_inputs_hash({"q": question, "query": query, "tenant": tenant_id}),
        analysis=analysis,
    )
