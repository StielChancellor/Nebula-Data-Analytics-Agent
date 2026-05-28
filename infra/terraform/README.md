# Infra — Terraform

GCP infrastructure-as-code for Project Insights Navigator V2.0.

## Cost guardrail (PRD Hard Constraint #10)

**No service costing > $5/month is added without explicit user approval.**

This Terraform deliberately avoids:
- **Spanner Graph** (~$650/mo minimum) — we use NetworkX + Firestore instead (PRD D10).
- **Cloud SQL** (~$10-15/mo for smallest instance) — Firestore covers our metadata needs.
- **Memorystore Redis** (~$50/mo smallest) — defer until we actually need a canonical-query cache that beats Firestore.
- **Dedicated Vertex AI endpoints** (idle-cost) — Gemini calls use the shared/online API.

Everything below scales to zero or is free-tier:

| Resource | Cost at idle | Notes |
|---|---|---|
| Cloud Run services | $0 | Free tier covers MVP traffic |
| Cloud Run jobs | $0 | Pay per invocation |
| BigQuery | $0 | Free tier 1 TB/month query + 10 GB storage |
| Firestore | $0 | Free tier 1 GiB storage + generous reads/writes |
| Cloud Storage | $0 | Free tier 5 GB |
| Artifact Registry | ~$0.10/mo | Per GB stored; first 0.5 GB free |
| Secret Manager | $0 | First 6 active secret versions free |
| Firebase Hosting | $0 | Free tier 10 GB transfer/month |

## Prerequisites

1. `gcloud auth login` (and `gcloud auth application-default login` for Terraform)
2. `gcloud config set project insights-navigator-v2`
3. Billing enabled on the project
4. `terraform >= 1.6` installed

## Workflow

```bash
# First time
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars: set project_id, region, brand_id

terraform init
terraform plan      # ALWAYS review the plan
terraform apply     # Creates resources
```

**Phase 0 status:** this scaffold is intentionally not yet applied. Review the
plan before running `apply`. Most resources are gated behind `enable_*`
toggles so you can stand up infra incrementally.

## Deploying to a new GCP project (the deployable-template flow)

1. `gcloud projects create <new-id>`
2. Enable billing on the project
3. `gcloud config set project <new-id>`
4. Edit `terraform.tfvars` → set `project_id = "<new-id>"`
5. `terraform init` (use a different state backend per project — see backend.tf)
6. `terraform plan && terraform apply`

The same .tf source produces independent GCP estates per project. Pair with
`pnpm build --mode <brand>` from `frontend/apps/web` to ship the per-brand
frontend to that project's Firebase Hosting target.
