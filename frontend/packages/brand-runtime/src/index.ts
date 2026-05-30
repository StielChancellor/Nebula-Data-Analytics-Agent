/**
 * @insnav/brand-runtime
 *
 * Runtime brand-token loader. Fetches GET /v1/me/brand and writes CSS vars
 * before React mounts. The build-time bundle (brand-static) is just the
 * entry point + favicon + logo path; EVERYTHING visual after first paint
 * is server-driven so a brand can be re-themed without rebuilding.
 *
 * PRD D3 + Critical files: apps/web/src/main.tsx must `await applyBrand()`
 * before `ReactDOM.createRoot(...).render(...)`.
 */

import type { RegionCode } from "@insnav/locale";

export interface BrandTokens {
  /** Accent color as `r g b` triplet for Tailwind `rgb(var(--accent) / <alpha>)` */
  accent: string;          // e.g. "124 58 237"   (violet-600)
  accentGlow: string;      // softer accent for hover halos
  accentSoft: string;      // very light accent surface
  /** Text color to use ON TOP of bg-accent surfaces. White on dark accents, black on bright. */
  accentForeground: string;
}

export interface BrandConfig {
  brandId: string;
  displayName: string;
  tokens: BrandTokens;
  logoUrl: string;
  faviconUrl?: string;
  currencyDefault: "USD" | "INR";
  regionDefault: RegionCode;
  featureFlags: Record<string, boolean>;
}

/**
 * Hardcoded fallback used during local dev or when /v1/me/brand is unreachable.
 * Per-brand `.env.<brand>` sets VITE_BRAND so we can pick the right fallback.
 */
const FALLBACK_BRANDS: Record<string, BrandConfig> = {
  nebula: {
    brandId: "nebula",
    displayName: "Insights Navigator",
    tokens: {
      accent: "124 58 237",            // violet-600
      accentGlow: "167 139 250",       // violet-400
      accentSoft: "237 233 254",       // violet-100
      accentForeground: "255 255 255", // white text on violet
    },
    logoUrl: "/brand/nebula/logo.svg",
    faviconUrl: "/brand/nebula/favicon.svg",
    currencyDefault: "USD",
    regionDefault: "US",
    featureFlags: {},
  },
};

const DEFAULT_BRAND_ID = "nebula";

/**
 * Apply CSS variables and metadata for the active brand.
 * Call this BEFORE React mounts. Throws nothing — falls back gracefully.
 */
export async function applyBrand(opts?: { apiBase?: string; brandId?: string }): Promise<BrandConfig> {
  const brandId = opts?.brandId ?? import.meta.env.VITE_BRAND ?? DEFAULT_BRAND_ID;
  const apiBase = opts?.apiBase ?? import.meta.env.VITE_API_BASE;

  let config: BrandConfig = FALLBACK_BRANDS[brandId] ?? FALLBACK_BRANDS[DEFAULT_BRAND_ID]!;

  // Try to fetch live brand config from backend. If anything fails, use fallback.
  if (apiBase) {
    try {
      const res = await fetch(`${apiBase}/v1/me/brand`, {
        headers: { "X-Brand-Id": brandId },
      });
      if (res.ok) {
        const live = (await res.json()) as BrandConfig;
        config = { ...config, ...live, tokens: { ...config.tokens, ...live.tokens } };
      }
    } catch {
      // Network error or backend not up — keep the fallback. Logged but not thrown.
      console.warn(`[brand-runtime] could not fetch /v1/me/brand; using fallback for "${brandId}"`);
    }
  }

  writeCssVars(config.tokens);
  setDocumentMeta(config);
  return config;
}

function writeCssVars(tokens: BrandTokens): void {
  const root = document.documentElement;
  root.style.setProperty("--accent", tokens.accent);
  root.style.setProperty("--accent-glow", tokens.accentGlow);
  root.style.setProperty("--accent-soft", tokens.accentSoft);
  root.style.setProperty("--accent-foreground", tokens.accentForeground);
}

function setDocumentMeta(config: BrandConfig): void {
  document.title = config.displayName;
  if (config.faviconUrl) {
    let link = document.querySelector<HTMLLinkElement>("link[rel~='icon']");
    if (!link) {
      link = document.createElement("link");
      link.rel = "icon";
      document.head.appendChild(link);
    }
    link.href = config.faviconUrl;
  }
}
