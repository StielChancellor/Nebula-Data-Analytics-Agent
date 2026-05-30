"""
Dual-mode auth tests — Firebase RS256 path, verified offline with a locally
generated RSA keypair (no live Firebase). Bootstrap HS256 path still covered
in test_main.py.
"""
import datetime as dt

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from services.api_gateway.app import firebase, settings
from services.api_gateway.app.auth import Principal, decode_token

PROJECT = "insights-navigator-v2"


@pytest.fixture
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    yield key, key.public_key()


@pytest.fixture(autouse=True)
def _firebase_env(monkeypatch: pytest.MonkeyPatch, rsa_keys):
    # Route the verifier's signing-key lookup to our local public key.
    _, public_key = rsa_keys
    firebase.set_signing_key_resolver(lambda _token: public_key)
    monkeypatch.setenv("INSNAV_FIREBASE_PROJECT", PROJECT)
    settings.get_settings.cache_clear()
    yield
    firebase.set_signing_key_resolver(None)
    settings.get_settings.cache_clear()


def _mint(private_key, *, sub="firebase-uid-1", email="user@acme.com",
          tenant: str | None = "acme", aud=PROJECT, iss=None,
          exp_delta=dt.timedelta(hours=1), extra=None) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    claims = {
        "sub": sub,
        "email": email,
        "aud": aud,
        "iss": iss or f"https://securetoken.google.com/{PROJECT}",
        "iat": int(now.timestamp()),
        "exp": int((now + exp_delta).timestamp()),
        "auth_time": int(now.timestamp()),
    }
    if tenant is not None:
        claims["firebase"] = {"tenant": tenant, "sign_in_provider": "password"}
    if extra:
        claims.update(extra)
    return jwt.encode(claims, private_key, algorithm="RS256")


class TestFirebaseVerify:
    def test_valid_token_yields_principal_with_tenant(self, rsa_keys) -> None:
        priv, _ = rsa_keys
        token = _mint(priv)
        p = decode_token(token)
        assert isinstance(p, Principal)
        assert p.sub == "firebase-uid-1"
        assert p.email == "user@acme.com"
        assert p.tenant_id == "acme"
        assert p.roles == ["user"]

    def test_default_tenant_when_no_firebase_tenant(self, rsa_keys) -> None:
        priv, _ = rsa_keys
        token = _mint(priv, tenant=None)
        assert decode_token(token).tenant_id == "default"

    def test_custom_claims_brand_and_roles(self, rsa_keys) -> None:
        priv, _ = rsa_keys
        token = _mint(priv, extra={"brand": "erev", "roles": ["admin", "user"]})
        p = decode_token(token)
        assert p.brand == "erev"
        assert "admin" in p.roles

    def test_wrong_audience_rejected(self, rsa_keys) -> None:
        priv, _ = rsa_keys
        token = _mint(priv, aud="some-other-project")
        with pytest.raises(HTTPException) as ei:
            decode_token(token)
        assert ei.value.status_code == 401

    def test_wrong_issuer_rejected(self, rsa_keys) -> None:
        priv, _ = rsa_keys
        token = _mint(priv, iss="https://evil.example/insights-navigator-v2")
        with pytest.raises(HTTPException) as ei:
            decode_token(token)
        assert ei.value.status_code == 401

    def test_expired_rejected(self, rsa_keys) -> None:
        priv, _ = rsa_keys
        token = _mint(priv, exp_delta=dt.timedelta(hours=-1))
        with pytest.raises(HTTPException) as ei:
            decode_token(token)
        assert ei.value.status_code == 401

    def test_token_signed_by_wrong_key_rejected(self, rsa_keys) -> None:
        # Sign with a DIFFERENT key than the resolver returns → bad signature.
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = _mint(other)
        with pytest.raises(HTTPException) as ei:
            decode_token(token)
        assert ei.value.status_code == 401


class TestDualMode:
    def test_bootstrap_hs256_still_works_alongside_firebase(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Issue a bootstrap HS256 token and confirm decode_token routes it correctly.
        monkeypatch.setenv("INSNAV_JWT_SECRET", "x" * 40)
        from services.api_gateway.app.auth import issue_token

        token, _ = issue_token(Principal(sub="boot", email="a@b.c", tenant_id="default"))
        p = decode_token(token)
        assert p.sub == "boot"
        assert p.tenant_id == "default"

    def test_garbage_token_rejected(self) -> None:
        with pytest.raises(HTTPException) as ei:
            decode_token("not-a-jwt")
        assert ei.value.status_code == 401
