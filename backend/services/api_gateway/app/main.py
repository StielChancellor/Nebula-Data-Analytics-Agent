"""
api_gateway — the REST + SSE surface for the platform.

Phase 2 endpoints (additions to Phase 1):
  POST /v1/uploads/start       — generate signed resumable upload URL
  POST /v1/uploads/complete    — kick off BQ load + profile
  GET  /v1/me/datasets         — real Firestore-backed list (replaces Phase 0 stub)
  GET  /v1/datasets/{id}       — full dataset record with status

Hot-reload locally:
    uvicorn services.api_gateway.app.main:app --reload --port 8000
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.api_gateway.app.auth import (
    LoginRequest,
    LoginResponse,
    Principal,
    authenticate_bootstrap,
    current_principal,
    issue_token,
)
from services.api_gateway.app.datasets_router import router as datasets_router
from services.api_gateway.app.settings import get_settings
from services.api_gateway.app.uploads import router as uploads_router

app = FastAPI(
    title="Insights Navigator V2.0 — API Gateway",
    version="0.3.0",
    description=(
        "Phase 2 — CSV ingestion via resumable signed URLs, BQ load, BQ-based "
        "profiler. See PRD.md and docs/PHASE-2-STATUS.md."
    ),
)

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Public endpoints ----------

class BrandTokens(BaseModel):
    accent: str = "0 217 192"
    accentGlow: str = "76 240 220"
    accentSoft: str = "14 50 47"
    accentForeground: str = "8 16 28"


class BrandConfig(BaseModel):
    brandId: str
    displayName: str
    tokens: BrandTokens
    logoUrl: str = "/brand/nebula/logo.svg"
    faviconUrl: str | None = "/brand/nebula/favicon.svg"
    currencyDefault: Literal["USD", "INR"] = "USD"
    regionDefault: Literal["US", "IN"] = "US"
    featureFlags: dict[str, bool] = Field(default_factory=dict)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "api_gateway", "version": app.version}


@app.get("/v1/me/brand", response_model=BrandConfig)
def get_brand(x_brand_id: str | None = Header(default=None)) -> BrandConfig:
    """Public so the frontend brand-runtime can fetch before login."""
    brand_id = x_brand_id or "nebula"
    if brand_id == "nebula":
        return BrandConfig(
            brandId="nebula",
            displayName="Insights Navigator",
            tokens=BrandTokens(),
            currencyDefault="USD",
            regionDefault="US",
        )
    return BrandConfig(brandId=brand_id, displayName=brand_id.title(), tokens=BrandTokens())


@app.get("/v1/events-schema.json")
def events_schema() -> JSONResponse:
    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "Insights Navigator V2.0 — SSE event schema",
        "description": "Stub. See PRD § Backend ↔ frontend contract.",
        "type": "object",
        "oneOf": [],
    }
    return JSONResponse(schema)


@app.get("/v1/openapi.json")
def openapi_v1() -> JSONResponse:
    return JSONResponse(app.openapi())


# ---------- Auth ----------

@app.post("/v1/auth/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    principal = authenticate_bootstrap(req)
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    token, ttl = issue_token(principal)
    return LoginResponse(access_token=token, expires_in=ttl)


@app.get("/v1/auth/me", response_model=Principal)
def me(principal: Principal = Depends(current_principal)) -> Principal:
    return principal


# ---------- Routers ----------

app.include_router(datasets_router)
app.include_router(uploads_router)
