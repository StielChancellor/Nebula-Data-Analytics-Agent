#!/usr/bin/env bash
# One-shot: enable the GCP APIs Terraform will manage.
# Idempotent. Run this once before `terraform apply` so the APIs exist when
# Terraform tries to use them.
#
# Usage:
#   PROJECT_ID=insights-navigator-v2 ./infra/scripts/enable-apis.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-insights-navigator-v2}"

APIS=(
  cloudbuild.googleapis.com
  run.googleapis.com
  artifactregistry.googleapis.com
  bigquery.googleapis.com
  aiplatform.googleapis.com
  secretmanager.googleapis.com
  firestore.googleapis.com
  storage.googleapis.com
  firebase.googleapis.com
  firebasehosting.googleapis.com
  iamcredentials.googleapis.com
  cloudresourcemanager.googleapis.com
)

echo "Enabling ${#APIS[@]} APIs on $PROJECT_ID ..."
gcloud services enable "${APIS[@]}" --project="$PROJECT_ID"
echo "Done."
