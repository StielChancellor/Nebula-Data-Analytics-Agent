"""Pivot endpoint tests (offline cube stub)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api_gateway.app import datasets as ds_mod
from services.api_gateway.app.main import app


@pytest.fixture
def client(auth_env) -> TestClient:
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    r = client.post("/v1/auth/login",
                    json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed_project_with_dataset(client: TestClient, h: dict[str, str]) -> str:
    pid = client.post("/v1/projects", headers=h, json={"name": "Pivot"}).json()["id"]
    ds_mod.save_dataset(ds_mod.Dataset(
        id="pds", tenant_id="default", project_id=pid, brand="nebula",
        label="sales", source_filename="s.csv", source_size_bytes=10,
        gcs_blob_path="gs://b/s.csv", status="ready", bq_table="p.raw.raw_pds",
        row_count=2, column_count=2,
    ))
    ds_mod.save_column_profiles("pds", [
        ds_mod.ColumnProfile(name="city", type="STRING", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.2),
        ds_mod.ColumnProfile(name="revenue", type="NUMERIC", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.05),
    ])
    return pid


class TestPivot:
    def test_fields_lists_measures_and_dimensions(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed_project_with_dataset(client, h)
        fields = client.get(f"/v1/pivot/fields?project_id={pid}", headers=h).json()
        names = {m["name"] for m in fields["measures"]}
        dims = {d["name"] for d in fields["dimensions"]}
        assert any(n.endswith(".sum_revenue") for n in names)
        assert any(d.endswith(".city") for d in dims)

    def test_query_returns_rows(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed_project_with_dataset(client, h)
        fields = client.get(f"/v1/pivot/fields?project_id={pid}", headers=h).json()
        measure = next(m["name"] for m in fields["measures"] if m["name"].endswith(".sum_revenue"))
        dim = next(d["name"] for d in fields["dimensions"] if d["name"].endswith(".city"))
        r = client.post("/v1/pivot/query", headers=h,
                        json={"project_id": pid, "measures": [measure], "dimensions": [dim]})
        assert r.status_code == 200, r.text
        body = r.json()
        assert dim in body["columns"] and measure in body["columns"]
        assert len(body["rows"]) >= 1

    def test_unknown_field_rejected(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed_project_with_dataset(client, h)
        r = client.post("/v1/pivot/query", headers=h,
                        json={"project_id": pid, "measures": ["ghost.sum_x"]})
        assert r.status_code == 400

    def test_empty_selection_rejected(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed_project_with_dataset(client, h)
        r = client.post("/v1/pivot/query", headers=h, json={"project_id": pid})
        assert r.status_code == 400

    def test_foreign_project_404(self, client: TestClient) -> None:
        r = client.get("/v1/pivot/fields?project_id=nope", headers=_auth(client))
        assert r.status_code == 404
