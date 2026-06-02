"""Phase 11 differentiator tests — lineage, metric registry, notebook export (offline)."""
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


def _seed(client: TestClient, h: dict[str, str]) -> str:
    pid = client.post("/v1/projects", headers=h, json={"name": "Phase11"}).json()["id"]
    ds_mod.save_dataset(ds_mod.Dataset(
        id="p11ds", tenant_id="default", project_id=pid, brand="nebula",
        label="sales", source_filename="s.csv", source_size_bytes=10,
        gcs_blob_path="gs://b/s.csv", status="ready", bq_table="proj.raw.raw_p11ds",
        row_count=2, column_count=2,
    ))
    ds_mod.save_column_profiles("p11ds", [
        ds_mod.ColumnProfile(name="city", type="STRING", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.2),
        ds_mod.ColumnProfile(name="revenue", type="NUMERIC", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.05),
    ])
    return pid


def _measure(client: TestClient, h: dict[str, str], pid: str) -> str:
    fields = client.get(f"/v1/pivot/fields?project_id={pid}", headers=h).json()
    return next(m["name"] for m in fields["measures"] if m["name"].endswith(".sum_revenue"))


class TestMetricRegistry:
    def test_lists_measures_with_provenance(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        reg = client.get(f"/v1/metrics?project_id={pid}", headers=h).json()
        rev = next(m for m in reg["metrics"] if m["name"].endswith(".sum_revenue"))
        assert rev["aggregation"] == "sum"
        assert rev["dataset_label"] == "sales"
        assert rev["definition_sql"] and "revenue" in rev["definition_sql"]
        assert rev["owner"] is None  # not yet human-confirmed

    def test_owner_surfaces_after_confirmation(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        ds_mod.save_column_semantics("p11ds", {
            "revenue": {"role": "measure", "is_revenue": True,
                        "confirmed_by": "admin@insnav.local", "confirmed_at": "2026-01-01T00:00:00Z"},
        })
        reg = client.get(f"/v1/metrics?project_id={pid}", headers=h).json()
        rev = next(m for m in reg["metrics"] if m["name"].endswith(".sum_revenue"))
        assert rev["owner"] == "admin@insnav.local"
        assert rev["effective_at"] == "2026-01-01T00:00:00Z"

    def test_foreign_project_404(self, client: TestClient) -> None:
        assert client.get("/v1/metrics?project_id=nope", headers=_auth(client)).status_code == 404


class TestLineage:
    def test_traces_measure_to_source_column(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        field = _measure(client, h, pid)
        trace = client.get(f"/v1/lineage?project_id={pid}&field={field}", headers=h).json()
        assert trace["kind"] == "measure"
        assert trace["aggregation"] == "sum"
        assert trace["bq_table"] == "proj.raw.raw_p11ds"
        cols = {c["column"] for c in trace["source_columns"]}
        assert "revenue" in cols

    def test_confirmed_semantics_surface_in_lineage(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        ds_mod.save_column_semantics("p11ds", {
            "revenue": {"role": "measure", "business_meaning": "net booking value",
                        "confirmed_by": "admin@insnav.local", "confirmed_at": "2026-01-01T00:00:00Z"},
        })
        field = _measure(client, h, pid)
        trace = client.get(f"/v1/lineage?project_id={pid}&field={field}", headers=h).json()
        src = next(c for c in trace["source_columns"] if c["column"] == "revenue")
        assert src["business_meaning"] == "net booking value"
        assert src["confirmed_by"] == "admin@insnav.local"

    def test_unknown_field_404(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        assert client.get(f"/v1/lineage?project_id={pid}&field=ghost.x", headers=h).status_code == 404

    def test_foreign_project_404(self, client: TestClient) -> None:
        assert client.get("/v1/lineage?project_id=nope&field=a.b", headers=_auth(client)).status_code == 404


class TestCostEstimate:
    def test_small_query_under_threshold(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        field = _measure(client, h, pid)
        r = client.post("/v1/pivot/estimate", headers=h,
                        json={"project_id": pid, "measures": [field]})
        assert r.status_code == 200, r.text
        est = r.json()
        assert est["exceeds_threshold"] is False
        assert est["estimated_bytes"] >= 0
        assert est["per_cube"] and est["per_cube"][0]["referenced_columns"] == ["revenue"]

    def test_large_dataset_exceeds_threshold(self, client: TestClient) -> None:
        h = _auth(client)
        pid = client.post("/v1/projects", headers=h, json={"name": "Big"}).json()["id"]
        ds_mod.save_dataset(ds_mod.Dataset(
            id="bigds", tenant_id="default", project_id=pid, brand="nebula",
            label="big", source_filename="b.csv", source_size_bytes=10,
            gcs_blob_path="gs://b/b.csv", status="ready", bq_table="proj.raw.raw_bigds",
            row_count=1_000_000_000, column_count=2,
        ))
        ds_mod.save_column_profiles("bigds", [
            ds_mod.ColumnProfile(name="city", type="STRING", row_count=1, null_count=0,
                                 null_pct=0.0, distinct_count=1, min_value=None, max_value=None, key_likeness=0.2),
            ds_mod.ColumnProfile(name="revenue", type="NUMERIC", row_count=1, null_count=0,
                                 null_pct=0.0, distinct_count=1, min_value=None, max_value=None, key_likeness=0.05),
        ])
        field = next(
            m["name"]
            for m in client.get(f"/v1/pivot/fields?project_id={pid}", headers=h).json()["measures"]
            if m["name"].endswith(".sum_revenue")
        )
        est = client.post("/v1/pivot/estimate", headers=h,
                          json={"project_id": pid, "measures": [field]}).json()
        assert est["exceeds_threshold"] is True
        assert est["estimated_gb"] > 5.0

    def test_unknown_field_400(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        r = client.post("/v1/pivot/estimate", headers=h,
                        json={"project_id": pid, "measures": ["ghost.x"]})
        assert r.status_code == 400


class TestNotebookExport:
    def test_exports_valid_ipynb(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        field = _measure(client, h, pid)
        dim = next(
            d["name"]
            for d in client.get(f"/v1/pivot/fields?project_id={pid}", headers=h).json()["dimensions"]
            if d["name"].endswith(".city")
        )
        r = client.post("/v1/notebook", headers=h, json={
            "project_id": pid, "title": "My export", "measures": [field], "dimensions": [dim],
        })
        assert r.status_code == 200, r.text
        nb = r.json()
        assert nb["nbformat"] == 4
        assert nb["metadata"]["insnav"]["project_id"] == pid
        srcs = "".join("".join(c["source"]) for c in nb["cells"])
        assert "CUBE_QUERY" in srcs and "My export" in srcs

    def test_unknown_field_400(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        r = client.post("/v1/notebook", headers=h, json={"project_id": pid, "measures": ["ghost.x"]})
        assert r.status_code == 400

    def test_foreign_project_404(self, client: TestClient) -> None:
        r = client.post("/v1/notebook", headers=_auth(client), json={"project_id": "nope", "measures": []})
        assert r.status_code == 404
