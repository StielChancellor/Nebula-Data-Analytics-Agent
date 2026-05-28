/**
 * @insnav/charts
 *
 * Smart chart-type auto-selection + ECharts adapters. Rule-based on result
 * shape (PRD § Features lifted from Metabase). LLM proposes only when rules tie.
 *
 * Rule table:
 *   1 measure × 1 time dim         → line
 *   N measures × 1 dim             → grouped bar
 *   1 measure × 2 dims             → heatmap OR stacked
 *   1 measure × 0 dims (scalar)    → KPI tile
 *   2 measures of same units       → scatter
 *   1 measure × 1 dim (≤ 8 categs) → bar
 *   1 measure × 1 dim (categorical, share) → treemap
 *
 * Region-aware color palettes: when a dim is detected as Indian states,
 * default the palette to a known-good 29-color set (Nebula §2.4).
 *
 * TODO Phase 8.
 */

import type { ChartType } from "@insnav/pivot";

export interface SelectChartInput {
  numMeasures: number;
  numDimensions: number;
  hasTimeDim: boolean;
  categoryCount?: number;
  sameUnits?: boolean;
}

export function selectChartType(input: SelectChartInput): ChartType {
  if (input.numDimensions === 0 && input.numMeasures === 1) return "kpi";
  if (input.numMeasures === 1 && input.numDimensions === 1 && input.hasTimeDim) return "line";
  if (input.numMeasures > 1 && input.numDimensions === 1) return "bar";
  if (input.numMeasures === 1 && input.numDimensions === 2) return "heatmap";
  if (input.numMeasures === 2 && input.sameUnits) return "scatter";
  if (input.numMeasures === 1 && input.numDimensions === 1) return "bar";
  return "table";
}

export const CHARTS_VERSION = "0.1.0";
