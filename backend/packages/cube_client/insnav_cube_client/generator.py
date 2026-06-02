"""
Cube schema generator.

Takes:
  - Dataset metadata (label, BQ table, locale_hint)
  - Column profiles from the profiler (type, key_likeness, etc.)
  - Approved graph edges where this dataset participates

Emits a CubeSchema (Pydantic) and can render it to Cube's JS format.

Conventions:
  - Cube name: sanitized label + short dataset_id suffix for uniqueness.
    Example: dataset "Sales 2026" with id "a3f4d2b1..." → "sales_2026__a3f4d2b1"
  - Every cube has a `count` measure.
  - Numeric columns become:
      - a dimension (always — useful for filtering)
      - a `sum_<col>` measure
      - an `avg_<col>` measure
      UNLESS the column is high-key-likeness (foreign key) — then no
      sum/avg (they're meaningless on FKs), just the dimension.
  - First column with key_likeness > 0.85 is marked as the primary_key
    (Cube uses primary_key to enable joins from other cubes).
  - Time columns (DATE/TIMESTAMP/DATETIME) → time-type dimension. Cube's
    built-in granularities cover day/week/month/quarter/year. India's
    fiscal-year stuff (Apr-Mar) requires custom Cube granularities — that
    lands when we deploy Cube in Phase 5b.
  - Revenue-touching heuristic: column name contains revenue/sales/roas/
    cost/spend/profit → the sum/avg measures are flagged revenue_touching.

Joins (PRD § Hard constraint #2):
  - Source: ONLY approved GraphEdges where this dataset is from or to.
  - Relationship inferred from distinct counts:
      from_distinct ≈ to_distinct           → one_to_one
      from_distinct > to_distinct (× 1.5)   → many_to_one
      from_distinct < to_distinct (× 1.5)   → one_to_many
      otherwise (unknown)                   → many_to_many (safe default)
"""
from __future__ import annotations

import re
from typing import Any

from .models import (
    CubeDimension,
    CubeJoin,
    CubeMeasure,
    CubeRelationship,
    CubeSchema,
)

# ---------- type mappings ----------

# BQ types (upper-case canonical) → Cube column type.
BQ_TYPE_TO_CUBE_TYPE: dict[str, str] = {
    # numeric
    "INT64": "number",
    "INTEGER": "number",
    "NUMERIC": "number",
    "BIGNUMERIC": "number",
    "FLOAT64": "number",
    "FLOAT": "number",
    # text
    "STRING": "string",
    "BYTES": "string",
    # boolean
    "BOOL": "boolean",
    "BOOLEAN": "boolean",
    # time
    "DATE": "time",
    "TIME": "time",
    "DATETIME": "time",
    "TIMESTAMP": "time",
}


def bq_type_to_cube_type(bq_type: str) -> str:
    return BQ_TYPE_TO_CUBE_TYPE.get(bq_type.upper(), "string")


# ---------- name sanitization ----------

_VALID_IDENT_RE = re.compile(r"[^a-z0-9_]")


def _sanitize_identifier(s: str) -> str:
    """Lowercase, replace non-[a-z0-9_] with _, collapse repeats, trim."""
    out = _VALID_IDENT_RE.sub("_", s.lower())
    out = re.sub(r"_+", "_", out).strip("_")
    if not out or out[0].isdigit():
        out = "x_" + out
    return out[:60]  # Cube identifiers — keep them readable


def cube_name_for_dataset(dataset_id: str, label: str) -> str:
    """
    Stable, deterministic, collision-resistant cube name.
    `<sanitized_label>__<first_8_chars_of_dataset_id>`
    """
    base = _sanitize_identifier(label) or "dataset"
    short_id = dataset_id[:8] if dataset_id else "noid"
    return f"{base}__{short_id}"


# ---------- revenue-touching heuristic ----------

_REVENUE_KEYWORDS = ("revenue", "sales", "roas", "cost", "spend", "profit", "margin")


def _is_revenue_column(col_name: str) -> bool:
    lname = col_name.lower()
    return any(kw in lname for kw in _REVENUE_KEYWORDS)


# ---------- relationship heuristic ----------

def _infer_relationship(from_distinct: int | None, to_distinct: int | None) -> CubeRelationship:
    """Cardinality-based join cardinality inference. See module docstring."""
    if not from_distinct or not to_distinct:
        return "many_to_many"
    ratio = from_distinct / to_distinct
    if 0.66 <= ratio <= 1.5:
        return "one_to_one"
    if ratio > 1.5:
        return "many_to_one"
    return "one_to_many"


# ---------- main API ----------

def build_cube_schema(
    *,
    dataset: dict[str, Any],
    columns: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    cube_name_lookup: dict[str, str] | None = None,
) -> CubeSchema:
    """
    Build a CubeSchema from the inputs in plain-dict form (so this function
    doesn't depend on insnav_contracts / graph_store types directly — keeps
    the cube_client package importable without backend deps).

    Args:
        dataset: dict with id, tenant_id, label, bq_table, locale_hint
        columns: list of column profiles. Each must have name, type,
                 plus optional null_pct, distinct_count, key_likeness.
        edges:   list of approved graph-edge dicts. Each must have id,
                 from_dataset, from_column, to_dataset, to_column,
                 from_distinct_count, to_distinct_count.
        cube_name_lookup: optional dataset_id → cube_name map. If a peer
                          dataset isn't in this map, we generate the name
                          from the peer's dataset_id alone (using "ds" as
                          a label fallback).
    """
    dataset_id = dataset["id"]
    tenant_id = dataset["tenant_id"]
    label = dataset.get("label") or dataset_id
    bq_table = dataset.get("bq_table") or ""
    locale_hint = dataset.get("locale_hint", "US")

    cube_name = cube_name_for_dataset(dataset_id, label)

    # Dimensions + measures from columns
    dims: list[CubeDimension] = []
    measures: list[CubeMeasure] = [CubeMeasure(name="count", type="count")]
    primary_key_assigned = False

    for c in columns:
        col_name = c["name"]
        col_type = c.get("type", "STRING")
        cube_type = bq_type_to_cube_type(col_type)
        key_likeness = float(c.get("key_likeness") or 0.0)
        safe_col = _sanitize_identifier(col_name)

        # Human-confirmed semantics (Phase 10-C) are merged onto the column dict
        # by save_column_semantics. When present they OVERRIDE the heuristics.
        role = c.get("role")
        if role:
            if role == "ignore":
                continue  # explicitly excluded from the model

            title = c.get("display_title") or col_name
            description = c.get("business_meaning") or None

            if role == "measure":
                agg = c.get("measure_aggregation") or "sum"
                # Revenue gating (PRD #3): only a HUMAN-CONFIRMED revenue column
                # (confirmed_by set) becomes a revenue-touching measure.
                is_rev = bool(c.get("is_revenue")) and bool(c.get("confirmed_by"))
                measures.append(
                    CubeMeasure(
                        name=f"{agg}_{safe_col}",
                        type=agg,  # type: ignore[arg-type]
                        sql=None if agg == "count" else f"`{col_name}`",
                        title=c.get("display_title") or f"{str(agg).title()} of {col_name}",
                        description=description,
                        revenue_touching=is_rev,
                    )
                )
            else:
                # dimension | time | identifier → a dimension
                is_pk = False
                if role == "identifier" and (c.get("join_key") or True) and not primary_key_assigned:
                    is_pk = True
                    primary_key_assigned = True
                dims.append(
                    CubeDimension(
                        name=safe_col,
                        sql=f"`{col_name}`",
                        type=("time" if role == "time" else cube_type),  # type: ignore[arg-type]
                        primary_key=is_pk,
                        title=title,
                        description=description,
                    )
                )
            continue

        # ---- heuristic path (no confirmed semantics) ----
        is_pk = False
        if not primary_key_assigned and key_likeness >= 0.85:
            is_pk = True
            primary_key_assigned = True

        dims.append(
            CubeDimension(
                name=safe_col,
                sql=f"`{col_name}`",
                type=cube_type,  # type: ignore[arg-type]
                primary_key=is_pk,
                title=col_name,
            )
        )

        # Numeric columns with low key-likeness become sum + avg measures.
        # High-key-likeness numerics are foreign keys → no aggregation.
        if cube_type == "number" and key_likeness < 0.7:
            is_revenue = _is_revenue_column(col_name)
            measures.append(
                CubeMeasure(
                    name=f"sum_{safe_col}",
                    type="sum",
                    sql=f"`{col_name}`",
                    title=f"Sum of {col_name}",
                    revenue_touching=is_revenue,
                )
            )
            measures.append(
                CubeMeasure(
                    name=f"avg_{safe_col}",
                    type="avg",
                    sql=f"`{col_name}`",
                    title=f"Avg {col_name}",
                    revenue_touching=is_revenue,
                )
            )

    # Joins — only from approved edges where this dataset is involved
    joins: list[CubeJoin] = []
    for e in edges:
        if e["from_dataset"] == dataset_id:
            other_id = e["to_dataset"]
            this_col = e["from_column"]
            other_col = e["to_column"]
            this_dist = e.get("from_distinct_count")
            other_dist = e.get("to_distinct_count")
        elif e["to_dataset"] == dataset_id:
            other_id = e["from_dataset"]
            this_col = e["to_column"]
            other_col = e["from_column"]
            this_dist = e.get("to_distinct_count")
            other_dist = e.get("from_distinct_count")
        else:
            continue  # edge doesn't touch this dataset

        other_cube = (cube_name_lookup or {}).get(other_id) or cube_name_for_dataset(other_id, "ds")
        sql_clause = f"${{CUBE}}.`{this_col}` = ${{{other_cube}}}.`{other_col}`"
        joins.append(
            CubeJoin(
                to_cube=other_cube,
                sql_clause=sql_clause,
                relationship=_infer_relationship(this_dist, other_dist),
                from_edge_id=e["id"],
                from_dataset_id=dataset_id,
                to_dataset_id=other_id,
            )
        )

    return CubeSchema(
        name=cube_name,
        title=label,
        sql_table=bq_table,
        description=f"Auto-generated cube for dataset {label} (id={dataset_id[:8]})",
        dimensions=dims,
        measures=measures,
        joins=joins,
        dataset_id=dataset_id,
        tenant_id=tenant_id,
        locale_hint=locale_hint,  # type: ignore[arg-type]
    )


def build_tenant_schemas(
    *,
    datasets: list[dict[str, Any]],
    columns_by_dataset: dict[str, list[dict[str, Any]]],
    edges: list[dict[str, Any]],
) -> list[CubeSchema]:
    """
    Build the full set of CubeSchemas for a tenant in one call.

    Computes the cube_name_lookup once (so cross-cube joins reference the
    real peer cube names) and builds one CubeSchema per dataset. Shared by
    the cube router (overview) and the cube-model sync (Phase 5b).
    """
    lookup = {
        d["id"]: cube_name_for_dataset(d["id"], d.get("label") or d["id"])
        for d in datasets
    }
    return [
        build_cube_schema(
            dataset=d,
            columns=columns_by_dataset.get(d["id"], []),
            edges=edges,
            cube_name_lookup=lookup,
        )
        for d in datasets
    ]


def render_to_js(schema: CubeSchema) -> str:
    """Render a CubeSchema to a Cube JS data-model file.

    Output is a complete, valid Cube .js file that can be dropped into
    `infra/cube-schema/` and loaded by a Cube deployment.

    Cube modern JS uses the `cube()` function with snake_case keys.

    NOTE: the render is intentionally DETERMINISTIC — no timestamp in the
    output — so identical schema content always produces identical bytes.
    This keeps the Cube model `schemaVersion` stable across re-syncs (a sync
    of unchanged data must not churn Cube into recompiling). The generation
    timestamp still lives in the CubeSchema model / JSON endpoint.
    """
    lines: list[str] = []
    lines.append("// Auto-generated by insnav_cube_client — DO NOT hand-edit.")
    lines.append(f"// Dataset: {schema.title} (id={schema.dataset_id[:8]}, tenant={schema.tenant_id})")
    lines.append(f"// Locale hint: {schema.locale_hint}")
    lines.append("//")
    lines.append("// PRD § Hard constraint #2: every join in this file traces to an")
    lines.append("// approved graph edge (see from_edge_id comments below). DO NOT")
    lines.append("// hand-edit joins — re-generate from approved edges instead.")
    lines.append("")
    lines.append(f"cube(`{schema.name}`, {{")
    lines.append(f"  sql_table: `{schema.sql_table}`,")
    lines.append(f"  description: `{_escape(schema.description)}`,")
    lines.append("")

    # Dimensions
    lines.append("  dimensions: {")
    for d in schema.dimensions:
        lines.append(f"    {d.name}: {{")
        # _escape so the BQ identifier backticks survive as LITERAL backticks
        # inside the JS template literal (otherwise `\`city\`` closes the
        # template early → "could not be cloned" compile error in Cube).
        lines.append(f"      sql: `{_escape(d.sql)}`,")
        lines.append(f"      type: `{d.type}`,")
        if d.primary_key:
            lines.append("      primary_key: true,")
        if d.title:
            lines.append(f"      title: `{_escape(d.title)}`,")
        lines.append("    },")
    lines.append("  },")
    lines.append("")

    # Measures
    lines.append("  measures: {")
    for m in schema.measures:
        lines.append(f"    {m.name}: {{")
        lines.append(f"      type: `{m.type}`,")
        if m.sql:
            lines.append(f"      sql: `{_escape(m.sql)}`,")
        if m.title:
            lines.append(f"      title: `{_escape(m.title)}`,")
        if m.revenue_touching:
            lines.append("      // revenue_touching: gated by PR review (PRD §11)")
        lines.append("    },")
    lines.append("  },")

    # Joins (omit the section entirely if there are none)
    if schema.joins:
        lines.append("")
        lines.append("  joins: {")
        for j in schema.joins:
            lines.append(f"    {j.to_cube}: {{")
            # _escape the BQ backticks; the ${CUBE}/${other} interpolations
            # are left live (not backticks) so Cube fills them at compile time.
            lines.append(f"      sql: `{_escape(j.sql_clause)}`,")
            lines.append(f"      relationship: `{j.relationship}`,")
            lines.append(f"      // from_edge_id: {j.from_edge_id}")
            lines.append("    },")
        lines.append("  },")

    lines.append("});")
    return "\n".join(lines) + "\n"


def _escape(s: str) -> str:
    """Escape backticks inside JS template literals."""
    return s.replace("`", "\\`")
