"""Cube REST query client tests (offline stub + token shape)."""
import jwt

from insnav_cube_client import CubeQueryClient, mint_cube_token


class TestMintToken:
    def test_payload_carries_security_context(self) -> None:
        token = mint_cube_token(secret="s" * 32, security_context={"tenant_id": "acme"})
        decoded = jwt.decode(token, "s" * 32, algorithms=["HS256"])
        assert decoded["tenant_id"] == "acme"
        assert "exp" in decoded and "iat" in decoded

    def test_signed_so_tamper_is_detectable(self) -> None:
        token = mint_cube_token(secret="secret-a" * 4, security_context={"tenant_id": "x"})
        # Verifying with a different secret must fail.
        import pytest

        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, "secret-b" * 4, algorithms=["HS256"])


class TestOfflineClient:
    def test_offline_when_no_api_url(self) -> None:
        c = CubeQueryClient(api_url="", api_secret="x" * 32)
        assert c.offline is True

    def test_load_returns_stub_shape(self) -> None:
        c = CubeQueryClient(api_url="", api_secret="x" * 32)
        result = c.load(
            {"measures": ["sales.revenue"], "dimensions": ["sales.city"]},
            tenant_id="t1",
        )
        assert result["_stub"] is True
        assert result["_tenant"] == "t1"
        assert len(result["data"]) == 2
        # Each row has the requested measure + dimension keys
        row = result["data"][0]
        assert "sales.revenue" in row
        assert "sales.city" in row

    def test_sql_returns_stub(self) -> None:
        c = CubeQueryClient(api_url="", api_secret="x" * 32)
        result = c.sql({"measures": ["sales.revenue"]}, tenant_id="t1")
        assert result["_stub"] is True
        assert "sql" in result

    def test_explicit_offline_overrides_url(self) -> None:
        c = CubeQueryClient(api_url="https://cube.example", api_secret="x" * 32, offline=True)
        assert c.offline is True
        out = c.load({"measures": ["m"]}, tenant_id="t1")
        assert out["_stub"] is True
