"""
Shared pytest fixtures for the api_gateway service tests.

- `offline_env`: turns on INSNAV_OFFLINE so Firestore/GCS/BQ calls short-circuit
  to in-memory stubs. Auto-applied to every test in this directory.
- `auth_env`: bootstrap admin creds + JWT secret so /v1/auth/login works.
"""
from __future__ import annotations

import pytest

from services.api_gateway.app import datasets, settings


@pytest.fixture(autouse=True)
def offline_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INSNAV_OFFLINE", "true")
    settings.get_settings.cache_clear()
    datasets.reset_offline_store()
    yield
    settings.get_settings.cache_clear()
    datasets.reset_offline_store()


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@insnav.local")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "TESTING-do-not-use-in-prod-123")
    monkeypatch.setenv("INSNAV_JWT_SECRET", "x" * 40)
    yield
