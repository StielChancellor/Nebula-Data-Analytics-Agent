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

from insnav_agents.schemas import Interpretation
from insnav_agents.swarm import _rows_from_cube, build_catalog, to_cube_query
from insnav_cube_client import CubeQueryClient

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.chat_router import _catalog_and_health
from services.api_gateway.app.settings import get_settings

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

    schemas, _ = _catalog_and_health(principal.tenant_id, [], req.project_id)
    _, valid = build_catalog(schemas)

    requested = list(req.measures) + list(req.dimensions)
    if req.time_dimension:
        requested.append(req.time_dimension)
    requested += [f.get("member") for f in req.filters if isinstance(f, dict) and f.get("member")]
    for name in requested:
        if name not in valid:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown field: {name}")

    interp = Interpretation(
        measures=req.measures,
        dimensions=req.dimensions,
        time_dimension=req.time_dimension,
        granularity=req.granularity,
        filters=req.filters,
        order=req.order,
        limit=req.limit or 5000,
    )
    query = to_cube_query(interp)

    settings = get_settings()
    cube = CubeQueryClient(
        api_url=settings.cube_api_url,
        api_secret=settings.cube_api_secret,
        offline=settings.offline_mode or not settings.cube_api_url,
        project_id=req.project_id,
    )
    result = cube.load(query, tenant_id=principal.tenant_id)
    columns, rows = _rows_from_cube(result, query)
    return PivotResult(columns=columns, rows=rows, cube_query=query)
