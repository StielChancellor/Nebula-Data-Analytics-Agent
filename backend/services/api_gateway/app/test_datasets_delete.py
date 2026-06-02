"""DELETE /v1/datasets/{id} full-cleanup tests (offline_mode)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import insnav_graph_store
from insnav_graph_store import GraphEdge
from services.api_gateway.app.main import app


@pytest.fixture
def client(auth_env) -> TestClient:
    return TestClient(app)


def _auth_headers(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/v1/auth/login",
        json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"},
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def _make_ready_dataset(client: TestClient, h: dict[str, str], project_id: str | None = None) -> str:
    body = {"filename": "sales.csv", "size_bytes": 1000}
    if project_id:
        body["project_id"] = project_id
    start = client.post("/v1/uploads/start", headers=h, json=body)
    ds_id = start.json()["dataset_id"]
    client.post("/v1/uploads/complete", headers=h, json={"dataset_id": ds_id})
    return ds_id


class TestDeleteDataset:
    def test_delete_removes_dataset(self, client: TestClient) -> None:
        h = _auth_headers(client)
        ds_id = _make_ready_dataset(client, h)
        r = client.delete(f"/v1/datasets/{ds_id}", headers=h)
        assert r.status_code == 200, r.text
        assert r.json()["deleted"] is True
        assert client.get(f"/v1/datasets/{ds_id}", headers=h).status_code == 404
        assert client.get("/v1/me/datasets", headers=h).json() == []

    def test_delete_is_idempotent(self, client: TestClient) -> None:
        h = _auth_headers(client)
        ds_id = _make_ready_dataset(client, h)
        assert client.delete(f"/v1/datasets/{ds_id}", headers=h).json()["deleted"] is True
        # second delete: gone already
        again = client.delete(f"/v1/datasets/{ds_id}", headers=h)
        assert again.status_code == 200
        assert again.json()["deleted"] is False

    def test_delete_removes_edges(self, client: TestClient) -> None:
        h = _auth_headers(client)
        ds_id = _make_ready_dataset(client, h)
        # seed an edge touching the dataset
        insnav_graph_store.propose_edge(
            GraphEdge(
                tenant_id="default",
                from_dataset=ds_id,
                from_column="id",
                to_dataset="other_ds",
                to_column="id",
            )
        )
        assert len(insnav_graph_store.list_proposed_edges("default")) == 1
        r = client.delete(f"/v1/datasets/{ds_id}", headers=h)
        assert r.json()["edges"] == 1
        assert insnav_graph_store.list_proposed_edges("default") == []

    def test_delete_detaches_from_project(self, client: TestClient) -> None:
        h = _auth_headers(client)
        pid = client.post("/v1/projects", headers=h, json={"name": "P"}).json()["id"]
        ds_id = _make_ready_dataset(client, h, project_id=pid)
        assert ds_id in client.get(f"/v1/projects/{pid}", headers=h).json()["dataset_ids"]
        client.delete(f"/v1/datasets/{ds_id}", headers=h)
        assert ds_id not in client.get(f"/v1/projects/{pid}", headers=h).json()["dataset_ids"]

    def test_cannot_delete_foreign_tenant_dataset(self, client: TestClient) -> None:
        from services.api_gateway.app.datasets import Dataset, save_dataset

        save_dataset(Dataset(
            id="foreign", tenant_id="other-tenant", brand="nebula",
            label="x", source_filename="x.csv", source_size_bytes=1,
            gcs_blob_path="gs://b/x", status="ready",
        ))
        r = client.delete("/v1/datasets/foreign", headers=_auth_headers(client))
        assert r.json()["deleted"] is False
