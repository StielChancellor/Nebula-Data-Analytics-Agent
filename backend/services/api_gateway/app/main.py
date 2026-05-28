"""
api_gateway — the REST + SSE surface for the platform.

Phase 1 endpoints (additions to Phase 0):
  POST /v1/auth/login     — bootstrap admin login → access token
  GET  /v1/auth/me        — current principal from bearer token

Endpoints now protected by current_principal dependency:
  GET  /v1/me/datasets    — returns datasets the principal can access

Always-public:
  GET /healthz, /v1/me/brand, /v1/openapi.json, /v1/events-schema.json

Hot-reload locally:
    uvicorn services.api_gateway.app.main:app --reload --port 8000
"""
from __future__ import annotations

import os
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

app = FastAPI(
    title="Insights Navigator V2.0 — API Gateway",
    version="0.2.0",
    description=(
        "Phase 1 scaffold. Bootstrap admin auth (Nebula §5.3) — Firebase Auth "
        "multi-tenant ships in Phase 1.5. See PRD.md for the full architecture."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("INSNAV_CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- Shapes ----------

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


class Dataset(BaseModel):
    id: str
    label: str
    locale_hint: Literal["US", "IN"] = "US"
    last_refreshed: str | None = None
    row_count: int | None = None
    scopes: list[str] = Field(default_factory=list)


# ---------- Public endpoints ----------

@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "service": "api_gateway", "version": app.version}


@app.get("/v1/me/brand", response_model=BrandConfig)
def get_brand(x_brand_id: str | None = Header(default=None)) -> BrandConfig:
    """
    Public so it can be fetched before login (the brand-runtime loader runs
    before React mounts, before any token exists).
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


# ---------- Auth endpoints ----------

@app.post("/v1/auth/login", response_model=LoginResponse)
def login(req: LoginRequest) -> LoginResponse:
    """
    Phase 1: bootstrap admin login only. Returns a 12h JWT.
    Phase 1.5 will swap this for the Firebase Auth multi-tenant flow.
    """
    principal = authenticate_bootstrap(req)
    if principal is None:
        # Same response code/body whether the user doesn't exist or the password
        # is wrong, to avoid user enumeration.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    token, ttl = issue_token(principal)
    return LoginResponse(access_token=token, expires_in=ttl)


@app.get("/v1/auth/me", response_model=Principal)
def me(principal: Principal = Depends(current_principal)) -> Principal:
    return principal


# ---------- Protected endpoints ----------

@app.get("/v1/me/datasets", response_model=list[Dataset])
def list_datasets(principal: Principal = Depends(current_principal)) -> list[Dataset]:
    """
    Datasets the current principal can query. Empty in Phase 1; populated by
    the ingestion pipeline + tenant_access lookups in Phase 2+.

    The principal is unused for now but logged here so tests verify that
    auth IS being applied (not just an empty list bypass).
    """
    _ = principal  # placeholder until tenant_access lookups land
    return []
