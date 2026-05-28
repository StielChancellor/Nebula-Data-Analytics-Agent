"""
insnav_graph_store — knowledge graph storage abstraction.

V1 implementation (PRD D10): NetworkX in-process + Firestore persistence ($0).
Swap to Neo4j Aura / Spanner Graph later by replacing the implementation
behind this same interface — a one-file port, not a rewrite.

Mitigations baked into v1:
  - Pin orchestrator to min_instances=1, max_instances=1 (no concurrent writers)
  - Cache serialized graph in GCS so cold-start load is < 1s
  - Wrap edge writes in Firestore transactions for safety

TODO Phase 4: implement.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

__version__ = "0.1.0"


@dataclass(frozen=True)
class GraphEdge:
    """A confirmed join between two columns."""
    from_dataset: str
    from_column: str
    to_dataset: str
    to_column: str
    approved_by: str
    approved_at: str  # ISO 8601
    similarity_score: float       # embedding-proposed score
    key_overlap_pct: float        # actual join-key overlap %


class GraphStore(Protocol):
    async def approve_edge(self, edge: GraphEdge) -> None: ...
    async def list_edges(self, dataset: str | None = None) -> list[GraphEdge]: ...
    async def find_path(self, from_dataset: str, to_dataset: str) -> list[GraphEdge] | None: ...
    async def neighbors(self, dataset: str) -> list[str]: ...
