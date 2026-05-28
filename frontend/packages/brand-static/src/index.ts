/**
 * @insnav/brand-static
 *
 * Build-time brand assets. Each brand is a folder under `assets/<brand-id>/`
 * containing logo.svg + favicon.svg + brand-meta.json. The build pipeline
 * copies the active brand's folder to `public/brand/<brand-id>/` so the
 * URLs referenced by brand-runtime (e.g. /brand/nebula/logo.svg) resolve.
 *
 * TODO Phase 1.5: implement the build-time copy step in tools/brand-build.
 */

export interface BrandStaticMeta {
  brandId: string;
  displayName: string;
}

export const KNOWN_BRANDS: Record<string, BrandStaticMeta> = {
  nebula: { brandId: "nebula", displayName: "Insights Navigator" },
};
