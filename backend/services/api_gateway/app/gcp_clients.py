"""
Lazy singleton GCP clients.

Why lazy: importing this module shouldn't trigger network calls or require
GCP credentials. Tests and CI without ADC must still be able to import the
api_gateway. Each accessor creates its client on first call and caches it.

Why singletons: GCP client objects are thread-safe and pool connections.
Recreating them per-request defeats the pooling.
"""
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.cloud import bigquery, firestore, storage


@lru_cache(maxsize=1)
def storage_client() -> "storage.Client":
    from google.cloud import storage  # local import keeps module-import cheap

    from services.api_gateway.app.settings import get_settings

    return storage.Client(project=get_settings().gcp_project)


@lru_cache(maxsize=1)
def bigquery_client() -> "bigquery.Client":
    from google.cloud import bigquery

    from services.api_gateway.app.settings import get_settings

    return bigquery.Client(project=get_settings().gcp_project)


@lru_cache(maxsize=1)
def firestore_client() -> "firestore.Client":
    from google.cloud import firestore

    from services.api_gateway.app.settings import get_settings

    return firestore.Client(project=get_settings().gcp_project)


def reset_clients_for_tests() -> None:
    """Test helper — clears the singletons so monkeypatched env vars take effect."""
    storage_client.cache_clear()
    bigquery_client.cache_clear()
    firestore_client.cache_clear()
