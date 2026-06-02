"""
Shared cube-spec runner (Phase 7/8).

Both the pivot panel and dashboard tiles take a user-built field selection and
run it as a governed Cube query. This centralizes: catalog validation (no
arbitrary member injection), query building, and the result→rows conversion —
reusing the swarm's builders so pivot, dashboards, and chat stay consistent.
"""
from __future__ import annotations

from typing import Any

from insnav_agents.schemas import Interpretation
from insnav_agents.swarm import _rows_from_cube, build_catalog, to_cube_query
from insnav_cube_client import CubeQueryClient

from services.api_gateway.app.chat_router import _catalog_and_health
from services.api_gateway.app.settings import get_settings


class UnknownField(ValueError):
    """A requested measure/dimension/filter member isn't in the project catalog."""


def valid_fields(tenant_id: str, project_id: str) -> set[str]:
    schemas, _ = _catalog_and_health(tenant_id, [], project_id)
    _, names = build_catalog(schemas)
    return names


def run_spec(
    *,
    tenant_id: str,
    project_id: str,
    measures: list[str],
    dimensions: list[str],
    time_dimension: str | None = None,
    granularity: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    order: dict[str, str] | None = None,
    limit: int | None = None,
) -> tuple[list[str], list[list[Any]], dict[str, Any]]:
    """Validate fields against the project catalog, run the Cube query, return
    (columns, rows, cube_query). Raises UnknownField on any unknown member."""
    filters = filters or []
    valid = valid_fields(tenant_id, project_id)
    requested = list(measures) + list(dimensions)
    if time_dimension:
        requested.append(time_dimension)
    requested += [f.get("member") for f in filters if isinstance(f, dict) and f.get("member")]
    bad = [n for n in requested if n not in valid]
    if bad:
        raise UnknownField(f"unknown field(s): {', '.join(bad)}")

    interp = Interpretation(
        measures=measures,
        dimensions=dimensions,
        time_dimension=time_dimension,
        granularity=granularity,
        filters=filters,
        order=order or {},
        limit=limit or 5000,
    )
    query = to_cube_query(interp)

    settings = get_settings()
    cube = CubeQueryClient(
        api_url=settings.cube_api_url,
        api_secret=settings.cube_api_secret,
        offline=settings.offline_mode or not settings.cube_api_url,
        project_id=project_id,
    )
    result = cube.load(query, tenant_id=tenant_id)
    columns, rows = _rows_from_cube(result, query)
    return columns, rows, query
