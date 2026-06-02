"""
Project workspace endpoints (Phase 10).

A project groups datasets + graph + cube model + locale + onboarding under a
tenant. CRUD is tenant-scoped via current_principal; the creator becomes the
owner. Dataset deletion / cube re-sync on project delete is delegated to the
dataset-delete path (datasets_router) so cleanup logic lives in one place.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.projects import (
    LocaleHint,
    Project,
    ProjectMember,
    ProjectStatus,
    delete_project_record,
    get_project,
    list_projects_for_tenant,
    new_project_id,
    save_project,
)

router = APIRouter(prefix="/v1/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    locale_default: LocaleHint = "US"


class UpdateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    locale_default: LocaleHint | None = None
    status: ProjectStatus | None = None


def _owned_or_404(project_id: str, principal: Principal) -> Project:
    p = get_project(project_id)
    if p is None or p.tenant_id != principal.tenant_id:
        # Don't leak existence across tenants.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
    return p


@router.post("", response_model=Project)
def create_project(
    req: CreateProjectRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Project:
    p = Project(
        id=new_project_id(),
        tenant_id=principal.tenant_id,
        brand=principal.brand,
        name=req.name,
        description=req.description,
        owner_email=principal.email,
        members=[ProjectMember(email=principal.email, role="owner")],
        locale_default=req.locale_default,
        status="draft",
    )
    save_project(p)
    return p


@router.get("", response_model=list[Project])
def list_projects(
    principal: Annotated[Principal, Depends(current_principal)],
) -> list[Project]:
    return list_projects_for_tenant(principal.tenant_id)


@router.get("/{project_id}", response_model=Project)
def get_one(
    project_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Project:
    return _owned_or_404(project_id, principal)


@router.patch("/{project_id}", response_model=Project)
def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Project:
    p = _owned_or_404(project_id, principal)
    if req.name is not None:
        p.name = req.name
    if req.description is not None:
        p.description = req.description
    if req.locale_default is not None:
        p.locale_default = req.locale_default
    if req.status is not None:
        p.status = req.status
    save_project(p)
    return p


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> None:
    p = get_project(project_id)
    if p is None or p.tenant_id != principal.tenant_id:
        # Idempotent: already gone (or never visible to this tenant).
        return None
    # Cascade-delete the project's datasets (full cleanup: BQ + GCS + Firestore
    # + edges + cube re-sync) so a deleted project leaves nothing behind.
    if p.dataset_ids:
        from services.api_gateway.app.datasets_cleanup import delete_dataset_fully

        for dataset_id in list(p.dataset_ids):
            try:
                delete_dataset_fully(dataset_id, principal)
            except Exception:  # noqa: BLE001 — best-effort; keep deleting the rest
                pass
    delete_project_record(project_id)
    return None
