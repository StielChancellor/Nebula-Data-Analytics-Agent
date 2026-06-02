"""
CSV sniffer (Phase 10-B) — read-before-commit schema inference.

Pure functions (no GCP imports) so they're unit-testable on raw bytes, mirroring
profiler.py being pure SQL-builders. The api_gateway reads the first N KB of the
uploaded GCS blob and runs these to produce a preview the user/agent can review
and override BEFORE the committing BigQuery load.

Why our own inference instead of BQ autodetect: autodetect mis-types real-world
India-locale data — DD-MM-YYYY dates become STRING, "1,24,000"/₹ amounts become
STRING — silently degrading every downstream query. We own a locale-aware ladder
so those are first-class.
"""
from __future__ import annotations

import csv
import io
import re

# ---------- public API ----------

# BQ types we infer. Kept to the load-friendly subset.
BQ_DATE = "DATE"
BQ_INT = "INT64"
BQ_NUMERIC = "NUMERIC"
BQ_BOOL = "BOOL"
BQ_STRING = "STRING"

_MAX_INFER_ROWS = 200
_BOOL_TOKENS = {"true", "false", "yes", "no", "y", "n", "t", "f"}
_INT_RE = re.compile(r"^[+-]?\d+$")
_DECIMAL_RE = re.compile(r"^[+-]?\d+(\.\d+)?$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")
_DMY_RE = re.compile(r"^(\d{1,2})([/-])(\d{1,2})\2(\d{4})$")  # 01-02-2024 or 01/02/2024


def sniff_csv(sample_bytes: bytes, locale_hint: str = "US") -> dict:
    """
    Infer encoding, delimiter, header, and per-column types from a byte sample.
    Returns a dict ready to serialize as the upload preview.
    """
    encoding, text = _decode(sample_bytes)
    delimiter, has_header = _sniff_dialect(text)

    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter) if r]
    truncated = len(rows) >= _MAX_INFER_ROWS
    if not rows:
        return {
            "encoding": encoding, "delimiter": delimiter, "has_header": has_header,
            "columns": [], "row_sample": [], "truncated": truncated,
        }

    ncols = max(len(r) for r in rows)
    if has_header:
        header = [(_clean(rows[0][i]) if i < len(rows[0]) else f"col_{i}") or f"col_{i}" for i in range(ncols)]
        data_rows = rows[1:]
    else:
        header = [f"col_{i}" for i in range(ncols)]
        data_rows = rows

    columns = []
    for i, name in enumerate(header):
        col_values = [r[i] for r in data_rows if i < len(r)]
        non_null = [v for v in col_values if v is not None and v.strip() != ""]
        bq_type, fmt = infer_column_type(non_null, locale_hint)
        columns.append({
            "name": name,
            "inferred_bq_type": bq_type,
            "inferred_format": fmt,
            "sample_values": [str(v) for v in non_null[:5]],
            "nullable": len(non_null) < len(col_values),
        })

    return {
        "encoding": encoding,
        "delimiter": delimiter,
        "has_header": has_header,
        "columns": columns,
        "row_sample": [[str(c) for c in r] for r in data_rows[:5]],
        "truncated": truncated,
    }


def infer_column_type(values: list[str], locale_hint: str = "US") -> tuple[str, str | None]:
    """
    Infer (bq_type, source_format) for a column from its non-null sample values.
    source_format is a hint for the normalize step (e.g. 'DD-MM-YYYY',
    'INR_GROUPED') or None when the raw value loads directly.
    """
    vals = [v.strip() for v in values if v is not None and v.strip() != ""]
    if not vals:
        return BQ_STRING, None

    # 1) Dates (ISO first, then day/month/year — disambiguated by locale + data).
    date_fmt = _infer_date_format(vals, locale_hint)
    if date_fmt is not None:
        return BQ_DATE, date_fmt

    # 2) Booleans (textual only — avoid stealing 0/1 integer columns).
    if all(v.lower() in _BOOL_TOKENS for v in vals):
        return BQ_BOOL, None

    # 3) Integers.
    if all(_INT_RE.match(v) for v in vals):
        return BQ_INT, None

    # 4) Numerics — including India-grouped / ₹ amounts after stripping.
    stripped = [_strip_money(v) for v in vals]
    if all(_DECIMAL_RE.match(s) for s in stripped):
        grouped = any(("," in v) or ("₹" in v) or ("Rs" in v) for v in vals)
        return BQ_NUMERIC, ("INR_GROUPED" if grouped else None)

    # 5) Fallback.
    return BQ_STRING, None


# ---------- internals ----------

def _decode(sample_bytes: bytes) -> tuple[str, str]:
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return (enc, sample_bytes.decode(enc))
        except UnicodeDecodeError:
            continue
    # latin-1 never raises, but keep a safe fallback.
    return ("latin-1", sample_bytes.decode("latin-1", errors="replace"))


def _sniff_dialect(text: str) -> tuple[str, bool]:
    head = "\n".join(text.splitlines()[:50])
    delimiter = ","
    has_header = True
    try:
        dialect = csv.Sniffer().sniff(head, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        # Guess by frequency among common delimiters on the first line.
        first = text.splitlines()[0] if text.splitlines() else ""
        delimiter = max(",;\t|", key=lambda d: first.count(d)) if first else ","
    try:
        has_header = csv.Sniffer().has_header(head)
    except csv.Error:
        has_header = True
    return delimiter, has_header


def _clean(s: str) -> str:
    return s.strip().lstrip("﻿")


def _strip_money(v: str) -> str:
    return (
        v.replace("₹", "").replace("Rs.", "").replace("Rs", "")
        .replace(",", "").replace(" ", "").strip()
    )


def _infer_date_format(vals: list[str], locale_hint: str) -> str | None:
    if all(_ISO_DATE_RE.match(v) for v in vals):
        return "YYYY-MM-DD"

    parsed = [_DMY_RE.match(v) for v in vals]
    if not all(parsed):
        return None

    sep = parsed[0].group(2)  # type: ignore[union-attr]
    first_nums = [int(m.group(1)) for m in parsed]   # type: ignore[union-attr]
    third_nums = [int(m.group(3)) for m in parsed]   # type: ignore[union-attr]

    # Disambiguate DMY vs MDY from the data, then fall back to locale.
    if any(n > 12 for n in first_nums):
        order = "DMY"
    elif any(n > 12 for n in third_nums):
        order = "MDY"
    else:
        order = "DMY" if locale_hint == "IN" else "MDY"

    if order == "DMY":
        return f"DD{sep}MM{sep}YYYY"
    return f"MM{sep}DD{sep}YYYY"
