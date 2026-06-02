"""
Column-level lineage (Phase 11 differentiator #1).

"Deterministic" is only credible if you can prove it. Given any cube field
(measure/dimension), trace it back: Cube member → its SQL expression → the raw
BigQuery table + source column(s) → who human-confirmed its meaning (onboarding)
→ the approved graph edges that let its cube join others. All derived from the
existing cube schema + column semantics + approved edges — no new storage.
"""
from __future__ import annotations

import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.chat_router import _catalog_and_health

router = APIRouter(prefix="/v1/lineage", tags=["lineage"])

_BACKTICK = re.compile(r"`([^`]+)`")


class SourceColumn(BaseModel):
    column: str
    role: str | None = None
    business_meaning: str | None = None
    confirmed_by: str | None = None
    confirmed_at: str | None = None


class JoinProvenance(BaseModel):
    to_cube: str
    from_edge_id: str
    sql_clause: str


class LineageTrace(BaseModel):
    field: str
    kind: str                       # measure | dimension
    aggregation: str | None = None  # for measures
    revenue_touching: bool = False
    cube: str
    dataset_id: str
    dataset_label: str
    bq_table: str | None = None
    locale: str = "US"
    sql: str | None = None
    source_columns: list[SourceColumn] = Field(default_factory=list)
    joins: list[JoinProvenance] = Field(default_factory=list)


def _project_or_404(principal: Principal, project_id: str) -> None:
    from services.api_gateway.app.projects import get_project

    p = get_project(project_id)
    if p is None or p.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")


@router.get("", response_model=LineageTrace)
def lineage(
    principal: Annotated[Principal, Depends(current_principal)],
    project_id: str,
    field: str,
) -> LineageTrace:
    """Trace a cube field (e.g. 'sales__ab12.sum_revenue') to its raw source."""
    _project_or_404(principal, project_id)
    schemas, _ = _catalog_and_health(principal.tenant_id, [], project_id)

    cube_name, _, member = field.partition(".")
    schema = next((s for s in schemas if s.name == cube_name), None)
    if schema is None or not member:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown field")

    measure = next((m for m in schema.measures if m.name == member), None)
    dim = next((d for d in schema.dimensions if d.name == member), None)
    if measure is None and dim is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown field")

    sql = measure.sql if measure else (dim.sql if dim else None)
    kind = "measure" if measure else "dimension"
    agg = measure.type if measure else None
    revenue = bool(measure.revenue_touching) if measure else False

    # Raw source columns referenced in the SQL (backtick-quoted identifiers).
    raw_cols = _BACKTICK.findall(sql or "")
    if not raw_cols and dim is not None:
        raw_cols = [member]

    # Enrich each source column with the human-confirmed semantics (provenance).
    from services.api_gateway.app.datasets import get_column_profiles

    profiles = {c.get("name"): c for c in get_column_profiles(schema.dataset_id)}
    source_columns = [
        SourceColumn(
            column=c,
            role=(profiles.get(c) or {}).get("role"),
            business_meaning=(profiles.get(c) or {}).get("business_meaning"),
            confirmed_by=(profiles.get(c) or {}).get("confirmed_by"),
            confirmed_at=(profiles.get(c) or {}).get("confirmed_at"),
        )
        for c in raw_cols
    ]

    joins = [
        JoinProvenance(to_cube=j.to_cube, from_edge_id=j.from_edge_id, sql_clause=j.sql_clause)
        for j in schema.joins
    ]

    return LineageTrace(
        field=field, kind=kind, aggregation=agg, revenue_touching=revenue,
        cube=schema.name, dataset_id=schema.dataset_id, dataset_label=schema.title,
        bq_table=schema.sql_table, locale=schema.locale_hint, sql=sql,
        source_columns=source_columns, joins=joins,
    )
