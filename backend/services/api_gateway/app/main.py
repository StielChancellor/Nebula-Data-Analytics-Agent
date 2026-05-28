"""
api_gateway — the REST + SSE surface for the platform.

Phase 0 scaffold: minimal endpoints to prove the frontend/backend seam works.

  GET /healthz            — liveness probe (Cloud Run health check)
  GET /v1/me/brand        — runtime brand tokens (used by frontend brand-runtime)
  GET /v1/me/datasets     — list datasets the current user can access (empty for now)
  GET /v1/openapi.json    — same as /openapi.json; codegen target for the FE api-client
  GET /v1/events-schema.json — sibling SSE event schema (stub)

Auth, real dataset access, ingestion, chat, pivot, dashboards land in later
phases per the PRD build order. Hot-reload locally:
    uvicorn services.api_gateway.app.main:app --reload --port 8000
"""
from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="Insights Navigator V2.0 — API Gateway",
    version="0.1.0",
    description=(
        "Phase 0 scaffold. See PRD.md for the full architecture, agent swarm "
        "wiring, and build order."
    ),
)

# CORS — wide-open in dev; tighten before prod.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("INSNAV_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Shapes (Phase 0) ----------

class BrandTokens(BaseModel):
    accent: str = "0 217 192"
    accentGlow: str = "76 240 220"
    accentSoft: str = "14 50 47"
    accentForeground: str = "8 16 28"


class BrandConfig(BaseModel):
    """
    Runtime brand response — frontend's @insnav/brand-runtime calls
    GET /v1/me/brand on bootstrap and applies tokens before React mounts.
    """
    brandId: str
    displayName: str
    tokens: BrandTokens
    logoUrl: str = "/brand/nebula/logo.svg"
    faviconUrl: str | None = "/brand/nebula/favicon.svg"
    currencyDefault: Literal["USD", "INR"] = "USD"
    regionDefault: Literal["US", "IN"] = "US"
    featureFlags: dict[str, bool] = Field(default_factory=dict)


class Dataset(BaseModel):
    id: str
    label: str
    locale_hint: Literal["US", "IN"] = "US"
    last_refreshed: str | None = None
    row_count: int | None = None
    scopes: list[str] = Field(default_factory=list)


# ---------- Endpoints ----------

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "api_gateway", "version": "0.1.0"}


@app.get("/v1/me/brand", response_model=BrandConfig)
def get_brand(x_brand_id: str | None = Header(default=None)) -> BrandConfig:
    """
    Returns the runtime brand config for the requesting frontend.

    Phase 0: returns the hardcoded Nebula brand. Phase 1 will look up the
    brand from the JWT `brand` claim and the tenant_access table.
    """
    brand_id = x_brand_id or "nebula"
    if brand_id == "nebula":
        return BrandConfig(
            brandId="nebula",
            displayName="Insights Navigator",
            tokens=BrandTokens(),
            currencyDefault="USD",
            regionDefault="US",
        )
    # Unknown brand → fall back to nebula so the frontend always renders.
    return BrandConfig(
        brandId=brand_id,
        displayName=brand_id.title(),
        tokens=BrandTokens(),
    )


@app.get("/v1/me/datasets", response_model=list[Dataset])
def list_datasets() -> list[Dataset]:
    """
    Datasets the current user can query. Empty in Phase 0; populated by
    the ingestion pipeline + tenant_access lookups in Phase 2+.
    """
    return []


@app.get("/v1/events-schema.json")
def events_schema() -> JSONResponse:
    """
    Sibling to OpenAPI: documents the SSE event shapes the chat endpoint will
    emit (agent narration, computation progress, partial chart specs).

    Phase 0: skeleton. Phase 6: populate as the agent swarm is built.
    """
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Insights Navigator V2.0 — SSE event schema",
        "description": "Stub. See PRD § Backend ↔ frontend contract.",
        "type": "object",
        "oneOf": [],
    }
    return JSONResponse(schema)


# Convenience: also expose /v1/openapi.json so the frontend codegen can pin a
# versioned path (rather than depending on FastAPI's /openapi.json default).
@app.get("/v1/openapi.json")
def openapi_v1() -> JSONResponse:
    return JSONResponse(app.openapi())
