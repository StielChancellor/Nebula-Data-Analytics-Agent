# Project Insights Navigator V2.0

> A modular, GCP-native intelligent BI analyst platform. Forkable, white-labelable, deployable.

**Repo:** https://github.com/StielChancellor/Nebula-Data-Analytics-Agent
**Default GCP project:** `insights-navigator-v2`
**Default brain:** Gemini 3.0 Preview (with Anthropic Claude as fallback)
**License:** MIT

This is a **deployable template**. Fork it, point it at a new GCP project, configure a brand, deploy. The same backend can serve multiple frontend brands; the same frontend codebase can build for any brand by setting `--mode <brand>`.

---

## What it is

An intelligent BI agent that lets non-engineers ask plain-English questions of messy, siloed marketing + transaction data and get back interactive charts, pivot tables, and narrated insights — with PhD-level statistical rigor and the rule that **LLMs orchestrate and narrate; deterministic code computes**.

Three lineages combined into one platform:

1. **Nebula / Insights Navigator UX** — Excel-grade drag-drop pivot table, pinnable dashboards, region-aware locales (India ₹ Lakh/Crore + Apr-Mar FY, US $ M/B + Jan-Dec FY), multi-brand skin layer.
2. **Intelligent Business Analyst architecture** — five-layer determinism stack (raw BQ → identity → human-confirmed knowledge graph → Cube semantic layer → agent swarm) with seven failure-mode mitigations.
3. **Metabase-inspired BI primitives** — dashboard-level parameter linking, public share links + embedding SDK, x-ray-style proactive insights, multi-database connector ecosystem.

See [`PRD.md`](./PRD.md) for the full product spec, architecture, build order, and acceptance criteria.

---

## Repo layout

```
frontend/                React + Vite + Tailwind monorepo (pnpm workspace)
  apps/web/              Main SPA entry; brand mode at build time, theme tokens at runtime
  apps/embed/            Smaller iframe-embed bundle for public share + customer embedding
  packages/              Frontend shared TS packages (locale, brand-runtime, pivot, dashboards, chat, charts, ...)
  tools/                 OpenAPI codegen, brand-build orchestration
backend/                 FastAPI + Python services (Cloud Run)
  services/              api-gateway, orchestrator, ingestion, graph-builder, cube-gen, compute-sandbox
  packages/              Python shared packages (agents, contracts, llm-router, locale, audit, ...)
infra/
  terraform/             GCP IaC (NOT applied without explicit approval)
  cube-schema/           Generated Cube .js files (PR-reviewed for revenue-touching changes)
  scripts/               One-shot deploy/setup scripts
.github/workflows/       CI: lint, typecheck, build, test, golden-question regression
docs/                    Architecture notes, runbooks, onboarding
PRD.md                   Master product requirements document
```

---

## Quick start (local dev)

> **Prerequisites:** Node 20 LTS, pnpm 9+, Python 3.11+, gcloud CLI authed against your GCP project. Terraform CLI if you'll touch infra.

```bash
# Install everything
make install

# Run frontend (Vite dev server, http://localhost:5173)
make dev-frontend

# Run backend (FastAPI on http://localhost:8000, auto-reload)
make dev-backend

# Both at once
make dev
```

---

## Deploying as a new brand (the deployable-template flow)

The whole point of the monorepo layout: this repo is the platform-in-a-box. To launch a new brand on a fresh GCP project:

1. **Fork or clone this repo.**
2. **Create the GCP project**: `gcloud projects create <new-project-id>`. Enable billing.
3. **Add a brand entry**:
   - `frontend/packages/brand-static/src/brands/<brand-id>/` — logo, favicon, brand metadata.
   - `frontend/.env.<brand-id>` — `VITE_BRAND=<brand-id>`, `VITE_API_BASE=https://<your-cloud-run>.run.app`.
4. **Configure Terraform**: copy `infra/terraform/terraform.tfvars.example` → `infra/terraform/terraform.tfvars` and set `project_id`, `region`, `brand_id`.
5. **Apply infra** (cost-flagged — review the plan first): `cd infra/terraform && terraform init && terraform plan && terraform apply`.
6. **Build + deploy the backend**: `make deploy-backend BRAND=<brand-id>` (builds image, pushes to Artifact Registry, deploys to Cloud Run).
7. **Build + deploy the frontend**: `make deploy-frontend BRAND=<brand-id>` (`vite build --mode <brand-id>` → `firebase deploy --only hosting:<brand-id>`).
8. **Verify**: visit the brand's Firebase Hosting URL; confirm theme tokens load from `GET /v1/me/brand` on first paint.

The same backend can serve multiple brand frontends. Branding is a runtime concern after the static asset bundle loads.

---

## Cost guardrail (hard constraint)

**No new GCP service costing more than $5/month is added without explicit approval.** Every infra change must flag estimated monthly cost. See `PRD.md` D11 + Hard Constraint #10.

Why this matters: it's trivial to accidentally provision a Spanner Graph instance ($650/mo minimum) or a Vertex AI endpoint with a min-replica that idles forever. We chose NetworkX + Firestore over Spanner Graph specifically to honor this rule.

---

## The non-negotiable line

**LLMs orchestrate, select, and narrate. Deterministic code computes.** No LLM-authored joins. No LLM-emitted final numbers. Every Cube join traces to a human-confirmed knowledge graph edge. Every answer carries provenance (definition version, snapshot, coverage, the query that ran). The platform must be able to say "I don't know."

See `PRD.md` § Hard Constraints for the full list.

---

## Status

**Phase 0 — Scaffold.** Directory structure, contracts, runnable shells for frontend + backend, Terraform skeleton (not applied). Subsequent phases follow the 13-step build order in `PRD.md`.
