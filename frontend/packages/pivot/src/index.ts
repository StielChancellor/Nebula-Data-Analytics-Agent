/**
 * @insnav/pivot
 *
 * Excel-grade drag-drop pivot table. Per PRD Phase 7: must ship with EVERY
 * Nebula §2.1 + §2.2 feature in one PR. No partial implementations.
 *
 * Feature checklist (each line is a non-negotiable):
 * - 4 drop zones: Filters / Rows / Columns / Values (@dnd-kit/core)
 * - Always-visible Table | Chart toggle
 * - Export ▾ (xlsx / csv / png) via portal'd dropdown (Nebula §6.5)
 * - Collapsible field zones (Fields ▾ toggle)
 * - Row-number gutter, sticky on x-axis
 * - All dim columns sticky on horizontal scroll (cumulative left offsets)
 * - Aggregation glyphs in headers (Σ Ø # ↑↓ μ)
 * - Active sort arrow + click-cycle desc→asc on measure cols
 * - Drag-to-reorder columns within same kind
 * - Excel-style row-dim group expand/collapse (≥ 2 row dims)
 * - Per-metric heatmap + global Heatmap quick-toggle
 * - Keyboard nav (arrows, Shift+arrows, Ctrl+A, Ctrl+C as TSV)
 * - Right-click context menu (drill / sort / filter / copy)
 * - In-table search overlay
 * - Live preview vs Compute (two latency budgets, two code paths)
 * - Pivot Lake modal at > 10 pivots
 * - Per-row + sort-by-measure
 * - Show-Values-As modes (% total, % col, running total, rank, raw)
 * - Slicers (detachable filter widgets)
 * - Numeric bucket chips (1/5/10/50/100/500/1000/custom histogram buckets)
 *
 * Backend pairs with backend/packages/cube-client (pivot_sql.py equivalent)
 * and the PivotConfig type defined in this file.
 */

import type { RegionCode } from "@insnav/locale";

export interface PivotConfig {
  datasetId: string;
  filters: PivotFilter[];
  rows: PivotRowField[];
  columns: PivotColField[];
  values: PivotValueField[];
  region?: RegionCode;
  chartType?: ChartType | null;
}

export interface PivotFilter { field: string; op: "in" | "between" | "eq"; value: unknown }
export interface PivotRowField { field: string; granularity?: "day" | "week" | "month" | "quarter" | "year" | "fy_year" | "fy_quarter" | "fortnight"; sortBy?: string; sortDir?: "asc" | "desc" }
export interface PivotColField { field: string }
export interface PivotValueField { field: string; agg: "sum" | "avg" | "count" | "min" | "max" | "median"; showAs?: "raw" | "pct_total" | "pct_col" | "running_total" | "rank" }

export type ChartType = "bar" | "line" | "area" | "pie" | "scatter" | "kpi" | "kpi_grid" | "treemap" | "waterfall" | "table" | "heatmap";

export const PIVOT_VERSION = "0.1.0";
