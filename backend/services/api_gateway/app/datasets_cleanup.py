"""
Full dataset deletion + cleanup (Phase 10-B).

Deleting a dataset must leave nothing behind: graph edges, the BQ raw table,
the GCS blob, the Firestore doc + columns, the project association, and the
published Cube model all have to be reconciled. Each step is best-effort and
logged so a partial failure still makes maximal progress; the whole thing is
idempotent (re-deleting a gone dataset is a no-op).

Order = most-derived first (edges → BQ → GCS → Firestore → project → cube)
so a mid-failure never leaves a reference pointing at a deleted thing.
"""
from __future__ import annotations

import logging
from typing import Any

from services.api_gateway.app.auth import Principal
from services.api_gateway.app.datasets import (
    Dataset,
    bq_table_name,
    delete_dataset_record,
    get_dataset,
)
from services.api_gateway.app.settings import get_settings

logger = logging.getLogger(__name__)


def delete_dataset_fully(dataset_id: str, principal: Principal) -> dict[str, Any]:
    """
    Delete a dataset and everything derived from it. Tenant-scoped and
    idempotent. Returns a summary of what was removed (for the API response).
    """
    ds = get_dataset(dataset_id)
    if ds is None or ds.tenant_id != principal.tenant_id:
        # Idempotent: already gone, or never visible to this tenant.
        return {"deleted": False, "reason": "not_found"}

    summary: dict[str, Any] = {
        "deleted": True,
        "edges": 0,
        "bq_table": False,
        "gcs_blob": False,
        "firestore": False,
        "project_detached": False,
        "cube_resynced": False,
    }

    # 1) Graph edges touching this dataset (either direction, any state).
    try:
        from insnav_graph_store import delete_edges_for_dataset

        summary["edges"] = delete_edges_for_dataset(ds.tenant_id, ds.id)
    except Exception:  # noqa: BLE001
        logger.exception("edge cleanup failed for dataset %s", ds.id)

    # 2) BQ raw table.
    try:
        _delete_bq_table(ds)
        summary["bq_table"] = True
    except Exception:  # noqa: BLE001
        logger.exception("BQ table delete failed for dataset %s", ds.id)

    # 3) GCS uploaded blob.
    try:
        _delete_gcs_blob(ds)
        summary["gcs_blob"] = True
    except Exception:  # noqa: BLE001
        logger.exception("GCS blob delete failed for dataset %s", ds.id)

    # 4) Firestore doc + columns subcollection.
    try:
        delete_dataset_record(ds.id)
        summary["firestore"] = True
    except Exception:  # noqa: BLE001
        logger.exception("Firestore delete failed for dataset %s", ds.id)

    # 5) Detach from its project.
    if ds.project_id:
        try:
            from services.api_gateway.app.projects import remove_dataset_from_project

            remove_dataset_from_project(ds.project_id, ds.id)
            summary["project_detached"] = True
        except Exception:  # noqa: BLE001
            logger.exception("project detach failed for dataset %s", ds.id)

    # 6) Re-publish the Cube model so the deleted dataset's cube is pruned.
    try:
        _resync_cube(ds)
        summary["cube_resynced"] = True
    except Exception:  # noqa: BLE001
        logger.exception("cube re-sync failed after deleting dataset %s", ds.id)

    return summary


# ---------- GCP-touching helpers (no-ops in offline_mode) ----------

def _delete_bq_table(ds: Dataset) -> None:
    settings = get_settings()
    if settings.offline_mode:
        return
    from services.api_gateway.app.gcp_clients import bigquery_client

    table_fqn = f"{settings.gcp_project}.{settings.bq_raw_dataset}.{bq_table_name(ds.id)}"
    bigquery_client().delete_table(table_fqn, not_found_ok=True)


def _delete_gcs_blob(ds: Dataset) -> None:
    settings = get_settings()
    if settings.offline_mode:
        return
    if not ds.gcs_blob_path:
        return
    from services.api_gateway.app.gcp_clients import storage_client

    # ds.gcs_blob_path is gs://<bucket>/<path>; strip the gs://bucket/ prefix.
    prefix = f"gs://{settings.staging_bucket}/"
    blob_path = ds.gcs_blob_path[len(prefix):] if ds.gcs_blob_path.startswith(prefix) else None
    if not blob_path:
        return
    bucket = storage_client().bucket(settings.staging_bucket)
    blob = bucket.blob(blob_path)
    if blob.exists():
        blob.delete()


def _resync_cube(ds: Dataset) -> None:
    """Re-publish the affected Cube model (project-scoped if possible)."""
    from services.api_gateway.app.cube_sync_service import sync_tenant

    try:
        # Phase 10-D introduces project-scoped sync; prefer it when available.
        from services.api_gateway.app.cube_sync_service import sync_project  # type: ignore

        if ds.project_id:
            sync_project(ds.tenant_id, ds.project_id)
            return
    except ImportError:
        pass
    sync_tenant(ds.tenant_id)
