"""End-to-end upload flow tests (offline_mode: no real GCP)."""
import pytest
from fastapi.testclient import TestClient

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


class TestStartUpload:
    def test_returns_dataset_id_and_signed_url(self, client: TestClient) -> None:
        r = client.post(
            "/v1/uploads/start",
            headers=_auth_headers(client),
            json={"filename": "sales.csv", "size_bytes": 1_000_000},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "dataset_id" in body
        assert body["signed_url"].startswith("https://")
        assert "uploads/" in body["gcs_blob_path"]
        assert body["gcs_blob_path"].endswith("sales.csv")

    def test_binds_resumable_session_to_caller_origin(self, client: TestClient) -> None:
        """The browser PUTs cross-origin to GCS; the resumable session must be
        bound to the caller's Origin or GCS omits Access-Control-Allow-Origin on
        the PUT and the browser blocks the upload. Regression guard for that
        wiring (only reproducible against a live GCS resumable session)."""
        from unittest.mock import patch

        origin = "https://brand-x.example.app"
        with patch(
            "services.api_gateway.app.uploads._create_resumable_upload_url",
            return_value=("https://example.invalid/u", "2099-01-01T00:00:00+00:00"),
        ) as m:
            r = client.post(
                "/v1/uploads/start",
                headers={**_auth_headers(client), "Origin": origin},
                json={"filename": "sales.csv", "size_bytes": 1000},
            )
        assert r.status_code == 200, r.text
        assert m.call_args.kwargs["origin"] == origin

    def test_requires_auth(self, client: TestClient) -> None:
        r = client.post("/v1/uploads/start", json={"filename": "x.csv", "size_bytes": 10})
        assert r.status_code == 401

    def test_rejects_files_over_size_cap(self, client: TestClient) -> None:
        r = client.post(
            "/v1/uploads/start",
            headers=_auth_headers(client),
            json={"filename": "huge.csv", "size_bytes": 10 * 1024 * 1024 * 1024},  # 10 GB
        )
        assert r.status_code == 413

    def test_supports_5gb_files(self, client: TestClient) -> None:
        """Confirms the 5 GB target from PRD requirement."""
        r = client.post(
            "/v1/uploads/start",
            headers=_auth_headers(client),
            json={"filename": "big.csv", "size_bytes": 5 * 1024 * 1024 * 1024},
        )
        assert r.status_code == 200

    def test_persists_dataset_in_queued_state(self, client: TestClient) -> None:
        start = client.post(
            "/v1/uploads/start",
            headers=_auth_headers(client),
            json={"filename": "sales.csv", "size_bytes": 1000, "locale_hint": "IN"},
        )
        ds_id = start.json()["dataset_id"]

        listing = client.get("/v1/me/datasets", headers=_auth_headers(client))
        assert listing.status_code == 200
        rows = listing.json()
        assert len(rows) == 1
        assert rows[0]["id"] == ds_id
        assert rows[0]["status"] == "queued"
        assert rows[0]["locale_hint"] == "IN"
        assert rows[0]["label"] == "sales.csv"

    def test_upload_into_project_associates_and_inherits_locale(self, client: TestClient) -> None:
        h = _auth_headers(client)
        pid = client.post(
            "/v1/projects", headers=h, json={"name": "Marriott", "locale_default": "IN"}
        ).json()["id"]
        start = client.post(
            "/v1/uploads/start",
            headers=h,
            json={"filename": "txns.csv", "size_bytes": 1000, "project_id": pid},
        )
        assert start.status_code == 200, start.text
        ds_id = start.json()["dataset_id"]
        # dataset carries project_id + inherited IN locale (no explicit locale_hint given)
        ds = client.get(f"/v1/datasets/{ds_id}", headers=h).json()
        assert ds["project_id"] == pid
        assert ds["locale_hint"] == "IN"
        # project now lists the dataset
        proj = client.get(f"/v1/projects/{pid}", headers=h).json()
        assert ds_id in proj["dataset_ids"]

    def test_upload_into_unknown_project_404s(self, client: TestClient) -> None:
        r = client.post(
            "/v1/uploads/start",
            headers=_auth_headers(client),
            json={"filename": "x.csv", "size_bytes": 10, "project_id": "nope"},
        )
        assert r.status_code == 404


class TestCompleteUpload:
    def test_runs_load_then_profile_then_marks_ready(self, client: TestClient) -> None:
        start = client.post(
            "/v1/uploads/start",
            headers=_auth_headers(client),
            json={"filename": "sales.csv", "size_bytes": 1000},
        )
        ds_id = start.json()["dataset_id"]

        complete = client.post(
            "/v1/uploads/complete",
            headers=_auth_headers(client),
            json={"dataset_id": ds_id},
        )
        assert complete.status_code == 200, complete.text
        body = complete.json()
        assert body["status"] == "ready"
        assert body["bq_table"] is not None
        assert body["column_count"] == 2  # synthetic schema from offline stub

    def test_unknown_dataset_returns_404(self, client: TestClient) -> None:
        r = client.post(
            "/v1/uploads/complete",
            headers=_auth_headers(client),
            json={"dataset_id": "deadbeef" * 4},
        )
        assert r.status_code == 404

    def test_other_tenant_cannot_complete(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """A dataset created by tenant A is invisible/uncompletable by tenant B."""
        start = client.post(
            "/v1/uploads/start",
            headers=_auth_headers(client),
            json={"filename": "x.csv", "size_bytes": 10},
        )
        ds_id = start.json()["dataset_id"]

        # Switch bootstrap admin to a different tenant
        monkeypatch.setenv("BOOTSTRAP_ADMIN_TENANT", "other-tenant")
        login = client.post(
            "/v1/auth/login",
            json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"},
        )
        other_token = login.json()["access_token"]
        r = client.post(
            "/v1/uploads/complete",
            headers={"Authorization": f"Bearer {other_token}"},
            json={"dataset_id": ds_id},
        )
        assert r.status_code == 404


class TestDatasetDetail:
    def test_get_dataset_returns_full_record(self, client: TestClient) -> None:
        start = client.post(
            "/v1/uploads/start",
            headers=_auth_headers(client),
            json={"filename": "sales.csv", "size_bytes": 1000},
        )
        ds_id = start.json()["dataset_id"]

        r = client.get(f"/v1/datasets/{ds_id}", headers=_auth_headers(client))
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == ds_id
        assert body["tenant_id"] == "default"
        assert body["status"] == "queued"

    def test_get_dataset_404_for_missing(self, client: TestClient) -> None:
        r = client.get(
            "/v1/datasets/" + ("a" * 32),
            headers=_auth_headers(client),
        )
        assert r.status_code == 404
