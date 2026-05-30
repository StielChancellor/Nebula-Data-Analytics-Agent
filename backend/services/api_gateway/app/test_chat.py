"""Chat endpoint tests — fake LLM router + offline Cube (no live deps)."""
import json

import pytest
from fastapi.testclient import TestClient

from insnav_cube_client import cube_name_for_dataset
from insnav_llm_router import LLMRouter
from insnav_llm_router.router import LLMResponse

from services.api_gateway.app import chat_router as chat_mod
from services.api_gateway.app.datasets import (
    ColumnProfile,
    Dataset,
    _OFFLINE_COLUMNS,
    _OFFLINE_DATASETS,
    save_column_profiles,
    save_dataset,
)
from services.api_gateway.app.main import app

DS_ID = "a" * 32
CUBE = cube_name_for_dataset(DS_ID, "Sales")


@pytest.fixture
def client(auth_env, monkeypatch):
    _OFFLINE_DATASETS.clear()
    _OFFLINE_COLUMNS.clear()
    chat_mod.reset_chat_cache()
    # Seed a ready dataset + profiles
    save_dataset(Dataset(
        id=DS_ID, tenant_id="default", brand="nebula", label="Sales",
        source_filename="sales.csv", source_size_bytes=1000,
        gcs_blob_path="gs://b/x", bq_table="p.raw.raw_x", status="ready", row_count=1000,
    ))
    save_column_profiles(DS_ID, [
        ColumnProfile(name="city", type="STRING", row_count=1000, null_count=0,
                       null_pct=0.0, distinct_count=20, min_value="a", max_value="z", key_likeness=0.2),
        ColumnProfile(name="revenue", type="FLOAT64", row_count=1000, null_count=0,
                       null_pct=0.0, distinct_count=900, min_value="0", max_value="9", key_likeness=0.0),
    ])
    yield TestClient(app)
    _OFFLINE_DATASETS.clear()
    _OFFLINE_COLUMNS.clear()
    chat_mod.reset_chat_cache()


def _headers(client):
    r = client.post("/v1/auth/login",
                    json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _patch_llm(monkeypatch, payload: dict):
    class _P:
        name = "stub"; model = "fake"
        async def generate(self, *, prompt, system=None, max_tokens=16384):
            return LLMResponse(text=json.dumps(payload), model="fake", provider="stub")
    # The endpoint calls build_router(req.llm); make any choice yield our fake.
    monkeypatch.setattr(chat_mod, "build_router", lambda _model_id: LLMRouter(_P()))


def _good(payload_overrides=None):
    p = {
        "measures": [f"{CUBE}.sum_revenue"], "dimensions": [f"{CUBE}.city"],
        "filters": [], "order": {f"{CUBE}.sum_revenue": "desc"},
        "plain_english": "Total revenue by city.", "analysis_level": "descriptive",
        "confidence": 0.9,
    }
    if payload_overrides:
        p.update(payload_overrides)
    return p


def test_chat_requires_auth(client):
    assert client.post("/v1/chat", json={"question": "x"}).status_code == 401


def test_chat_happy_path(client, monkeypatch):
    _patch_llm(monkeypatch, _good())
    r = client.post("/v1/chat", headers=_headers(client), json={"question": "revenue by city"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "answer"
    assert body["interpretation_echo"] == "Total revenue by city."
    assert body["cube_query"]["measures"] == [f"{CUBE}.sum_revenue"]
    assert body["data_health"]["status"] == "ok"
    assert len(body["rows"]) == 2  # offline stub
    # Cube isn't deployed in tests → illustrative caveat present
    assert any("illustrative" in c for c in body["caveats"])


def test_chat_hallucination_clarifies(client, monkeypatch):
    _patch_llm(monkeypatch, _good({"measures": [f"{CUBE}.profit"]}))
    r = client.post("/v1/chat", headers=_headers(client), json={"question": "profit?"})
    assert r.json()["kind"] == "clarify"


def test_chat_caches_identical_question(client, monkeypatch):
    _patch_llm(monkeypatch, _good())
    h = _headers(client)
    a = client.post("/v1/chat", headers=h, json={"question": "revenue by city"}).json()
    # Swap the LLM to something that would clarify — but the cache should serve
    # the original answer, proving determinism.
    _patch_llm(monkeypatch, _good({"confidence": 0.0}))
    b = client.post("/v1/chat", headers=h, json={"question": "revenue by city"}).json()
    assert a["inputs_hash"] == b["inputs_hash"]
    assert b["kind"] == "answer"


def test_llm_options_lists_models(client):
    r = client.get("/v1/llm/options", headers=_headers(client))
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()]
    assert "gemini-3.0-preview" in ids
    assert "stub" in ids
    # stub is always available; exactly one default
    by_id = {m["id"]: m for m in r.json()}
    assert by_id["stub"]["available"] is True
    assert by_id["gemini-3.0-preview"]["default"] is True


def test_llm_options_requires_auth(client):
    assert client.get("/v1/llm/options").status_code == 401


def test_chat_no_datasets_refuses(client, monkeypatch):
    _OFFLINE_DATASETS.clear()  # remove the seeded dataset
    _OFFLINE_COLUMNS.clear()
    chat_mod.reset_chat_cache()
    _patch_llm(monkeypatch, _good())
    r = client.post("/v1/chat", headers=_headers(client), json={"question": "anything"})
    assert r.json()["kind"] == "refuse"
