"""
Cube REST query client (Phase 5b).

The Semantic agent (Phase 6) calls this to run governed queries against the
deployed Cube service. It NEVER authors SQL — it selects measures/dimensions/
filters and Cube compiles the deterministic SQL. This is the determinism line
from PRD § Hard constraint #1.

Auth: Cube authenticates API calls with a JWT signed by the shared
`CUBEJS_API_SECRET`. The token payload becomes Cube's `securityContext`, which
cube.js uses (via `queryRewrite`) to enforce tenant isolation. So the token we
mint carries `tenant_id` and Cube refuses to return another tenant's rows.

Offline behavior: when `api_url` is empty or `offline=True`, the client returns
a deterministic stub so tests and local dev work without a running Cube.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import jwt

# Cube REST API paths (Cube 1.x).
_LOAD_PATH = "/cubejs-api/v1/load"
_SQL_PATH = "/cubejs-api/v1/sql"
_META_PATH = "/cubejs-api/v1/meta"

_TOKEN_TTL = dt.timedelta(hours=1)


def mint_cube_token(*, secret: str, security_context: dict[str, Any], ttl: dt.timedelta = _TOKEN_TTL) -> str:
    """
    Mint a Cube API token. The payload IS the security context Cube exposes
    to cube.js. Always include `tenant_id` so queryRewrite can scope rows.
    """
    now = dt.datetime.now(dt.timezone.utc)
    payload = {**security_context, "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp())}
    return jwt.encode(payload, secret, algorithm="HS256")


class CubeQueryClient:
    def __init__(
        self,
        *,
        api_url: str,
        api_secret: str,
        offline: bool = False,
        timeout_s: float = 30.0,
        project_id: str | None = None,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_secret = api_secret
        # Offline if explicitly requested OR no API url configured yet.
        self.offline = offline or not self.api_url
        self.timeout_s = timeout_s
        # Project workspace (Phase 10): carried in the Cube security context so
        # the Cube container compiles + serves the project's model in isolation.
        self.project_id = project_id

    # ---------- public API ----------

    def load(self, query: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
        """Run a Cube query. Returns Cube's load response {data, annotation, ...}."""
        if self.offline:
            return _stub_load(query, tenant_id)
        return self._post(_LOAD_PATH, {"query": query}, tenant_id=tenant_id)

    def sql(self, query: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
        """Return the SQL Cube WOULD run for this query (show-your-work / audit)."""
        if self.offline:
            return _stub_sql(query, tenant_id)
        return self._post(_SQL_PATH, {"query": query}, tenant_id=tenant_id)

    def meta(self, *, tenant_id: str) -> dict[str, Any]:
        """Return Cube's metadata (available cubes/measures/dimensions)."""
        if self.offline:
            return {"cubes": []}
        return self._get(_META_PATH, tenant_id=tenant_id)

    # ---------- internals ----------

    def _token(self, tenant_id: str) -> str:
        ctx: dict[str, Any] = {"tenant_id": tenant_id}
        if self.project_id:
            ctx["project_id"] = self.project_id
        return mint_cube_token(secret=self.api_secret, security_context=ctx)

    def _post(self, path: str, body: dict[str, Any], *, tenant_id: str) -> dict[str, Any]:
        import httpx

        headers = {"Authorization": self._token(tenant_id), "Content-Type": "application/json"}
        with httpx.Client(timeout=self.timeout_s) as c:
            resp = c.post(f"{self.api_url}{path}", json=body, headers=headers)
            resp.raise_for_status()
            return resp.json()

    def _get(self, path: str, *, tenant_id: str) -> dict[str, Any]:
        import httpx

        headers = {"Authorization": self._token(tenant_id)}
        with httpx.Client(timeout=self.timeout_s) as c:
            resp = c.get(f"{self.api_url}{path}", headers=headers)
            resp.raise_for_status()
            return resp.json()


# ---------- offline stubs ----------

def _stub_load(query: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    measures = query.get("measures", [])
    dimensions = query.get("dimensions", [])
    # Two synthetic rows so downstream code (and tests) have a shape to work with.
    rows: list[dict[str, Any]] = []
    for i in range(2):
        row: dict[str, Any] = {}
        for d in dimensions:
            row[d] = f"{d.split('.')[-1]}_{i}"
        for m in measures:
            row[m] = (i + 1) * 100
        rows.append(row)
    return {
        "data": rows,
        "annotation": {
            "measures": {m: {"title": m} for m in measures},
            "dimensions": {d: {"title": d} for d in dimensions},
        },
        "query": query,
        "_stub": True,
        "_tenant": tenant_id,
    }


def _stub_sql(query: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    return {
        "sql": {
            "sql": ["SELECT /* stub: cube not deployed */ 1", []],
        },
        "_stub": True,
        "_tenant": tenant_id,
    }
