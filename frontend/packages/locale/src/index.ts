/**
 * @insnav/locale
 *
 * Region-aware locale presets. The single source of truth for how numbers,
 * dates, currency, and fiscal year behave across the entire frontend.
 *
 * Mirror lives at backend/packages/locale/insnav_locale/__init__.py.
 * A CI test asserts the two stay in sync (currency code, FY start, timezone).
 *
 * NON-NEGOTIABLE per PRD § Hard Constraints #8: when region = IN, every number
 * displayed in the app MUST use ₹, en-IN grouping (1,24,00,000), Lakh/Crore
 * compaction, Apr-Mar fiscal year default on every date dimension, and the
 * Asia/Kolkata timezone for "today/yesterday" semantics.
 */

export type RegionCode = "US" | "IN";

export interface LocalePreset {
  region: RegionCode;
  currency: "USD" | "INR";
  currencySymbol: "$" | "₹";
  /** IANA timezone — drives "yesterday" / day-bucketing in the user's locale */
  timezone: string;
  /** 1 = January (US calendar FY), 4 = April (Indian FY) */
  fyStartMonth: number;
  /** BCP-47 locale used for Intl.NumberFormat / Intl.DateTimeFormat */
  locale: "en-US" | "en-IN";
}

export const LOCALES: Record<RegionCode, LocalePreset> = {
  US: {
    region: "US",
    currency: "USD",
    currencySymbol: "$",
    timezone: "America/New_York",
    fyStartMonth: 1,
    locale: "en-US",
  },
  IN: {
    region: "IN",
    currency: "INR",
    currencySymbol: "₹",
    timezone: "Asia/Kolkata",
    fyStartMonth: 4,
    locale: "en-IN",
  },
};

export const DEFAULT_REGION: RegionCode = "US";

// ---------- Number formatting ----------

/**
 * Format an integer/float with locale-aware grouping.
 *   formatNumber(1240000, "US") => "1,240,000"
 *   formatNumber(1240000, "IN") => "12,40,000"
 */
export function formatNumber(
  value: number,
  region: RegionCode = DEFAULT_REGION,
  options: Intl.NumberFormatOptions = {},
): string {
  const preset = LOCALES[region];
  return new Intl.NumberFormat(preset.locale, options).format(value);
}

/**
 * Compact format. US uses K/M/B; IN uses K/L/Cr (Lakh/Crore).
 *   formatCompact(12_400_000, "US") => "12.4M"
 *   formatCompact(12_400_000, "IN") => "1.24Cr"
 *   formatCompact(125_000, "IN")    => "1.25L"
 *
 * NOTE: Intl.NumberFormat's `notation: "compact"` does NOT emit Lakh/Crore
 * for en-IN as of 2025/26. We implement IN compaction manually.
 */
export function formatCompact(value: number, region: RegionCode = DEFAULT_REGION): string {
  if (region === "IN") {
    const abs = Math.abs(value);
    const sign = value < 0 ? "-" : "";
    if (abs >= 1e7) return `${sign}${(abs / 1e7).toFixed(2).replace(/\.?0+$/, "")}Cr`;
    if (abs >= 1e5) return `${sign}${(abs / 1e5).toFixed(2).replace(/\.?0+$/, "")}L`;
    if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(2).replace(/\.?0+$/, "")}K`;
    return `${sign}${abs}`;
  }
  return new Intl.NumberFormat(LOCALES[region].locale, {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Format as currency.
 *   formatCurrency(1240000, "US") => "$1,240,000.00"
 *   formatCurrency(1240000, "IN") => "₹12,40,000.00"
 */
export function formatCurrency(value: number, region: RegionCode = DEFAULT_REGION): string {
  const preset = LOCALES[region];
  return new Intl.NumberFormat(preset.locale, {
    style: "currency",
    currency: preset.currency,
  }).format(value);
}

/**
 * Compact currency.
 *   formatCurrencyCompact(12_400_000, "US") => "$12.4M"
 *   formatCurrencyCompact(12_400_000, "IN") => "₹1.24Cr"
 */
export function formatCurrencyCompact(value: number, region: RegionCode = DEFAULT_REGION): string {
  return `${LOCALES[region].currencySymbol}${formatCompact(value, region)}`;
}

// ---------- Fiscal-year helpers ----------

/**
 * Given a calendar date and a region, return the fiscal-year label
 * the customer expects to see.
 *   fyLabel(new Date("2025-05-15"), "IN") => "FY26" (Apr 2025 - Mar 2026)
 *   fyLabel(new Date("2025-05-15"), "US") => "FY25" (Jan 2025 - Dec 2025)
 */
export function fyLabel(date: Date, region: RegionCode = DEFAULT_REGION): string {
  const preset = LOCALES[region];
  const month = date.getMonth() + 1; // 1-12
  const year = date.getFullYear();
  if (preset.fyStartMonth === 1) {
    return `FY${String(year).slice(-2)}`;
  }
  // April-start FY: a date in Jan-Mar belongs to "previous" FY end
  const fyEndYear = month >= preset.fyStartMonth ? year + 1 : year;
  return `FY${String(fyEndYear).slice(-2)}`;
}

/**
 * Quarter within fiscal year. Q1..Q4.
 *   fyQuarter(new Date("2025-05-15"), "IN") => "Q1" (Apr-Jun)
 *   fyQuarter(new Date("2025-05-15"), "US") => "Q2" (Apr-Jun in Jan-start FY)
 */
export function fyQuarter(date: Date, region: RegionCode = DEFAULT_REGION): string {
  const preset = LOCALES[region];
  const month = date.getMonth() + 1; // 1-12
  // Number of months since FY start (0..11)
  const fyMonth = (month - preset.fyStartMonth + 12) % 12;
  return `Q${Math.floor(fyMonth / 3) + 1}`;
}

// ---------- Date formatting ----------

export function formatDate(
  date: Date,
  region: RegionCode = DEFAULT_REGION,
  options: Intl.DateTimeFormatOptions = { dateStyle: "medium" },
): string {
  const preset = LOCALES[region];
  return new Intl.DateTimeFormat(preset.locale, { ...options, timeZone: preset.timezone }).format(date);
}
