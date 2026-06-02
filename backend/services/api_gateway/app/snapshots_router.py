"""
Snapshot + assumption endpoints (Phase 11 #3 + #5).

  POST   /v1/snapshots            capture a governed query's result with a timestamp
  GET    /v1/snapshots?project_id list snapshots (metadata, no rows)
  GET    /v1/snapshots/{id}       one snapshot (full)
  DELETE /v1/snapshots/{id}
  POST   /v1/snapshots/diff       diff two snapshots of the same spec
  POST   /v1/assumptions/check    re-check a tile spec's statistical assumptions

All deterministic; the diff + assumption logic is pure (see snapshots.py).
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.snapshots import (
    Snapshot,
    delete_snapshot_record,
    diff_snapshots,
    evaluate_assumptions,
    get_snapshot,
    list_snapshots_for_project,
    save_snapshot,
)

router = APIRouter(tags=["snapshots"])


def _project_or_404(principal: Principal, project_id: str) -> None:
    from services.api_gateway.app.projects import get_project

    p = get_project(project_id)
    if p is None or p.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")


def _snapshot_owned(principal: Principal, snapshot_id: str) -> Snapshot:
    s = get_snapshot(snapshot_id)
    if s is None or s.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "snapshot not found")
    return s


class SpecBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    time_dimension: str | None = None
    granularity: str | None = None
    filters: list[dict[str, Any]] = Field(default_factory=list)
    order: dict[str, str] = Field(default_factory=dict)
    limit: int | None = None


class CaptureRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    label: str = ""
    spec: SpecBody


def _run(principal: Principal, project_id: str, spec: SpecBody) -> tuple[list[str], list[list[Any]]]:
    from services.api_gateway.app.cube_query_service import UnknownField, run_spec

    try:
        columns, rows, _ = run_spec(
            tenant_id=principal.tenant_id, project_id=project_id,
            measures=spec.measures, dimensions=spec.dimensions,
            time_dimension=spec.time_dimension, granularity=spec.granularity,
            filters=spec.filters, order=spec.order, limit=spec.limit,
        )
    except UnknownField as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return columns, rows


@router.post("/v1/snapshots", response_model=Snapshot, status_code=status.HTTP_201_CREATED)
def capture_snapshot(
    body: CaptureRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Snapshot:
    _project_or_404(principal, body.project_id)
    columns, rows = _run(principal, body.project_id, body.spec)
    snap = Snapshot(
        tenant_id=principal.tenant_id, project_id=body.project_id, label=body.label,
        spec=body.spec.model_dump(), columns=columns, rows=rows,
    )
    save_snapshot(snap)
    return snap


class SnapshotMeta(BaseModel):
    id: str
    label: str
    captured_at: str
    spec: dict[str, Any]
    row_count: int


@router.get("/v1/snapshots", response_model=list[SnapshotMeta])
def list_snapshots(
    principal: Annotated[Principal, Depends(current_principal)],
    project_id: str,
) -> list[SnapshotMeta]:
    _project_or_404(principal, project_id)
    snaps = list_snapshots_for_project(principal.tenant_id, project_id)
    snaps.sort(key=lambda s: s.captured_at, reverse=True)
    return [SnapshotMeta(id=s.id, label=s.label, captured_at=s.captured_at,
                         spec=s.spec, row_count=len(s.rows)) for s in snaps]


@router.get("/v1/snapshots/{snapshot_id}", response_model=Snapshot)
def read_snapshot(
    snapshot_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Snapshot:
    return _snapshot_owned(principal, snapshot_id)


@router.delete("/v1/snapshots/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_snapshot(
    snapshot_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> None:
    _snapshot_owned(principal, snapshot_id)
    delete_snapshot_record(snapshot_id)


class DiffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: str  # baseline snapshot id
    b: str  # comparison snapshot id


@router.post("/v1/snapshots/diff")
def diff(
    body: DiffRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict[str, Any]:
    a = _snapshot_owned(principal, body.a)
    b = _snapshot_owned(principal, body.b)
    if a.project_id != b.project_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "snapshots are from different projects")
    result = diff_snapshots(a.spec or b.spec, a.columns, a.rows, b.columns, b.rows)
    return {
        "baseline": {"id": a.id, "label": a.label, "captured_at": a.captured_at},
        "comparison": {"id": b.id, "label": b.label, "captured_at": b.captured_at},
        "diff": result,
    }


class AssumptionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    spec: SpecBody


@router.post("/v1/assumptions/check")
def check_assumptions(
    body: AssumptionsRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict[str, Any]:
    """Re-evaluate a tile's statistical assumptions now (Phase 11 #5)."""
    _project_or_404(principal, body.project_id)
    columns, rows = _run(principal, body.project_id, body.spec)
    warnings = evaluate_assumptions(body.spec.model_dump(), columns, rows)
    return {"warnings": warnings, "ok": not any(w["level"] == "warn" for w in warnings)}
