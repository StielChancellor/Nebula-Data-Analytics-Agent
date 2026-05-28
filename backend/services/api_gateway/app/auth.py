"""
Bootstrap admin auth + JWT verify dependency.

PRD Nebula §5.3: env-based admin override for pre-user-management shipping.
Critically: the JWT claim shape mirrors what Firebase Auth multi-tenant tokens
look like (tenant_id, brand custom claim, sub, email, exp, iat) so swapping
to Firebase in Phase 1.5 is a verify-side change (HS256→RS256, our issuer →
Firebase's issuer) without disturbing the rest of the codebase.

Bootstrap admin credentials:
  BOOTSTRAP_ADMIN_EMAIL      — required to enable bootstrap login
  BOOTSTRAP_ADMIN_PASSWORD   — required; compared via secrets.compare_digest
  BOOTSTRAP_ADMIN_TENANT     — default 'default'
  BOOTSTRAP_ADMIN_BRAND      — default 'nebula'

JWT signing:
  INSNAV_JWT_SECRET          — required in production. Falls back to a stable
                                dev secret with a loud warning if unset, so
                                local dev doesn't break.

Rotate the bootstrap admin password and JWT secret before ANY real customer.
"""
from __future__ import annotations

import datetime as dt
import logging
import os
import secrets as _secrets
from dataclasses import dataclass
from typing import Annotated, Literal

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ----- config -----

_DEV_FALLBACK_SECRET = "insnav-dev-only-do-not-use-in-prod-" + "x" * 16  # >= 32 bytes


def _jwt_secret() -> str:
    s = os.getenv("INSNAV_JWT_SECRET")
    if not s:
        logger.warning(
            "INSNAV_JWT_SECRET is not set; using a dev fallback. "
            "DO NOT deploy this way — set the env var from Secret Manager."
        )
        return _DEV_FALLBACK_SECRET
    if len(s) < 32:
        raise RuntimeError("INSNAV_JWT_SECRET must be >= 32 bytes for HS256 security")
    return s


_JWT_ALGO = "HS256"
_JWT_ISSUER = "insnav-bootstrap"  # Firebase will set this to "https://securetoken.google.com/<project>"
_JWT_AUDIENCE = "insnav"
_JWT_TTL = dt.timedelta(hours=12)


# ----- shapes -----

class Principal(BaseModel):
    """The authenticated user — what every protected endpoint receives."""
    sub: str
    email: str
    tenant_id: str = Field(default="default")
    brand: str = Field(default="nebula")
    roles: list[Literal["admin", "user"]] = Field(default_factory=lambda: ["user"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int  # seconds


@dataclass(frozen=True)
class BootstrapAdminConfig:
    email: str
    password: str
    tenant_id: str
    brand: str

    @classmethod
    def from_env(cls) -> "BootstrapAdminConfig | None":
        email = os.getenv("BOOTSTRAP_ADMIN_EMAIL")
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
        if not email or not password:
            return None
        return cls(
            email=email,
            password=password,
            tenant_id=os.getenv("BOOTSTRAP_ADMIN_TENANT", "default"),
            brand=os.getenv("BOOTSTRAP_ADMIN_BRAND", "nebula"),
        )


# ----- JWT issue / verify -----

def issue_token(principal: Principal, ttl: dt.timedelta = _JWT_TTL) -> tuple[str, int]:
    now = dt.datetime.now(dt.timezone.utc)
    exp = now + ttl
    claims = {
        "sub": principal.sub,
        "email": principal.email,
        "tenant_id": principal.tenant_id,
        "brand": principal.brand,
        "roles": principal.roles,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": _JWT_ISSUER,
        "aud": _JWT_AUDIENCE,
    }
    token = jwt.encode(claims, _jwt_secret(), algorithm=_JWT_ALGO)
    return token, int(ttl.total_seconds())


def decode_token(token: str) -> Principal:
    try:
        claims = jwt.decode(
            token,
            _jwt_secret(),
            algorithms=[_JWT_ALGO],
            issuer=_JWT_ISSUER,
            audience=_JWT_AUDIENCE,
        )
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid token: {e}") from e

    return Principal(
        sub=claims["sub"],
        email=claims["email"],
        tenant_id=claims.get("tenant_id", "default"),
        brand=claims.get("brand", "nebula"),
        roles=claims.get("roles", ["user"]),
    )


# ----- login -----

def authenticate_bootstrap(req: LoginRequest) -> Principal | None:
    """Returns a Principal if the request matches the bootstrap admin env vars."""
    cfg = BootstrapAdminConfig.from_env()
    if cfg is None:
        return None
    email_ok = _secrets.compare_digest(req.email.encode("utf-8"), cfg.email.encode("utf-8"))
    pwd_ok = _secrets.compare_digest(req.password.encode("utf-8"), cfg.password.encode("utf-8"))
    if not (email_ok and pwd_ok):
        return None
    return Principal(
        sub=f"bootstrap:{cfg.email}",
        email=cfg.email,
        tenant_id=cfg.tenant_id,
        brand=cfg.brand,
        roles=["admin", "user"],
    )


# ----- FastAPI dependency -----

_bearer = HTTPBearer(auto_error=False)


def current_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    """
    Dependency for protected endpoints. Raises 401 if missing/invalid token.
    Usage:
        @app.get("/v1/me/datasets")
        def list_datasets(p: Principal = Depends(current_principal)): ...
    """
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return decode_token(creds.credentials)
