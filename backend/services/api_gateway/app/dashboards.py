"""
Pinnable dashboards (Phase 8).

A dashboard is a project-scoped collection of tiles; each tile is a saved cube
query spec (the same shape pivot/chat produce). Tiles re-run against fresh data
on every visit. A dashboard can be shared read-only via an unguessable token.

Firestore layout: /dashboards/{id}. Mirrors projects.py (dual offline backend).
"""
from __future__ import annotations

import datetime as dt
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

ChartType = str  # auto | bar | line | kpi | table | heatmap


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class TileSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    time_dimension: str | None = None
    granularity: str | None = None
    filters: list[dict[str, Any]] = Field(default_factory=list)
    order: dict[str, str] = Field(default_factory=dict)
    limit: int | None = None
    chart_type: ChartType = "auto"


class Tile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    title: str = "Untitled"
    spec: TileSpec = Field(default_factory=TileSpec)


class Dashboard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(default_factory=lambda: uuid4().hex)
    tenant_id: str
    project_id: str
    name: str
    created_by: str = ""
    tiles: list[Tile] = Field(default_factory=list)
    share_token: str | None = None
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


# ---------- storage ----------

_OFFLINE: dict[str, dict[str, Any]] = {}


def reset_offline_store() -> None:
    _OFFLINE.clear()


def new_dashboard_id() -> str:
    return uuid4().hex


def _offline() -> bool:
    from services.api_gateway.app.settings import get_settings

    return get_settings().offline_mode


def _col() -> str:
    from services.api_gateway.app.settings import get_settings

    return get_settings().fs_dashboards_collection


def save_dashboard(d: Dashboard) -> None:
    d.updated_at = _now()
    payload = d.model_dump()
    if _offline():
        _OFFLINE[d.id] = payload
        return
    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_col()).document(d.id).set(payload)


def get_dashboard(dashboard_id: str) -> Dashboard | None:
    if _offline():
        data = _OFFLINE.get(dashboard_id)
        return Dashboard(**data) if data else None
    from services.api_gateway.app.gcp_clients import firestore_client

    doc = firestore_client().collection(_col()).document(dashboard_id).get()
    return Dashboard(**doc.to_dict()) if doc.exists else None


def list_dashboards_for_project(tenant_id: str, project_id: str) -> list[Dashboard]:
    if _offline():
        return [
            Dashboard(**d)
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
    return [Dashboard(**(d.to_dict() or {})) for d in docs if d.to_dict()]


def get_by_share_token(token: str) -> Dashboard | None:
    if not token:
        return None
    if _offline():
        for d in _OFFLINE.values():
            if d.get("share_token") == token:
                return Dashboard(**d)
        return None
    from google.cloud.firestore_v1.base_query import FieldFilter

    from services.api_gateway.app.gcp_clients import firestore_client

    docs = list(
        firestore_client()
        .collection(_col())
        .where(filter=FieldFilter("share_token", "==", token))
        .limit(1)
        .stream()
    )
    return Dashboard(**docs[0].to_dict()) if docs else None


def delete_dashboard_record(dashboard_id: str) -> None:
    if _offline():
        _OFFLINE.pop(dashboard_id, None)
        return
    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_col()).document(dashboard_id).delete()
