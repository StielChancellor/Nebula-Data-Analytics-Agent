"""
insnav_locale — Python mirror of the frontend @insnav/locale package.

Must stay in sync with frontend/packages/locale/src/index.ts. A CI test
(tests/test_locale_sync.py — TODO Phase 1) asserts the LOCALES dict
matches the frontend equivalent.

The backend uses this for:
  - Absolute date resolution ("last 30 days" → snapshot-tied range)
  - FY arithmetic in pivot SQL date dimensions
  - Currency labels in narration ("revenue is ₹1.24 Cr" vs "$12.4M")

NON-NEGOTIABLE per PRD § Hard Constraints #8: when region = "IN", every
formatted number / date used in answer narration MUST use ₹, en-IN grouping,
Lakh/Crore compaction, Apr-Mar FY, Asia/Kolkata timezone.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

RegionCode = Literal["US", "IN"]


@dataclass(frozen=True)
class LocalePreset:
    region: RegionCode
    currency: Literal["USD", "INR"]
    currency_symbol: str
    timezone: str
    fy_start_month: int   # 1 = Jan, 4 = April
    locale: Literal["en-US", "en-IN"]


LOCALES: dict[RegionCode, LocalePreset] = {
    "US": LocalePreset(
        region="US",
        currency="USD",
        currency_symbol="$",
        timezone="America/New_York",
        fy_start_month=1,
        locale="en-US",
    ),
    "IN": LocalePreset(
        region="IN",
        currency="INR",
        currency_symbol="₹",
        timezone="Asia/Kolkata",
        fy_start_month=4,
        locale="en-IN",
    ),
}

DEFAULT_REGION: RegionCode = "US"


def format_compact(value: int | float, region: RegionCode = DEFAULT_REGION) -> str:
    """
    US: K / M / B.   IN: K / L / Cr (Lakh / Crore).
    Matches the frontend formatCompact() exactly.
    """
    sign = "-" if value < 0 else ""
    abs_v = abs(float(value))
    if region == "IN":
        if abs_v >= 1e7:
            return f"{sign}{_strip_zeros(abs_v / 1e7)}Cr"
        if abs_v >= 1e5:
            return f"{sign}{_strip_zeros(abs_v / 1e5)}L"
        if abs_v >= 1e3:
            return f"{sign}{_strip_zeros(abs_v / 1e3)}K"
        return f"{sign}{int(abs_v) if abs_v == int(abs_v) else abs_v}"
    # US
    if abs_v >= 1e9:
        return f"{sign}{_strip_zeros(abs_v / 1e9)}B"
    if abs_v >= 1e6:
        return f"{sign}{_strip_zeros(abs_v / 1e6)}M"
    if abs_v >= 1e3:
        return f"{sign}{_strip_zeros(abs_v / 1e3)}K"
    return f"{sign}{int(abs_v) if abs_v == int(abs_v) else abs_v}"


def format_currency_compact(value: int | float, region: RegionCode = DEFAULT_REGION) -> str:
    return f"{LOCALES[region].currency_symbol}{format_compact(value, region)}"


def fy_label(d: date | datetime, region: RegionCode = DEFAULT_REGION) -> str:
    """India: Apr-Mar FY. May 2025 → FY26 (Apr 2025 – Mar 2026)."""
    preset = LOCALES[region]
    if preset.fy_start_month == 1:
        return f"FY{str(d.year)[-2:]}"
    end_year = d.year + 1 if d.month >= preset.fy_start_month else d.year
    return f"FY{str(end_year)[-2:]}"


def fy_quarter(d: date | datetime, region: RegionCode = DEFAULT_REGION) -> str:
    preset = LOCALES[region]
    fy_month = (d.month - preset.fy_start_month + 12) % 12
    return f"Q{fy_month // 3 + 1}"


def _strip_zeros(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s or "0"
