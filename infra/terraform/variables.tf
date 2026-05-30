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

variable "enable_orchestrator" {
  type        = bool
  default     = false
  description = "Deploy the separate orchestrator service. The agent swarm runs in-process in api_gateway (PRD D5), so this stays off until the swarm is extracted + its image built."
}

variable "bootstrap_admin_email" {
  type        = string
  default     = "admin@insnav.local"
  description = "Break-glass admin email (password lives in Secret Manager)."
}

variable "llm_primary" {
  type        = string
  default     = "gemini"
  description = "Default chat brain provider (gemini|claude|stub)."
}

variable "llm_model" {
  type        = string
  default     = "gemini-2.5-pro"
  description = "Default Gemini model (a known-available Vertex model)."
}

variable "enable_identity_platform" {
  type        = bool
  default     = false
  description = <<-EOT
    Phase 1.5: provision Identity Platform (Firebase Auth) config + a default
    tenant + a browser API key. Default off. First-time Identity Platform
    enablement may require a one-time "Get Started" click in the console
    (the API can't always self-initialize) — see docs/PHASE-1.5-STATUS.md.
    The backend already verifies Firebase tokens regardless of this toggle.
  EOT
}

variable "enable_identity_platform_tenant" {
  type        = bool
  default     = false
  description = <<-EOT
    Create a named Identity Platform tenant (multi-brand isolation). Default
    off — single-tenant works for the MVP (users land in the default tenant and
    the backend maps them to "default"). Multi-tenancy must be enabled on the
    project first (Admin API multiTenant.allowTenants=true). The provider's
    named-tenant create can be finicky; turn this on per-brand once you onboard
    a second brand.
  EOT
}

variable "enable_cube_store" {
  type        = bool
  default     = false
  description = <<-EOT
    Phase 5c: run a Cube Store sidecar in the Cube service so Cube runs in
    PRODUCTION mode (JWT enforced, no Playground) instead of dev mode. Durable
    Cube Store data lives in GCS. Default off.

    Cost note: with min_instance_count = 0 it scales to zero ($0 idle) but the
    Cube Store metastore cold-starts per request. A true production Cube Store
    wants always-on (min_instance_count = 1) which costs > $5/mo — that exceeds
    the cost guardrail and needs explicit approval (change the scaling block).
  EOT
}

variable "cube_dev_mode" {
  type        = bool
  default     = false
  description = <<-EOT
    Run Cube with CUBEJS_DEV_MODE. Dev mode bundles an embedded Cube Store so a
    SINGLE container can execute queries (no separate Cube Store cluster). It
    also exposes the Playground and relaxes JWT verification, so the service
    MUST be kept private (no allUsers invoker) when this is true.

    Secure default is false (production mode). For production with public
    access, deploy a real Cube Store and leave this false. Set true (via
    terraform.tfvars) only for a single-container MVP/demo on a private service.
  EOT
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
