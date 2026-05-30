# Cube container

The Cube semantic-layer service for Insights Navigator V2.0.

## How the model gets here

The data model is **not** baked into this image. The backend's cube-model sync
(`insnav_cube_client.sync`) writes generated `.js` schemas to GCS:

```
gs://<bucket>/<prefix>/<tenant_id>/<cube_name>.js
gs://<bucket>/<prefix>/<tenant_id>/__version__
```

`cube.js` reads them per-tenant at compile time via `repositoryFactory`, and
`schemaVersion` reads the `__version__` marker so Cube recompiles when the model
changes (e.g. after an edge is approved). No redeploy needed for model changes.

## Build + push (at deploy time)

```bash
REGION=us-central1
PROJECT=insights-navigator-v2
IMAGE="$REGION-docker.pkg.dev/$PROJECT/insnav/cube:latest"

docker build -t "$IMAGE" infra/cube/
docker push "$IMAGE"
```

> Verify the pinned base tag (`cubejs/cube:v1.6.52`) is still current:
> https://hub.docker.com/r/cubejs/cube/tags — bump in the Dockerfile if needed.

## Required runtime env (set by Terraform on the Cloud Run service)

| Env | Value |
|---|---|
| `CUBEJS_DB_TYPE` | `bigquery` |
| `CUBEJS_DB_BQ_PROJECT_ID` | `insights-navigator-v2` |
| `CUBEJS_API_SECRET` | shared secret (Secret Manager `cube-api-secret`) — must match backend `INSNAV_CUBE_API_SECRET` |
| `INSNAV_CUBE_MODEL_BUCKET` | the GCS bucket holding the model |
| `INSNAV_CUBE_MODEL_PREFIX` | `cube-model` |
| `CUBEJS_DEV_MODE` | `false` |

Credentials: the Cloud Run **runtime service account** provides ADC, which both
`@google-cloud/storage` (model reads) and the BigQuery driver (query execution)
use automatically. The SA needs `roles/bigquery.dataViewer`,
`roles/bigquery.jobUser`, and `roles/storage.objectViewer` (granted in
`infra/terraform/main.tf`).

## Local smoke test (optional)

```bash
docker build -t insnav-cube infra/cube/
docker run --rm -p 4000:4000 \
  -e CUBEJS_DB_TYPE=bigquery \
  -e CUBEJS_DB_BQ_PROJECT_ID=insights-navigator-v2 \
  -e CUBEJS_API_SECRET=dev-secret \
  -e INSNAV_CUBE_MODEL_BUCKET=insights-navigator-v2-staging \
  -e INSNAV_CUBE_MODEL_PREFIX=cube-model \
  -e GOOGLE_APPLICATION_CREDENTIALS=/adc.json \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/adc.json:ro" \
  insnav-cube
# then visit http://localhost:4000 (Cube Playground is dev-mode only; in prod the REST API is at /cubejs-api/v1/*)
```
