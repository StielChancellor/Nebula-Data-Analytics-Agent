"""Pure unit tests for the India-aware CSV sniffer (Phase 10-B)."""
from __future__ import annotations

from services.api_gateway.app.sniffer import (
    BQ_BOOL,
    BQ_DATE,
    BQ_INT,
    BQ_NUMERIC,
    BQ_STRING,
    infer_column_type,
    sniff_csv,
)


class TestInferColumnType:
    def test_iso_date(self) -> None:
        assert infer_column_type(["2024-01-02", "2024-12-31"]) == (BQ_DATE, "YYYY-MM-DD")

    def test_india_ddmmyyyy_by_locale(self) -> None:
        # ambiguous (all parts <= 12) → locale decides
        assert infer_column_type(["01-02-2024", "03-04-2024"], "IN") == (BQ_DATE, "DD-MM-YYYY")
        assert infer_column_type(["01/02/2024", "03/04/2024"], "US") == (BQ_DATE, "MM/DD/YYYY")

    def test_ddmmyyyy_disambiguated_by_data(self) -> None:
        # day 25 > 12 forces DMY regardless of locale
        assert infer_column_type(["25-12-2024", "01-02-2024"], "US") == (BQ_DATE, "DD-MM-YYYY")

    def test_int(self) -> None:
        assert infer_column_type(["1", "2", "-3"]) == (BQ_INT, None)

    def test_plain_numeric(self) -> None:
        assert infer_column_type(["1.5", "2.0", "3.14"]) == (BQ_NUMERIC, None)

    def test_india_grouped_currency(self) -> None:
        # "1,24,000" + ₹ → NUMERIC with INR_GROUPED hint
        assert infer_column_type(["₹1,24,000", "₹50,000"], "IN") == (BQ_NUMERIC, "INR_GROUPED")
        assert infer_column_type(["1,24,000", "2,00,000"], "IN") == (BQ_NUMERIC, "INR_GROUPED")

    def test_bool(self) -> None:
        assert infer_column_type(["true", "false", "yes", "no"]) == (BQ_BOOL, None)

    def test_string_fallback(self) -> None:
        assert infer_column_type(["Mumbai", "Pune", "Delhi"]) == (BQ_STRING, None)

    def test_empty_is_string(self) -> None:
        assert infer_column_type([]) == (BQ_STRING, None)


class TestSniffCsv:
    def test_full_india_sample(self) -> None:
        csv_bytes = (
            "city,txn_date,amount,is_member\n"
            "Mumbai,25-12-2024,₹1,24,000,true\n"  # note: amount has internal comma → quoting matters
        ).encode("utf-8")
        # use a properly quoted amount so the comma isn't a delimiter
        csv_bytes = (
            'city,txn_date,amount,is_member\n'
            'Mumbai,25-12-2024,"1,24,000",true\n'
            'Pune,01-02-2024,"2,00,000",false\n'
        ).encode("utf-8")
        out = sniff_csv(csv_bytes, "IN")
        assert out["has_header"] is True
        assert out["delimiter"] == ","
        types = {c["name"]: (c["inferred_bq_type"], c["inferred_format"]) for c in out["columns"]}
        assert types["city"] == (BQ_STRING, None)
        assert types["txn_date"] == (BQ_DATE, "DD-MM-YYYY")
        assert types["amount"] == (BQ_NUMERIC, "INR_GROUPED")
        assert types["is_member"] == (BQ_BOOL, None)

    def test_us_sample(self) -> None:
        csv_bytes = b"region,rev\nWest,1000\nEast,2500\n"
        out = sniff_csv(csv_bytes, "US")
        types = {c["name"]: c["inferred_bq_type"] for c in out["columns"]}
        assert types == {"region": BQ_STRING, "rev": BQ_INT}
        assert out["row_sample"][0] == ["West", "1000"]
