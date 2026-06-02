"""
Agent-led onboarding models (Phase 10-C).

Pure Pydantic — no Firestore/api_gateway imports — so the onboarding agent stays
independently testable/extractable (same boundary discipline as swarm.py). The
api_gateway persists these; the cube generator consumes ColumnSemantics as plain
dicts off the columns subcollection.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

ColumnRole = Literal["dimension", "measure", "time", "identifier", "ignore"]
MeasureAgg = Literal["sum", "avg", "count", "min", "max", "count_distinct"]

InterviewStep = Literal[
    "project_name",   # awaiting the project name (skipped if the project already exists)
    "grain",          # "one row per ___?"
    "draft_review",   # agent presents the auto-classified draft; human reviews/corrects
    "joins",          # confirm proposed join edges (revenue-feeding joins gated here)
    "confirm",        # final yes/no before building the cube + graph
    "done",           # semantics persisted, project activated, cube+graph generated
]
QuestionType = Literal["free_text", "single_choice", "confirm", "draft_review"]
SessionStatus = Literal["in_progress", "completed", "abandoned"]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class ColumnSemantics(BaseModel):
    """Human-confirmed per-column meaning that overrides the heuristics.

    `is_revenue` only becomes a governed revenue measure once `confirmed_by` is
    set (PRD Hard Constraint #3) — so an unreviewed draft never auto-flags revenue.
    """

    model_config = ConfigDict(extra="ignore")  # tolerant: merged dicts may carry profile keys

    column: str
    role: ColumnRole = "dimension"
    business_meaning: str = ""
    is_revenue: bool = False
    is_cost: bool = False
    measure_aggregation: MeasureAgg | None = None
    date_granularity: str | None = None
    join_key: bool = False
    display_title: str | None = None
    confirmed_by: str | None = None
    confirmed_at: str | None = None


class AgentQuestion(BaseModel):
    """What the API returns for the UI to render the current interview turn."""

    model_config = ConfigDict(extra="forbid")

    step: InterviewStep
    prompt: str
    question_type: QuestionType = "free_text"
    choices: list[str] = Field(default_factory=list)
    target_column: str | None = None
    # For draft_review: the current draft the human edits in the compact table.
    draft: list[ColumnSemantics] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class TranscriptEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["agent", "user"]
    step: InterviewStep
    text: str
    ts: str = Field(default_factory=_now)


class IngestSession(BaseModel):
    """Persisted interview state (chat is stateless, so this is its own store)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex)
    tenant_id: str
    project_id: str | None = None
    dataset_id: str
    status: SessionStatus = "in_progress"
    current_step: InterviewStep = "draft_review"
    columns_remaining: list[str] = Field(default_factory=list)
    current_column: str | None = None
    semantics: dict[str, ColumnSemantics] = Field(default_factory=dict)
    grain_description: str | None = None
    confirmed_join_edge_ids: list[str] = Field(default_factory=list)
    transcript: list[TranscriptEntry] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
