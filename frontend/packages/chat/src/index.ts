/**
 * @insnav/chat
 *
 * Agent chat UI: streaming narration, interpretation echo (PRD mitigation #2),
 * data-health badge (PRD mitigation #3), provenance citations, "show the
 * Cube query that ran" toggle. Pin button on every chart that materializes.
 *
 * Multi-dataset selection header — user picks N datasets; the orchestrator
 * resolves cross-dataset queries via confirmed graph edges. If a required
 * edge is missing, the chat surfaces the unmet edge for admin approval.
 *
 * TODO Phase 6 (MVP single-source chat), Phase 10 (multi-dataset).
 */

export interface InterpretationEcho {
  text: string;
  confidence: number; // 0..1
  fields: { metric: string; dimensions: string[]; filters: string[]; attributionModel?: string };
}

export interface DataHealthBadge {
  freshness: { source: string; lastLoaded: string }[];
  completeness: { source: string; rowCount: number; expected: number }[];
  coverage: number | null;
  status: "ok" | "warn" | "block";
}

export const CHAT_VERSION = "0.1.0";
