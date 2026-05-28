"""Graph store tests — offline mode (no GCP)."""
import os

import pytest

# Force offline mode for these tests
os.environ.setdefault("INSNAV_OFFLINE", "true")

from insnav_graph_store import (
    GraphEdge,
    approve_edge,
    list_approved_edges,
    list_proposed_edges,
    propose_edge,
    reject_edge,
    reset_offline_store,
)
from insnav_graph_store.store import find_path, neighbors


@pytest.fixture(autouse=True)
def _clean():
    # Clear settings cache so INSNAV_OFFLINE picks up
    from services.api_gateway.app.settings import get_settings

    get_settings.cache_clear()
    reset_offline_store()
    yield
    reset_offline_store()


def _make(from_ds: str, from_col: str, to_ds: str, to_col: str, *, tenant: str = "t1", **kw) -> GraphEdge:
    return GraphEdge(
        tenant_id=tenant,
        from_dataset=from_ds,
        from_column=from_col,
        to_dataset=to_ds,
        to_column=to_col,
        **kw,
    )


class TestPropose:
    def test_persists_in_proposed_state(self) -> None:
        e = propose_edge(_make("google_ads", "gclid", "ga4", "gclid"))
        assert e.state == "proposed"
        proposed = list_proposed_edges("t1")
        assert len(proposed) == 1
        assert proposed[0].id == e.id

    def test_idempotent_directionless(self) -> None:
        """Proposing (A.x ↔ B.y) then (B.y ↔ A.x) does NOT duplicate."""
        first = propose_edge(_make("google_ads", "gclid", "ga4", "gclid"))
        second = propose_edge(_make("ga4", "gclid", "google_ads", "gclid"))
        assert second.id == first.id
        assert len(list_proposed_edges("t1")) == 1


class TestStateTransitions:
    def test_approve_moves_to_approved_with_reviewer(self) -> None:
        e = propose_edge(_make("ga4", "transaction_id", "site", "txn_id"))
        approved = approve_edge(e.id, reviewer_email="admin@local")
        assert approved.state == "approved"
        assert approved.reviewed_by == "admin@local"
        assert approved.reviewed_at is not None

        # No longer in proposed
        assert list_proposed_edges("t1") == []
        assert len(list_approved_edges("t1")) == 1

    def test_reject_moves_to_rejected_and_does_not_re_propose(self) -> None:
        e = propose_edge(_make("a", "x", "b", "y"))
        rejected = reject_edge(e.id, reviewer_email="admin@local")
        assert rejected.state == "rejected"

        # Re-proposing the same pair should not create a new edge or
        # un-reject the existing one — admin's decision is sticky.
        same = propose_edge(_make("b", "y", "a", "x"))
        assert same.id == e.id
        assert same.state == "rejected"   # still rejected

    def test_approve_unknown_edge_raises(self) -> None:
        with pytest.raises(KeyError):
            approve_edge("does-not-exist", reviewer_email="admin@local")


class TestTenantIsolation:
    def test_tenant_b_does_not_see_tenant_a_edges(self) -> None:
        propose_edge(_make("a", "x", "b", "y", tenant="alice"))
        propose_edge(_make("a", "x", "b", "y", tenant="bob"))

        assert len(list_proposed_edges("alice")) == 1
        assert len(list_proposed_edges("bob")) == 1
        # Idempotency is also scoped to tenant — same edge under different
        # tenants is allowed (different orgs may have overlapping data).


class TestPathQueries:
    def test_find_path_single_hop(self) -> None:
        e = propose_edge(_make("a", "x", "b", "y"))
        approve_edge(e.id, reviewer_email="admin@local")

        path = find_path("t1", "a", "b")
        assert path is not None
        assert len(path) == 1
        assert path[0].id == e.id

    def test_find_path_two_hop(self) -> None:
        """a — b — c via two approved edges"""
        e1 = propose_edge(_make("a", "x", "b", "y"))
        e2 = propose_edge(_make("b", "y", "c", "z"))
        approve_edge(e1.id, reviewer_email="admin@local")
        approve_edge(e2.id, reviewer_email="admin@local")

        path = find_path("t1", "a", "c")
        assert path is not None
        assert len(path) == 2

    def test_find_path_returns_none_when_no_approved_path(self) -> None:
        # Only PROPOSED, not approved — must not count toward path
        propose_edge(_make("a", "x", "b", "y"))
        assert find_path("t1", "a", "b") is None

    def test_neighbors_returns_directly_connected_datasets(self) -> None:
        e1 = propose_edge(_make("a", "x", "b", "y"))
        e2 = propose_edge(_make("a", "x", "c", "z"))
        approve_edge(e1.id, reviewer_email="admin@local")
        approve_edge(e2.id, reviewer_email="admin@local")

        assert neighbors("t1", "a") == ["b", "c"]
        assert neighbors("t1", "b") == ["a"]
