"""
Graph data model.

PRD § Hard constraint #2: every Cube join MUST trace to a human-confirmed
graph edge. The edge state machine enforces that:

   proposed → approved   (admin reviewed; can become a Cube join)
   proposed → rejected   (admin reviewed; do not re-propose)

Once an edge is approved, it's referenceable from Cube schema generation
(Phase 5). Rejected edges are remembered so the proposer doesn't re-suggest
them. Proposed edges are pending admin review and do nothing until approved.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

EdgeState = Literal["proposed", "approved", "rejected"]


class GraphEdge(BaseModel):
    """A relationship between two columns across datasets."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex)
    tenant_id: str

    from_dataset: str       # dataset_id (not the BQ table fqn)
    from_column: str
    to_dataset: str
    to_column: str

    # Signals used to propose this edge
    similarity_score: float = 0.0    # embedding cosine sim (0.0 v1 — no embeddings yet)
    key_overlap_pct: float = 0.0     # actual value overlap from BQ JOIN (0..1)
    from_distinct_count: int | None = None
    to_distinct_count: int | None = None
    sample_overlap: list[str] = Field(default_factory=list)   # up to 5 shared values for the UI

    # State machine
    state: EdgeState = "proposed"
    reviewed_by: str | None = None        # principal.email
    reviewed_at: str | None = None        # ISO 8601

    # Timestamps
    created_at: str = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )

    def directionless_key(self) -> tuple[str, str, str, str]:
        """
        A key that's the same for (A.x ↔ B.y) and (B.y ↔ A.x). Used to
        dedup proposals — we don't want both directions of the same edge
        cluttering the admin review.
        """
        a = (self.from_dataset, self.from_column)
        b = (self.to_dataset, self.to_column)
        lo, hi = (a, b) if a <= b else (b, a)
        return (lo[0], lo[1], hi[0], hi[1])
