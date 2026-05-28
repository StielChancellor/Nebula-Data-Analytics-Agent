# Project Insights Navigator V2.0 — top-level Makefile
# Convenience wrappers around pnpm + python + terraform + gcloud.
#
# Usage: `make help` for the full list.

BRAND ?= nebula
GCP_PROJECT ?= insights-navigator-v2
REGION ?= us-central1

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# --- Install ---

.PHONY: install
install: install-frontend install-backend  ## Install all dependencies (frontend + backend)

.PHONY: install-frontend
install-frontend:  ## Install frontend deps (pnpm)
	cd frontend && pnpm install

.PHONY: install-backend
install-backend:  ## Install backend deps (pip + editable packages)
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -e .

# --- Dev ---

.PHONY: dev
dev:  ## Run frontend + backend in parallel
	@echo "Run 'make dev-frontend' and 'make dev-backend' in separate terminals (or use a process manager like overmind)."

.PHONY: dev-frontend
dev-frontend:  ## Start the Vite dev server at http://localhost:5173
	cd frontend/apps/web && pnpm dev

.PHONY: dev-backend
dev-backend:  ## Start the FastAPI dev server at http://localhost:8000
	cd backend && . .venv/bin/activate && uvicorn services.api-gateway.app.main:app --reload --port 8000

# --- Build ---

.PHONY: build
build: build-frontend build-backend  ## Build everything

.PHONY: build-frontend
build-frontend:  ## Build frontend for $(BRAND)
	cd frontend/apps/web && pnpm build --mode $(BRAND)

.PHONY: build-backend
build-backend:  ## Build backend Docker image
	docker build -t $(REGION)-docker.pkg.dev/$(GCP_PROJECT)/insnav/api:latest -f backend/services/api-gateway/Dockerfile backend/

# --- Test ---

.PHONY: test
test: test-frontend test-backend  ## Run all tests

.PHONY: test-frontend
test-frontend:
	cd frontend && pnpm test

.PHONY: test-backend
test-backend:
	cd backend && . .venv/bin/activate && pytest

# --- Lint / typecheck ---

.PHONY: check
check:  ## Lint + typecheck (frontend + backend)
	cd frontend && pnpm typecheck && pnpm lint
	cd backend && . .venv/bin/activate && ruff check . && mypy .

# --- Deploy ---

.PHONY: deploy-backend
deploy-backend:  ## Deploy backend to Cloud Run for $(BRAND) in $(GCP_PROJECT)
	@echo "TODO: implement backend deploy script in infra/scripts/deploy-backend.sh"

.PHONY: deploy-frontend
deploy-frontend:  ## Deploy frontend to Firebase Hosting for $(BRAND)
	@echo "TODO: implement frontend deploy script in infra/scripts/deploy-frontend.sh"

# --- Infra ---

.PHONY: tf-init
tf-init:
	cd infra/terraform && terraform init

.PHONY: tf-plan
tf-plan:
	cd infra/terraform && terraform plan -var="project_id=$(GCP_PROJECT)" -var="region=$(REGION)" -var="brand_id=$(BRAND)"

.PHONY: tf-apply
tf-apply:  ## DANGER: applies Terraform. Review the plan first. Honors the $5/mo cost guardrail (see PRD).
	@echo "About to apply Terraform to $(GCP_PROJECT). Run 'make tf-plan' first and review."
	@read -p "Proceed? [y/N] " ans && [ "$$ans" = "y" ] || exit 1
	cd infra/terraform && terraform apply -var="project_id=$(GCP_PROJECT)" -var="region=$(REGION)" -var="brand_id=$(BRAND)"

# --- Misc ---

.PHONY: clean
clean:  ## Remove build artifacts and caches
	find . -type d -name node_modules -prune -exec rm -rf {} +
	find . -type d -name dist -prune -exec rm -rf {} +
	find . -type d -name 'dist-*' -prune -exec rm -rf {} +
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	find . -type d -name .ruff_cache -prune -exec rm -rf {} +
