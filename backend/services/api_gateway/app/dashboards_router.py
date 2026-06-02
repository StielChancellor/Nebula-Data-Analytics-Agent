"""
Dashboard endpoints (Phase 8) — CRUD, pin tiles, re-run on visit, share links.

Tiles re-run against fresh data via the shared cube-spec runner. A read-only
public share token exposes GET /v1/public/dashboards/{token} with no auth (the
query runs as the dashboard's stored tenant/project).
"""
from __future__ import annotations

from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.api_gateway.app.auth import Principal, current_principal, require_admin
from services.api_gateway.app.cube_query_service import UnknownField, run_spec
from services.api_gateway.app.dashboards import (
    Dashboard,
    Tile,
    TileSpec,
    delete_dashboard_record,
    get_by_share_token,
    get_dashboard,
    list_dashboards_for_project,
    new_dashboard_id,
    save_dashboard,
)

router = APIRouter(tags=["dashboards"])


class CreateDashboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    name: str = Field(min_length=1, max_length=200)


class UpdateDashboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)


class AddTileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Untitled", max_length=200)
    spec: TileSpec


class TileResult(BaseModel):
    tile_id: str
    title: str
    spec: TileSpec
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    chart_type: str = "auto"
    error: str | None = None


class RunResult(BaseModel):
    dashboard_id: str
    name: str
    tiles: list[TileResult]


def _owned(dashboard_id: str, principal: Principal) -> Dashboard:
    d = get_dashboard(dashboard_id)
    if d is None or d.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dashboard not found")
    return d


def _project_owned(principal: Principal, project_id: str) -> None:
    from services.api_gateway.app.projects import get_project

    p = get_project(project_id)
    if p is None or p.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")


# ---------- CRUD ----------

@router.post("/v1/dashboards", response_model=Dashboard)
def create_dashboard(
    req: CreateDashboardRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Dashboard:
    _project_owned(principal, req.project_id)
    d = Dashboard(
        id=new_dashboard_id(), tenant_id=principal.tenant_id, project_id=req.project_id,
        name=req.name, created_by=principal.email,
    )
    save_dashboard(d)
    return d


@router.get("/v1/dashboards", response_model=list[Dashboard])
def list_dashboards(
    principal: Annotated[Principal, Depends(current_principal)],
    project_id: str,
) -> list[Dashboard]:
    _project_owned(principal, project_id)
    return list_dashboards_for_project(principal.tenant_id, project_id)


@router.get("/v1/dashboards/{dashboard_id}", response_model=Dashboard)
def get_one(
    dashboard_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Dashboard:
    return _owned(dashboard_id, principal)


@router.patch("/v1/dashboards/{dashboard_id}", response_model=Dashboard)
def update_dashboard(
    dashboard_id: str,
    req: UpdateDashboardRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Dashboard:
    d = _owned(dashboard_id, principal)
    if req.name is not None:
        d.name = req.name
    save_dashboard(d)
    return d


@router.delete("/v1/dashboards/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dashboard(
    dashboard_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
) -> None:
    d = get_dashboard(dashboard_id)
    if d is None or d.tenant_id != principal.tenant_id:
        return None
    delete_dashboard_record(dashboard_id)
    return None


# ---------- tiles ----------

@router.post("/v1/dashboards/{dashboard_id}/tiles", response_model=Dashboard)
def add_tile(
    dashboard_id: str,
    req: AddTileRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Dashboard:
    d = _owned(dashboard_id, principal)
    d.tiles.append(Tile(id=uuid4().hex[:12], title=req.title, spec=req.spec))
    save_dashboard(d)
    return d


@router.delete("/v1/dashboards/{dashboard_id}/tiles/{tile_id}", response_model=Dashboard)
def remove_tile(
    dashboard_id: str,
    tile_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Dashboard:
    d = _owned(dashboard_id, principal)
    d.tiles = [t for t in d.tiles if t.id != tile_id]
    save_dashboard(d)
    return d


# ---------- run + share ----------

def _run_tiles(d: Dashboard) -> list[TileResult]:
    out: list[TileResult] = []
    for t in d.tiles:
        try:
            cols, rows, _ = run_spec(
                tenant_id=d.tenant_id, project_id=d.project_id,
                measures=t.spec.measures, dimensions=t.spec.dimensions,
                time_dimension=t.spec.time_dimension, granularity=t.spec.granularity,
                filters=t.spec.filters, order=t.spec.order, limit=t.spec.limit,
            )
            out.append(TileResult(tile_id=t.id, title=t.title, spec=t.spec, columns=cols,
                                  rows=rows, chart_type=t.spec.chart_type))
        except UnknownField as e:
            out.append(TileResult(tile_id=t.id, title=t.title, spec=t.spec,
                                  chart_type=t.spec.chart_type, error=str(e)))
        except Exception:  # noqa: BLE001 — a single tile failure must not kill the board
            out.append(TileResult(tile_id=t.id, title=t.title, spec=t.spec,
                                  chart_type=t.spec.chart_type, error="tile query failed"))
    return out


@router.post("/v1/dashboards/{dashboard_id}/run", response_model=RunResult)
def run_dashboard(
    dashboard_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> RunResult:
    d = _owned(dashboard_id, principal)
    return RunResult(dashboard_id=d.id, name=d.name, tiles=_run_tiles(d))


@router.post("/v1/dashboards/{dashboard_id}/share", response_model=Dashboard)
def share_dashboard(
    dashboard_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
) -> Dashboard:
    d = _owned(dashboard_id, principal)
    d.share_token = uuid4().hex
    save_dashboard(d)
    return d


@router.delete("/v1/dashboards/{dashboard_id}/share", response_model=Dashboard)
def revoke_share(
    dashboard_id: str,
    principal: Annotated[Principal, Depends(require_admin)],
) -> Dashboard:
    d = _owned(dashboard_id, principal)
    d.share_token = None
    save_dashboard(d)
    return d


@router.get("/v1/public/dashboards/{token}", response_model=RunResult)
def public_dashboard(token: str) -> RunResult:
    """Read-only public view via a share token — NO auth (the query runs as the
    dashboard's stored tenant/project). Unknown token → 404."""
    d = get_by_share_token(token)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return RunResult(dashboard_id=d.id, name=d.name, tiles=_run_tiles(d))
