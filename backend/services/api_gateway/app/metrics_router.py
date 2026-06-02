"""
Metric registry (Phase 11 differentiator #8).

Surfaces every governed Cube measure in a project with its provenance: the
aggregation, definition SQL, the dataset it lives on, whether it's revenue-
touching, and WHO confirmed its meaning + WHEN (the effective date) during
onboarding. Stops "revenue means three different things" drift by making every
metric's definition + owner explicit. Derived from the cube schema + the
human-confirmed column semantics — no new storage.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.chat_router import _catalog_and_health

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


class MetricEntry(BaseModel):
    name: str               # fully-qualified cube.measure
    title: str
    aggregation: str
    revenue_touching: bool
    definition_sql: str | None = None
    cube: str
    dataset_id: str
    dataset_label: str
    owner: str | None = None       # who confirmed (onboarding)
    effective_at: str | None = None  # when confirmed


class MetricRegistry(BaseModel):
    project_id: str
    metrics: list[MetricEntry] = Field(default_factory=list)


def _project_or_404(principal: Principal, project_id: str) -> None:
    from services.api_gateway.app.projects import get_project

    p = get_project(project_id)
    if p is None or p.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")


@router.get("", response_model=MetricRegistry)
def list_metrics(
    principal: Annotated[Principal, Depends(current_principal)],
    project_id: str,
) -> MetricRegistry:
    _project_or_404(principal, project_id)
    schemas, _ = _catalog_and_health(principal.tenant_id, [], project_id)

    from services.api_gateway.app.datasets import get_column_profiles

    out: list[MetricEntry] = []
    for s in schemas:
        profiles = {c.get("name"): c for c in get_column_profiles(s.dataset_id)}
        for m in s.measures:
            # The measure's source column (best-effort: first backticked identifier).
            src = None
            if m.sql:
                import re as _re

                found = _re.findall(r"`([^`]+)`", m.sql)
                src = found[0] if found else None
            prof = profiles.get(src) if src else None
            out.append(MetricEntry(
                name=f"{s.name}.{m.name}", title=m.title or m.name,
                aggregation=m.type, revenue_touching=bool(m.revenue_touching),
                definition_sql=m.sql, cube=s.name, dataset_id=s.dataset_id,
                dataset_label=s.title,
                owner=(prof or {}).get("confirmed_by"),
                effective_at=(prof or {}).get("confirmed_at"),
            ))
    return MetricRegistry(project_id=project_id, metrics=out)
