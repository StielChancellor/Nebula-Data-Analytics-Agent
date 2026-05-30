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
"""


# ---------- Semantic agent: interpret ----------

async def interpret(question: str, catalog_text: str, router: LLMRouter) -> Interpretation:
    prompt = f"{_SYSTEM_PROMPT}\n\nCATALOG:\n{catalog_text}\n\nQUESTION: {question}\n\nJSON:"
    resp = await router.generate(prompt=prompt, system=_SYSTEM_PROMPT, max_tokens=2048)
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
    )
