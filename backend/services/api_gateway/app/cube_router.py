"""
Cube schema endpoints (Phase 5).

Approved graph edges + dataset metadata + column profiles → generated Cube
schemas, computed on demand from the current Firestore state. No separate
persistence layer in v1 — schemas are pure functions of those three inputs,
so it's faster and safer to regenerate than to cache.

PRD § Hard constraint #2 enforcement happens inside insnav_cube_client:
joins are derived ONLY from approved edges. Proposed/rejected edges never
become joins.

Endpoints:
  GET /v1/cube/schemas             — summary per dataset (counts of dims/measures/joins,
                                      revenue_touching flag)
  GET /v1/cube/schemas/{dataset_id}/json   — full CubeSchema (Pydantic) as JSON
  GET /v1/cube/schemas/{dataset_id}.js     — raw Cube .js file (Content-Type: application/javascript)
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from insnav_cube_client import CubeSchema, build_cube_schema, cube_name_for_dataset, render_to_js
from insnav_graph_store import list_approved_edges
from pydantic import BaseModel

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.cube_sync_service import sync_tenant
from services.api_gateway.app.datasets import (
    Dataset,
    get_column_profiles,
    get_dataset,
    list_datasets_for_tenant,
)

router = APIRouter(tags=["cube"])


# ---------- response shapes ----------

class CubeSchemaSummary(BaseModel):
    """Lightweight overview, one per ready dataset."""

    dataset_id: str
    dataset_label: str
    cube_name: str
    bq_table: str | None
    dimension_count: int
    measure_count: int
    join_count: int
    revenue_touching: bool


class CubeSyncResult(BaseModel):
    tenant_id: str
    version: str
    file_count: int
    cube_names: list[str]


# ---------- endpoints ----------


@router.post("/v1/cube/sync", response_model=CubeSyncResult)
def sync_cube_model_endpoint(
    principal: Annotated[Principal, Depends(current_principal)],
    project_id: str | None = None,
) -> CubeSyncResult:
    """
    Rebuild + publish a Cube model to GCS so the deployed Cube container picks
    it up. With ?project_id=… syncs that project workspace (Phase 10); without,
    the legacy tenant-level model. Auto-runs on edge approve + onboarding done.
    """
    if project_id:
        from services.api_gateway.app.cube_sync_service import sync_project

        result = sync_project(principal.tenant_id, project_id)
    else:
        result = sync_tenant(principal.tenant_id)
    return CubeSyncResult(
        tenant_id=principal.tenant_id,
        version=result["version"],
        file_count=result["file_count"],
        cube_names=result["cube_names"],
    )

@router.get("/v1/cube/schemas", response_model=list[CubeSchemaSummary])
def list_schemas(
    principal: Annotated[Principal, Depends(current_principal)],
) -> list[CubeSchemaSummary]:
    """One entry per dataset the principal can see. Compute schemas on demand."""
    datasets = [d for d in list_datasets_for_tenant(principal.tenant_id) if d.status == "ready"]
    edges = list_approved_edges(principal.tenant_id)
    edge_dicts = [e.model_dump() for e in edges]
    cube_name_lookup = {d.id: cube_name_for_dataset(d.id, d.label) for d in datasets}

    out: list[CubeSchemaSummary] = []
    for d in datasets:
        columns = get_column_profiles(d.id)
        schema = build_cube_schema(
            dataset=d.model_dump(),
            columns=columns,
            edges=edge_dicts,
            cube_name_lookup=cube_name_lookup,
        )
        out.append(
            CubeSchemaSummary(
                dataset_id=d.id,
                dataset_label=d.label,
                cube_name=schema.name,
                bq_table=d.bq_table,
                dimension_count=len(schema.dimensions),
                measure_count=len(schema.measures),
                join_count=len(schema.joins),
                revenue_touching=schema.revenue_touching(),
            )
        )
    return out


@router.get("/v1/cube/schemas/{dataset_id}/json", response_model=CubeSchema)
def get_schema_json(
    dataset_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> CubeSchema:
    return _build_for(dataset_id, principal)


@router.get("/v1/cube/schemas/{dataset_id}.js", response_class=PlainTextResponse)
def get_schema_js(
    dataset_id: str,
    principal: Annotated[Principal, Depends(current_principal)],
) -> PlainTextResponse:
    schema = _build_for(dataset_id, principal)
    return PlainTextResponse(
        content=render_to_js(schema),
        media_type="application/javascript",
    )


# ---------- internals ----------

def _build_for(dataset_id: str, principal: Principal) -> CubeSchema:
    d = get_dataset(dataset_id)
    if d is None or d.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    if d.status != "ready":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"dataset not ready (current status: {d.status})",
        )

    edges = list_approved_edges(principal.tenant_id)
    edge_dicts = [e.model_dump() for e in edges]

    # Build the cube_name_lookup so joins reference the actual cube names
    # of peer datasets (otherwise the lookup falls back to a less-readable
    # default).
    peers = list_datasets_for_tenant(principal.tenant_id)
    cube_name_lookup = {p.id: cube_name_for_dataset(p.id, p.label) for p in peers}

    return build_cube_schema(
        dataset=d.model_dump(),
        columns=get_column_profiles(d.id),
        edges=edge_dicts,
        cube_name_lookup=cube_name_lookup,
    )
