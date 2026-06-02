"""
Cube model sync (Phase 5b).

Writes generated Cube .js schema files to GCS so the deployed Cube container
can read them via its `repositoryFactory` (see infra/cube/cube.js). One model
directory per tenant:

    gs://<bucket>/<prefix>/<tenant_id>/<cube_name>.js
    gs://<bucket>/<prefix>/<tenant_id>/__version__        (sha256 of all files)

The Cube container's `schemaVersion` reads `__version__`; when it changes,
Cube recompiles the data model — so approving a new edge → re-sync → Cube
picks up the new join on its next query without a restart.

Offline mode keeps an in-memory model store so tests + local dev work
without GCS.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .generator import build_tenant_schemas, render_to_js
from .models import CubeSchema

# ---------- offline store ----------

# tenant_id -> {"files": {filename: content}, "version": str}
_OFFLINE_MODEL: dict[str, dict[str, Any]] = {}


def reset_offline_model() -> None:
    _OFFLINE_MODEL.clear()


def _model_key(tenant_id: str, project_id: str | None) -> str:
    return tenant_id if project_id is None else f"{tenant_id}/{project_id}"


def read_offline_model(tenant_id: str, project_id: str | None = None) -> dict[str, Any]:
    """Test/inspection helper. Returns {"files": {...}, "version": str} or {}."""
    return _OFFLINE_MODEL.get(_model_key(tenant_id, project_id), {})


# ---------- rendering ----------

def render_model_files(schemas: list[CubeSchema]) -> dict[str, str]:
    """Map each schema to a {filename: js_content} entry."""
    return {f"{s.name}.js": render_to_js(s) for s in schemas}


def model_version(files: dict[str, str]) -> str:
    """
    Deterministic content hash across all files. Used as Cube's schemaVersion
    so identical model content always yields the same version string (and a
    changed model yields a new one → Cube recompiles).
    """
    h = hashlib.sha256()
    for name in sorted(files):
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(files[name].encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


# ---------- sync ----------

def sync_cube_model(
    *,
    tenant_id: str,
    project_id: str | None = None,
    datasets: list[dict[str, Any]],
    columns_by_dataset: dict[str, list[dict[str, Any]]],
    edges: list[dict[str, Any]],
    bucket: str,
    prefix: str = "cube-model",
    offline: bool = False,
) -> dict[str, Any]:
    """
    Build + write a Cube model. Scoped per project (Phase 10): models land at
    `<prefix>/<tenant>/<project>/`. project_id=None keeps the legacy
    `<prefix>/<tenant>/` path for back-compat. Returns
    {"version", "file_count", "cube_names"}. Idempotent.
    """
    schemas = build_tenant_schemas(
        datasets=datasets, columns_by_dataset=columns_by_dataset, edges=edges
    )
    files = render_model_files(schemas)
    version = model_version(files)

    if offline:
        _OFFLINE_MODEL[_model_key(tenant_id, project_id)] = {"files": dict(files), "version": version}
        return _result(version, files, schemas)

    _write_to_gcs(
        bucket=bucket, prefix=prefix, tenant_id=tenant_id,
        project_id=project_id, files=files, version=version,
    )
    return _result(version, files, schemas)


def _result(version: str, files: dict[str, str], schemas: list[CubeSchema]) -> dict[str, Any]:
    return {
        "version": version,
        "file_count": len(files),
        "cube_names": [s.name for s in schemas],
    }


def _write_to_gcs(
    *, bucket: str, prefix: str, tenant_id: str, project_id: str | None,
    files: dict[str, str], version: str,
) -> None:
    """
    Write each model file + the version marker. Deletes stale .js files that
    are no longer part of the model (e.g. a dataset was removed) so the Cube
    container never compiles a cube for a dataset that no longer exists.
    """
    from google.cloud import storage  # lazy import — keeps module import cheap

    client = storage.Client()
    gcs_bucket = client.bucket(bucket)
    base = f"{prefix}/{tenant_id}" if project_id is None else f"{prefix}/{tenant_id}/{project_id}"

    # 1) Write current files.
    desired_blob_names = set()
    for filename, content in files.items():
        blob_name = f"{base}/{filename}"
        desired_blob_names.add(blob_name)
        gcs_bucket.blob(blob_name).upload_from_string(content, content_type="application/javascript")

    # 2) Version marker.
    version_blob = f"{base}/__version__"
    gcs_bucket.blob(version_blob).upload_from_string(version, content_type="text/plain")

    # 3) Prune stale .js files no longer in the model.
    for blob in client.list_blobs(bucket, prefix=f"{base}/"):
        if blob.name.endswith(".js") and blob.name not in desired_blob_names:
            blob.delete()
