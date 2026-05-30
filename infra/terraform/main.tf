###############################################################################
# Insights Navigator V2.0 — root infra
#
# Cost guardrail (PRD Hard Constraint #10): every resource here is either free
# tier or scale-to-zero. Spanner Graph / Cloud SQL / dedicated Vertex endpoints
# are deliberately NOT included — see README.md.
###############################################################################

# ---------- 1) Enable APIs ----------
locals {
  required_apis = [
    "cloudbuild.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "aiplatform.googleapis.com", # Vertex AI Gemini
    "secretmanager.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudresourcemanager.googleapis.com",
  ]
}

resource "google_project_service" "enabled" {
  for_each                   = toset(local.required_apis)
  service                    = each.key
  disable_dependent_services = false
  disable_on_destroy         = false
}

# ---------- 2) Artifact Registry (Docker images) ----------
resource "google_artifact_registry_repository" "insnav" {
  count         = var.enable_artifact_registry ? 1 : 0
  location      = var.region
  repository_id = "insnav"
  description   = "Docker images for Insights Navigator V2.0 services"
  format        = "DOCKER"
  labels        = var.labels
  depends_on    = [google_project_service.enabled]
}

# ---------- 3) GCS staging bucket (resumable CSV uploads) ----------
resource "google_storage_bucket" "staging" {
  count    = var.enable_staging_bucket ? 1 : 0
  name     = "${var.project_id}-staging"
  location = var.region
  labels   = var.labels

  uniform_bucket_level_access = true
  force_destroy               = false

  # PRD Nebula §5.4: CORS must allow `Location` + `x-goog-resumable` response
  # headers so the resumable PUT flow works from the browser.
  cors {
    origin          = ["*"] # tighten to brand origins before prod
    method          = ["GET", "POST", "PUT", "OPTIONS"]
    response_header = ["Content-Type", "Location", "x-goog-resumable"]
    max_age_seconds = 3600
  }

  lifecycle_rule {
    condition { age = 30 }
    action { type = "Delete" } # Staging is ephemeral — wipe after 30d
  }

  depends_on = [google_project_service.enabled]
}

# ---------- 4) BigQuery datasets ----------
resource "google_bigquery_dataset" "datasets" {
  count                       = var.enable_bq_datasets ? 1 : 0
  dataset_id                  = "datasets"
  location                    = var.bq_location
  default_table_expiration_ms = null
  labels                      = var.labels
  description                 = "Cleaned, modeled datasets (L1+) the agent queries via Cube"
  depends_on                  = [google_project_service.enabled]
}

resource "google_bigquery_dataset" "audit" {
  count       = var.enable_bq_datasets ? 1 : 0
  dataset_id  = "audit"
  location    = var.bq_location
  labels      = var.labels
  description = "Append-only audit log of every query (PRD § Features lifted from Metabase)"
  depends_on  = [google_project_service.enabled]
}

# raw_* datasets are created on demand by the ingestion service, not here.

# ---------- 5) Firestore (native mode) ----------
# Holds: users, tenant_access, dashboards, pinned recipes, brand configs,
# knowledge-graph edges (PRD D10 — NetworkX in-process + Firestore persistence).
resource "google_firestore_database" "default" {
  count       = var.enable_firestore ? 1 : 0
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.enabled]
}

# ---------- 6) Secret Manager — placeholders ----------
resource "google_secret_manager_secret" "jwt" {
  count     = var.enable_secrets ? 1 : 0
  secret_id = "insnav-jwt-secret"
  replication {
    auto {}
  }
  labels     = var.labels
  depends_on = [google_project_service.enabled]
}

resource "google_secret_manager_secret" "anthropic_api_key" {
  count     = var.enable_secrets ? 1 : 0
  secret_id = "anthropic-api-key"
  replication {
    auto {}
  }
  labels     = var.labels
  depends_on = [google_project_service.enabled]
}

# Phase 5b: shared secret signing Cube API tokens. Backend
# (INSNAV_CUBE_API_SECRET) and the Cube service (CUBEJS_API_SECRET) must read
# the SAME value. Add a version after apply:
#   python -c "import secrets;print(secrets.token_hex(24))" | \
#     gcloud secrets versions add cube-api-secret --data-file=-
resource "google_secret_manager_secret" "cube_api_secret" {
  count     = var.enable_secrets ? 1 : 0
  secret_id = "cube-api-secret"
  replication {
    auto {}
  }
  labels     = var.labels
  depends_on = [google_project_service.enabled]
}

# ---------- 7) Service accounts ----------
resource "google_service_account" "api_gateway" {
  account_id   = "insnav-api-gateway"
  display_name = "Insights Navigator — API Gateway runtime SA"
}

resource "google_service_account" "orchestrator" {
  account_id   = "insnav-orchestrator"
  display_name = "Insights Navigator — Orchestrator (agent swarm) runtime SA"
}

resource "google_service_account" "compute_sandbox" {
  account_id   = "insnav-compute-sandbox"
  display_name = "Insights Navigator — Compute sandbox (Stats/Maths) runtime SA"
}

# IAM roles for the orchestrator SA (most privileged of the three)
locals {
  orchestrator_roles = [
    "roles/bigquery.dataEditor",
    "roles/bigquery.jobUser",
    "roles/datastore.user",
    "roles/secretmanager.secretAccessor",
    "roles/aiplatform.user",
    "roles/storage.objectUser",
  ]
}

resource "google_project_iam_member" "orchestrator" {
  for_each = toset(local.orchestrator_roles)
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.orchestrator.email}"
}

resource "google_project_iam_member" "api_gateway" {
  for_each = toset([
    "roles/datastore.user",               # Firestore reads for /v1/me/*
    "roles/secretmanager.secretAccessor", # JWT secret + cube API secret
    "roles/storage.objectUser",           # write/prune the Cube model in GCS (Phase 5b sync)
    "roles/bigquery.dataViewer",          # profiler + edge-overlap queries
    "roles/bigquery.jobUser",             # run those queries
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.api_gateway.email}"
}

# ---------- Cube runtime SA (Phase 5b) ----------
resource "google_service_account" "cube" {
  account_id   = "insnav-cube"
  display_name = "Insights Navigator — Cube semantic-layer runtime SA"
}

resource "google_project_iam_member" "cube" {
  for_each = toset([
    "roles/bigquery.dataViewer",          # read the raw tables to answer queries
    "roles/bigquery.jobUser",             # run the compiled SQL
    "roles/storage.objectViewer",         # read the data model from GCS
    "roles/secretmanager.secretAccessor", # read the cube API secret
  ])
  project = var.project_id
  role    = each.key
  member  = "serviceAccount:${google_service_account.cube.email}"
}

# ---------- 8) Cloud Run (gated until the first image exists) ----------
# Toggle var.enable_cloud_run = true after `make build-backend && docker push`.
resource "google_cloud_run_v2_service" "api_gateway" {
  count    = var.enable_cloud_run ? 1 : 0
  name     = "insnav-api-gateway"
  location = var.region

  template {
    service_account = google_service_account.api_gateway.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/insnav/api:latest"
      ports { container_port = 8080 }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }
    }
    scaling {
      min_instance_count = 0 # scale to zero ($0 at idle)
      max_instance_count = 5
    }
  }
  depends_on = [google_artifact_registry_repository.insnav]
}

resource "google_cloud_run_v2_service" "orchestrator" {
  count    = var.enable_cloud_run ? 1 : 0
  name     = "insnav-orchestrator"
  location = var.region

  template {
    service_account = google_service_account.orchestrator.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/insnav/orchestrator:latest"
      ports { container_port = 8080 }
      resources {
        limits = {
          cpu    = "2"
          memory = "1Gi"
        }
      }
    }
    scaling {
      # PRD D10 mitigation: pin to single instance v1 so NetworkX in-process
      # graph stays consistent (no cross-instance write races).
      min_instance_count = 1
      max_instance_count = 1
    }
  }
  depends_on = [google_artifact_registry_repository.insnav]
}

# ---------- 9) Cube semantic layer (Phase 5b, gated on enable_cube) ----------
# Scales to zero — $0 at idle. Reads its data model from GCS (written by the
# backend sync) and queries BigQuery via the cube runtime SA's ADC.
resource "google_cloud_run_v2_service" "cube" {
  count    = var.enable_cube ? 1 : 0
  name     = "insnav-cube"
  location = var.region

  template {
    service_account = google_service_account.cube.email
    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/insnav/cube:latest"
      ports { container_port = 8080 }
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
      env {
        name  = "CUBEJS_DB_TYPE"
        value = "bigquery"
      }
      env {
        name  = "CUBEJS_DB_BQ_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "CUBEJS_DEV_MODE"
        value = "false"
      }
      env {
        name  = "INSNAV_CUBE_MODEL_BUCKET"
        value = "${var.project_id}-staging"
      }
      env {
        name  = "INSNAV_CUBE_MODEL_PREFIX"
        value = "cube-model"
      }
      env {
        name = "CUBEJS_API_SECRET"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.cube_api_secret[0].secret_id
            version = "latest"
          }
        }
      }
    }
    scaling {
      min_instance_count = 0
      max_instance_count = 3
    }
  }
  depends_on = [
    google_artifact_registry_repository.insnav,
    google_secret_manager_secret.cube_api_secret,
  ]
}

# cube-gen Cloud Run JOB — full rebuild of every tenant's Cube model. Uses the
# backend image with a different entrypoint command. Run on a schedule or
# manually; the api_gateway also syncs incrementally on edge approve.
resource "google_cloud_run_v2_job" "cube_gen" {
  count    = var.enable_cube ? 1 : 0
  name     = "insnav-cube-gen"
  location = var.region

  template {
    template {
      service_account = google_service_account.api_gateway.email
      containers {
        image   = "${var.region}-docker.pkg.dev/${var.project_id}/insnav/api:latest"
        command = ["python", "-m", "services.cube_gen.app.main"]
        env {
          name  = "INSNAV_CUBE_MODEL_BUCKET"
          value = "${var.project_id}-staging"
        }
        env {
          name  = "INSNAV_CUBE_MODEL_PREFIX"
          value = "cube-model"
        }
        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }
      }
      timeout = "600s"
    }
  }
  depends_on = [google_artifact_registry_repository.insnav]
}
