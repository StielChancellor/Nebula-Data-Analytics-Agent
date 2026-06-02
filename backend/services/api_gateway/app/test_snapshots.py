"""Snapshot diff + assumption-check tests — pure logic + router (offline)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api_gateway.app import datasets as ds_mod
from services.api_gateway.app.main import app
from services.api_gateway.app.snapshots import diff_snapshots, evaluate_assumptions


# ---------- pure diff ----------

class TestDiff:
    def test_added_removed_changed(self) -> None:
        spec = {"dimensions": ["c.city"], "measures": ["c.rev"]}
        a = (["c.city", "c.rev"], [["Mumbai", 100], ["Pune", 50]])
        b = (["c.city", "c.rev"], [["Mumbai", 120], ["Delhi", 30]])
        d = diff_snapshots(spec, a[0], a[1], b[0], b[1])
        assert d["added"] == [["Delhi"]]
        assert d["removed"] == [["Pune"]]
        assert len(d["changed"]) == 1
        ch = d["changed"][0]
        assert ch["key"] == ["Mumbai"]
        assert ch["deltas"]["c.rev"]["delta"] == 20
        assert ch["deltas"]["c.rev"]["pct"] == pytest.approx(20.0)

    def test_no_change_when_identical(self) -> None:
        spec = {"dimensions": ["c.city"], "measures": ["c.rev"]}
        rows = [["Mumbai", 100]]
        d = diff_snapshots(spec, ["c.city", "c.rev"], rows, ["c.city", "c.rev"], [list(r) for r in rows])
        assert d["summary"] == {"added": 0, "removed": 0, "changed": 0}

    def test_kpi_single_row_diff(self) -> None:
        spec = {"dimensions": [], "measures": ["c.total"]}
        d = diff_snapshots(spec, ["c.total"], [[100]], ["c.total"], [[150]])
        assert d["changed"][0]["deltas"]["c.total"]["delta"] == 50


# ---------- pure assumptions ----------

class TestAssumptions:
    def test_empty_warns(self) -> None:
        w = evaluate_assumptions({"measures": ["m"]}, ["m"], [])
        assert w[0]["code"] == "empty" and w[0]["level"] == "warn"

    def test_small_sample_info(self) -> None:
        w = evaluate_assumptions({"measures": ["m"]}, ["m"], [[1], [2], [3]])
        assert any(x["code"] == "small_sample" for x in w)

    def test_recent_anomaly_flagged(self) -> None:
        cols = ["c.t", "c.m"]
        rows = [[i, 10] for i in range(19)] + [[19, 200]]
        spec = {"measures": ["c.m"], "time_dimension": "c.t"}
        w = evaluate_assumptions(spec, cols, rows)
        assert any(x["code"] == "recent_anomaly" and x["level"] == "warn" for x in w)


# ---------- router ----------

@pytest.fixture
def client(auth_env) -> TestClient:
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    r = client.post("/v1/auth/login",
                    json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _seed(client: TestClient, h: dict[str, str]) -> tuple[str, str]:
    pid = client.post("/v1/projects", headers=h, json={"name": "Snaps"}).json()["id"]
    ds_mod.save_dataset(ds_mod.Dataset(
        id="snds", tenant_id="default", project_id=pid, brand="nebula",
        label="sales", source_filename="s.csv", source_size_bytes=10,
        gcs_blob_path="gs://b/s.csv", status="ready", bq_table="p.raw.raw_snds",
        row_count=2, column_count=2,
    ))
    ds_mod.save_column_profiles("snds", [
        ds_mod.ColumnProfile(name="city", type="STRING", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.2),
        ds_mod.ColumnProfile(name="revenue", type="NUMERIC", row_count=2, null_count=0,
                             null_pct=0.0, distinct_count=2, min_value=None, max_value=None, key_likeness=0.05),
    ])
    measure = next(
        m["name"]
        for m in client.get(f"/v1/pivot/fields?project_id={pid}", headers=h).json()["measures"]
        if m["name"].endswith(".sum_revenue")
    )
    return pid, measure


class TestSnapshotRouter:
    def test_capture_list_get_delete(self, client: TestClient) -> None:
        h = _auth(client)
        pid, measure = _seed(client, h)
        snap = client.post("/v1/snapshots", headers=h, json={
            "project_id": pid, "label": "today", "spec": {"measures": [measure]},
        }).json()
        assert snap["label"] == "today"
        metas = client.get(f"/v1/snapshots?project_id={pid}", headers=h).json()
        assert any(m["id"] == snap["id"] for m in metas)
        assert client.get(f"/v1/snapshots/{snap['id']}", headers=h).status_code == 200
        assert client.delete(f"/v1/snapshots/{snap['id']}", headers=h).status_code == 204

    def test_diff_two_snapshots(self, client: TestClient) -> None:
        h = _auth(client)
        pid, measure = _seed(client, h)
        spec = {"measures": [measure]}
        a = client.post("/v1/snapshots", headers=h, json={"project_id": pid, "spec": spec}).json()
        b = client.post("/v1/snapshots", headers=h, json={"project_id": pid, "spec": spec}).json()
        r = client.post("/v1/snapshots/diff", headers=h, json={"a": a["id"], "b": b["id"]})
        assert r.status_code == 200, r.text
        assert "diff" in r.json() and "summary" in r.json()["diff"]

    def test_assumptions_check(self, client: TestClient) -> None:
        h = _auth(client)
        pid, measure = _seed(client, h)
        r = client.post("/v1/assumptions/check", headers=h,
                        json={"project_id": pid, "spec": {"measures": [measure]}})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "warnings" in body and "ok" in body

    def test_foreign_project_404(self, client: TestClient) -> None:
        r = client.post("/v1/snapshots", headers=_auth(client),
                        json={"project_id": "nope", "spec": {"measures": []}})
        assert r.status_code == 404


class TestFirestoreRowsSerialization:
    """Regression: Firestore rejects nested arrays (list-of-lists), so captured
    rows must be JSON-serialized on write and parsed back on read."""

    def test_rows_roundtrip_via_fake_firestore(self, monkeypatch) -> None:
        from services.api_gateway.app import gcp_clients
        from services.api_gateway.app import snapshots as snap_mod

        class _Doc:
            def __init__(self, store, key):
                self.store, self.key = store, key

            def set(self, payload):
                self.store[self.key] = payload

            def get(self):
                d = self.store.get(self.key)
                return type("M", (), {"exists": d is not None, "to_dict": lambda self=None, d=d: d})()

        class _Col:
            def __init__(self, store):
                self.store = store

            def document(self, key):
                return _Doc(self.store, key)

        class _Fs:
            def __init__(self):
                self.store = {}

            def collection(self, _name):
                return _Col(self.store)

        fake = _Fs()
        monkeypatch.setattr(snap_mod, "_offline", lambda: False)
        monkeypatch.setattr(gcp_clients, "firestore_client", lambda: fake)

        s = snap_mod.Snapshot(tenant_id="t", project_id="p", spec={"measures": ["m"]},
                              columns=["a", "b"], rows=[["x", 1], ["y", 2]])
        snap_mod.save_snapshot(s)
        # Stored as a JSON string (Firestore-safe), not a raw nested array.
        assert isinstance(fake.store[s.id]["rows"], str)
        got = snap_mod.get_snapshot(s.id)
        assert got is not None and got.rows == [["x", 1], ["y", 2]]
