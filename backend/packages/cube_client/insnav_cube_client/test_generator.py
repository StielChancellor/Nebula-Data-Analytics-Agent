"""Unit tests for the Cube schema generator + JS renderer."""
import re

import pytest

from insnav_cube_client import (
    build_cube_schema,
    bq_type_to_cube_type,
    cube_name_for_dataset,
    render_to_js,
)


def _no_unescaped_nested_backticks(js: str) -> bool:
    """
    Every `sql:` value is a JS template literal (delimited by backticks). The
    BQ identifier backticks inside MUST be escaped (\\`), otherwise the value
    backtick closes the template early and Cube fails to compile with a
    "could not be cloned" DataCloneError. This guards that regression: no
    `sql:` line may contain an UNescaped backtick between its delimiters.
    """
    for line in js.splitlines():
        m = re.search(r"sql: `(.*)`,?$", line)
        if not m:
            continue
        body = m.group(1)
        # Walk the body; every backtick must be preceded by a backslash.
        for i, ch in enumerate(body):
            if ch == "`" and (i == 0 or body[i - 1] != "\\"):
                return False
    return True


def _ds(id_: str = "a3f4d2b1c0d9e8f7a3f4d2b1c0d9e8f7", label: str = "Sales 2026") -> dict:
    return {
        "id": id_,
        "tenant_id": "t1",
        "label": label,
        "bq_table": f"proj.raw.raw_{id_}",
        "locale_hint": "US",
    }


def _col(name: str, bq_type: str = "STRING", **kw) -> dict:
    return {"name": name, "type": bq_type, "key_likeness": 0.0, **kw}


class TestTypeMapping:
    def test_numeric_types_become_number(self) -> None:
        for t in ("INT64", "INTEGER", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
            assert bq_type_to_cube_type(t) == "number"

    def test_string_types_become_string(self) -> None:
        for t in ("STRING", "BYTES"):
            assert bq_type_to_cube_type(t) == "string"

    def test_time_types_become_time(self) -> None:
        for t in ("DATE", "TIMESTAMP", "DATETIME", "TIME"):
            assert bq_type_to_cube_type(t) == "time"

    def test_unknown_type_falls_back_to_string(self) -> None:
        assert bq_type_to_cube_type("GEOGRAPHY") == "string"

    def test_lowercase_input_works(self) -> None:
        assert bq_type_to_cube_type("int64") == "number"


class TestCubeName:
    def test_sanitizes_label_and_suffixes_with_short_id(self) -> None:
        name = cube_name_for_dataset("a3f4d2b1c0d9e8f7", "Sales 2026.csv")
        assert name == "sales_2026_csv__a3f4d2b1"

    def test_handles_label_starting_with_digit(self) -> None:
        name = cube_name_for_dataset("abcdef1234567890", "2026 Sales")
        # leading digit → prefixed with "x_"
        assert name.startswith("x_")

    def test_collapses_repeated_separators(self) -> None:
        name = cube_name_for_dataset("abcdef1234567890", "Hello!! World??")
        assert "__" not in name.replace("__abcdef12", "")  # only the separator before the id

    def test_empty_label_still_unique(self) -> None:
        n1 = cube_name_for_dataset("aaaaaaaa1234", "")
        n2 = cube_name_for_dataset("bbbbbbbb5678", "")
        assert n1 != n2


class TestBuildSchema:
    def test_every_cube_has_a_count_measure(self) -> None:
        s = build_cube_schema(dataset=_ds(), columns=[], edges=[])
        assert any(m.name == "count" and m.type == "count" for m in s.measures)

    def test_numeric_low_key_likeness_becomes_dimension_plus_sum_plus_avg(self) -> None:
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("revenue", "FLOAT64", key_likeness=0.05)],
            edges=[],
        )
        assert any(d.name == "revenue" for d in s.dimensions)
        names = {m.name for m in s.measures}
        assert "sum_revenue" in names
        assert "avg_revenue" in names

    def test_numeric_high_key_likeness_is_dimension_only_no_aggregation(self) -> None:
        """Foreign-key-like numerics shouldn't get sum/avg measures."""
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("user_id", "INT64", key_likeness=0.95)],
            edges=[],
        )
        names = {m.name for m in s.measures}
        assert "sum_user_id" not in names
        assert "avg_user_id" not in names
        assert any(d.name == "user_id" for d in s.dimensions)

    def test_revenue_column_flagged_revenue_touching(self) -> None:
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("net_revenue", "FLOAT64", key_likeness=0.0)],
            edges=[],
        )
        m = next(m for m in s.measures if m.name == "sum_net_revenue")
        assert m.revenue_touching is True
        assert s.revenue_touching() is True

    def test_non_revenue_numeric_not_flagged(self) -> None:
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("click_count", "INT64", key_likeness=0.0)],
            edges=[],
        )
        m = next(m for m in s.measures if m.name == "sum_click_count")
        assert m.revenue_touching is False
        assert s.revenue_touching() is False

    def test_first_high_key_likeness_column_becomes_primary_key(self) -> None:
        s = build_cube_schema(
            dataset=_ds(),
            columns=[
                _col("gclid", "STRING", key_likeness=0.95),
                _col("session_id", "STRING", key_likeness=0.92),
            ],
            edges=[],
        )
        pk_dims = [d for d in s.dimensions if d.primary_key]
        assert len(pk_dims) == 1
        assert pk_dims[0].name == "gclid"

    def test_no_primary_key_when_no_column_is_high_cardinality(self) -> None:
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("city", "STRING", key_likeness=0.4)],
            edges=[],
        )
        assert not any(d.primary_key for d in s.dimensions)

    def test_time_columns_become_time_dimensions(self) -> None:
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("event_date", "DATE"), _col("created_at", "TIMESTAMP")],
            edges=[],
        )
        time_dims = [d for d in s.dimensions if d.type == "time"]
        assert {d.name for d in time_dims} == {"event_date", "created_at"}

    def test_sanitizes_column_identifier_but_preserves_sql(self) -> None:
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("order id", "STRING", key_likeness=0.5)],
            edges=[],
        )
        d = next(d for d in s.dimensions if d.name == "order_id")
        # SQL uses the ORIGINAL column name (escaped) — BQ accepts "order id"
        assert d.sql == "`order id`"


class TestJoinsFromEdges:
    def test_join_only_added_when_edge_touches_this_dataset(self) -> None:
        s = build_cube_schema(
            dataset=_ds("aaaa1111aaaa1111aaaa1111aaaa1111", "A"),
            columns=[],
            edges=[
                {
                    "id": "e1",
                    "from_dataset": "BBBB",
                    "from_column": "x",
                    "to_dataset": "CCCC",
                    "to_column": "y",
                    "from_distinct_count": 100,
                    "to_distinct_count": 100,
                }
            ],
        )
        assert s.joins == []

    def test_join_from_side(self) -> None:
        ds_id = "aaaa1111aaaa1111aaaa1111aaaa1111"
        s = build_cube_schema(
            dataset=_ds(ds_id, "A"),
            columns=[],
            edges=[
                {
                    "id": "e1",
                    "from_dataset": ds_id,
                    "from_column": "gclid",
                    "to_dataset": "BBBBBBBB22222222BBBBBBBB22222222",
                    "to_column": "gclid",
                    "from_distinct_count": 1000,
                    "to_distinct_count": 1000,
                }
            ],
        )
        assert len(s.joins) == 1
        j = s.joins[0]
        assert j.from_edge_id == "e1"
        assert "gclid" in j.sql_clause
        # 1000 vs 1000 within 0.66-1.5 ratio → one_to_one
        assert j.relationship == "one_to_one"

    def test_join_to_side_reverses_columns(self) -> None:
        ds_id = "aaaa1111aaaa1111aaaa1111aaaa1111"
        s = build_cube_schema(
            dataset=_ds(ds_id, "A"),
            columns=[],
            edges=[
                {
                    "id": "e1",
                    "from_dataset": "BBBBBBBB22222222BBBBBBBB22222222",
                    "from_column": "external_id",
                    "to_dataset": ds_id,
                    "to_column": "id",
                    "from_distinct_count": 5000,
                    "to_distinct_count": 1000,
                }
            ],
        )
        j = s.joins[0]
        # Our `id` column joins to the OTHER cube's `external_id` column
        assert "${CUBE}.`id`" in j.sql_clause
        # From this dataset's POV (to_distinct=1000) the other side has 5000
        # → 1000/5000=0.2 → one_to_many
        assert j.relationship == "one_to_many"

    def test_many_to_many_when_distinct_unknown(self) -> None:
        ds_id = "aaaa1111aaaa1111aaaa1111aaaa1111"
        s = build_cube_schema(
            dataset=_ds(ds_id, "A"),
            columns=[],
            edges=[
                {
                    "id": "e1",
                    "from_dataset": ds_id,
                    "from_column": "x",
                    "to_dataset": "BBBBBBBB22222222BBBBBBBB22222222",
                    "to_column": "y",
                }
            ],
        )
        assert s.joins[0].relationship == "many_to_many"


class TestRenderToJS:
    def test_emits_count_measure(self) -> None:
        s = build_cube_schema(dataset=_ds(), columns=[], edges=[])
        js = render_to_js(s)
        assert "cube(`sales_2026__a3f4d2b1`," in js
        assert "count: {" in js
        assert "type: `count`," in js

    def test_omits_joins_block_when_no_joins(self) -> None:
        s = build_cube_schema(dataset=_ds(), columns=[], edges=[])
        js = render_to_js(s)
        assert "joins:" not in js

    def test_emits_joins_block_with_provenance_comment(self) -> None:
        ds_id = "aaaa1111aaaa1111aaaa1111aaaa1111"
        s = build_cube_schema(
            dataset=_ds(ds_id, "A"),
            columns=[],
            edges=[
                {
                    "id": "edge-xyz",
                    "from_dataset": ds_id,
                    "from_column": "gclid",
                    "to_dataset": "BBBBBBBB22222222BBBBBBBB22222222",
                    "to_column": "gclid",
                    "from_distinct_count": 1000,
                    "to_distinct_count": 1000,
                }
            ],
        )
        js = render_to_js(s)
        assert "joins: {" in js
        assert "from_edge_id: edge-xyz" in js
        assert "relationship: `one_to_one`," in js

    def test_emits_primary_key_marker(self) -> None:
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("gclid", "STRING", key_likeness=0.95)],
            edges=[],
        )
        js = render_to_js(s)
        assert "primary_key: true," in js

    def test_revenue_measures_get_warning_comment(self) -> None:
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("revenue", "FLOAT64", key_likeness=0.0)],
            edges=[],
        )
        js = render_to_js(s)
        assert "revenue_touching" in js

    def test_includes_provenance_header(self) -> None:
        s = build_cube_schema(dataset=_ds(), columns=[], edges=[])
        js = render_to_js(s)
        # Trail back to PRD constraint #2
        assert "Hard constraint #2" in js

    def test_sql_backticks_are_escaped_dimensions_and_measures(self) -> None:
        """Regression: nested backticks in sql: fields must be escaped, or Cube
        fails to compile (DataCloneError). Caught only at deploy in Phase 5b."""
        s = build_cube_schema(
            dataset=_ds(),
            columns=[_col("city", "STRING", key_likeness=0.2), _col("revenue", "FLOAT64", key_likeness=0.0)],
            edges=[],
        )
        js = render_to_js(s)
        assert _no_unescaped_nested_backticks(js), js
        # And the escaped form is actually present (not just absent of bare ones)
        assert r"sql: `\`city\``," in js
        assert r"sql: `\`revenue\``," in js

    def test_sql_backticks_are_escaped_in_joins(self) -> None:
        ds_id = "aaaa1111aaaa1111aaaa1111aaaa1111"
        s = build_cube_schema(
            dataset=_ds(ds_id, "A"),
            columns=[],
            edges=[{
                "id": "e1", "from_dataset": ds_id, "from_column": "gclid",
                "to_dataset": "BBBBBBBB22222222BBBBBBBB22222222", "to_column": "gclid",
                "from_distinct_count": 100, "to_distinct_count": 100,
            }],
        )
        js = render_to_js(s)
        assert _no_unescaped_nested_backticks(js), js
        # ${CUBE} interpolation stays LIVE (not escaped) so Cube fills it in.
        assert "${CUBE}" in js


class TestRoundtripWithComplexSchema:
    """Realistic: e-commerce transactions + ads, both with shared keys."""

    def test_full_schema(self) -> None:
        transactions_id = "tx0000aatx0000aatx0000aatx0000aa"
        ads_id = "ad0000bbad0000bbad0000bbad0000bb"
        s = build_cube_schema(
            dataset=_ds(transactions_id, "Transactions"),
            columns=[
                _col("order_id", "STRING", key_likeness=0.99),
                _col("gclid", "STRING", key_likeness=0.85),
                _col("city", "STRING", key_likeness=0.20),
                _col("revenue", "FLOAT64", key_likeness=0.01),
                _col("quantity", "INT64", key_likeness=0.02),
                _col("created_at", "TIMESTAMP"),
            ],
            edges=[
                {
                    "id": "e-tx-gclid",
                    "from_dataset": transactions_id,
                    "from_column": "gclid",
                    "to_dataset": ads_id,
                    "to_column": "gclid",
                    "from_distinct_count": 800,
                    "to_distinct_count": 1500,
                }
            ],
        )

        # Primary key picked once (highest-likeness column wins → order_id)
        pks = [d for d in s.dimensions if d.primary_key]
        assert len(pks) == 1
        assert pks[0].name == "order_id"

        # Revenue → revenue_touching
        assert s.revenue_touching() is True

        # Quantity numeric → sum/avg, not revenue-touching
        qty_sum = next(m for m in s.measures if m.name == "sum_quantity")
        assert qty_sum.revenue_touching is False

        # Join → one_to_many (transactions has fewer distinct gclids per row)
        assert len(s.joins) == 1
        assert s.joins[0].relationship == "one_to_many"

        # Renders to valid-looking JS
        js = render_to_js(s)
        assert js.startswith("// Auto-generated")
        assert js.endswith("});\n")
