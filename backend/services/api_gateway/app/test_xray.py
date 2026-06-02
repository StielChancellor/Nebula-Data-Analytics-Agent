"""X-ray proactive insights tests (Phase 12, offline)."""
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
    pid = client.post("/v1/projects", headers=h, json={"name": "Xray"}).json()["id"]
    ds_mod.save_dataset(ds_mod.Dataset(
        id="xrds", tenant_id="default", project_id=pid, brand="nebula",
        label="sales", source_filename="s.csv", source_size_bytes=10,
        gcs_blob_path="gs://b/s.csv", status="ready", bq_table="p.raw.raw_xrds",
        row_count=2, column_count=2,
    ))
    ds_mod.save_column_profiles("xrds", [
        ds_mod.ColumnProfile(name="city", type="STRING", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.2),
        ds_mod.ColumnProfile(name="revenue", type="NUMERIC", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.05),
    ])
    return pid


class TestXray:
    def test_suggest_returns_tiles(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        tiles = client.post("/v1/xray/suggest", headers=h, json={"project_id": pid}).json()
        assert len(tiles) >= 2
        # A KPI total and a by-city breakdown should both be present.
        assert any(t["spec"].get("chart_type") == "kpi" for t in tiles)
        assert any(t["spec"].get("dimensions") and t["spec"]["dimensions"][0].endswith(".city") for t in tiles)
        for t in tiles:
            assert t["title"] and t["rationale"]

    def test_caps_tile_count(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        tiles = client.post("/v1/xray/suggest", headers=h, json={"project_id": pid}).json()
        assert len(tiles) <= 8

    def test_creates_starter_dashboard(self, client: TestClient) -> None:
        h = _auth(client)
        pid = _seed(client, h)
        out = client.post("/v1/xray/dashboard", headers=h,
                          json={"project_id": pid, "name": "Auto"}).json()
        assert out["tile_count"] >= 2
        # The dashboard is real + runnable.
        run = client.post(f"/v1/dashboards/{out['dashboard_id']}/run", headers=h, json={})
        assert run.status_code == 200
        assert run.json()["name"] == "Auto"

    def test_foreign_project_404(self, client: TestClient) -> None:
        assert client.post("/v1/xray/suggest", headers=_auth(client),
                           json={"project_id": "nope"}).status_code == 404
