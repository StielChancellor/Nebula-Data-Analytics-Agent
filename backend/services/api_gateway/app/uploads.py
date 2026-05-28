"""
Upload endpoints + orchestration.

Flow (PRD Nebula §5.4 + 5GB-file architecture):
  1. POST /v1/uploads/start
       → server generates signed resumable upload URL for GCS
       → writes a Firestore Dataset doc with status=queued
       → returns dataset_id + signed_url
  2. Client PUTs the file bytes directly to GCS via the signed URL
       (chunked resumable; bypasses our API completely for any file size)
  3. POST /v1/uploads/complete
       → kicks off BQ load job from GCS → raw_<dataset_id>
       → on load success, runs profiler → writes column profiles to Firestore
       → updates Dataset status to "ready"
  4. GET /v1/datasets/{id} returns the current status (poll until ready/failed)

For v1 the load + profile happens inline in the /complete handler. Total
time for a 5 GB CSV: ~30-60s for load + a few seconds for profile. Cloud
Run's 60-minute request timeout covers it. We extract to a Cloud Run Job
in Phase 2.5 if this latency starts to bite.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.datasets import (
    Dataset,
    bq_table_name,
    gcs_blob_path,
    new_dataset_id,
    save_dataset,
    update_dataset_status,
)
from services.api_gateway.app.profiler import (
    build_profile_query,
    build_sample_query,
    parse_profile_row,
)
from services.api_gateway.app.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/uploads", tags=["uploads"])


# ---------- request / response shapes ----------

class StartUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    label: str | None = None
    locale_hint: str = Field(default="US", pattern="^(US|IN)$")


class StartUploadResponse(BaseModel):
    dataset_id: str
    signed_url: str
    gcs_blob_path: str
    expires_at: str
    """ISO-8601 timestamp after which the signed URL stops working."""


class CompleteUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str


class CompleteUploadResponse(BaseModel):
    dataset_id: str
    status: str
    bq_table: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    error: str | None = None
    # Phase 4: how many new edge proposals were discovered for the
    # just-uploaded dataset. Frontend surfaces this as a "3 edges to review"
    # callout pointing at the Graph tab.
    new_edge_proposals: int = 0


# ---------- endpoints ----------

@router.post("/start", response_model=StartUploadResponse)
def start_upload(
    req: StartUploadRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> StartUploadResponse:
    settings = get_settings()

    if req.size_bytes > settings.upload_max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file too large: max {settings.upload_max_bytes} bytes",
        )

    dataset_id = new_dataset_id()
    blob_path = gcs_blob_path(dataset_id, req.filename)

    signed_url, expires_at = _create_resumable_upload_url(
        blob_path=blob_path,
        content_type="text/csv",  # CSV-only v1
        ttl_seconds=settings.upload_signed_url_ttl_seconds,
    )

    ds = Dataset(
        id=dataset_id,
        tenant_id=principal.tenant_id,
        brand=principal.brand,
        label=req.label or req.filename,
        locale_hint=req.locale_hint,  # type: ignore[arg-type]
        source_filename=req.filename,
        source_size_bytes=req.size_bytes,
        gcs_blob_path=f"gs://{settings.staging_bucket}/{blob_path}",
        status="queued",
    )
    save_dataset(ds)

    return StartUploadResponse(
        dataset_id=dataset_id,
        signed_url=signed_url,
        gcs_blob_path=blob_path,
        expires_at=expires_at,
    )


@router.post("/complete", response_model=CompleteUploadResponse)
def complete_upload(
    req: CompleteUploadRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> CompleteUploadResponse:
    from services.api_gateway.app.datasets import get_dataset

    ds = get_dataset(req.dataset_id)
    if ds is None or ds.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")
    if ds.status not in {"queued", "uploading", "failed"}:
        # Already processed; just return current state
        return CompleteUploadResponse(
            dataset_id=ds.id, status=ds.status, bq_table=ds.bq_table,
            row_count=ds.row_count, column_count=ds.column_count, error=ds.error,
        )

    try:
        update_dataset_status(ds.id, "loading")
        table_fqn, columns = _load_csv_to_bq(ds)
        update_dataset_status(ds.id, "profiling", bq_table=table_fqn, column_count=len(columns))
        row_count = _profile_table(ds.id, table_fqn, columns)
        update_dataset_status(ds.id, "ready", row_count=row_count)

        # Phase 4: auto-discover edges for the just-loaded dataset.
        # Wrapped in try/except so a discovery hiccup doesn't fail the
        # whole upload — the dataset is already 'ready' at this point.
        new_proposals: int = 0
        try:
            from services.api_gateway.app.edge_proposer import propose_for_dataset
            from services.api_gateway.app.datasets import get_dataset as _get

            fresh = _get(ds.id)
            if fresh is not None:
                proposals = propose_for_dataset(fresh)
                new_proposals = len(proposals)
        except Exception:  # noqa: BLE001 — proposer failure must not undo upload
            logger.exception("edge discovery failed for dataset %s", ds.id)

        return CompleteUploadResponse(
            dataset_id=ds.id, status="ready", bq_table=table_fqn,
            row_count=row_count, column_count=len(columns),
            new_edge_proposals=new_proposals,
        )
    except Exception as e:  # noqa: BLE001 — final fallback, must record failure
        logger.exception("upload complete failed for dataset %s", ds.id)
        update_dataset_status(ds.id, "failed", error=str(e))
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, str(e)) from e


# ---------- GCP integration (real calls; mocked in tests) ----------

def _create_resumable_upload_url(blob_path: str, content_type: str, ttl_seconds: int) -> tuple[str, str]:
    """
    Returns (signed_url, expires_at_iso). For dev/test without GCP creds,
    returns a placeholder URL so tests can run offline.
    """
    settings = get_settings()
    if settings.offline_mode:
        return (
            f"https://example.invalid/upload/{blob_path}",
            (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=ttl_seconds)).isoformat(),
        )

    from services.api_gateway.app.gcp_clients import storage_client

    bucket = storage_client().bucket(settings.staging_bucket)
    blob = bucket.blob(blob_path)
    # Use create_resumable_upload_session — this returns a session URL the
    # client PUTs the chunks to. The bucket's CORS (set in Terraform) lets
    # the browser do this from any origin.
    url = blob.create_resumable_upload_session(content_type=content_type, size=None)
    expires_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=ttl_seconds)).isoformat()
    return url, expires_at


def _load_csv_to_bq(ds: Dataset) -> tuple[str, list[tuple[str, str]]]:
    """
    Submit a BQ load job from the GCS blob to `<project>.<raw_dataset>.<raw_id>`.
    Returns (table_fqn, [(column_name, bq_type), ...]).

    Phase 2 simplification: BQ autodetects schema. Phase 4 will let users
    confirm/override types before the load.
    """
    settings = get_settings()
    if settings.offline_mode:
        # Synthetic schema for tests
        return (f"{settings.gcp_project}.{settings.bq_raw_dataset}.{bq_table_name(ds.id)}",
                [("city", "STRING"), ("revenue", "FLOAT64")])

    from google.cloud import bigquery

    from services.api_gateway.app.gcp_clients import bigquery_client

    client = bigquery_client()
    raw_dataset_ref = bigquery.DatasetReference(settings.gcp_project, settings.bq_raw_dataset)
    # Create raw dataset on demand (idempotent)
    client.create_dataset(bigquery.Dataset(raw_dataset_ref), exists_ok=True)

    table_ref = raw_dataset_ref.table(bq_table_name(ds.id))
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        allow_quoted_newlines=True,
    )
    load_job = client.load_table_from_uri(ds.gcs_blob_path, table_ref, job_config=job_config)
    load_job.result()  # block until load completes (free op, but can take seconds)

    table = client.get_table(table_ref)
    columns = [(f.name, str(f.field_type)) for f in table.schema]
    table_fqn = f"{settings.gcp_project}.{settings.bq_raw_dataset}.{table.table_id}"
    return table_fqn, columns


def _profile_table(dataset_id: str, table_fqn: str, columns: list[tuple[str, str]]) -> int:
    """Run the profile + sample queries; persist column profiles; return row count."""
    settings = get_settings()
    if settings.offline_mode:
        # Skip real profiling in tests
        from services.api_gateway.app.datasets import ColumnProfile, save_column_profiles

        profiles = [
            ColumnProfile(name=c, type=t, row_count=0, null_count=0, null_pct=0.0,
                           distinct_count=None, min_value=None, max_value=None)
            for c, t in columns
        ]
        save_column_profiles(dataset_id, profiles)
        return 0

    from services.api_gateway.app.datasets import save_column_profiles
    from services.api_gateway.app.gcp_clients import bigquery_client

    client = bigquery_client()
    agg_query = build_profile_query(table_fqn, columns)
    sample_query = build_sample_query(table_fqn, [c for c, _ in columns], n=5)

    agg_row = next(iter(client.query(agg_query).result()))
    samples = [dict(r.items()) for r in client.query(sample_query).result()]
    profiles = parse_profile_row(dict(agg_row.items()), columns, samples)
    save_column_profiles(dataset_id, profiles)
    return int(agg_row.get("__total_rows", 0) or 0)
