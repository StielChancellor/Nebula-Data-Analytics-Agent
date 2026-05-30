"""Cube model sync: endpoint, approve-hook, and cube_gen job (offline)."""
import pytest
from fastapi.testclient import TestClient

from insnav_cube_client import read_offline_model, reset_offline_model
from insnav_graph_store import GraphEdge, propose_edge, reset_offline_store

from services.api_gateway.app.cube_sync_service import sync_all_tenants
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
    reset_offline_model()
    _OFFLINE_DATASETS.clear()
    _OFFLINE_COLUMNS.clear()
    yield TestClient(app)
    reset_offline_store()
    reset_offline_model()
    _OFFLINE_DATASETS.clear()
    _OFFLINE_COLUMNS.clear()


def _headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ready_dataset(id_: str, label: str, tenant: str = "default") -> Dataset:
    ds = Dataset(
        id=id_, tenant_id=tenant, brand="nebula", label=label,
        source_filename=f"{label}.csv", source_size_bytes=1000,
        gcs_blob_path=f"gs://b/uploads/{id_}/x.csv",
        bq_table=f"proj.raw.raw_{id_}", status="ready",
    )
    save_dataset(ds)
    return ds


def _cols(dataset_id: str, specs: list[tuple[str, str, float]]) -> None:
    save_column_profiles(dataset_id, [
        ColumnProfile(name=n, type=t, row_count=1000, null_count=0, null_pct=0.0,
                       distinct_count=900 if kl > 0.5 else 5, min_value="a", max_value="z",
                       key_likeness=kl)
        for n, t, kl in specs
    ])


class TestSyncEndpoint:
    def test_requires_auth(self, client: TestClient) -> None:
        assert client.post("/v1/cube/sync").status_code == 401

    def test_sync_publishes_model(self, client: TestClient) -> None:
        ds = _ready_dataset("a" * 32, "Sales")
        _cols(ds.id, [("city", "STRING", 0.1), ("revenue", "FLOAT64", 0.0)])

        r = client.post("/v1/cube/sync", headers=_headers(client))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tenant_id"] == "default"
        assert body["file_count"] == 1
        assert body["cube_names"][0].startswith("sales__")
        assert len(body["version"]) == 64

        # The offline model store now holds the published model
        model = read_offline_model("default")
        assert model["version"] == body["version"]


class TestApproveTriggersSync:
    def test_approving_edge_republishes_model_with_join(self, client: TestClient) -> None:
        a = _ready_dataset("a" * 32, "Ads")
        b = _ready_dataset("b" * 32, "GA")
        _cols(a.id, [("gclid", "STRING", 0.95)])
        _cols(b.id, [("gclid", "STRING", 0.95)])

        # Publish baseline (no joins)
        before = client.post("/v1/cube/sync", headers=_headers(client)).json()["version"]

        # Propose + approve an edge → approve hook should re-sync
        edge = propose_edge(GraphEdge(
            tenant_id="default", from_dataset=a.id, from_column="gclid",
            to_dataset=b.id, to_column="gclid", key_overlap_pct=0.9,
            from_distinct_count=900, to_distinct_count=900,
        ))
        r = client.post(f"/v1/edges/{edge.id}/approve", headers=_headers(client))
        assert r.status_code == 200, r.text

        # Model version changed because the join was added
        after = read_offline_model("default")["version"]
        assert after != before


class TestCubeGenJob:
    def test_sync_all_tenants_covers_every_tenant(self, client: TestClient) -> None:
        _ready_dataset("a" * 32, "Alice DS", tenant="alice")
        _cols("a" * 32, [("revenue", "FLOAT64", 0.0)])
        _ready_dataset("b" * 32, "Bob DS", tenant="bob")
        _cols("b" * 32, [("spend", "FLOAT64", 0.0)])

        results = sync_all_tenants()
        assert set(results.keys()) == {"alice", "bob"}
        assert results["alice"]["file_count"] == 1
        assert results["bob"]["file_count"] == 1
        # Each tenant's model is isolated in the offline store
        assert read_offline_model("alice")["version"] != read_offline_model("bob")["version"]
