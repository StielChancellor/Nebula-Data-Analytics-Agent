"""
Centralized config via pydantic-settings. All knobs that vary between
environments (dev / prod / per-brand) live here, sourced from env vars.

Why a settings module: this keeps env-var names in one place and makes them
typed + documented. Anything reading os.environ directly is a smell.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # GCP wiring
    gcp_project: str = Field(default="insights-navigator-v2", alias="INSNAV_GCP_PROJECT")
    gcp_region: str = Field(default="us-central1", alias="INSNAV_GCP_REGION")
    staging_bucket: str = Field(
        default="insights-navigator-v2-staging", alias="INSNAV_STAGING_BUCKET"
    )
    """GCS bucket for resumable CSV uploads."""

    bq_raw_dataset: str = Field(default="raw", alias="INSNAV_BQ_RAW_DATASET")
    """BigQuery dataset that holds raw_<id> tables (L0 landing per PRD)."""

    # Firestore collection name for dataset metadata
    fs_datasets_collection: str = Field(
        default="datasets", alias="INSNAV_FS_DATASETS_COLLECTION"
    )
    # Firestore collection for project workspaces (Phase 10). A project groups
    # datasets + graph + cube model + locale + onboarding under one tenant.
    fs_projects_collection: str = Field(
        default="projects", alias="INSNAV_FS_PROJECTS_COLLECTION"
    )
    # Firestore collection for agent-led ingestion/onboarding sessions (Phase 10).
    fs_ingest_sessions_collection: str = Field(
        default="ingest_sessions", alias="INSNAV_FS_INGEST_SESSIONS_COLLECTION"
    )

    # --- Cube (Phase 5b) ---
    # Where generated Cube .js schemas are written for the Cube container to read.
    # Reuses the staging bucket with a dedicated prefix.
    cube_model_bucket: str = Field(
        default="insights-navigator-v2-staging", alias="INSNAV_CUBE_MODEL_BUCKET"
    )
    cube_model_prefix: str = Field(default="cube-model", alias="INSNAV_CUBE_MODEL_PREFIX")
    # Cube REST API base URL (the deployed Cube Cloud Run service). Empty until
    # Cube is deployed (Phase 5b apply); the query client falls back to offline.
    cube_api_url: str = Field(default="", alias="INSNAV_CUBE_API_URL")
    # Shared secret used to sign Cube API tokens (matches Cube's CUBEJS_API_SECRET).
    # Read from Secret Manager in prod; falls back to a dev value offline.
    cube_api_secret: str = Field(default="dev-cube-secret-change-me", alias="INSNAV_CUBE_API_SECRET")

    # --- Firebase Auth / Identity Platform (Phase 1.5) ---
    # Project that issues Firebase ID tokens. Empty → falls back to gcp_project.
    firebase_project: str = Field(default="", alias="INSNAV_FIREBASE_PROJECT")
    # Google's public JWK endpoint for Firebase Secure Token signing keys.
    firebase_jwks_url: str = Field(
        default="https://www.googleapis.com/robot/v1/metadata/jwk/securetoken@system.gserviceaccount.com",
        alias="INSNAV_FIREBASE_JWKS_URL",
    )

    def effective_firebase_project(self) -> str:
        return self.firebase_project or self.gcp_project

    # CORS — comma-separated origin list (or "*" in dev)
    cors_origins: str = Field(default="*", alias="INSNAV_CORS_ORIGINS")

    # Upload constraints (PRD requirement: support up to 5 GB files)
    upload_max_bytes: int = Field(
        default=5 * 1024 * 1024 * 1024, alias="INSNAV_UPLOAD_MAX_BYTES"
    )
    upload_signed_url_ttl_seconds: int = Field(
        default=3600, alias="INSNAV_UPLOAD_TTL_SECONDS"
    )
    # Read-before-commit preview (Phase 10-B): how many bytes of the uploaded
    # blob to sniff. 64 KB is plenty to infer types and is file-size-independent.
    preview_sample_bytes: int = Field(default=65536, alias="INSNAV_PREVIEW_SAMPLE_BYTES")

    # When true, skip live GCP calls (used in pytest). Defaults to detecting
    # the env var PYTEST_CURRENT_TEST so test runs are offline by default.
    offline_mode: bool = Field(default=False, alias="INSNAV_OFFLINE")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
