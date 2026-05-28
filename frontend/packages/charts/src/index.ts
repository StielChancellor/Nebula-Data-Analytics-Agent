/**
 * @insnav/charts
 *
 * Smart chart-type auto-selection + Unovis adapters.
 *
 * PRD D13: charts = Unovis (`@unovis/react` + `@unovis/ts`), Apache-2.0.
 * TypeScript-first, modular tree-shaking, includes `VisGraph` for the
 * knowledge-graph visualization (Phase 4) and the standard chart set
 * (line, area, bar, scatter, KPI, treemap, heatmap, sankey, chord, ...).
 * Imported directly from @unovis/react in apps/web — this package owns
 * the *selection rules*, not the rendering primitives.
 *
 * The selectChartType() rule below is rule-based: result-shape → chart
 * type. LLM proposes a chart type only when rules tie (PRD § Features
 * lifted from Metabase).
 *
 * Region-aware color palettes: when a dim is detected as Indian states,
 * default the palette to a known-good 29-color set (Nebula §2.4).
 *
 * TODO Phase 8: implement the actual <SmartChart spec={...}/> renderer
 * that consumes a portable chart spec (the pinning unit) and dispatches
 * to the right VisXxx component.
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

export const CHARTS_VERSION = "0.2.0";
