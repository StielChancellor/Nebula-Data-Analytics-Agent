/**
 * @insnav/dashboards
 *
 * Pinnable dashboards. The chart spec is the unit of pinning (Nebula §2.3).
 * POST /v1/dashboards with a portable spec → server persists + saves a
 * refresh recipe → dashboard re-runs against fresh data each visit.
 *
 * Also: dashboard-level parameter linking (one filter changes N cards) —
 * Metabase-inspired, see PRD § Features lifted from Metabase.
 *
 * TODO Phase 8.
 */

export interface ChartSpec {
  type: "bar" | "line" | "area" | "pie" | "scatter" | "kpi" | "kpi_grid" | "treemap" | "waterfall" | "table" | "heatmap";
  title?: string;
  // Portable spec — rows + columns + encodings + interactions. Defined fully in Phase 8.
  data: { columns: string[]; rows: unknown[][] };
  encodings?: Record<string, unknown>;
}

export interface DashboardCard {
  id: string;
  spec: ChartSpec;
  /** SHA hash of the resolved Cube query so refresh re-runs the same thing */
  refreshRecipeHash: string;
}

export const DASHBOARDS_VERSION = "0.1.0";
