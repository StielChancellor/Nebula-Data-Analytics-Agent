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

    # CORS — comma-separated origin list (or "*" in dev)
    cors_origins: str = Field(default="*", alias="INSNAV_CORS_ORIGINS")

    # Upload constraints (PRD requirement: support up to 5 GB files)
    upload_max_bytes: int = Field(
        default=5 * 1024 * 1024 * 1024, alias="INSNAV_UPLOAD_MAX_BYTES"
    )
    upload_signed_url_ttl_seconds: int = Field(
        default=3600, alias="INSNAV_UPLOAD_TTL_SECONDS"
    )

    # When true, skip live GCP calls (used in pytest). Defaults to detecting
    # the env var PYTEST_CURRENT_TEST so test runs are offline by default.
    offline_mode: bool = Field(default=False, alias="INSNAV_OFFLINE")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
