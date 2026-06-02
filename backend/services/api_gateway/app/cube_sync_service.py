"""
Cube model sync service (Phase 5b).

Bridges the Firestore state (datasets + column profiles + approved edges) to
the GCS Cube model directory the deployed Cube container reads. Shared by:
  - POST /v1/cube/sync             (sync the caller's tenant on demand)
  - the edge-approve hook          (keep Cube fresh as edges are confirmed)
  - the cube_gen Cloud Run Job     (full rebuild across all tenants)

All the I/O-shaped reads honor offline_mode so this is testable without GCP.
"""
from __future__ import annotations

from typing import Any

from insnav_cube_client import sync_cube_model
from insnav_graph_store import list_approved_edges

from services.api_gateway.app.datasets import (
    get_column_profiles,
    list_all_ready_datasets,
    list_datasets_for_project,
    list_datasets_for_tenant,
)
from services.api_gateway.app.settings import get_settings


def sync_project(tenant_id: str, project_id: str) -> dict[str, Any]:
    """
    Build + write the Cube model for ONE project workspace (Phase 10). Datasets
    + approved edges are scoped to the project; the model lands at the
    per-project GCS path so the Cube container compiles it in isolation.
    """
    settings = get_settings()
    datasets = [d for d in list_datasets_for_project(tenant_id, project_id) if d.status == "ready"]
    columns_by_dataset = {d.id: get_column_profiles(d.id) for d in datasets}
    edges = [e.model_dump() for e in list_approved_edges(tenant_id, project_id)]

    return sync_cube_model(
        tenant_id=tenant_id,
        project_id=project_id,
        datasets=[d.model_dump() for d in datasets],
        columns_by_dataset=columns_by_dataset,
        edges=edges,
        bucket=settings.cube_model_bucket,
        prefix=settings.cube_model_prefix,
        offline=settings.offline_mode,
    )


def sync_tenant(tenant_id: str) -> dict[str, Any]:
    """
    Legacy/back-compat: build the tenant-level model from ALL the tenant's ready
    datasets (project_id=None path). Kept for pre-projects data + the cube_gen
    job's legacy bucket. New code paths use sync_project.
    """
    settings = get_settings()
    datasets = [d for d in list_datasets_for_tenant(tenant_id) if d.status == "ready"]
    columns_by_dataset = {d.id: get_column_profiles(d.id) for d in datasets}
    edges = [e.model_dump() for e in list_approved_edges(tenant_id)]

    return sync_cube_model(
        tenant_id=tenant_id,
        datasets=[d.model_dump() for d in datasets],
        columns_by_dataset=columns_by_dataset,
        edges=edges,
        bucket=settings.cube_model_bucket,
        prefix=settings.cube_model_prefix,
        offline=settings.offline_mode,
    )


def sync_all() -> dict[str, dict[str, Any]]:
    """
    Rebuild every project model + any legacy (no-project) tenant model. Used by
    the cube_gen job.
    """
    ready = list_all_ready_datasets()
    out: dict[str, dict[str, Any]] = {}
    for tenant_id, project_id in sorted({(d.tenant_id, d.project_id) for d in ready if d.project_id}):
        out[f"{tenant_id}/{project_id}"] = sync_project(tenant_id, project_id)
    for tenant_id in sorted({d.tenant_id for d in ready if not d.project_id}):
        out[tenant_id] = sync_tenant(tenant_id)
    return out


# Back-compat alias for the cube_gen job entrypoint.
sync_all_tenants = sync_all
