/**
 * Metric registry (Phase 11 #8).
 *
 * Every governed measure in the project with its provenance: aggregation,
 * definition SQL, dataset, revenue flag, and WHO confirmed its meaning + WHEN.
 * Click a metric to trace its full lineage. Stops "revenue means three things".
 */
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@insnav/auth";
import { ApiClient, type MetricEntry } from "@insnav/api-client";
import { LineageSlideOver } from "./LineageSlideOver";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function MetricsView({ projectId }: { projectId: string }) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );
  const [metrics, setMetrics] = useState<MetricEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lineageField, setLineageField] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setMetrics(null);
    setError(null);
    client
      .getMetrics(projectId)
      .then((r) => live && setMetrics(r.metrics))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [client, projectId]);

  if (error)
    return (
      <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-3 py-2">
        {error}
      </div>
    );
  if (!metrics) return <div className="text-[12px] text-ink-300">Loading metrics…</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-semibold">Metric registry</h3>
        <span className="text-[11px] text-ink-300">{metrics.length} governed measures</span>
      </div>
      {metrics.length === 0 ? (
        <div className="text-[12px] text-ink-300 border border-ink-700/60 rounded-lg p-6 bg-ink-800/30">
          No measures yet. Upload a dataset and run onboarding to define metrics.
        </div>
      ) : (
        <div className="overflow-auto border border-ink-700/60 rounded-lg">
          <table className="w-full text-[12px]">
            <thead className="text-ink-300 text-[10px] uppercase tracking-wider bg-ink-800/50">
              <tr>
                <th className="text-left px-3 py-2">Metric</th>
                <th className="text-left px-3 py-2">Agg</th>
                <th className="text-left px-3 py-2">Dataset</th>
                <th className="text-left px-3 py-2">Owner</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((m) => (
                <tr key={m.name} className="border-t border-ink-700/40 hover:bg-ink-800/30">
                  <td className="px-3 py-2">
                    <div className="font-medium text-ink-100">{m.title}</div>
                    <div className="font-mono text-[10px] text-ink-400">{m.name}</div>
                    {m.revenue_touching && (
                      <span className="inline-block mt-0.5 text-[9px] px-1.5 py-0.5 rounded border bg-amber-500/15 text-amber-300 border-amber-500/30">
                        revenue
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-ink-200">{m.aggregation}</td>
                  <td className="px-3 py-2 text-ink-200">{m.dataset_label}</td>
                  <td className="px-3 py-2">
                    {m.owner ? (
                      <div>
                        <div className="text-emerald-300 text-[11px]">{m.owner}</div>
                        {m.effective_at && <div className="text-ink-500 text-[10px]">{m.effective_at.slice(0, 10)}</div>}
                      </div>
                    ) : (
                      <span className="text-ink-500 text-[11px]">unconfirmed</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right">
                    <button
                      onClick={() => setLineageField(m.name)}
                      className="text-[11px] px-2 py-1 rounded border border-ink-700/60 text-accent-glow hover:bg-ink-700/40"
                    >
                      Lineage
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {lineageField && (
        <LineageSlideOver projectId={projectId} field={lineageField} onClose={() => setLineageField(null)} />
      )}
      <p className="text-[10px] text-ink-400">
        Click <span className="text-accent-glow">Lineage</span> to trace any metric to its raw columns and confirmations.
      </p>
    </div>
  );
}
