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

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from services.api_gateway.app.auth import Principal, current_principal
from services.api_gateway.app.datasets import (
    ColumnSpec,
    Dataset,
    IngestError,
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
    # Project workspace this upload belongs to (Phase 10). When set, the dataset
    # is scoped to the project and inherits the project's default locale unless
    # locale_hint is given explicitly.
    project_id: str | None = None
    locale_hint: str | None = Field(default=None, pattern="^(US|IN)$")


class StartUploadResponse(BaseModel):
    dataset_id: str
    signed_url: str
    gcs_blob_path: str
    expires_at: str
    """ISO-8601 timestamp after which the signed URL stops working."""


class CompleteUploadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str
    # Confirmed/overridden column types (Phase 10-B). When present they drive an
    # explicit BQ load schema + India-format normalization instead of autodetect.
    schema_overrides: list[ColumnSpec] | None = None


class CompleteUploadResponse(BaseModel):
    dataset_id: str
    status: str
    bq_table: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    error: str | None = None
    error_detail: IngestError | None = None
    # Phase 4: how many new edge proposals were discovered for the
    # just-uploaded dataset. Frontend surfaces this as a "3 edges to review"
    # callout pointing at the Graph tab.
    new_edge_proposals: int = 0


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_id: str


class PreviewColumn(BaseModel):
    name: str
    inferred_bq_type: str
    inferred_format: str | None = None
    sample_values: list[str] = Field(default_factory=list)
    nullable: bool = True


class PreviewResponse(BaseModel):
    dataset_id: str
    encoding: str
    delimiter: str
    has_header: bool
    columns: list[PreviewColumn]
    row_sample: list[list[str]] = Field(default_factory=list)
    truncated: bool = False


# ---------- endpoints ----------

@router.post("/start", response_model=StartUploadResponse)
def start_upload(
    req: StartUploadRequest,
    request: Request,
    principal: Annotated[Principal, Depends(current_principal)],
) -> StartUploadResponse:
    settings = get_settings()

    if req.size_bytes > settings.upload_max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file too large: max {settings.upload_max_bytes} bytes",
        )

    # Resolve the project workspace (Phase 10). If a project is named, it must
    # belong to the caller's tenant; the dataset inherits the project's locale
    # unless the request overrides it explicitly.
    locale_hint = req.locale_hint or "US"
    if req.project_id is not None:
        from services.api_gateway.app.projects import get_project

        project = get_project(req.project_id)
        if project is None or project.tenant_id != principal.tenant_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "project not found")
        if req.locale_hint is None:
            locale_hint = project.locale_default

    dataset_id = new_dataset_id()
    blob_path = gcs_blob_path(dataset_id, req.filename)

    # The browser will PUT the file directly to GCS cross-origin. A resumable
    # session created server-side carries no Origin, so GCS won't emit
    # Access-Control-Allow-Origin on the client's PUT and the browser blocks it
    # (even with bucket CORS = "*"). Binding the session to the caller's Origin
    # fixes this and is multi-brand-safe: whatever frontend origin calls us gets
    # bound to its own session.
    origin = request.headers.get("origin")

    signed_url, expires_at = _create_resumable_upload_url(
        blob_path=blob_path,
        content_type="text/csv",  # CSV-only v1
        ttl_seconds=settings.upload_signed_url_ttl_seconds,
        origin=origin,
    )

    ds = Dataset(
        id=dataset_id,
        tenant_id=principal.tenant_id,
        project_id=req.project_id,
        brand=principal.brand,
        label=req.label or req.filename,
        locale_hint=locale_hint,  # type: ignore[arg-type]
        source_filename=req.filename,
        source_size_bytes=req.size_bytes,
        gcs_blob_path=f"gs://{settings.staging_bucket}/{blob_path}",
        status="queued",
    )
    save_dataset(ds)

    # Associate the dataset with its project workspace (idempotent).
    if req.project_id is not None:
        from services.api_gateway.app.projects import add_dataset_to_project

        add_dataset_to_project(req.project_id, dataset_id)

    return StartUploadResponse(
        dataset_id=dataset_id,
        signed_url=signed_url,
        gcs_blob_path=blob_path,
        expires_at=expires_at,
    )


@router.post("/preview", response_model=PreviewResponse)
def preview_upload(
    req: PreviewRequest,
    principal: Annotated[Principal, Depends(current_principal)],
) -> PreviewResponse:
    """
    Read-before-commit: sniff the first N KB of the uploaded blob and return the
    inferred schema (encoding, delimiter, header, per-column types + samples) so
    the user/agent can review and override types before the committing load.
    """
    from services.api_gateway.app.datasets import get_dataset
    from services.api_gateway.app.sniffer import sniff_csv

    ds = get_dataset(req.dataset_id)
    if ds is None or ds.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dataset not found")

    sample = _read_sample_bytes(ds)
    result = sniff_csv(sample, ds.locale_hint)
    # Persist the preview so /complete can default to it and the UI can reload.
    # Firestore rejects nested arrays, so drop row_sample (list-of-lists) from the
    # stored copy — /complete only needs the per-column inferred types. The
    # response below still returns the full sniff result for the UI.
    persisted = {k: v for k, v in result.items() if k != "row_sample"}
    update_dataset_status(ds.id, ds.status, preview=persisted)

    return PreviewResponse(
        dataset_id=ds.id,
        encoding=result["encoding"],
        delimiter=result["delimiter"],
        has_header=result["has_header"],
        columns=result["columns"],  # dicts coerce to PreviewColumn
        row_sample=result["row_sample"],
        truncated=result["truncated"],
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

    # Confirmed/overridden types drive an explicit load; else fall back to the
    # persisted preview; else BQ autodetect (legacy behavior).
    explicit_schema = _resolve_schema(req, ds)

    stage = "load"
    try:
        update_dataset_status(ds.id, "loading")
        table_fqn, columns = _load_csv_to_bq(ds, explicit_schema=explicit_schema)
        stage = "profile"
        update_dataset_status(ds.id, "profiling", bq_table=table_fqn, column_count=len(columns))
        row_count = _profile_table(ds.id, table_fqn, columns)
        update_dataset_status(ds.id, "ready", row_count=row_count)
    except Exception as e:  # noqa: BLE001 — record a structured failure
        logger.exception("upload complete failed for dataset %s at stage %s", ds.id, stage)
        detail = _classify_ingest_failure(stage, e)  # type: ignore[arg-type]
        update_dataset_status(ds.id, "failed", error_detail=detail)
        # SEC H4: don't echo the raw exception (table names / SQL) in the 500 body.
        # The curated reason + hint are persisted on the dataset for the owner to
        # read via GET /v1/datasets/{id}.
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"ingestion failed at the {stage} stage; see the dataset's error detail.",
        ) from e

    # Phase 4: auto-discover edges for the just-loaded dataset. Best-effort —
    # the dataset is already 'ready', so a discovery hiccup must not fail it.
    new_proposals: int = 0
    try:
        from services.api_gateway.app.edge_proposer import propose_for_dataset
        from services.api_gateway.app.datasets import get_dataset as _get

        fresh = _get(ds.id)
        if fresh is not None:
            new_proposals = len(propose_for_dataset(fresh))
    except Exception:  # noqa: BLE001
        logger.exception("edge discovery failed for dataset %s", ds.id)

    return CompleteUploadResponse(
        dataset_id=ds.id, status="ready", bq_table=table_fqn,
        row_count=row_count, column_count=len(columns),
        new_edge_proposals=new_proposals,
    )


# ---------- GCP integration (real calls; mocked in tests) ----------

def _create_resumable_upload_url(
    blob_path: str,
    content_type: str,
    ttl_seconds: int,
    origin: str | None = None,
) -> tuple[str, str]:
    """
    Returns (signed_url, expires_at_iso). For dev/test without GCP creds,
    returns a placeholder URL so tests can run offline.

    `origin` is the browser origin that will PUT the bytes. Passing it binds
    the resumable session to that origin so GCS returns the CORS headers the
    browser needs (see start_upload for why this is required).
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
    # client PUTs the chunks to. `origin` binds the session to the calling
    # browser origin so the cross-origin PUT passes CORS (the bucket CORS
    # config is "*", but a server-initiated session needs the origin echoed
    # here or GCS omits Access-Control-Allow-Origin on the PUT response).
    url = blob.create_resumable_upload_session(
        content_type=content_type, size=None, origin=origin
    )
    expires_at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=ttl_seconds)).isoformat()
    return url, expires_at


def _resolve_schema(req: CompleteUploadRequest, ds: Dataset) -> list[ColumnSpec] | None:
    """Confirmed overrides > persisted preview > None (autodetect)."""
    if req.schema_overrides:
        return req.schema_overrides
    if ds.preview and ds.preview.get("columns"):
        return [
            ColumnSpec(
                name=c["name"],
                bq_type=c.get("inferred_bq_type", "STRING"),
                source_format=c.get("inferred_format"),
            )
            for c in ds.preview["columns"]
        ]
    return None


def _needs_normalize(spec: ColumnSpec) -> bool:
    """A format that BQ load can't ingest directly (DD-MM-YYYY, INR grouping...)."""
    return spec.source_format is not None and spec.source_format != "YYYY-MM-DD"


def _strptime_fmt(source_format: str) -> str:
    """'DD-MM-YYYY' -> '%d-%m-%Y' (YYYY first to avoid clobbering)."""
    return source_format.replace("YYYY", "%Y").replace("DD", "%d").replace("MM", "%m")


_ALLOWED_BQ_TYPES = {
    "DATE", "INT64", "NUMERIC", "FLOAT64", "BOOL", "STRING", "TIMESTAMP", "DATETIME", "TIME",
}


def build_normalize_sql(table_fqn: str, specs: list[ColumnSpec]) -> str:
    """
    CREATE-OR-REPLACE the loaded raw table, normalizing India-locale columns:
    DD-MM-YYYY dates via SAFE.PARSE_DATE, ₹/grouped numbers via regex-strip +
    SAFE_CAST. SAFE.* turns bad cells into NULL (surfaced via the profiler's
    null_pct) rather than failing the whole job. Pure string builder (testable).

    SEC C1: every identifier is quoted+escaped (quote_bq_identifier) and the
    date format + bq_type are validated against allowlists, so an attacker-
    controlled column name/format from a CSV header cannot inject SQL.
    """
    from services.api_gateway.app.sql_safety import quote_bq_identifier, safe_date_format

    exprs: list[str] = []
    for s in specs:
        col = quote_bq_identifier(s.name)
        if s.bq_type not in _ALLOWED_BQ_TYPES:
            raise ValueError(f"unsupported bq_type: {s.bq_type!r}")
        if _needs_normalize(s) and s.bq_type == "DATE":
            fmt = safe_date_format(_strptime_fmt(s.source_format or ""))
            exprs.append(f"SAFE.PARSE_DATE('{fmt}', {col}) AS {col}")
        elif _needs_normalize(s) and s.bq_type in ("NUMERIC", "FLOAT64", "INT64"):
            cleaned = f"REGEXP_REPLACE({col}, r'[^0-9.\\-]', '')"
            exprs.append(f"SAFE_CAST({cleaned} AS {s.bq_type}) AS {col}")
        else:
            exprs.append(f"{col} AS {col}")
    select_sql = ",\n  ".join(exprs)
    tbl = quote_bq_identifier(table_fqn)
    return f"CREATE OR REPLACE TABLE {tbl} AS\nSELECT\n  {select_sql}\nFROM {tbl}"


def _classify_ingest_failure(stage: str, exc: Exception) -> IngestError:
    """Turn a raw exception into a structured, actionable IngestError."""
    msg = str(exc)
    low = msg.lower()
    sample_bad: list[str] = []
    errs = getattr(exc, "errors", None)
    if isinstance(errs, list):
        for e in errs[:5]:
            if isinstance(e, dict) and e.get("message"):
                sample_bad.append(str(e["message"])[:300])

    reason, hint = "ingest_failed", None
    if any(k in low for k in ("permission", "denied", "accessdenied")):
        reason = "permission_denied"
        hint = "The runtime service account lacks BigQuery access on the raw dataset."
    elif any(k in low for k in ("could not parse", "invalid", "mismatch", "cannot be converted")):
        reason = "schema_type_mismatch"
        hint = "Some values don't match the chosen column types. Re-preview, adjust the types, and retry."
    elif stage == "load":
        reason = "load_failed"
        hint = "Check the file is valid CSV with a single header row and a consistent delimiter."
    elif stage == "profile":
        reason = "profile_failed"
        hint = "The data loaded but profiling failed. Retry; the file may have an unusual column."

    return IngestError(
        stage=stage,  # type: ignore[arg-type]
        reason=reason,
        message=(msg[:500] or "ingestion failed"),
        hint=hint,
        sample_bad_rows=sample_bad,
    )


def _read_sample_bytes(ds: Dataset) -> bytes:
    """First N KB of the uploaded blob (offline: a synthetic 2-col CSV)."""
    settings = get_settings()
    if settings.offline_mode:
        return b"city,revenue\nMumbai,125\nPune,50\n"
    from services.api_gateway.app.gcp_clients import storage_client

    prefix = f"gs://{settings.staging_bucket}/"
    if not ds.gcs_blob_path.startswith(prefix):
        return b""
    blob_path = ds.gcs_blob_path[len(prefix):]
    blob = storage_client().bucket(settings.staging_bucket).blob(blob_path)
    n = max(1, settings.preview_sample_bytes)
    return blob.download_as_bytes(start=0, end=n - 1)


def _load_csv_to_bq(
    ds: Dataset, explicit_schema: list[ColumnSpec] | None = None
) -> tuple[str, list[tuple[str, str]]]:
    """
    Submit a BQ load job from the GCS blob to `<project>.<raw_dataset>.<raw_id>`.
    Returns (table_fqn, [(column_name, bq_type), ...]).

    With `explicit_schema` (confirmed types), columns needing normalization load
    as STRING and a follow-up transform casts them (India dates/numbers). Without
    it, BQ autodetect is the fallback (legacy behavior).
    """
    settings = get_settings()
    table_fqn = f"{settings.gcp_project}.{settings.bq_raw_dataset}.{bq_table_name(ds.id)}"
    if settings.offline_mode:
        if explicit_schema:
            return table_fqn, [(s.name, s.bq_type) for s in explicit_schema]
        return table_fqn, [("city", "STRING"), ("revenue", "FLOAT64")]

    from google.cloud import bigquery

    from services.api_gateway.app.gcp_clients import bigquery_client

    client = bigquery_client()
    raw_dataset_ref = bigquery.DatasetReference(settings.gcp_project, settings.bq_raw_dataset)
    client.create_dataset(bigquery.Dataset(raw_dataset_ref), exists_ok=True)  # idempotent

    table_ref = raw_dataset_ref.table(bq_table_name(ds.id))
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        allow_quoted_newlines=True,
    )
    if explicit_schema:
        job_config.autodetect = False
        job_config.schema = [
            bigquery.SchemaField(s.name, "STRING" if _needs_normalize(s) else s.bq_type)
            for s in explicit_schema
        ]
    else:
        job_config.autodetect = True

    load_job = client.load_table_from_uri(ds.gcs_blob_path, table_ref, job_config=job_config)
    load_job.result()  # block until load completes

    # India-format normalization pass (only when something needs it).
    if explicit_schema and any(_needs_normalize(s) for s in explicit_schema):
        client.query(build_normalize_sql(table_fqn, explicit_schema)).result()

    table = client.get_table(table_ref)
    columns = [(f.name, str(f.field_type)) for f in table.schema]
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
