"""
Shared pytest fixtures for the api_gateway service tests.

- `offline_env`: turns on INSNAV_OFFLINE so Firestore/GCS/BQ calls short-circuit
  to in-memory stubs. Auto-applied to every test in this directory.
- `auth_env`: bootstrap admin creds + JWT secret so /v1/auth/login works.
"""
from __future__ import annotations

import pytest

from services.api_gateway.app import datasets, projects, settings


def _reset_all_offline_stores() -> None:
    """Wipe every in-memory store so tests are isolated (Phase 10 added more)."""
    datasets.reset_offline_store()
    projects.reset_offline_store()
    try:
        from services.api_gateway.app import ingest_router

        ingest_router.reset_offline_store()
    except Exception:  # noqa: BLE001
        pass
    # Cross-package stores (edges, cube model) — reset if importable.
    try:
        import insnav_graph_store

        insnav_graph_store.reset_offline_store()
    except Exception:  # noqa: BLE001 — package not on path in some unit suites
        pass
    try:
        from insnav_cube_client import sync as _cube_sync

        _cube_sync.reset_offline_model()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture(autouse=True)
def offline_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("INSNAV_OFFLINE", "true")
    settings.get_settings.cache_clear()
    _reset_all_offline_stores()
    yield
    settings.get_settings.cache_clear()
    _reset_all_offline_stores()


@pytest.fixture
def auth_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@insnav.local")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "TESTING-do-not-use-in-prod-123")
    monkeypatch.setenv("INSNAV_JWT_SECRET", "x" * 40)
    yield
