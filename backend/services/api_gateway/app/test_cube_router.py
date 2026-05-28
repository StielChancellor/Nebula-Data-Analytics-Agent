"""Cube router endpoint tests (offline mode)."""
import pytest
from fastapi.testclient import TestClient

from insnav_graph_store import GraphEdge, approve_edge, propose_edge, reset_offline_store

from services.api_gateway.app.datasets import (
    ColumnProfile,
    Dataset,
    _OFFLINE_COLUMNS,
    _OFFLINE_DATASETS,
    save_column_profiles,
    save_dataset,
)
from services.api_gateway.app.main import app


@pytest.fixture
def client(auth_env) -> TestClient:
    reset_offline_store()
    _OFFLINE_DATASETS.clear()
    _OFFLINE_COLUMNS.clear()
    yield TestClient(app)
    reset_offline_store()
    _OFFLINE_DATASETS.clear()
    _OFFLINE_COLUMNS.clear()


def _headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _make_ready_dataset(id_: str, label: str = "Sales") -> Dataset:
    ds = Dataset(
        id=id_,
        tenant_id="default",
        brand="nebula",
        label=label,
        source_filename=f"{label.lower()}.csv",
        source_size_bytes=1000,
        gcs_blob_path=f"gs://b/uploads/{id_}/x.csv",
        bq_table=f"proj.raw.raw_{id_}",
        status="ready",
    )
    save_dataset(ds)
    return ds


def _save_cols(dataset_id: str, columns: list[tuple[str, str, float]]) -> None:
    """columns is [(name, bq_type, key_likeness), ...]"""
    profiles = [
        ColumnProfile(
            name=name,
            type=bq_type,
            row_count=1000,
            null_count=0,
            null_pct=0.0,
            distinct_count=900 if kl > 0.5 else 5,
            min_value="a",
            max_value="z",
            key_likeness=kl,
        )
        for name, bq_type, kl in columns
    ]
    save_column_profiles(dataset_id, profiles)


class TestListSchemas:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get("/v1/cube/schemas").status_code == 401

    def test_empty_for_fresh_tenant(self, client: TestClient) -> None:
        r = client.get("/v1/cube/schemas", headers=_headers(client))
        assert r.status_code == 200
        assert r.json() == []

    def test_one_summary_per_ready_dataset(self, client: TestClient) -> None:
        ds = _make_ready_dataset("a" * 32, "Sales")
        _save_cols(ds.id, [("city", "STRING", 0.1), ("revenue", "FLOAT64", 0.0)])

        r = client.get("/v1/cube/schemas", headers=_headers(client))
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 1
        s = body[0]
        assert s["dataset_id"] == ds.id
        assert s["cube_name"].startswith("sales__")
        # dim count = 2 (city + revenue)
        assert s["dimension_count"] == 2
        # measure count = count + sum_revenue + avg_revenue = 3
        assert s["measure_count"] == 3
        assert s["revenue_touching"] is True

    def test_excludes_non_ready_datasets(self, client: TestClient) -> None:
        ds = _make_ready_dataset("b" * 32, "Loading")
        # flip to a non-ready state
        ds.status = "loading"
        save_dataset(ds)
        r = client.get("/v1/cube/schemas", headers=_headers(client))
        assert r.json() == []


class TestSchemaJSON:
    def test_returns_full_cube_schema(self, client: TestClient) -> None:
        ds = _make_ready_dataset("c" * 32, "Transactions")
        _save_cols(ds.id, [("gclid", "STRING", 0.95), ("amount", "FLOAT64", 0.0)])

        r = client.get(f"/v1/cube/schemas/{ds.id}/json", headers=_headers(client))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dataset_id"] == ds.id
        # gclid is high-key-likeness → primary key
        pk_dims = [d for d in body["dimensions"] if d["primary_key"]]
        assert len(pk_dims) == 1 and pk_dims[0]["name"] == "gclid"

    def test_404_for_unknown_dataset(self, client: TestClient) -> None:
        r = client.get(f"/v1/cube/schemas/{'z' * 32}/json", headers=_headers(client))
        assert r.status_code == 404

    def test_409_for_non_ready_dataset(self, client: TestClient) -> None:
        ds = _make_ready_dataset("d" * 32, "Pending")
        ds.status = "queued"
        save_dataset(ds)
        r = client.get(f"/v1/cube/schemas/{ds.id}/json", headers=_headers(client))
        assert r.status_code == 409


class TestSchemaJS:
    def test_returns_valid_cube_js(self, client: TestClient) -> None:
        ds = _make_ready_dataset("e" * 32, "Orders")
        _save_cols(ds.id, [("order_id", "STRING", 0.99), ("revenue", "FLOAT64", 0.0)])

        r = client.get(f"/v1/cube/schemas/{ds.id}.js", headers=_headers(client))
        assert r.status_code == 200, r.text
        assert "javascript" in r.headers["content-type"]
        text = r.text
        assert text.startswith("// Auto-generated")
        assert "cube(`orders__" in text
        assert "primary_key: true," in text  # order_id should get marked
        # has revenue measures + warning comment
        assert "sum_revenue" in text
        assert "revenue_touching" in text
        assert text.endswith("});\n")


class TestJoinsFromApprovedEdges:
    def test_approved_edge_becomes_join_in_both_cubes(self, client: TestClient) -> None:
        a = _make_ready_dataset("a" * 32, "Ads")
        b = _make_ready_dataset("b" * 32, "GA")
        _save_cols(a.id, [("gclid", "STRING", 0.95)])
        _save_cols(b.id, [("gclid", "STRING", 0.95)])

        # Approve an edge between them
        edge = propose_edge(GraphEdge(
            tenant_id="default",
            from_dataset=a.id, from_column="gclid",
            to_dataset=b.id, to_column="gclid",
            key_overlap_pct=0.9,
            from_distinct_count=900,
            to_distinct_count=900,
        ))
        approve_edge(edge.id, reviewer_email="admin@local")

        # Both schemas should now have one join
        ja = client.get(f"/v1/cube/schemas/{a.id}/json", headers=_headers(client)).json()
        jb = client.get(f"/v1/cube/schemas/{b.id}/json", headers=_headers(client)).json()
        assert len(ja["joins"]) == 1
        assert len(jb["joins"]) == 1
        # The join's to_cube must point at the OTHER dataset's cube name
        assert ja["joins"][0]["to_cube"] == jb["name"]
        assert jb["joins"][0]["to_cube"] == ja["name"]
        # Provenance is preserved
        assert ja["joins"][0]["from_edge_id"] == edge.id

    def test_proposed_edge_does_NOT_become_join(self, client: TestClient) -> None:
        """PRD § Hard constraint #2: only approved edges become joins."""
        a = _make_ready_dataset("a" * 32, "Ads")
        b = _make_ready_dataset("b" * 32, "GA")
        _save_cols(a.id, [("gclid", "STRING", 0.95)])
        _save_cols(b.id, [("gclid", "STRING", 0.95)])

        # Propose but DON'T approve
        propose_edge(GraphEdge(
            tenant_id="default",
            from_dataset=a.id, from_column="gclid",
            to_dataset=b.id, to_column="gclid",
            key_overlap_pct=0.9,
        ))

        sa = client.get(f"/v1/cube/schemas/{a.id}/json", headers=_headers(client)).json()
        assert sa["joins"] == []
