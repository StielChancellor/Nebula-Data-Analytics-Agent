"""
Cohort builder endpoints (Phase 11 #2).

Save named segments (filter-sets on one cube), then combine them with set algebra
— `(A & B) - C` — resolved deterministically into a governed Cube query. Every
leaf member is validated against the project catalog before it reaches Cube, so
the set algebra can't smuggle in an arbitrary member. Set algebra is per-cube:
mixing segments from different cubes is refused (row identity is only defined
within one fact). LLM-free.
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.cohorts import (
    Segment,
    delete_segment_record,
    get_segment,
    list_segments_for_project,
    save_segment,
)

router = APIRouter(prefix="/v1/cohorts", tags=["cohorts"])


def _project_or_404(principal: Principal, project_id: str) -> None:
    from services.api_gateway.app.projects import get_project

    p = get_project(project_id)
    if p is None or p.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")


def _segment_owned(principal: Principal, segment_id: str) -> Segment:
    s = get_segment(segment_id)
    if s is None or s.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "segment not found")
    return s


class SegmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    name: str = Field(min_length=1, max_length=120)
    cube: str
    filters: list[dict[str, Any]] = Field(default_factory=list)


class ResolveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    expression: str = Field(min_length=1, max_length=2000)  # e.g. (A & B) - C
    measures: list[str] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    time_dimension: str | None = None
    granularity: str | None = None
    order: dict[str, str] = Field(default_factory=dict)
    limit: int | None = None


@router.get("", response_model=list[Segment])
def list_cohorts(
    principal: Annotated[Principal, Depends(current_principal)],
    project_id: str,
) -> list[Segment]:
    _project_or_404(principal, project_id)
    return list_segments_for_project(principal.tenant_id, project_id)


@router.post("", response_model=Segment, status_code=status.HTTP_201_CREATED)
def create_cohort(
    body: SegmentCreate,
    principal: Annotated[Principal, Depends(current_principal)],
) -> Segment:
    _project_or_404(principal, body.project_id)
    # Validate the cube + every filter member against the project catalog.
    from services.api_gateway.app.cube_query_service import valid_fields

    valid = valid_fields(principal.tenant_id, body.project_id)
    bad = [f.get("member") for f in body.filters
           if isinstance(f, dict) and f.get("member") and f["member"] not in valid]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown field(s): {', '.join(bad)}")
    seg = Segment(
        tenant_id=principal.tenant_id, project_id=body.project_id,
        name=body.name, cube=body.cube, filters=body.filters,
        created_by=principal.email,
    )
    save_segment(seg)
    return seg


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cohort(
    segment_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> None:
    _segment_owned(principal, segment_id)
    delete_segment_record(segment_id)


class ResolveResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    cube_query: dict[str, Any]
    filter_tree: dict[str, Any]
    segments_used: list[str]


@router.post("/resolve", response_model=ResolveResult)
def resolve_cohort(
    body: ResolveRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> ResolveResult:
    _project_or_404(principal, body.project_id)
    from services.api_gateway.app.cohort_algebra import (
        CohortSyntaxError,
        NonInvertibleFilter,
        UnknownSegment,
        compile_expression,
    )
    from services.api_gateway.app.cube_query_service import UnknownField, run_spec, valid_fields

    segments = list_segments_for_project(principal.tenant_id, body.project_id)
    by_name = {s.name: s for s in segments}
    # Set algebra is per-cube — all referenced segments must share one base cube.
    seg_filters = {name: s.filters for name, s in by_name.items()}

    try:
        tree, members = compile_expression(body.expression, seg_filters)
    except UnknownSegment as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    except NonInvertibleFilter as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    except CohortSyntaxError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"bad expression: {e}") from e

    # Which segments did the expression actually name? (for cube-consistency + echo)
    used = _names_in_expression(body.expression, set(by_name))
    cubes = {by_name[n].cube for n in used}
    if len(cubes) > 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"cohort set algebra is per-cube; expression mixes cubes: {', '.join(sorted(cubes))}",
        )

    # Govern: every leaf member must be a real catalog field.
    valid = valid_fields(principal.tenant_id, body.project_id)
    bad = [m for m in members if m not in valid]
    if bad:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unknown field(s): {', '.join(bad)}")

    try:
        columns, rows, query = run_spec(
            tenant_id=principal.tenant_id, project_id=body.project_id,
            measures=body.measures, dimensions=body.dimensions,
            time_dimension=body.time_dimension, granularity=body.granularity,
            filters=[tree] if tree.get("and") or tree.get("or") or tree.get("member") else [],
            order=body.order, limit=body.limit,
        )
    except UnknownField as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    return ResolveResult(
        columns=columns, rows=rows, cube_query=query,
        filter_tree=tree, segments_used=sorted(used),
    )


def _names_in_expression(expr: str, known: set[str]) -> set[str]:
    from services.api_gateway.app.cohort_algebra import parse_expression

    def walk(node: Any, out: set[str]) -> None:
        if node[0] == "name":
            out.add(node[1])
        else:
            walk(node[1], out)
            walk(node[2], out)

    found: set[str] = set()
    try:
        walk(parse_expression(expr), found)
    except Exception:  # noqa: BLE001 — validation already happened in the caller
        return set()
    return {n for n in found if n in known}
