"""Smoke tests for the api_gateway. Run: pytest services/api_gateway"""
from fastapi.testclient import TestClient

from services.api_gateway.app.main import app

client = TestClient(app)


def test_healthz_returns_ok() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "api_gateway"


def test_brand_returns_nebula_by_default() -> None:
    r = client.get("/v1/me/brand")
    assert r.status_code == 200
    body = r.json()
    assert body["brandId"] == "nebula"
    assert "tokens" in body
    assert body["tokens"]["accent"] == "0 217 192"  # Aurora teal


def test_datasets_empty_in_phase_0() -> None:
    r = client.get("/v1/me/datasets")
    assert r.status_code == 200
    assert r.json() == []


def test_openapi_v1_served() -> None:
    r = client.get("/v1/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert body["info"]["title"].startswith("Insights Navigator")


def test_events_schema_skeleton() -> None:
    r = client.get("/v1/events-schema.json")
    assert r.status_code == 200
    body = r.json()
    assert body["title"].startswith("Insights Navigator")
