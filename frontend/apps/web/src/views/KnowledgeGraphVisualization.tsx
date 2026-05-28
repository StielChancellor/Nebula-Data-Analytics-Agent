/**
 * Knowledge-graph node-link visualization using @unovis/react.
 *
 * Each unique dataset (referenced by any approved edge) becomes a node;
 * each approved edge becomes a link. Theming reads from the brand-runtime
 * CSS vars so this re-skins automatically per brand.
 *
 * Why Unovis: TypeScript-first, modular tree-shaking, Apache-2.0, used by
 * the PRD's chart system everywhere going forward (replaces ECharts).
 *
 * Phase 4.5: nodes can be clicked to filter the proposals/approved list
 * to just edges touching that dataset. Not wired this turn.
 */
import { useMemo } from "react";
import { VisGraph, VisSingleContainer } from "@unovis/react";
import type { GraphEdge as Edge } from "@insnav/api-client";

// Unovis data shape. Source/target are node ids (strings).
interface GraphNode {
  id: string;
  label: string;
  edgeCount: number;
}

interface GraphLink {
  id: string;
  source: string;
  target: string;
  overlapPct: number;
}

interface Props {
  approvedEdges: Edge[];
  datasetLabels?: Record<string, string>; // optional dataset_id → display label
}

export function KnowledgeGraphVisualization({ approvedEdges, datasetLabels = {} }: Props) {
  const { nodes, links } = useMemo(() => buildGraphData(approvedEdges, datasetLabels), [approvedEdges, datasetLabels]);

  if (nodes.length === 0) {
    return (
      <div className="border border-dashed border-ink-700/60 rounded p-6 text-center text-[12px] text-ink-300">
        Approve an edge above to render the knowledge graph here.
      </div>
    );
  }

  return (
    <div className="border border-ink-700/60 rounded-lg bg-ink-800/40 p-2">
      <div className="px-2 pt-1 pb-2 text-[11px] uppercase tracking-wider text-ink-300">
        Approved edges · {nodes.length} datasets · {links.length} confirmed joins
      </div>
      <div className="h-[360px]">
        <VisSingleContainer<GraphData> data={{ nodes, links }}>
          <VisGraph<GraphNode, GraphLink>
            nodeLabel={(d: GraphNode) => d.label}
            nodeSize={(d: GraphNode) => 18 + Math.min(d.edgeCount * 4, 24)}
            nodeFill="rgb(var(--accent))"
            nodeStroke="rgb(var(--accent-glow))"
            nodeStrokeWidth={1.5}
            linkStroke="rgb(var(--accent-glow) / 0.55)"
            linkWidth={(l: GraphLink) => 1 + l.overlapPct * 3}
            linkArrow={false}
          />
        </VisSingleContainer>
      </div>
    </div>
  );
}

type GraphData = { nodes: GraphNode[]; links: GraphLink[] };

function buildGraphData(edges: Edge[], labels: Record<string, string>): GraphData {
  const nodeMap = new Map<string, GraphNode>();
  const links: GraphLink[] = [];

  for (const e of edges) {
    incNode(nodeMap, e.from_dataset, labels);
    incNode(nodeMap, e.to_dataset, labels);
    links.push({
      id: e.id,
      source: e.from_dataset,
      target: e.to_dataset,
      overlapPct: e.key_overlap_pct,
    });
  }

  return { nodes: Array.from(nodeMap.values()), links };
}

function incNode(map: Map<string, GraphNode>, datasetId: string, labels: Record<string, string>) {
  const existing = map.get(datasetId);
  if (existing) {
    existing.edgeCount += 1;
    return;
  }
  map.set(datasetId, {
    id: datasetId,
    label: labels[datasetId] ?? shortId(datasetId),
    edgeCount: 1,
  });
}

function shortId(id: string): string {
  // dataset_id is a 32-char hex; show first 8 for the label
  return id.length > 12 ? `${id.slice(0, 8)}…` : id;
}
