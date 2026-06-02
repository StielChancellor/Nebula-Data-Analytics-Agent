"""Security regression tests (audit hardening: C1 injection, H1 RBAC, H2 ownership)."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.api_gateway.app import projects
from services.api_gateway.app.auth import Principal, require_admin
from services.api_gateway.app.datasets import ColumnSpec
from services.api_gateway.app.main import app
from services.api_gateway.app.uploads import build_normalize_sql


@pytest.fixture
def client(auth_env) -> TestClient:
    return TestClient(app)


def _auth(client: TestClient) -> dict[str, str]:
    r = client.post("/v1/auth/login",
                    json={"email": "admin@insnav.local", "password": "TESTING-do-not-use-in-prod-123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


class TestSqlInjection:  # SEC C1
    def test_malicious_column_name_is_escaped(self) -> None:
        evil = ColumnSpec(name="a` AS x; DROP TABLE y; --", bq_type="STRING")
        sql = build_normalize_sql("p.raw.t", [evil])
        # the embedded backtick is escaped, so it stays inside a quoted identifier
        assert "\\`" in sql
        # no bare unescaped `…` breakout: every backtick is preceded by a backslash
        # except the intentional opening/closing of identifiers — assert the evil
        # payload didn't produce an unescaped ` AS sequence outside quoting
        assert "a` AS x" not in sql  # would be the breakout if unescaped

    def test_malicious_date_format_rejected(self) -> None:
        evil = ColumnSpec(name="d", bq_type="DATE", source_format="') ; DROP --")
        with pytest.raises(ValueError):
            build_normalize_sql("p.raw.t", [evil])

    def test_unknown_bq_type_rejected(self) -> None:
        evil = ColumnSpec(name="d", bq_type="STRING; DROP", source_format="INR_GROUPED")
        with pytest.raises(ValueError):
            build_normalize_sql("p.raw.t", [evil])


class TestRbac:  # SEC H1
    def test_require_admin_blocks_plain_user(self) -> None:
        with pytest.raises(HTTPException) as ei:
            require_admin(Principal(sub="x", email="u@x", roles=["user"]))
        assert ei.value.status_code == 403

    def test_require_admin_allows_admin(self) -> None:
        p = Principal(sub="x", email="a@x", roles=["admin", "user"])
        assert require_admin(p) is p


class TestChatProjectOwnership:  # SEC H2
    def test_chat_foreign_project_404(self, client: TestClient) -> None:
        projects.save_project(projects.Project(
            id="foreignp", tenant_id="other-tenant", brand="nebula",
            name="secret", owner_email="z@y.x",
        ))
        r = client.post("/v1/chat", headers=_auth(client),
                        json={"question": "hi", "project_id": "foreignp"})
        assert r.status_code == 404
