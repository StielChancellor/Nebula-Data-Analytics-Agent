"""Edge proposer tests — offline mode + synthetic profiles."""
import pytest

from insnav_graph_store import list_proposed_edges, reset_offline_store

from services.api_gateway.app.datasets import (
    ColumnProfile,
    Dataset,
    _OFFLINE_COLUMNS,
    _OFFLINE_DATASETS,
    save_column_profiles,
    save_dataset,
    update_dataset_status,
)
from services.api_gateway.app.edge_proposer import (
    KEY_LIKENESS_MIN,
    build_overlap_sql,
    propose_for_dataset,
)


@pytest.fixture(autouse=True)
def _clean():
    reset_offline_store()
    _OFFLINE_DATASETS.clear()
    _OFFLINE_COLUMNS.clear()
    yield
    reset_offline_store()
    _OFFLINE_DATASETS.clear()
    _OFFLINE_COLUMNS.clear()


def _make_dataset(dataset_id: str, tenant: str = "t1") -> Dataset:
    ds = Dataset(
        id=dataset_id,
        tenant_id=tenant,
        brand="nebula",
        label=f"label-{dataset_id}",
        source_filename=f"{dataset_id}.csv",
        source_size_bytes=1000,
        gcs_blob_path=f"gs://b/uploads/{dataset_id}/x.csv",
        status="ready",
        bq_table=f"proj.raw.raw_{dataset_id}",
    )
    save_dataset(ds)
    update_dataset_status(dataset_id, "ready", bq_table=ds.bq_table)
    return ds


def _save_profiles(dataset_id: str, columns: list[tuple[str, float]]) -> None:
    """columns is [(column_name, key_likeness), ...]"""
    profiles = [
        ColumnProfile(
            name=name,
            type="STRING",
            row_count=1000,
            null_count=0,
            null_pct=0.0,
            distinct_count=900 if kl > 0.5 else 5,
            min_value="a",
            max_value="z",
            key_likeness=kl,
        )
        for name, kl in columns
    ]
    save_column_profiles(dataset_id, profiles)


class TestBuildOverlapSQL:
    def test_returns_a_single_select(self) -> None:
        sql = build_overlap_sql("p.r.a", "gclid", "p.r.b", "gclid")
        assert "overlap_pct" in sql
        assert "from_distinct" in sql
        assert "to_distinct" in sql
        assert "ARRAY(SELECT v FROM shared LIMIT 5) AS samples" in sql

    def test_uses_safe_divide_to_avoid_div_by_zero(self) -> None:
        sql = build_overlap_sql("p.r.a", "x", "p.r.b", "y")
        assert "SAFE_DIVIDE" in sql

    def test_casts_to_string_for_cross_type_join(self) -> None:
        sql = build_overlap_sql("p.r.a", "txn_id", "p.r.b", "transaction_id")
        # both sides cast — int↔string foreign-key relationships still work
        assert "CAST(`txn_id` AS STRING)" in sql
        assert "CAST(`transaction_id` AS STRING)" in sql


class TestProposeForDataset:
    def test_no_proposals_when_no_peers(self) -> None:
        ds = _make_dataset("solo")
        _save_profiles("solo", [("gclid", 0.95), ("status", 0.05)])
        proposals = propose_for_dataset(ds)
        assert proposals == []

    def test_proposes_between_high_key_likeness_columns(self) -> None:
        # Two datasets, both with a high-key-likeness "gclid" column
        a = _make_dataset("a")
        b = _make_dataset("b")
        _save_profiles("a", [("gclid", 0.95), ("country", 0.10)])
        _save_profiles("b", [("gclid", 0.90), ("category", 0.08)])

        proposals = propose_for_dataset(a)
        # gclid↔gclid is the only high-key pair → exactly one proposal
        assert len(proposals) == 1
        e = proposals[0]
        assert e.state == "proposed"
        assert {e.from_column, e.to_column} == {"gclid"}
        # offline stub returns 0.85 overlap
        assert e.key_overlap_pct == 0.85
        # And it's now in list_proposed_edges
        assert len(list_proposed_edges("t1")) == 1

    def test_ignores_low_key_likeness_columns(self) -> None:
        a = _make_dataset("a")
        b = _make_dataset("b")
        # All columns below threshold
        _save_profiles("a", [("status", 0.05), ("country", 0.10)])
        _save_profiles("b", [("status", 0.06), ("region", 0.12)])

        proposals = propose_for_dataset(a)
        assert proposals == []

    def test_idempotent_on_repeated_discovery(self) -> None:
        """Running propose_for_dataset twice doesn't duplicate proposals."""
        a = _make_dataset("a")
        b = _make_dataset("b")
        _save_profiles("a", [("gclid", 0.95)])
        _save_profiles("b", [("gclid", 0.90)])

        first = propose_for_dataset(a)
        second = propose_for_dataset(a)
        assert len(first) == 1
        assert len(second) == 1
        assert first[0].id == second[0].id
        assert len(list_proposed_edges("t1")) == 1

    def test_respects_tenant_isolation(self) -> None:
        a = _make_dataset("a", tenant="alice")
        b = _make_dataset("b", tenant="bob")
        _save_profiles("a", [("gclid", 0.95)])
        _save_profiles("b", [("gclid", 0.95)])

        # Alice's discovery should NOT join across to Bob's datasets
        proposals = propose_for_dataset(a)
        assert proposals == []
        assert list_proposed_edges("alice") == []
        assert list_proposed_edges("bob") == []

    def test_threshold_is_at_documented_constant(self) -> None:
        # Sanity — make sure we didn't typo the threshold somewhere
        assert KEY_LIKENESS_MIN == 0.7
