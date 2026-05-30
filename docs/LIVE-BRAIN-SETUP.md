# Wiring a live brain (LLM) — step by step

The agent swarm works today, but without an LLM configured it **honestly
clarifies** (the stub can't interpret). To get real answers, give it a brain.
You can switch brains from the **dropdown** in the chat UI (next to "Ask"); this
guide makes those options actually usable.

There are two independent pieces:
- **A) the LLM** (so the agent can interpret questions), and
- **B) pointing the backend at the live Cube** (so answers run real SQL — Cube
  is already deployed and verified).

Everything below honors the $5/mo guardrail except the LLM's own per-query cost,
which only accrues when you actually ask questions.

---

## A) Give the agent an LLM

### Option 1 — Gemini (the default, recommended; PRD D6)

Gemini runs through **Vertex AI** with the backend's service-account ADC, so
there's **no API key to manage**.

1. Install the LLM SDKs into the backend image. They're already declared as the
   `[llm]` extra; add it to the Cloud Run image:
   ```dockerfile
   # backend/services/api_gateway/Dockerfile
   RUN pip install --no-cache-dir '.[gcp,llm]'   # was '.[gcp]'
   ```
2. The backend runtime SA already has `roles/aiplatform.user` (granted in
   Terraform for the orchestrator; grant it to the api_gateway SA too if you run
   chat there):
   ```bash
   gcloud projects add-iam-policy-binding insights-navigator-v2 \
     --member="serviceAccount:insnav-api-gateway@insights-navigator-v2.iam.gserviceaccount.com" \
     --role="roles/aiplatform.user"
   ```
3. Set the model env on the backend service (optional — `gemini-3.0-preview` is
   the default): `INSNAV_LLM_PRIMARY=gemini`, `INSNAV_LLM_MODEL=gemini-3.0-preview`.
4. Vertex AI must be available for your project + region (`aiplatform.googleapis.com`
   is already enabled). If `gemini-3.0-preview` isn't yet GA in `us-central1`,
   pick `gemini-2.5-pro` in the dropdown (or set `INSNAV_LLM_MODEL`).

> The dropdown calls `GET /v1/llm/options`, which reports `available: true/false`
> per model based on whether the SDK (and, for Claude, the key) is present. Gemini
> shows available once the `[llm]` extra is in the image.

### Option 2 — Claude (fallback / alternative)

1. Same `[llm]` extra in the Dockerfile.
2. Put your Anthropic key in Secret Manager and inject it:
   ```bash
   printf '%s' "$ANTHROPIC_API_KEY" | gcloud secrets create anthropic-api-key \
     --data-file=- --project=insights-navigator-v2   # (secret already exists; use: versions add)
   ```
   Then add an env on the backend Cloud Run service sourced from that secret:
   `ANTHROPIC_API_KEY` ← `anthropic-api-key:latest`.
3. Claude shows `available: true` in the dropdown once the key env is present.

### The dropdown / switching brains

- The chat request carries an optional `llm` (the chosen model id). The backend
  builds a router for that choice via `insnav_llm_router.build_router(...)`.
- If you pick a brain that isn't configured in this deploy, it **degrades to the
  stub** (the agent clarifies) rather than erroring — so the UI never 500s.
- Change the menu itself by editing `MODELS` in
  `backend/packages/llm_router/insnav_llm_router/router.py`.

---

## B) Point the backend at the live Cube

Cube is deployed (Phase 5b/5c) and answers real SQL. The backend just needs its
URL + the shared secret so `CubeQueryClient` hits it instead of the offline stub.

Set on the backend Cloud Run service:
```
INSNAV_CUBE_API_URL    = https://insnav-cube-q3rm3dw2tq-uc.a.run.app
INSNAV_CUBE_API_SECRET = (from Secret Manager: cube-api-secret:latest)
```
The backend mints a tenant-scoped Cube JWT and queries Cube; Cube compiles + runs
the SQL against BigQuery. Without `INSNAV_CUBE_API_URL`, answers are flagged
"illustrative (stub)".

> The Cube service is public but **JWT-enforced** (prod mode, Phase 5c), so this
> is safe. Make sure the backend's `INSNAV_CUBE_API_SECRET` matches Cube's
> `CUBEJS_API_SECRET` (both read `cube-api-secret`).

---

## Putting it together (deploy the backend)

The backend isn't deployed yet (`enable_cloud_run=false`). To go fully live:

1. Edit the Dockerfile to `.[gcp,llm]` (above).
2. Rebuild + push the backend image:
   ```bash
   gcloud builds submit backend --config=backend/cloudbuild.yaml \
     --substitutions=_IMAGE=us-central1-docker.pkg.dev/insights-navigator-v2/insnav/api:latest
   ```
3. Add backend env to the Cloud Run service in `infra/terraform/main.tf`
   (api_gateway container): `BOOTSTRAP_ADMIN_EMAIL/PASSWORD`, `INSNAV_JWT_SECRET`
   (← `insnav-jwt-secret`), `INSNAV_CUBE_API_URL`, `INSNAV_CUBE_API_SECRET`
   (← `cube-api-secret`), optional `INSNAV_LLM_PRIMARY/MODEL`, `INSNAV_CORS_ORIGINS`.
   (The Phase 1 api_gateway service block has no env yet — that's the one gap.)
4. `terraform apply -var=enable_cloud_run=true`.
5. Point the frontend's `VITE_API_BASE` at the backend URL and (optionally) deploy
   it to Firebase Hosting.

Then: open the app → **Ask** tab → pick a brain in the dropdown → ask
"total revenue by city" → you'll get a grounded answer with the interpretation
echo, data-health badge, and the real Cube query.

## Quick local test (no deploy)

```bash
cd backend && . .venv/Scripts/activate
pip install -e '.[gcp,llm]'
export INSNAV_LLM_PRIMARY=gemini INSNAV_LLM_MODEL=gemini-2.5-pro
export INSNAV_CUBE_API_URL=https://insnav-cube-q3rm3dw2tq-uc.a.run.app
export INSNAV_CUBE_API_SECRET=$(gcloud secrets versions access latest --secret=cube-api-secret)
export BOOTSTRAP_ADMIN_EMAIL=admin@local BOOTSTRAP_ADMIN_PASSWORD=changeme
export INSNAV_JWT_SECRET=$(python -c "import secrets;print(secrets.token_hex(24))")
uvicorn services.api_gateway.app.main:app --port 8000
# then drive it from frontend (pnpm dev) or curl /v1/chat with a bootstrap token
```
