"""
Pivot endpoints (Phase 7) — deterministic crosstab queries over the project cube.

The pivot UI is pure user-driven field selection (drag-drop), so there's no LLM
here: the user picks measures + row/column dimensions, we build a governed Cube
query and run it. Every requested field is validated against the project's cube
catalog (no arbitrary member injection). Reuses the swarm's query builder + the
cube result→rows conversion so pivot and chat stay consistent.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.chat_router import _catalog_and_health

router = APIRouter(prefix="/v1/pivot", tags=["pivot"])


class PivotField(BaseModel):
    name: str          # fully-qualified cube.member
    title: str
    type: str          # number | string | time | boolean | count | sum | ...
    revenue: bool = False


class PivotFields(BaseModel):
    measures: list[PivotField] = Field(default_factory=list)
    dimensions: list[PivotField] = Field(default_factory=list)
    time_dimensions: list[PivotField] = Field(default_factory=list)


class PivotQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)  # row + column dims
    time_dimension: str | None = None
    granularity: str | None = None
    filters: list[dict[str, Any]] = Field(default_factory=list)  # Cube {member,operator,values}
    order: dict[str, str] = Field(default_factory=dict)
    limit: int | None = None


class PivotResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    cube_query: dict[str, Any]


def _project_or_404(principal: Principal, project_id: str) -> None:
    from services.api_gateway.app.projects import get_project

    p = get_project(project_id)
    if p is None or p.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")


@router.get("/fields", response_model=PivotFields)
def pivot_fields(
    principal: Annotated[Principal, Depends(current_principal)],
    project_id: str,
) -> PivotFields:
    """The measures + dimensions available to drag onto the pivot shelves."""
    _project_or_404(principal, project_id)
    schemas, _ = _catalog_and_health(principal.tenant_id, [], project_id)
    measures: list[PivotField] = []
    dims: list[PivotField] = []
    times: list[PivotField] = []
    for s in schemas:
        for m in s.measures:
            measures.append(PivotField(
                name=f"{s.name}.{m.name}", title=m.title or m.name,
                type=m.type, revenue=getattr(m, "revenue_touching", False),
            ))
        for d in s.dimensions:
            f = PivotField(name=f"{s.name}.{d.name}", title=d.title or d.name, type=d.type)
            (times if d.type == "time" else dims).append(f)
    return PivotFields(measures=measures, dimensions=dims, time_dimensions=times)


@router.post("/query", response_model=PivotResult)
def pivot_query(
    req: PivotQueryRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> PivotResult:
    _project_or_404(principal, req.project_id)
    if not req.measures and not req.dimensions and not req.time_dimension:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "select at least one field")

    from services.api_gateway.app.cube_query_service import UnknownField, run_spec

    try:
        columns, rows, query = run_spec(
            tenant_id=principal.tenant_id,
            project_id=req.project_id,
            measures=req.measures,
            dimensions=req.dimensions,
            time_dimension=req.time_dimension,
            granularity=req.granularity,
            filters=req.filters,
            order=req.order,
            limit=req.limit,
        )
    except UnknownField as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return PivotResult(columns=columns, rows=rows, cube_query=query)
