"""Smoke + auth tests for the api_gateway."""
import pytest
from fastapi.testclient import TestClient

from services.api_gateway.app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Set bootstrap admin env so /v1/auth/login can succeed in tests."""
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@insnav.local")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "TESTING-do-not-use-in-prod-123")
    monkeypatch.setenv("INSNAV_JWT_SECRET", "x" * 40)  # >= 32 bytes
    return TestClient(app)


def test_healthz_returns_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "api_gateway"


def test_brand_returns_nebula_by_default(client: TestClient) -> None:
    r = client.get("/v1/me/brand")
    assert r.status_code == 200
    body = r.json()
    assert body["brandId"] == "nebula"
    assert body["tokens"]["accent"] == "0 217 192"  # Aurora teal


def test_openapi_v1_served(client: TestClient) -> None:
    r = client.get("/v1/openapi.json")
    assert r.status_code == 200
    assert r.json()["info"]["title"].startswith("Insights Navigator")


def test_events_schema_skeleton(client: TestClient) -> None:
    r = client.get("/v1/events-schema.json")
    assert r.status_code == 200
    assert r.json()["title"].startswith("Insights Navigator")


# --- Auth ---

class TestAuth:
    def test_login_succeeds_with_bootstrap_creds(self, client: TestClient) -> None:
        r = client.post(
            "/v1/auth/login",
            json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] > 0

    def test_login_fails_with_wrong_password(self, client: TestClient) -> None:
        r = client.post(
            "/v1/auth/login",
            json={"email": "admin@insnav.local", "password": "wrong"},
        )
        assert r.status_code == 401
        # Avoid leaking which of email/password was wrong
        assert "invalid email or password" in r.json()["detail"]

    def test_login_fails_with_unknown_user(self, client: TestClient) -> None:
        r = client.post(
            "/v1/auth/login",
            json={"email": "nobody@insnav.local", "password": "whatever"},
        )
        assert r.status_code == 401

    def test_me_requires_token(self, client: TestClient) -> None:
        r = client.get("/v1/auth/me")
        assert r.status_code == 401

    def test_me_returns_principal_when_authed(self, client: TestClient) -> None:
        login = client.post(
            "/v1/auth/login",
            json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"},
        )
        token = login.json()["access_token"]

        r = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "admin@insnav.local"
        assert body["tenant_id"] == "default"
        assert body["brand"] == "nebula"
        assert "admin" in body["roles"]

    def test_me_rejects_garbage_token(self, client: TestClient) -> None:
        r = client.get("/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
        assert r.status_code == 401

    def test_datasets_requires_auth(self, client: TestClient) -> None:
        r = client.get("/v1/me/datasets")
        assert r.status_code == 401

    def test_datasets_works_with_token(self, client: TestClient) -> None:
        login = client.post(
            "/v1/auth/login",
            json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"},
        )
        token = login.json()["access_token"]
        r = client.get("/v1/me/datasets", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        assert r.json() == []  # empty in Phase 0/1


class TestBootstrapNotConfigured:
    def test_login_returns_401_when_bootstrap_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BOOTSTRAP_ADMIN_EMAIL", raising=False)
        monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
        monkeypatch.setenv("INSNAV_JWT_SECRET", "x" * 40)
        no_bootstrap_client = TestClient(app)
        r = no_bootstrap_client.post(
            "/v1/auth/login",
            json={"email": "anyone@example.com", "password": "anything"},
        )
        assert r.status_code == 401
