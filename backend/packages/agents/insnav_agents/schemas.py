"""
Agent-swarm data shapes (Phase 6).

The interpretation is the load-bearing object: the LLM SELECTS governed
measures/dimensions/filters (it never writes SQL). Everything downstream is
deterministic — Cube compiles the SQL, the Critic grounds the selection against
the real catalog, and the Data-Quality agent stamps a health badge.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AnalysisLevel = Literal["descriptive", "diagnostic", "path", "predictive", "prescriptive"]


class Interpretation(BaseModel):
    """What the LLM produces from the question (structured selection, not SQL)."""

    model_config = ConfigDict(extra="ignore")

    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    time_dimension: str | None = None
    granularity: str | None = None  # day/week/month/quarter/year
    filters: list[dict[str, Any]] = Field(default_factory=list)
    order: dict[str, Literal["asc", "desc"]] = Field(default_factory=dict)
    limit: int | None = None
    plain_english: str = ""
    analysis_level: AnalysisLevel = "descriptive"
    confidence: float = 0.0
    # Optional specialist directive (Phase 9). When the question is inferential,
    # the LLM picks a method + the fields to run it on; deterministic stats code
    # computes the numbers. e.g. {"method":"forecast","value_field":"c.m","periods":3}
    # or {"method":"significance","value_field":"c.m","group_field":"c.d",
    #     "group_a":"X","group_b":"Y"} or {"method":"correlation","x_field","y_field"}.
    analysis: dict[str, Any] | None = None


class DataHealthBadge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "warn", "block"]
    freshness: list[dict[str, Any]] = Field(default_factory=list)
    completeness: list[dict[str, Any]] = Field(default_factory=list)
    coverage_rate: float | None = None
    warnings: list[str] = Field(default_factory=list)


class ChatAnswer(BaseModel):
    """The synthesized answer the chat endpoint returns."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["answer", "clarify", "refuse"] = "answer"
    # Interpretation echo (PRD mitigation #2) — always shown.
    interpretation_echo: str = ""
    confidence: float = 0.0
    analysis_level: AnalysisLevel = "descriptive"
    # The governed selection + the Cube query that ran (show-your-work).
    cube_query: dict[str, Any] | None = None
    # Result rows from Cube (or the offline stub).
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    # Provenance / trust.
    data_health: DataHealthBadge | None = None
    method_used: str = "cube_query"
    caveats: list[str] = Field(default_factory=list)
    inputs_hash: str = ""
    # Specialist result (Phase 9): the stats/maths envelope
    # {method_used, result, assumptions_checked, confidence, caveats}.
    analysis: dict[str, Any] | None = None
    # For kind="clarify"/"refuse": the message to show the user.
    message: str = ""
