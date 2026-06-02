"""
BQ-based profiler.

Per PRD/scope: must handle datasets up to 5 GB. Doing this in-process (pandas
on the file) would need ~15 GB RAM. Instead we let BigQuery do the scan and
just collect aggregates.

Cost: a single SELECT across a 5 GB table is < $0.03 (BQ on-demand pricing
is $5/TB; free tier covers the first 1 TB/month). Stays inside the $5/mo
guardrail comfortably.

What we compute per column:
  - type (from INFORMATION_SCHEMA.COLUMNS)
  - row_count, null_count, null_pct
  - distinct_count (only for typed-as-string / low-cardinality)
  - min_value / max_value
  - 5 sample values
  - key_likeness score = (1 - null_pct) * min(distinct_count / row_count, 1.0)
    high score → high cardinality + low nulls = candidate join key
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from services.api_gateway.app.datasets import ColumnProfile


def build_profile_query(table_fqn: str, columns: list[tuple[str, str]]) -> str:
    """
    Build a single SELECT that aggregates everything we need across all columns.

    Args:
        table_fqn:   `project.dataset.table`
        columns:     [(column_name, bq_type), ...] from INFORMATION_SCHEMA.COLUMNS

    Returns:
        A single SQL statement returning ONE row with all the per-column stats
        as flattened columns (count_<name>, nulls_<name>, ...). Cheaper than
        N round-trips even if uglier to consume.

    Why we don't run COUNT DISTINCT on every column: it's expensive on high-
    cardinality columns and we don't need exact counts. We use APPROX_COUNT_DISTINCT
    which is single-pass and within ~2% accurate.
    """
    if not columns:
        raise ValueError("profile query needs at least one column")

    from services.api_gateway.app.sql_safety import quote_bq_identifier

    tbl = quote_bq_identifier(table_fqn)
    parts: list[str] = ["COUNT(*) AS __total_rows"]
    for name, bq_type in columns:
        safe = _safe_alias(name)
        col = quote_bq_identifier(name)  # SEC C1: escape attacker-controlled names
        parts.append(f"COUNTIF({col} IS NULL) AS nulls_{safe}")
        parts.append(f"APPROX_COUNT_DISTINCT({col}) AS distinct_{safe}")
        # min/max only for orderable types; for the rest, use ANY_VALUE
        if bq_type.upper() in {
            "INT64", "INTEGER", "NUMERIC", "BIGNUMERIC", "FLOAT64", "FLOAT",
            "DATE", "TIME", "DATETIME", "TIMESTAMP", "STRING",
        }:
            parts.append(f"CAST(MIN({col}) AS STRING) AS min_{safe}")
            parts.append(f"CAST(MAX({col}) AS STRING) AS max_{safe}")
        else:
            parts.append(f"CAST(ANY_VALUE({col}) AS STRING) AS min_{safe}")
            parts.append(f"CAST(ANY_VALUE({col}) AS STRING) AS max_{safe}")

    select = ", ".join(parts)
    return f"SELECT {select} FROM {tbl}"


def build_sample_query(table_fqn: str, columns: list[str], n: int = 5) -> str:
    """Sample query — pulls N rows for sample_values."""
    from services.api_gateway.app.sql_safety import quote_bq_identifier

    col_list = ", ".join(quote_bq_identifier(c) for c in columns)
    return f"SELECT {col_list} FROM {quote_bq_identifier(table_fqn)} LIMIT {int(n)}"


def parse_profile_row(
    row: dict[str, Any], columns: list[tuple[str, str]], samples: list[dict[str, Any]]
) -> list[ColumnProfile]:
    """Turn the single aggregate row + sample rows into ColumnProfile objects."""
    total = int(row.get("__total_rows", 0) or 0)
    out: list[ColumnProfile] = []
    for name, bq_type in columns:
        safe = _safe_alias(name)
        nulls = int(row.get(f"nulls_{safe}", 0) or 0)
        distinct = row.get(f"distinct_{safe}")
        distinct = int(distinct) if distinct is not None else None
        null_pct = (nulls / total) if total else 0.0
        key_likeness = 0.0
        if total > 0 and distinct is not None:
            cardinality_ratio = min(distinct / total, 1.0)
            key_likeness = round((1.0 - null_pct) * cardinality_ratio, 4)

        sample_vals: list[str] = []
        for s in samples:
            v = s.get(name)
            if v is not None:
                sample_vals.append(_stringify(v))

        out.append(
            ColumnProfile(
                name=name,
                type=bq_type,
                row_count=total,
                null_count=nulls,
                null_pct=round(null_pct, 4),
                distinct_count=distinct,
                min_value=_stringify(row.get(f"min_{safe}")),
                max_value=_stringify(row.get(f"max_{safe}")),
                sample_values=sample_vals[:5],
                key_likeness=key_likeness,
            )
        )
    return out


def _safe_alias(col_name: str) -> str:
    """Make a column name safe for use as a SQL alias."""
    return "".join(c if (c.isalnum() or c == "_") else "_" for c in col_name)


def _stringify(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return str(v)
