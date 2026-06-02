"""
insnav_graph_store — knowledge graph storage.

v1 implementation (PRD D10): NetworkX in-memory + Firestore persistence ($0).
Swap to Neo4j Aura / Spanner Graph later by replacing the implementation
behind this same interface — a one-file port, not a rewrite.

Why NetworkX + Firestore (vs Neo4j or Spanner Graph):
  - Cost: $0 (Firestore free tier covers thousands of edges; NetworkX is in
    process so no separate DB charges)
  - Real path queries (NetworkX has BFS / shortest_path)
  - Storage layer is hidden behind the GraphStore interface; can port to
    Neo4j in one file when we outgrow it (~50k edges or multi-instance
    write contention)

Mitigations baked in:
  - Pin orchestrator to min_instances=1 in v1 (no concurrent writers; see
    infra/terraform/main.tf::orchestrator)
  - Cache serialized graph in GCS for fast cold-start when we get there
  - Edge writes wrapped in Firestore transactions for safety
"""
from .models import EdgeState, GraphEdge
from .store import (
    GraphStore,
    approve_edge,
    delete_edge,
    delete_edges_for_dataset,
    list_approved_edges,
    list_proposed_edges,
    propose_edge,
    reject_edge,
    reset_offline_store,
)

__all__ = [
    "GraphEdge",
    "EdgeState",
    "GraphStore",
    "approve_edge",
    "reject_edge",
    "propose_edge",
    "delete_edge",
    "delete_edges_for_dataset",
    "list_approved_edges",
    "list_proposed_edges",
    "reset_offline_store",
]

__version__ = "0.2.0"
