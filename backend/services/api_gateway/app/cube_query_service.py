"""
Shared cube-spec runner (Phase 7/8).

Both the pivot panel and dashboard tiles take a user-built field selection and
run it as a governed Cube query. This centralizes: catalog validation (no
arbitrary member injection), query building, and the result→rows conversion —
reusing the swarm's builders so pivot, dashboards, and chat stay consistent.
"""
from __future__ import annotations

import re
from typing import Any

from insnav_agents.schemas import Interpretation
from insnav_agents.swarm import _rows_from_cube, build_catalog, to_cube_query
from insnav_cube_client import CubeQueryClient

from services.api_gateway.app.chat_router import _catalog_and_health
from services.api_gateway.app.settings import get_settings

_BACKTICK = re.compile(r"`([^`]+)`")
# BigQuery on-demand price (USD per TB scanned). Approximate; for the cost gate.
_BQ_USD_PER_TB = 6.25


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


def estimate_spec(
    *,
    tenant_id: str,
    project_id: str,
    measures: list[str],
    dimensions: list[str],
    time_dimension: str | None = None,
    filters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Cost preview (Phase 11 #4) — estimate bytes BigQuery would scan for this
    selection BEFORE running it, so the UI can gate expensive cross-dataset
    queries (PRD §11.4). Deterministic + $0: derived from table metadata
    (num_bytes) scaled by the fraction of columns the query actually references
    (BigQuery's main cost lever is columns scanned). A conservative upper bound —
    better to over-warn than surprise. Offline synthesizes bytes from row counts.
    """
    filters = filters or []
    valid = valid_fields(tenant_id, project_id)
    members = list(measures) + list(dimensions)
    if time_dimension:
        members.append(time_dimension)
    members += [f.get("member") for f in filters if isinstance(f, dict) and f.get("member")]
    bad = [n for n in members if n not in valid]
    if bad:
        raise UnknownField(f"unknown field(s): {', '.join(bad)}")

    schemas, _ = _catalog_and_health(tenant_id, [], project_id)
    by_name = {s.name: s for s in schemas}

    # Which source columns does each touched cube actually reference?
    touched: dict[str, set[str]] = {}
    for m in members:
        cube_name, _, member = m.partition(".")
        s = by_name.get(cube_name)
        if s is None:
            continue
        meas = next((x for x in s.measures if x.name == member), None)
        dim = next((x for x in s.dimensions if x.name == member), None)
        sql = (meas.sql if meas else None) or (dim.sql if dim else None)
        cols = _BACKTICK.findall(sql or "")
        if not cols and dim is not None:
            cols = [member]
        touched.setdefault(cube_name, set()).update(cols)

    settings = get_settings()
    offline = settings.offline_mode or not settings.cube_api_url
    from services.api_gateway.app.datasets import get_column_profiles

    per_cube: list[dict[str, Any]] = []
    total_bytes = 0.0
    for cube_name, cols in touched.items():
        s = by_name[cube_name]
        ref = max(1, len(cols))
        if offline:
            profiles = get_column_profiles(s.dataset_id)
            total_cols = max(ref, len(profiles) or ref)
            row_count = next(
                (h["row_count"] for h in _catalog_and_health(tenant_id, [], project_id)[1]
                 if h["id"] == s.dataset_id), 0,
            ) or 0
            cube_total = float(row_count) * total_cols * 8.0  # ~8 bytes/cell synth
        else:
            from services.api_gateway.app.gcp_clients import bigquery_client

            try:
                t = bigquery_client().get_table(s.sql_table)
                total_cols = max(1, len(t.schema))
                cube_total = float(t.num_bytes or 0)
            except Exception:
                total_cols, cube_total = ref, 0.0
        frac = min(ref, total_cols) / float(total_cols or 1)
        est = cube_total * frac
        total_bytes += est
        per_cube.append({
            "cube": cube_name, "table": s.sql_table,
            "referenced_columns": sorted(cols), "total_columns": total_cols,
            "bytes_estimate": int(est),
        })

    gb = total_bytes / 1e9
    threshold = settings.bq_cost_preview_gb_threshold
    return {
        "estimated_bytes": int(total_bytes),
        "estimated_gb": round(gb, 4),
        "estimated_usd": round(gb / 1024.0 * _BQ_USD_PER_TB, 4),
        "threshold_gb": threshold,
        "exceeds_threshold": gb > threshold,
        "per_cube": per_cube,
        "method": "table-metadata upper bound (columns-touched fraction)",
    }
