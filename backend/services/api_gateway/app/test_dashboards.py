"""Dashboard CRUD + tiles + run + share tests (offline cube stub)."""
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


def _seed(client: TestClient, h: dict[str, str]) -> tuple[str, str, str]:
    pid = client.post("/v1/projects", headers=h, json={"name": "Dash"}).json()["id"]
    ds_mod.save_dataset(ds_mod.Dataset(
        id="dds", tenant_id="default", project_id=pid, brand="nebula", label="sales",
        source_filename="s.csv", source_size_bytes=10, gcs_blob_path="gs://b/s.csv",
        status="ready", bq_table="p.raw.raw_dds", row_count=2, column_count=2,
    ))
    ds_mod.save_column_profiles("dds", [
        ds_mod.ColumnProfile(name="city", type="STRING", row_count=2, null_count=0, null_pct=0.0,
                             distinct_count=2, min_value=None, max_value=None, key_likeness=0.2),
        ds_mod.ColumnProfile(name="revenue", type="NUMERIC", row_count=2, null_count=0, null_pct=0.0,
                             distinct_count=2, min_value=None, max_value=None, key_likeness=0.05),
    ])
    fields = client.get(f"/v1/pivot/fields?project_id={pid}", headers=h).json()
    measure = next(m["name"] for m in fields["measures"] if m["name"].endswith(".sum_revenue"))
    dim = next(d["name"] for d in fields["dimensions"] if d["name"].endswith(".city"))
    return pid, measure, dim


class TestDashboards:
    def test_create_pin_run_share_flow(self, client: TestClient) -> None:
        h = _auth(client)
        pid, measure, dim = _seed(client, h)

        # create
        d = client.post("/v1/dashboards", headers=h, json={"project_id": pid, "name": "Sales"}).json()
        did = d["id"]
        assert client.get(f"/v1/dashboards?project_id={pid}", headers=h).json()[0]["id"] == did

        # pin a tile
        d = client.post(f"/v1/dashboards/{did}/tiles", headers=h, json={
            "title": "Revenue by city",
            "spec": {"measures": [measure], "dimensions": [dim], "chart_type": "bar"},
        }).json()
        assert len(d["tiles"]) == 1
        tile_id = d["tiles"][0]["id"]

        # run → tile returns stub rows
        run = client.post(f"/v1/dashboards/{did}/run", headers=h).json()
        assert run["tiles"][0]["title"] == "Revenue by city"
        assert len(run["tiles"][0]["rows"]) >= 1
        assert run["tiles"][0]["error"] is None

        # share → public view (no auth)
        shared = client.post(f"/v1/dashboards/{did}/share", headers=h).json()
        token = shared["share_token"]
        assert token
        pub = TestClient(app).get(f"/v1/public/dashboards/{token}")  # no auth header
        assert pub.status_code == 200
        assert pub.json()["tiles"][0]["title"] == "Revenue by city"

        # remove tile + delete
        d = client.delete(f"/v1/dashboards/{did}/tiles/{tile_id}", headers=h).json()
        assert d["tiles"] == []
        assert client.delete(f"/v1/dashboards/{did}", headers=h).status_code == 204

    def test_public_unknown_token_404(self, client: TestClient) -> None:
        assert client.get("/v1/public/dashboards/nope").status_code == 404

    def test_foreign_dashboard_404(self, client: TestClient) -> None:
        from services.api_gateway.app import dashboards as dmod
        dmod.save_dashboard(dmod.Dashboard(id="foreign", tenant_id="other", project_id="p", name="x"))
        assert client.get("/v1/dashboards/foreign", headers=_auth(client)).status_code == 404
