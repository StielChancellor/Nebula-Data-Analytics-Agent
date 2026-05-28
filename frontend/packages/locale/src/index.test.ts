/**
 * Locale tests — enforce the India non-negotiables from the PRD.
 * Run with: pnpm --filter @insnav/locale test
 */
import { describe, it, expect } from "vitest";
import {
  formatNumber,
  formatCompact,
  formatCurrency,
  formatCurrencyCompact,
  fyLabel,
  fyQuarter,
  LOCALES,
} from "./index";

describe("India locale (non-negotiable per PRD §8)", () => {
  it("uses en-IN grouping (1,24,00,000) for large numbers", () => {
    // en-IN puts the first comma after 3 digits then every 2 digits.
    expect(formatNumber(12400000, "IN")).toBe("1,24,00,000");
  });

  it("compacts via Lakh / Crore, not M / B", () => {
    expect(formatCompact(125000, "IN")).toBe("1.25L");
    expect(formatCompact(12400000, "IN")).toBe("1.24Cr");
    expect(formatCompact(50000, "IN")).toBe("50K");
  });

  it("formats currency with ₹ symbol", () => {
    const formatted = formatCurrency(1240000, "IN");
    expect(formatted).toContain("₹");
    expect(formatted).toMatch(/12,40,000/);
  });

  it("compact currency uses ₹ prefix + L/Cr", () => {
    expect(formatCurrencyCompact(12400000, "IN")).toBe("₹1.24Cr");
  });

  it("uses Apr-Mar fiscal year", () => {
    // May 2025 falls in FY26 (Apr 2025 - Mar 2026) in Indian convention
    expect(fyLabel(new Date("2025-05-15"), "IN")).toBe("FY26");
    // Feb 2025 falls in FY25 (Apr 2024 - Mar 2025)
    expect(fyLabel(new Date("2025-02-15"), "IN")).toBe("FY25");
  });

  it("uses Apr-Jun as Q1 of fiscal year", () => {
    expect(fyQuarter(new Date("2025-05-15"), "IN")).toBe("Q1");
    expect(fyQuarter(new Date("2025-11-15"), "IN")).toBe("Q3");
    expect(fyQuarter(new Date("2025-02-15"), "IN")).toBe("Q4");
  });

  it("uses Asia/Kolkata timezone", () => {
    expect(LOCALES.IN.timezone).toBe("Asia/Kolkata");
  });
});

describe("US locale", () => {
  it("uses M/B compaction", () => {
    expect(formatCompact(12400000, "US")).toMatch(/12\.4M/);
  });

  it("uses Jan-Dec FY (FY25 = calendar 2025)", () => {
    expect(fyLabel(new Date("2025-05-15"), "US")).toBe("FY25");
    expect(fyQuarter(new Date("2025-05-15"), "US")).toBe("Q2");
  });
});
