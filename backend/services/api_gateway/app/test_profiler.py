"""Unit tests for the profile-SQL builder + the result parser."""
from services.api_gateway.app.profiler import (
    build_profile_query,
    build_sample_query,
    parse_profile_row,
)


class TestBuildProfileQuery:
    def test_emits_a_single_select_with_total_rows(self) -> None:
        sql = build_profile_query(
            "p.d.t",
            [("city", "STRING"), ("revenue", "FLOAT64")],
        )
        assert sql.startswith("SELECT ")
        assert "COUNT(*) AS __total_rows" in sql
        assert "FROM `p.d.t`" in sql

    def test_aggregates_each_column(self) -> None:
        sql = build_profile_query(
            "p.d.t",
            [("city", "STRING"), ("revenue", "FLOAT64")],
        )
        # nulls + distinct + min/max for each column
        assert "nulls_city" in sql and "nulls_revenue" in sql
        assert "distinct_city" in sql and "distinct_revenue" in sql
        assert "min_city" in sql and "min_revenue" in sql
        assert "max_city" in sql and "max_revenue" in sql
        # uses APPROX for cost
        assert "APPROX_COUNT_DISTINCT" in sql

    def test_uses_any_value_for_unorderable_types(self) -> None:
        sql = build_profile_query("p.d.t", [("blob_col", "BYTES")])
        assert "ANY_VALUE" in sql

    def test_escapes_column_names_with_backticks(self) -> None:
        sql = build_profile_query("p.d.t", [("order id", "STRING")])
        assert "`order id`" in sql


class TestBuildSampleQuery:
    def test_limits_rows(self) -> None:
        sql = build_sample_query("p.d.t", ["a", "b"], n=10)
        assert "LIMIT 10" in sql
        assert "`a`" in sql and "`b`" in sql


class TestParseProfileRow:
    def test_computes_null_pct_and_key_likeness(self) -> None:
        row = {
            "__total_rows": 1000,
            "nulls_email": 100,
            "distinct_email": 900,
            "min_email": "a@example.com",
            "max_email": "z@example.com",
        }
        profiles = parse_profile_row(
            row,
            [("email", "STRING")],
            samples=[{"email": "a@example.com"}, {"email": "b@example.com"}],
        )
        assert len(profiles) == 1
        p = profiles[0]
        assert p.row_count == 1000
        assert p.null_count == 100
        assert p.null_pct == 0.1
        assert p.distinct_count == 900
        # key_likeness = (1 - 0.1) * (900/1000) = 0.81
        assert abs(p.key_likeness - 0.81) < 1e-9
        assert p.sample_values == ["a@example.com", "b@example.com"]

    def test_handles_zero_rows(self) -> None:
        profiles = parse_profile_row(
            {"__total_rows": 0, "nulls_x": 0, "distinct_x": 0, "min_x": None, "max_x": None},
            [("x", "STRING")],
            samples=[],
        )
        assert profiles[0].row_count == 0
        assert profiles[0].null_pct == 0.0
        assert profiles[0].key_likeness == 0.0

    def test_low_cardinality_columns_get_low_key_likeness(self) -> None:
        # status field with 3 distinct values out of 1000 rows = low key candidate
        row = {
            "__total_rows": 1000, "nulls_status": 0, "distinct_status": 3,
            "min_status": "active", "max_status": "pending",
        }
        p = parse_profile_row(row, [("status", "STRING")], samples=[])[0]
        # key_likeness = (1 - 0) * (3/1000) = 0.003
        assert p.key_likeness < 0.01
