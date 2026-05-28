output "project_id" {
  value = var.project_id
}

output "artifact_registry_url" {
  value       = var.enable_artifact_registry ? "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.insnav[0].repository_id}" : null
  description = "Push backend images here (Docker host:port path)"
}

output "staging_bucket" {
  value       = var.enable_staging_bucket ? google_storage_bucket.staging[0].name : null
  description = "GCS bucket for resumable CSV uploads"
}

output "api_gateway_url" {
  value       = var.enable_cloud_run ? google_cloud_run_v2_service.api_gateway[0].uri : null
  description = "Cloud Run URL for the api_gateway (set as VITE_API_BASE on frontend)"
}

output "orchestrator_url" {
  value       = var.enable_cloud_run ? google_cloud_run_v2_service.orchestrator[0].uri : null
  description = "Cloud Run URL for the orchestrator (agent swarm)"
}

output "bq_datasets" {
  value = var.enable_bq_datasets ? {
    datasets = google_bigquery_dataset.datasets[0].dataset_id
    audit    = google_bigquery_dataset.audit[0].dataset_id
  } : null
}

output "service_accounts" {
  value = {
    api_gateway     = google_service_account.api_gateway.email
    orchestrator    = google_service_account.orchestrator.email
    compute_sandbox = google_service_account.compute_sandbox.email
  }
}
