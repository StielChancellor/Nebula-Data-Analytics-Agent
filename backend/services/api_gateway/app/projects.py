"""
Project workspace model + Firestore CRUD (Phase 10).

A *project* is the central organizing entity below a tenant. Each project is a
self-contained workspace that owns its own datasets, knowledge graph, Cube
model, locale default, onboarding sessions, and members. Everything that used
to be scoped by tenant_id only is now additionally scoped by project_id.

Firestore layout:
  /projects/{project_id}     ← document with the fields below

Mirrors datasets.py exactly: a Pydantic model + a dual backend (Firestore in
prod, in-memory dict in offline_mode) so production code paths stay identical
and tests run without GCP.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

ProjectStatus = Literal["draft", "active", "archived"]
MemberRole = Literal["owner", "admin", "viewer"]
LocaleHint = Literal["US", "IN"]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


class ProjectMember(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str
    role: MemberRole = "viewer"


class Project(BaseModel):
    """The Firestore record describing a project workspace."""

    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    brand: str
    name: str
    description: str = ""
    owner_email: str
    members: list[ProjectMember] = Field(default_factory=list)
    locale_default: LocaleHint = "US"
    status: ProjectStatus = "draft"
    dataset_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


# ---------- helpers ----------

def new_project_id() -> str:
    return uuid4().hex


# ---------- Storage backend (Firestore in prod, in-memory in offline_mode) ----------

_OFFLINE_PROJECTS: dict[str, dict[str, Any]] = {}


def reset_offline_store() -> None:
    """Test helper — wipe the in-memory store between tests."""
    _OFFLINE_PROJECTS.clear()


def _offline() -> bool:
    from services.api_gateway.app.settings import get_settings

    return get_settings().offline_mode


def _collection_name() -> str:
    from services.api_gateway.app.settings import get_settings

    return get_settings().fs_projects_collection


def save_project(p: Project) -> None:
    payload = p.model_dump()
    payload["updated_at"] = _now()

    if _offline():
        _OFFLINE_PROJECTS[p.id] = payload
        return

    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_collection_name()).document(p.id).set(payload, merge=True)


def get_project(project_id: str) -> Project | None:
    if _offline():
        data = _OFFLINE_PROJECTS.get(project_id)
        return Project(**data) if data else None

    from services.api_gateway.app.gcp_clients import firestore_client

    doc = firestore_client().collection(_collection_name()).document(project_id).get()
    if not doc.exists:
        return None
    return Project(**doc.to_dict())


def list_projects_for_tenant(tenant_id: str) -> list[Project]:
    if _offline():
        return [
            Project(**d)
            for d in _OFFLINE_PROJECTS.values()
            if d.get("tenant_id") == tenant_id
        ]

    from google.cloud.firestore_v1.base_query import FieldFilter

    from services.api_gateway.app.gcp_clients import firestore_client

    docs = (
        firestore_client()
        .collection(_collection_name())
        .where(filter=FieldFilter("tenant_id", "==", tenant_id))
        .stream()
    )
    out: list[Project] = []
    for doc in docs:
        data = doc.to_dict()
        if data:
            out.append(Project(**data))
    return out


def add_dataset_to_project(project_id: str, dataset_id: str) -> Project | None:
    """Idempotently associate a dataset with a project. Returns the updated project."""
    p = get_project(project_id)
    if p is None:
        return None
    if dataset_id not in p.dataset_ids:
        p.dataset_ids.append(dataset_id)
        save_project(p)
    return p


def remove_dataset_from_project(project_id: str, dataset_id: str) -> Project | None:
    p = get_project(project_id)
    if p is None:
        return None
    if dataset_id in p.dataset_ids:
        p.dataset_ids = [d for d in p.dataset_ids if d != dataset_id]
        save_project(p)
    return p


def update_project_status(project_id: str, status: ProjectStatus) -> None:
    patch: dict[str, Any] = {"status": status, "updated_at": _now()}

    if _offline():
        existing = _OFFLINE_PROJECTS.get(project_id)
        if existing is not None:
            existing.update(patch)
        return

    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_collection_name()).document(project_id).set(patch, merge=True)


def delete_project_record(project_id: str) -> None:
    """Remove the project document. Datasets are deleted separately by the caller."""
    if _offline():
        _OFFLINE_PROJECTS.pop(project_id, None)
        return

    from services.api_gateway.app.gcp_clients import firestore_client

    firestore_client().collection(_collection_name()).document(project_id).delete()
