"""Project workspace CRUD tests (offline_mode)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api_gateway.app import projects
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


class TestProjectsCrud:
    def test_create_sets_owner_and_draft(self, client: TestClient) -> None:
        r = client.post(
            "/v1/projects",
            headers=_auth_headers(client),
            json={"name": "Marriott India", "locale_default": "IN"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["name"] == "Marriott India"
        assert body["locale_default"] == "IN"
        assert body["status"] == "draft"
        assert body["owner_email"] == "admin@insnav.local"
        assert body["members"] == [{"email": "admin@insnav.local", "role": "owner"}]
        assert body["dataset_ids"] == []

    def test_list_returns_created(self, client: TestClient) -> None:
        h = _auth_headers(client)
        client.post("/v1/projects", headers=h, json={"name": "P1"})
        client.post("/v1/projects", headers=h, json={"name": "P2"})
        r = client.get("/v1/projects", headers=h)
        assert r.status_code == 200
        names = {p["name"] for p in r.json()}
        assert names == {"P1", "P2"}

    def test_get_and_patch(self, client: TestClient) -> None:
        h = _auth_headers(client)
        pid = client.post("/v1/projects", headers=h, json={"name": "P"}).json()["id"]
        r = client.patch(
            f"/v1/projects/{pid}", headers=h, json={"name": "Renamed", "status": "active"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "Renamed"
        assert r.json()["status"] == "active"
        got = client.get(f"/v1/projects/{pid}", headers=h)
        assert got.json()["name"] == "Renamed"

    def test_delete_empty_project(self, client: TestClient) -> None:
        h = _auth_headers(client)
        pid = client.post("/v1/projects", headers=h, json={"name": "Doomed"}).json()["id"]
        r = client.delete(f"/v1/projects/{pid}", headers=h)
        assert r.status_code == 204
        assert client.get(f"/v1/projects/{pid}", headers=h).status_code == 404
        # idempotent
        assert client.delete(f"/v1/projects/{pid}", headers=h).status_code == 204

    def test_requires_auth(self, client: TestClient) -> None:
        assert client.get("/v1/projects").status_code == 401
        assert client.post("/v1/projects", json={"name": "x"}).status_code == 401

    def test_tenant_isolation(self, client: TestClient) -> None:
        # A project owned by a different tenant must be invisible (404).
        other = projects.Project(
            id="otherproj", tenant_id="other-tenant", brand="nebula",
            name="Secret", owner_email="x@y.z",
        )
        projects.save_project(other)
        r = client.get("/v1/projects/otherproj", headers=_auth_headers(client))
        assert r.status_code == 404
        # and it doesn't show in this tenant's list
        listed = client.get("/v1/projects", headers=_auth_headers(client)).json()
        assert all(p["id"] != "otherproj" for p in listed)
