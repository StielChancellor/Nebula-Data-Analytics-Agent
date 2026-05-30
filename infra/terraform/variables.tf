variable "project_id" {
  type        = string
  description = "GCP project ID (e.g. insights-navigator-v2)."
}

variable "region" {
  type        = string
  default     = "us-central1"
  description = "Default GCP region for Cloud Run, Artifact Registry, GCS bucket."
}

variable "bq_location" {
  type        = string
  default     = "US"
  description = "BigQuery multi-region. Free tier is US/EU."
}

variable "brand_id" {
  type        = string
  default     = "nebula"
  description = "Brand identifier. Used to name brand-scoped resources."
}

variable "firebase_hosting_targets" {
  type        = list(string)
  default     = ["nebula"]
  description = "Brand IDs to provision Firebase Hosting targets for. Each gets its own subdomain."
}

# --- Feature toggles (stand up infra incrementally to keep costs $0) ---

variable "enable_artifact_registry" {
  type    = bool
  default = true
}

variable "enable_staging_bucket" {
  type    = bool
  default = true
}

variable "enable_bq_datasets" {
  type    = bool
  default = true
}

variable "enable_firestore" {
  type    = bool
  default = true
}

variable "enable_secrets" {
  type    = bool
  default = true
}

variable "enable_cloud_run" {
  type        = bool
  default     = false
  description = "Turn on after the first backend image is built and pushed to Artifact Registry."
}

variable "enable_cube" {
  type        = bool
  default     = false
  description = "Phase 5b: deploy the Cube semantic-layer Cloud Run service + cube-gen job. Turn on after the cube image is built and pushed. Scales to zero ($0 at idle)."
}

variable "enable_firebase_hosting" {
  type        = bool
  default     = false
  description = "Requires interactive Firebase project init via the Firebase console first."
}

# --- Tagging ---

variable "labels" {
  type = map(string)
  default = {
    project = "insights-navigator-v2"
    managed = "terraform"
  }
}
