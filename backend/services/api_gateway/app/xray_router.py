"""
X-ray proactive insights (Phase 12).

On a project's cube, auto-generate a *starter dashboard* without being asked:
KPI totals for each measure, top-N breakdowns by each dimension, and a trend
over the time dimension. Rule-based (deterministic) spec generation from the
schema — the LLM is not in this path. Revenue measures are surfaced first.

  POST /v1/xray/suggest    → the suggested tiles (specs only, nothing run)
  POST /v1/xray/dashboard  → create a dashboard pre-filled with those tiles
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.chat_router import _catalog_and_health

router = APIRouter(prefix="/v1/xray", tags=["xray"])

# Keep a starter dashboard tidy + cheap: bounded tile count.
_MAX_TILES = 8
_MAX_DIMS_PER_MEASURE = 2


class SuggestedTile(BaseModel):
    title: str
    spec: dict[str, Any]
    rationale: str


def _project_or_404(principal: Principal, project_id: str) -> None:
    from services.api_gateway.app.projects import get_project

    p = get_project(project_id)
    if p is None or p.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")


def build_xray_tiles(schemas: list[Any]) -> list[SuggestedTile]:
    """Deterministic starter tiles from cube schemas. Pure (no I/O)."""
    short = lambda n: n.split(".")[-1]  # noqa: E731
    tiles: list[SuggestedTile] = []

    # Revenue measures first, then the rest — most-useful-first ordering.
    def measures_ranked(s: Any) -> list[Any]:
        return sorted(s.measures, key=lambda m: (not getattr(m, "revenue_touching", False), m.name))

    for s in schemas:
        time_dims = [d for d in s.dimensions if d.type == "time"]
        cat_dims = [d for d in s.dimensions if d.type != "time"]
        td = time_dims[0] if time_dims else None

        for m in measures_ranked(s):
            mname = f"{s.name}.{m.name}"
            mlabel = m.title or short(m.name)
            # KPI total
            tiles.append(SuggestedTile(
                title=f"Total {mlabel}",
                spec={"measures": [mname], "dimensions": [], "chart_type": "kpi"},
                rationale="Headline total for this measure.",
            ))
            # Trend over time
            if td is not None:
                tiles.append(SuggestedTile(
                    title=f"{mlabel} over time",
                    spec={"measures": [mname], "dimensions": [], "time_dimension": f"{s.name}.{td.name}",
                          "granularity": "month", "chart_type": "line"},
                    rationale="Trend over the dataset's time dimension.",
                ))
            # Top-N breakdowns by category dims
            for d in cat_dims[:_MAX_DIMS_PER_MEASURE]:
                dname = f"{s.name}.{d.name}"
                tiles.append(SuggestedTile(
                    title=f"{mlabel} by {d.title or short(d.name)}",
                    spec={"measures": [mname], "dimensions": [dname],
                          "order": {mname: "desc"}, "limit": 10, "chart_type": "bar"},
                    rationale="Top contributors — where the measure concentrates.",
                ))
            if len(tiles) >= _MAX_TILES:
                break
        if len(tiles) >= _MAX_TILES:
            break

    return tiles[:_MAX_TILES]


class XrayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str


@router.post("/suggest", response_model=list[SuggestedTile])
def suggest(
    body: XrayRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> list[SuggestedTile]:
    _project_or_404(principal, body.project_id)
    schemas, _ = _catalog_and_health(principal.tenant_id, [], body.project_id)
    if not schemas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no cube model yet — onboard a dataset first")
    return build_xray_tiles(schemas)


class XrayDashboardRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    name: str = "Starter dashboard"


@router.post("/dashboard")
def create_starter_dashboard(
    body: XrayDashboardRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> dict[str, Any]:
    _project_or_404(principal, body.project_id)
    schemas, _ = _catalog_and_health(principal.tenant_id, [], body.project_id)
    if not schemas:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no cube model yet — onboard a dataset first")

    from services.api_gateway.app.dashboards import Dashboard, Tile, TileSpec, save_dashboard

    suggested = build_xray_tiles(schemas)
    tiles = [Tile(title=t.title, spec=TileSpec(**t.spec)) for t in suggested]
    dash = Dashboard(
        tenant_id=principal.tenant_id, project_id=body.project_id,
        name=body.name, created_by=principal.email, tiles=tiles,
    )
    save_dashboard(dash)
    return {"dashboard_id": dash.id, "name": dash.name, "tile_count": len(tiles)}
