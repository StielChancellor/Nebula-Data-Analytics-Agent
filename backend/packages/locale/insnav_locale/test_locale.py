"""Mirror of the frontend locale tests — India non-negotiables (PRD §8)."""
from datetime import date

from insnav_locale import (
    LOCALES,
    format_compact,
    format_currency_compact,
    fy_label,
    fy_quarter,
)


class TestIndiaLocale:
    def test_lakh_crore_compaction(self) -> None:
        assert format_compact(125_000, "IN") == "1.25L"
        assert format_compact(12_400_000, "IN") == "1.24Cr"
        assert format_compact(50_000, "IN") == "50K"

    def test_currency_compact_with_rupee_symbol(self) -> None:
        assert format_currency_compact(12_400_000, "IN") == "₹1.24Cr"

    def test_apr_mar_fiscal_year(self) -> None:
        assert fy_label(date(2025, 5, 15), "IN") == "FY26"
        assert fy_label(date(2025, 2, 15), "IN") == "FY25"

    def test_fiscal_quarter(self) -> None:
        assert fy_quarter(date(2025, 5, 15), "IN") == "Q1"
        assert fy_quarter(date(2025, 11, 15), "IN") == "Q3"
        assert fy_quarter(date(2025, 2, 15), "IN") == "Q4"

    def test_asia_kolkata_timezone(self) -> None:
        assert LOCALES["IN"].timezone == "Asia/Kolkata"


class TestUSLocale:
    def test_million_billion_compaction(self) -> None:
        assert format_compact(12_400_000, "US") == "12.4M"
        assert format_compact(2_500_000_000, "US") == "2.5B"

    def test_calendar_fiscal_year(self) -> None:
        assert fy_label(date(2025, 5, 15), "US") == "FY25"
        assert fy_quarter(date(2025, 5, 15), "US") == "Q2"
