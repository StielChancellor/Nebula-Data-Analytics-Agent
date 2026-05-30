"""
Firebase ID token verification (Phase 1.5).

Firebase Auth / Identity Platform issues RS256 ID tokens signed with Google's
rotating private keys. We verify against Google's published JWKS:

  - alg:    RS256
  - issuer: https://securetoken.google.com/<project-id>
  - aud:    <project-id>
  - tenant: claims["firebase"]["tenant"]  (multi-tenant); None for the default tenant

This module is import-safe (no network on import). The signing key is fetched
lazily via PyJWKClient and cached by pyjwt. Tests inject a local resolver via
`set_signing_key_resolver` so the whole path is verifiable offline with a
generated RSA keypair — no live Firebase needed.
"""
from __future__ import annotations

from typing import Any, Callable

import jwt
from fastapi import HTTPException, status

# Test hook: given a token, return the signing key (a public key object or PEM).
# When None (production), we use PyJWKClient against Google's JWKS.
_signing_key_resolver: Callable[[str], Any] | None = None

# Cache the PyJWKClient per JWKS URL so we don't rebuild it per request.
_jwk_clients: dict[str, "jwt.PyJWKClient"] = {}


def set_signing_key_resolver(fn: Callable[[str], Any] | None) -> None:
    """Test helper — override how signing keys are resolved (or reset with None)."""
    global _signing_key_resolver
    _signing_key_resolver = fn


def _resolve_signing_key(token: str, jwks_url: str) -> Any:
    if _signing_key_resolver is not None:
        return _signing_key_resolver(token)
    client = _jwk_clients.get(jwks_url)
    if client is None:
        client = jwt.PyJWKClient(jwks_url)
        _jwk_clients[jwks_url] = client
    return client.get_signing_key_from_jwt(token).key


def verify_firebase_token(token: str, *, project: str, jwks_url: str) -> dict[str, Any]:
    """
    Verify a Firebase ID token and return its claims. Raises HTTP 401 on any
    failure (expired, bad signature, wrong issuer/audience).
    """
    issuer = f"https://securetoken.google.com/{project}"
    try:
        key = _resolve_signing_key(token, jwks_url)
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=project,
            issuer=issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "firebase token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"invalid firebase token: {e}") from e

    # Firebase ID tokens also require sub to be non-empty and auth_time present.
    if not claims.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "firebase token missing sub")
    return claims


def tenant_from_claims(claims: dict[str, Any]) -> str:
    """Extract the tenant id from a Firebase token. Default tenant → 'default'."""
    fb = claims.get("firebase") or {}
    return fb.get("tenant") or "default"
