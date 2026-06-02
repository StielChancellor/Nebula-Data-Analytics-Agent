"""
Agent-led onboarding state machine (Phase 10-C).

"Agent drafts, you review": the agent auto-classifies EVERY column from the
profile (heuristic_semantics), presents the draft, and the human reviews/corrects
it. The LLM only authors question/summary text and parses free-text corrections
into typed ColumnSemantics — deterministic code computes the cube (PRD #1). With
the stub LLM (offline), everything degrades to deterministic heuristics so tests
are stable and the gate stays honest (no auto-confirmed revenue, PRD #3).

Pure + injectable (no Firestore imports) — the api_gateway fetches data and
persists; this module only transforms.
"""
from __future__ import annotations

import json
import re
from typing import Any

from insnav_llm_router import LLMRouter

from .onboarding_models import ColumnSemantics, InterviewStep

# Keep this list in sync with cube_client.generator._is_revenue_column (kept
# local to preserve the pure boundary — no cube_client import here).
_REVENUE_KEYWORDS = ("revenue", "sales", "roas", "cost", "spend", "profit", "margin")
_COST_KEYWORDS = ("cost", "spend", "expense")
_NUMERIC_BQ = {"INT64", "INTEGER", "FLOAT64", "FLOAT", "NUMERIC", "BIGNUMERIC"}
_TIME_BQ = {"DATE", "DATETIME", "TIME", "TIMESTAMP"}
_KEY_LIKENESS_ID = 0.85
_KEY_LIKENESS_FK = 0.70

_AFFIRMATIVE = {
    "yes", "y", "accept", "accepted", "looks good", "lgtm", "ok", "okay",
    "confirm", "confirmed", "done", "proceed", "build", "go", "sounds good",
}


# ---------- draft (heuristic) ----------

def _is_revenue_name(name: str) -> bool:
    return any(k in name.lower() for k in _REVENUE_KEYWORDS)


def _is_cost_name(name: str) -> bool:
    return any(k in name.lower() for k in _COST_KEYWORDS)


def heuristic_semantics(profile: dict[str, Any]) -> ColumnSemantics:
    """
    Auto-classify one column from its profile. The `is_revenue` flag here is an
    UNCONFIRMED guess (confirmed_by stays None) — it only becomes a governed
    revenue measure once a human confirms during the interview.
    """
    name = profile.get("name", "")
    bq = str(profile.get("type", "") or "").upper()
    kl = float(profile.get("key_likeness", 0.0) or 0.0)

    if bq in _TIME_BQ:
        return ColumnSemantics(column=name, role="time", date_granularity="day")
    if kl >= _KEY_LIKENESS_ID:
        return ColumnSemantics(column=name, role="identifier", join_key=True)
    if bq in _NUMERIC_BQ and kl < _KEY_LIKENESS_FK:
        return ColumnSemantics(
            column=name,
            role="measure",
            measure_aggregation="sum",
            is_revenue=_is_revenue_name(name),
            is_cost=_is_cost_name(name),
        )
    if bq in _NUMERIC_BQ:  # numeric but high-cardinality → likely a foreign key
        return ColumnSemantics(column=name, role="identifier", join_key=True)
    return ColumnSemantics(column=name, role="dimension")


def build_draft(profiles: list[dict[str, Any]]) -> dict[str, ColumnSemantics]:
    """Auto-classify all columns up front (the 'draft' in 'agent drafts, you review')."""
    return {p.get("name", ""): heuristic_semantics(p) for p in profiles if p.get("name")}


def draft_counts(semantics: dict[str, ColumnSemantics]) -> dict[str, int]:
    counts = {"measure": 0, "dimension": 0, "time": 0, "identifier": 0, "ignore": 0, "revenue": 0}
    for s in semantics.values():
        counts[s.role] = counts.get(s.role, 0) + 1
        if s.is_revenue:
            counts["revenue"] += 1
    return counts


def deterministic_draft_summary(
    project_name: str | None, semantics: dict[str, ColumnSemantics]
) -> str:
    c = draft_counts(semantics)
    where = f" for project “{project_name}”" if project_name else ""
    rev = f", flagging {c['revenue']} as revenue/cost (please confirm)" if c["revenue"] else ""
    return (
        f"I read {len(semantics)} columns{where}: {c['measure']} measures, "
        f"{c['dimension']} dimensions, {c['time']} date, {c['identifier']} IDs/keys{rev}. "
        f"Review and correct anything below, or say “looks good” to build."
    )


# ---------- transitions ----------

def next_step(current: InterviewStep, *, has_joins: bool) -> InterviewStep:
    if current == "project_name":
        return "grain"
    if current == "grain":
        return "draft_review"
    if current == "draft_review":
        return "joins" if has_joins else "confirm"
    if current == "joins":
        return "confirm"
    if current == "confirm":
        return "done"
    return "done"


def is_affirmative(answer: str) -> bool:
    a = (answer or "").strip().lower().rstrip(".!")
    return a in _AFFIRMATIVE or a.startswith("yes") or a.startswith("accept")


# ---------- LLM-authored text + answer parsing (graceful offline fallback) ----------

async def draft_summary(
    project_name: str | None,
    semantics: dict[str, ColumnSemantics],
    router: LLMRouter,
) -> str:
    """One friendly sentence summarizing the draft. Falls back to deterministic."""
    base = deterministic_draft_summary(project_name, semantics)
    try:
        resp = await router.generate(
            prompt=f"Rewrite this data-onboarding summary as one friendly sentence; keep all the numbers and the call to review:\n{base}",
            system="You are a concise data-onboarding assistant.",
            max_tokens=200,
        )
        text = (resp.text or "").strip()
        if text and not text.startswith("[stub:"):
            return text
    except Exception:  # noqa: BLE001 — LLM outage must not break onboarding
        pass
    return base


async def interpret_correction(
    answer: str,
    semantics: dict[str, ColumnSemantics],
    router: LLMRouter,
) -> dict[str, ColumnSemantics]:
    """
    Parse a free-text correction ("amount is revenue, drop notes") into typed
    ColumnSemantics patches merged onto the current draft. Returns ONLY the
    changed columns. Offline/stub or unparseable → {} (no change).
    """
    known = ", ".join(sorted(semantics.keys()))
    prompt = (
        "You relabel dataset columns. Output ONLY a JSON object mapping column "
        "names to changes. Allowed roles: dimension|measure|time|identifier|ignore. "
        "Allowed measure_aggregation: sum|avg|count|min|max|count_distinct. "
        "Only include columns the user explicitly mentions. Example: "
        '{"amount": {"role": "measure", "is_revenue": true, "measure_aggregation": "sum"}, '
        '"notes": {"role": "ignore"}}\n\n'
        f"COLUMNS: {known}\n\nUSER CORRECTION: {answer}\n\nJSON:"
    )
    try:
        resp = await router.generate(prompt=prompt, system="You output only JSON.", max_tokens=1024)
    except Exception:  # noqa: BLE001
        return {}
    data = _extract_json(resp.text)
    if not isinstance(data, dict):
        return {}

    patches: dict[str, ColumnSemantics] = {}
    for col, change in data.items():
        if col not in semantics or not isinstance(change, dict):
            continue
        merged = semantics[col].model_dump()
        for k, v in change.items():
            if k in merged:
                merged[k] = v
        try:
            patches[col] = ColumnSemantics.model_validate(merged)
        except Exception:  # noqa: BLE001 — skip a malformed patch, keep the rest
            continue
    return patches


def _extract_json(text: str) -> dict[str, Any] | None:
    """Mirror of swarm._extract_json (inlined to keep this module dependency-light)."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.DOTALL)
    raw = fenced.group(1) if fenced else None
    if raw is None:
        brace = re.search(r"\{.*\}", text or "", re.DOTALL)
        raw = brace.group(0) if brace else None
    if raw is None:
        return None
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else None
    except json.JSONDecodeError:
        return None
