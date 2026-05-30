"""
Dataset metadata model + Firestore CRUD.

PRD § L0 + §4.1: every uploaded file becomes a Dataset record tracked through
its lifecycle (queued → uploading → loading → profiling → ready / failed).

Firestore layout (Phase 2):
  /datasets/{dataset_id}     ← document with the fields below
    /columns/{column_name}   ← subcollection holding the schema catalog

Multi-tenancy (Phase 1.5+): partition by tenant_id either as a path prefix
(/tenants/{tenant_id}/datasets/{dataset_id}) or as a tenant_id field with
composite indexes. v1 stores tenant_id as a field; we'll restructure paths
when we have a second tenant.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

DatasetStatus = Literal[
    "queued",        # POST /v1/uploads/start has been called; awaiting client PUT to GCS
    "uploading",     # client is uploading (we infer this from upload session activity)
    "loading",       # POST /v1/uploads/complete called; BQ load job in flight
    "profiling",     # BQ load done; profile query running
    "ready",         # profile written; dataset is queryable
    "failed",        # any step failed; check `error` field
]


class ColumnProfile(BaseModel):
    """Per-column statistics emitted by the profiler. Lives in the columns subcollection."""

    model_config = ConfigDict(extra="forbid")

    name: str
    type: str                         # BQ type: STRING, INT64, FLOAT64, BOOL, DATE, TIMESTAMP, ...
    row_count: int
    null_count: int
    null_pct: float
    distinct_count: int | None        # only computed for low-cardinality columns
    min_value: str | None
    max_value: str | None
    sample_values: list[str] = Field(default_factory=list)
    key_likeness: float = 0.0         # 0..1, high = candidate join key (high cardinality + low null)


class Dataset(BaseModel):
    """The Firestore record describing an uploaded dataset."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    brand: str
    label: str                        # human-friendly name (defaults to original filename)
    locale_hint: Literal["US", "IN"] = "US"
    source_filename: str
    source_size_bytes: int
    gcs_blob_path: str                # gs://bucket/<path>  (the uploaded file)
    bq_table: str | None = None       # `project.dataset.table`  populated after load
    status: DatasetStatus = "queued"
    row_count: int | None = None
    column_count: int | None = None
    created_at: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat())
    error: str | None = None


# ---------- helpers ----------

_SAFE_TABLE_RE = re.compile(r"[^A-Za-z0-9_]")


def new_dataset_id() -> str:
    """Generate a new dataset id. uuid4 with dashes → underscores so it's BQ-table-safe."""
    return uuid4().hex   # 32 hex chars; no dashes; valid BQ table char range


def bq_table_name(dataset_id: str) -> str:
    """Sanitize and return the raw table name for this dataset."""
    safe = _SAFE_TABLE_RE.sub("_", dataset_id)
    if not safe or not (safe[0].isalpha() or safe[0] == "_"):
        safe = "raw_" + safe
    else:
        safe = "raw_" + safe
    return safe[:1024]  # BQ limit


def gcs_blob_path(dataset_id: str, original_filename: str) -> str:
    """Where the uploaded file lands in the staging bucket."""
    # Sanitize the filename to avoid weird chars in object names
    safe_fn = re.sub(r"[^A-Za-z0-9._-]", "_", original_filename)[:200]
    return f"uploads/{dataset_id}/{safe_fn}"


# ---------- Storage backend (Firestore in prod, in-memory in offline_mode) ----------
# offline_mode is set by tests + by anyone running without GCP credentials.
# Why in-memory: keeps the same function signatures so production code paths
# stay identical; the only switch is at the backend selection.

_OFFLINE_DATASETS: dict[str, dict[str, Any]] = {}
_OFFLINE_COLUMNS: dict[str, dict[str, dict[str, Any]]] = {}


def reset_offline_store() -> None:
    """Test helper — wipe the in-memory store between tests."""
    _OFFLINE_DATASETS.clear()
    _OFFLINE_COLUMNS.clear()


def _offline() -> bool:
    from services.api_gateway.app.settings import get_settings

    return get_settings().offline_mode


def save_dataset(d: Dataset) -> None:
    payload = d.model_dump()
    payload["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    if _offline():
        _OFFLINE_DATASETS[d.id] = payload
        return

    from services.api_gateway.app.gcp_clients import firestore_client
    from services.api_gateway.app.settings import get_settings

    col = firestore_client().collection(get_settings().fs_datasets_collection)
    col.document(d.id).set(payload, merge=True)


def get_dataset(dataset_id: str) -> Dataset | None:
    if _offline():
        data = _OFFLINE_DATASETS.get(dataset_id)
        return Dataset(**data) if data else None

    from services.api_gateway.app.gcp_clients import firestore_client
    from services.api_gateway.app.settings import get_settings

    doc = (
        firestore_client()
        .collection(get_settings().fs_datasets_collection)
        .document(dataset_id)
        .get()
    )
    if not doc.exists:
        return None
    return Dataset(**doc.to_dict())


def list_datasets_for_tenant(tenant_id: str) -> list[Dataset]:
    if _offline():
        return [
            Dataset(**d)
            for d in _OFFLINE_DATASETS.values()
            if d.get("tenant_id") == tenant_id
        ]

    from services.api_gateway.app.gcp_clients import firestore_client
    from services.api_gateway.app.settings import get_settings

    docs = (
        firestore_client()
        .collection(get_settings().fs_datasets_collection)
        .where(filter=("tenant_id", "==", tenant_id))
        .stream()
    )
    out: list[Dataset] = []
    for doc in docs:
        data = doc.to_dict()
        if data:
            out.append(Dataset(**data))
    return out


def list_all_ready_datasets() -> list[Dataset]:
    """All ready datasets across every tenant. Used by the cube_gen job to
    rebuild the full Cube model. Tenant-scoped reads use
    list_datasets_for_tenant() instead."""
    if _offline():
        return [Dataset(**d) for d in _OFFLINE_DATASETS.values() if d.get("status") == "ready"]

    from services.api_gateway.app.gcp_clients import firestore_client
    from services.api_gateway.app.settings import get_settings

    docs = (
        firestore_client()
        .collection(get_settings().fs_datasets_collection)
        .where(filter=("status", "==", "ready"))
        .stream()
    )
    out: list[Dataset] = []
    for doc in docs:
        data = doc.to_dict()
        if data:
            out.append(Dataset(**data))
    return out


def get_column_profiles(dataset_id: str) -> list[dict[str, Any]]:
    """Read a dataset's column profiles as plain dicts (for the Cube generator)."""
    if _offline():
        return list(_OFFLINE_COLUMNS.get(dataset_id, {}).values())

    from services.api_gateway.app.gcp_clients import firestore_client
    from services.api_gateway.app.settings import get_settings

    docs = (
        firestore_client()
        .collection(get_settings().fs_datasets_collection)
        .document(dataset_id)
        .collection("columns")
        .stream()
    )
    return [d.to_dict() or {} for d in docs]


def save_column_profiles(dataset_id: str, profiles: list[ColumnProfile]) -> None:
    if _offline():
        _OFFLINE_COLUMNS[dataset_id] = {p.name: p.model_dump() for p in profiles}
        return

    from services.api_gateway.app.gcp_clients import firestore_client
    from services.api_gateway.app.settings import get_settings

    fs = firestore_client()
    col = (
        fs.collection(get_settings().fs_datasets_collection)
        .document(dataset_id)
        .collection("columns")
    )
    batch = fs.batch()
    for p in profiles:
        batch.set(col.document(p.name), p.model_dump())
    batch.commit()


def update_dataset_status(
    dataset_id: str,
    status: DatasetStatus,
    *,
    bq_table: str | None = None,
    row_count: int | None = None,
    column_count: int | None = None,
    error: str | None = None,
) -> None:
    patch: dict[str, Any] = {
        "status": status,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if bq_table is not None:
        patch["bq_table"] = bq_table
    if row_count is not None:
        patch["row_count"] = row_count
    if column_count is not None:
        patch["column_count"] = column_count
    if error is not None:
        patch["error"] = error

    if _offline():
        existing = _OFFLINE_DATASETS.get(dataset_id)
        if existing is not None:
            existing.update(patch)
        return

    from services.api_gateway.app.gcp_clients import firestore_client
    from services.api_gateway.app.settings import get_settings

    (
        firestore_client()
        .collection(get_settings().fs_datasets_collection)
        .document(dataset_id)
        .set(patch, merge=True)
    )
