"""
GraphStore — the storage interface.

Phase 4 implementation: in-memory + Firestore (`graph_edges` collection).
Offline mode (set by tests) uses an in-process dict.

NetworkX integration: the read-side helpers (`find_path`, `neighbors`) build
a NetworkX graph from approved edges on demand. For v1's expected scale
(< 5k edges/tenant), rebuilding per query is cheap (<10 ms). Once we cross
1k edges/sec query rate, swap to a process-cached graph with a Firestore
listener invalidating on edge writes — Phase 6+.
"""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any, Protocol

from .models import EdgeState, GraphEdge

if TYPE_CHECKING:
    import networkx as nx


# ---------- Storage backend ----------

_OFFLINE_EDGES: dict[str, dict[str, Any]] = {}


def reset_offline_store() -> None:
    _OFFLINE_EDGES.clear()


def _offline() -> bool:
    # Import here to avoid a hard dep cycle; settings live in api_gateway.
    try:
        from services.api_gateway.app.settings import get_settings

        return get_settings().offline_mode
    except Exception:
        return False


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


# ---------- Public API (module-level, like other insnav packages) ----------

def propose_edge(edge: GraphEdge) -> GraphEdge:
    """
    Persist a new proposed edge. If a directionless-equivalent edge already
    exists (regardless of state), this is a no-op — we never propose the
    same pair twice, and we don't undo an admin's approve/reject decision.
    """
    existing = _find_directionless(edge.tenant_id, edge.directionless_key())
    if existing is not None:
        return existing  # idempotent

    edge.state = "proposed"
    edge.updated_at = _now()
    _save(edge)
    return edge


def approve_edge(edge_id: str, *, reviewer_email: str) -> GraphEdge:
    edge = _get(edge_id)
    if edge is None:
        raise KeyError(edge_id)
    edge.state = "approved"
    edge.reviewed_by = reviewer_email
    edge.reviewed_at = _now()
    edge.updated_at = edge.reviewed_at
    _save(edge)
    return edge


def reject_edge(edge_id: str, *, reviewer_email: str) -> GraphEdge:
    edge = _get(edge_id)
    if edge is None:
        raise KeyError(edge_id)
    edge.state = "rejected"
    edge.reviewed_by = reviewer_email
    edge.reviewed_at = _now()
    edge.updated_at = edge.reviewed_at
    _save(edge)
    return edge


def list_approved_edges(tenant_id: str) -> list[GraphEdge]:
    return _list_by_state(tenant_id, "approved")


def list_proposed_edges(tenant_id: str) -> list[GraphEdge]:
    return _list_by_state(tenant_id, "proposed")


def get_edge(edge_id: str) -> GraphEdge | None:
    return _get(edge_id)


# ---------- Path queries (NetworkX on the approved-edges subgraph) ----------

class GraphStore(Protocol):
    """Interface for any future graph backend swap (Neo4j, Spanner Graph)."""
    def propose_edge(self, edge: GraphEdge) -> GraphEdge: ...
    def approve_edge(self, edge_id: str, *, reviewer_email: str) -> GraphEdge: ...
    def reject_edge(self, edge_id: str, *, reviewer_email: str) -> GraphEdge: ...
    def list_approved_edges(self, tenant_id: str) -> list[GraphEdge]: ...
    def list_proposed_edges(self, tenant_id: str) -> list[GraphEdge]: ...
    def find_path(self, tenant_id: str, from_dataset: str, to_dataset: str) -> list[GraphEdge] | None: ...


def find_path(tenant_id: str, from_dataset: str, to_dataset: str) -> list[GraphEdge] | None:
    """
    Find a path of confirmed edges connecting two datasets, or None if there
    is no such path. Used by the Cube generator (Phase 5) and the agent
    swarm's multi-dataset query resolver (Phase 10).
    """
    import networkx as nx

    edges = list_approved_edges(tenant_id)
    if not edges:
        return None
    g: nx.Graph = nx.Graph()
    edge_lookup: dict[tuple[str, str], GraphEdge] = {}
    for e in edges:
        g.add_edge(e.from_dataset, e.to_dataset)
        edge_lookup[(e.from_dataset, e.to_dataset)] = e
        edge_lookup[(e.to_dataset, e.from_dataset)] = e
    try:
        nodes = nx.shortest_path(g, from_dataset, to_dataset)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    return [edge_lookup[(a, b)] for a, b in zip(nodes, nodes[1:])]


def neighbors(tenant_id: str, dataset: str) -> list[str]:
    """Direct neighbors of `dataset` in the approved-edges graph."""
    edges = list_approved_edges(tenant_id)
    out: set[str] = set()
    for e in edges:
        if e.from_dataset == dataset:
            out.add(e.to_dataset)
        elif e.to_dataset == dataset:
            out.add(e.from_dataset)
    return sorted(out)


# ---------- Internal: storage primitives ----------

_FS_COLLECTION = "graph_edges"


def _save(edge: GraphEdge) -> None:
    payload = edge.model_dump()
    if _offline():
        _OFFLINE_EDGES[edge.id] = payload
        return

    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_FS_COLLECTION).document(edge.id).set(payload, merge=False)


def _get(edge_id: str) -> GraphEdge | None:
    if _offline():
        data = _OFFLINE_EDGES.get(edge_id)
        return GraphEdge(**data) if data else None

    from services.api_gateway.app.gcp_clients import firestore_client

    doc = firestore_client().collection(_FS_COLLECTION).document(edge_id).get()
    if not doc.exists:
        return None
    return GraphEdge(**doc.to_dict())


def _list_by_state(tenant_id: str, state: EdgeState) -> list[GraphEdge]:
    if _offline():
        return [
            GraphEdge(**d)
            for d in _OFFLINE_EDGES.values()
            if d.get("tenant_id") == tenant_id and d.get("state") == state
        ]

    from google.cloud.firestore_v1.base_query import FieldFilter

    from services.api_gateway.app.gcp_clients import firestore_client

    docs = (
        firestore_client()
        .collection(_FS_COLLECTION)
        .where(filter=FieldFilter("tenant_id", "==", tenant_id))
        .where(filter=FieldFilter("state", "==", state))
        .stream()
    )
    out: list[GraphEdge] = []
    for d in docs:
        data = d.to_dict()
        if data:
            out.append(GraphEdge(**data))
    return out


def _find_directionless(tenant_id: str, key: tuple[str, str, str, str]) -> GraphEdge | None:
    """Linear scan; fine at v1 scale (<5k edges/tenant)."""
    if _offline():
        for data in _OFFLINE_EDGES.values():
            if data.get("tenant_id") != tenant_id:
                continue
            e = GraphEdge(**data)
            if e.directionless_key() == key:
                return e
        return None

    # Firestore: pull all edges for the tenant and scan in-process
    from google.cloud.firestore_v1.base_query import FieldFilter

    from services.api_gateway.app.gcp_clients import firestore_client

    docs = (
        firestore_client()
        .collection(_FS_COLLECTION)
        .where(filter=FieldFilter("tenant_id", "==", tenant_id))
        .stream()
    )
    for d in docs:
        data = d.to_dict()
        if data:
            e = GraphEdge(**data)
            if e.directionless_key() == key:
                return e
    return None
