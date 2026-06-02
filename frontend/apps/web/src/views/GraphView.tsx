/**
 * Graph view: knowledge-graph proposals + approved edges.
 *
 * PRD § 4.3: this is the headline UX. Admin reviews each proposed edge and
 * confirms which become real joins. Until approved, the agent swarm cannot
 * connect those datasets.
 *
 * Two sections:
 *   - Proposed: pending review, with approve/reject buttons + the evidence
 *     (key-overlap %, sample shared values).
 *   - Approved: read-only list of confirmed joins (the "real" graph).
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@insnav/auth";
import {
  ApiClient,
  type GraphEdge as Edge,
  type DatasetListItem,
} from "@insnav/api-client";
import { KnowledgeGraphVisualization } from "./KnowledgeGraphVisualization";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function GraphView({ projectId }: { projectId?: string } = {}) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );

  const [proposed, setProposed] = useState<Edge[]>([]);
  const [approved, setApproved] = useState<Edge[]>([]);
  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // dataset_id → display label, so VisGraph nodes show human names not hex IDs
  const datasetLabels = useMemo<Record<string, string>>(
    () => Object.fromEntries(datasets.map((d) => [d.id, d.label])),
    [datasets],
  );

  const refresh = useCallback(async () => {
    try {
      const [p, a, ds] = await Promise.all([
        client.listEdgeProposals(projectId),
        client.listApprovedEdges(projectId),
        client.listDatasets(projectId),
      ]);
      setProposed(p);
      setApproved(a);
      setDatasets(ds);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [client, projectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onApprove = async (edge: Edge) => {
    setBusyId(edge.id);
    try {
      await client.approveEdge(edge.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  const onReject = async (edge: Edge) => {
    setBusyId(edge.id);
    try {
      await client.rejectEdge(edge.id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="space-y-6">
      <header>
        <h2 className="text-lg font-semibold">Knowledge graph</h2>
        <p className="text-[12px] text-ink-300 mt-0.5">
          Confirm which column pairs are real join keys. Until approved, the agent cannot
          connect those datasets — that's the non-negotiable trust line (PRD §4.3).
        </p>
      </header>

      {error && (
        <div className="text-[12px] text-red-400 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
          {error}
        </div>
      )}

      <ProposalsSection
        items={proposed}
        busyId={busyId}
        onApprove={onApprove}
        onReject={onReject}
      />

      <KnowledgeGraphVisualization
        approvedEdges={approved}
        datasetLabels={datasetLabels}
      />

      <ApprovedSection items={approved} />
    </section>
  );
}

function ProposalsSection({
  items,
  busyId,
  onApprove,
  onReject,
}: {
  items: Edge[];
  busyId: string | null;
  onApprove: (e: Edge) => void;
  onReject: (e: Edge) => void;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-ink-300">
          Proposed · {items.length}
        </div>
        <div className="text-[11px] text-ink-300">
          {items.length > 0 ? "review these to unlock cross-dataset joins" : "no pending proposals"}
        </div>
      </div>
      {items.length === 0 ? (
        <div className="border border-dashed border-ink-700/60 rounded p-4 text-center text-[12px] text-ink-300">
          Nothing to review. Upload datasets with shared join keys to see proposals here.
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map((e) => (
            <ProposalCard
              key={e.id}
              edge={e}
              busy={busyId === e.id}
              onApprove={() => onApprove(e)}
              onReject={() => onReject(e)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function ProposalCard({
  edge,
  busy,
  onApprove,
  onReject,
}: {
  edge: Edge;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
}) {
  const overlapPct = Math.round(edge.key_overlap_pct * 100);
  return (
    <li className="border border-ink-700/60 rounded-lg p-4 bg-ink-800/40 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1 min-w-0">
          <div className="text-sm font-medium font-mono break-all">
            {edge.from_dataset}<span className="text-ink-300">.</span>{edge.from_column}
            <span className="text-accent mx-2">↔</span>
            {edge.to_dataset}<span className="text-ink-300">.</span>{edge.to_column}
          </div>
          <div className="flex items-center gap-3 text-[11px] text-ink-300">
            <span><span className="text-ink-100 font-mono">{overlapPct}%</span> key overlap</span>
            {edge.from_distinct_count !== null && (
              <span>{edge.from_distinct_count} ↔ {edge.to_distinct_count} distinct</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={onReject}
            disabled={busy}
            className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60 hover:bg-red-950/40 hover:border-red-900/60 hover:text-red-300 disabled:opacity-50"
          >
            Reject
          </button>
          <button
            onClick={onApprove}
            disabled={busy}
            className="text-[12px] px-4 py-1.5 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "…" : "Approve"}
          </button>
        </div>
      </div>

      {edge.sample_overlap.length > 0 && (
        <div className="text-[11px] text-ink-300">
          <span className="text-ink-400">Shared sample values:</span>{" "}
          <span className="font-mono text-ink-100">
            {edge.sample_overlap.slice(0, 5).join(", ")}
          </span>
        </div>
      )}
    </li>
  );
}

function ApprovedSection({ items }: { items: Edge[] }) {
  return (
    <div className="space-y-2">
      <div className="text-[11px] uppercase tracking-wider text-ink-300">
        Approved · {items.length}
      </div>
      {items.length === 0 ? (
        <div className="border border-dashed border-ink-700/60 rounded p-4 text-center text-[12px] text-ink-300">
          No approved edges yet. Approve a proposal above to enable cross-dataset queries.
        </div>
      ) : (
        <div className="border border-ink-700/60 rounded-lg overflow-hidden">
          <table className="w-full text-[12px]">
            <thead className="bg-ink-800/60 text-ink-300 text-[11px] uppercase tracking-wider">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Edge</th>
                <th className="text-right px-3 py-2 font-medium">Overlap</th>
                <th className="text-left px-3 py-2 font-medium">Approved by</th>
                <th className="text-left px-3 py-2 font-medium">When</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id} className="border-t border-ink-700/40 hover:bg-ink-800/40">
                  <td className="px-3 py-2 font-mono break-all">
                    {e.from_dataset}.{e.from_column}
                    <span className="text-accent mx-2">↔</span>
                    {e.to_dataset}.{e.to_column}
                  </td>
                  <td className="px-3 py-2 text-right font-mono numeric">
                    {Math.round(e.key_overlap_pct * 100)}%
                  </td>
                  <td className="px-3 py-2 text-ink-300">{e.reviewed_by ?? "—"}</td>
                  <td className="px-3 py-2 text-ink-300 font-mono text-[11px]">
                    {e.reviewed_at ? new Date(e.reviewed_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
