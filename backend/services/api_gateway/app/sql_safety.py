"""
BigQuery identifier safety (SEC C1).

Column names originate from uploaded CSV headers (attacker-controlled). Anywhere
a name is interpolated into a SQL string, it MUST be backtick-quoted with its
backticks/backslashes escaped, or a crafted header (e.g. ``a` AS x; DROP ...``)
breaks out and injects DDL/DML run by the api_gateway SA (which has BQ write).

Use `quote_bq_identifier()` for every identifier interpolated into SQL, and
`safe_date_format()` to validate a strptime format before it reaches PARSE_DATE.
"""
from __future__ import annotations

import re

# A strptime format we are willing to hand to BigQuery SAFE.PARSE_DATE: only the
# tokens our sniffer emits (%d %m %Y) plus '-' and '/' separators. Anything else
# (quotes, parens, semicolons) is rejected so it can't break the string literal.
_DATE_FMT_OK = re.compile(r"^(%[dmY]|[-/])+$")


def quote_bq_identifier(name: str) -> str:
    """Backtick-quote a BigQuery identifier, escaping embedded backticks/backslashes."""
    safe = str(name).replace("\\", "\\\\").replace("`", "\\`")
    return f"`{safe}`"


def safe_date_format(strptime_fmt: str) -> str:
    """Return the format if it only contains date tokens/separators, else raise."""
    if not _DATE_FMT_OK.match(strptime_fmt or ""):
        raise ValueError(f"unsafe date format: {strptime_fmt!r}")
    return strptime_fmt
