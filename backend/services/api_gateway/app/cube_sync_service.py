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
    list_datasets_for_tenant,
)
from services.api_gateway.app.settings import get_settings


def sync_tenant(tenant_id: str) -> dict[str, Any]:
    """Build + write the full Cube model for one tenant. Returns the sync result."""
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


def sync_all_tenants() -> dict[str, dict[str, Any]]:
    """Rebuild every tenant's Cube model. Used by the cube_gen job."""
    tenants = sorted({d.tenant_id for d in list_all_ready_datasets()})
    return {t: sync_tenant(t) for t in tenants}
