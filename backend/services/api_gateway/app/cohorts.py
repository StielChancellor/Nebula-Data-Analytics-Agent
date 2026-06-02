"""
Cohort segments (Phase 11 #2) storage — named, saved filter-sets per project.

A segment is a reusable filter-set on one cube (e.g. "High-value EU customers").
The cohort builder combines segments with set algebra (see cohort_algebra.py).
Firestore layout: /segments/{id}. Mirrors dashboards.py (dual offline backend).
"""
from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class Segment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: uuid4().hex)
    tenant_id: str
    project_id: str
    name: str                                   # referenced by name in expressions
    cube: str                                   # the base cube (set algebra is per-cube)
    filters: list[dict[str, Any]] = Field(default_factory=list)  # implicitly ANDed
    created_by: str = ""
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


_OFFLINE: dict[str, dict[str, Any]] = {}


def reset_offline_store() -> None:
    _OFFLINE.clear()


def _offline() -> bool:
    from services.api_gateway.app.settings import get_settings

    return get_settings().offline_mode


def _col() -> str:
    from services.api_gateway.app.settings import get_settings

    return get_settings().fs_segments_collection


def save_segment(s: Segment) -> None:
    s.updated_at = _now()
    payload = s.model_dump()
    if _offline():
        _OFFLINE[s.id] = payload
        return
    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_col()).document(s.id).set(payload)


def get_segment(segment_id: str) -> Segment | None:
    if _offline():
        data = _OFFLINE.get(segment_id)
        return Segment(**data) if data else None
    from services.api_gateway.app.gcp_clients import firestore_client

    doc = firestore_client().collection(_col()).document(segment_id).get()
    return Segment(**doc.to_dict()) if doc.exists else None


def list_segments_for_project(tenant_id: str, project_id: str) -> list[Segment]:
    if _offline():
        return [
            Segment(**d)
            for d in _OFFLINE.values()
            if d.get("tenant_id") == tenant_id and d.get("project_id") == project_id
        ]
    from google.cloud.firestore_v1.base_query import FieldFilter

    from services.api_gateway.app.gcp_clients import firestore_client

    docs = (
        firestore_client()
        .collection(_col())
        .where(filter=FieldFilter("tenant_id", "==", tenant_id))
        .where(filter=FieldFilter("project_id", "==", project_id))
        .stream()
    )
    return [Segment(**(d.to_dict() or {})) for d in docs if d.to_dict()]


def delete_segment_record(segment_id: str) -> None:
    if _offline():
        _OFFLINE.pop(segment_id, None)
        return
    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_col()).document(segment_id).delete()
