"""Agent-led ingestion session tests (offline_mode, scripted interview)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api_gateway.app import datasets as ds_mod
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


def _ready_dataset_with_columns(ds_id: str, project_id: str | None = None) -> None:
    """Seed a ready dataset + a couple of column profiles directly in the offline store."""
    ds_mod.save_dataset(ds_mod.Dataset(
        id=ds_id, tenant_id="default", project_id=project_id, brand="nebula",
        label="txns", source_filename="txns.csv", source_size_bytes=10,
        gcs_blob_path="gs://b/txns.csv", status="ready",
        bq_table="p.raw.raw_x", row_count=2, column_count=2,
    ))
    ds_mod.save_column_profiles(ds_id, [
        ds_mod.ColumnProfile(name="city", type="STRING", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None,
                             key_likeness=0.2),
        ds_mod.ColumnProfile(name="total_revenue", type="NUMERIC", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None,
                             key_likeness=0.05),
    ])


class TestIngestSession:
    def test_start_requires_ready_dataset(self, client: TestClient) -> None:
        h = _auth_headers(client)
        # queued dataset → 409
        sid = client.post("/v1/uploads/start", headers=h,
                          json={"filename": "f.csv", "size_bytes": 1}).json()["dataset_id"]
        r = client.post("/v1/ingest/sessions", headers=h, json={"dataset_id": sid})
        assert r.status_code == 409

    def test_full_interview_creates_project_and_confirms_revenue(self, client: TestClient) -> None:
        h = _auth_headers(client)
        _ready_dataset_with_columns("dsabc")

        # start → first step is project_name (no project yet)
        start = client.post("/v1/ingest/sessions", headers=h, json={"dataset_id": "dsabc"})
        assert start.status_code == 200, start.text
        body = start.json()
        sid = body["session"]["id"]
        assert body["agent_message"]["step"] == "project_name"
        # draft already auto-classified total_revenue as a measure (unconfirmed revenue)
        sem = body["session"]["semantics"]
        assert sem["total_revenue"]["role"] == "measure"
        assert sem["total_revenue"]["is_revenue"] is True
        assert sem["total_revenue"]["confirmed_by"] is None  # GATE: not yet confirmed

        # reply project name → advances to grain
        r = client.post(f"/v1/ingest/sessions/{sid}/reply", headers=h, json={"answer": "Marriott India"})
        assert r.json()["agent_message"]["step"] == "grain"
        # the dataset is now attached to the new project
        proj_id = r.json()["session"]["project_id"]
        assert proj_id
        assert client.get("/v1/datasets/dsabc", headers=h).json()["project_id"] == proj_id

        # grain → draft_review
        r = client.post(f"/v1/ingest/sessions/{sid}/reply", headers=h,
                        json={"answer": "one transaction"})
        assert r.json()["agent_message"]["step"] == "draft_review"
        assert r.json()["agent_message"]["question_type"] == "draft_review"
        assert len(r.json()["agent_message"]["draft"]) == 2

        # accept the draft → confirm (no joins for a single dataset)
        r = client.post(f"/v1/ingest/sessions/{sid}/reply", headers=h, json={"answer": "looks good"})
        assert r.json()["agent_message"]["step"] == "confirm"

        # confirm → done + completion
        r = client.post(f"/v1/ingest/sessions/{sid}/reply", headers=h, json={"answer": "yes"})
        body = r.json()
        assert body["session"]["status"] == "completed"
        assert body["completion"]["columns_confirmed"] == 2
        assert body["completion"]["project_id"] == proj_id

        # semantics persisted onto the columns subcollection, revenue now CONFIRMED
        cols = {c["name"]: c for c in ds_mod.get_column_profiles("dsabc")}
        assert cols["total_revenue"]["role"] == "measure"
        assert cols["total_revenue"]["is_revenue"] is True
        assert cols["total_revenue"]["confirmed_by"] == "admin@insnav.local"

    def test_existing_project_skips_name_step(self, client: TestClient) -> None:
        h = _auth_headers(client)
        pid = client.post("/v1/projects", headers=h, json={"name": "Pre"}).json()["id"]
        _ready_dataset_with_columns("dsxyz", project_id=pid)
        start = client.post("/v1/ingest/sessions", headers=h, json={"dataset_id": "dsxyz"})
        assert start.json()["agent_message"]["step"] == "draft_review"

    def test_draft_review_structured_patch(self, client: TestClient) -> None:
        h = _auth_headers(client)
        pid = client.post("/v1/projects", headers=h, json={"name": "Pre"}).json()["id"]
        _ready_dataset_with_columns("dspatch", project_id=pid)
        sid = client.post("/v1/ingest/sessions", headers=h,
                          json={"dataset_id": "dspatch"}).json()["session"]["id"]
        # override: city becomes ignore, revenue keeps measure
        patch = [
            {"column": "city", "role": "ignore"},
            {"column": "total_revenue", "role": "measure", "is_revenue": True,
             "measure_aggregation": "sum"},
        ]
        r = client.post(f"/v1/ingest/sessions/{sid}/reply", headers=h,
                        json={"answer": "accept", "semantics_patch": patch})
        assert r.json()["session"]["semantics"]["city"]["role"] == "ignore"
        # then confirm
        r = client.post(f"/v1/ingest/sessions/{sid}/reply", headers=h, json={"answer": "yes"})
        cols = {c["name"]: c for c in ds_mod.get_column_profiles("dspatch")}
        assert cols["city"]["role"] == "ignore"

    def test_session_404_for_other_tenant(self, client: TestClient) -> None:
        r = client.get("/v1/ingest/sessions/nope", headers=_auth_headers(client))
        assert r.status_code == 404
