/**
 * Column-level lineage slide-over (Phase 11 #1).
 *
 * Click any governed field → trace it back: Cube member → SQL → raw BigQuery
 * columns → who human-confirmed each one → the approved graph edges that let it
 * join. Makes "deterministic" provable to a skeptic.
 */
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@insnav/auth";
import { ApiClient, type LineageTrace } from "@insnav/api-client";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const short = (n: string) => n.split(".").pop() || n;

export function LineageSlideOver({
  projectId,
  field,
  onClose,
}: {
  projectId: string;
  field: string;
  onClose: () => void;
}) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );
  const [trace, setTrace] = useState<LineageTrace | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setTrace(null);
    setError(null);
    client
      .getLineage(projectId, field)
      .then((t) => live && setTrace(t))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [client, projectId, field]);

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Lineage">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <aside className="relative w-full max-w-md h-full bg-ink-900 border-l border-ink-700/60 overflow-y-auto p-5 space-y-4 shadow-2xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-ink-300">Lineage</div>
            <h3 className="text-sm font-semibold font-mono">{field}</h3>
          </div>
          <button onClick={onClose} className="text-ink-300 hover:text-ink-100 text-lg leading-none" aria-label="Close">×</button>
        </div>

        {error && (
          <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
            {error}
          </div>
        )}
        {!trace && !error && <div className="text-[12px] text-ink-300">Tracing…</div>}

        {trace && (
          <div className="space-y-4 text-[12px]">
            <Row label="Kind">
              <span className="capitalize">{trace.kind}</span>
              {trace.aggregation && <Chip>{trace.aggregation}</Chip>}
              {trace.revenue_touching && <Chip tone="amber">revenue-touching</Chip>}
            </Row>
            <Row label="Cube">{trace.cube}</Row>
            <Row label="Dataset">{trace.dataset_label} <span className="text-ink-500">· {trace.locale}</span></Row>
            {trace.bq_table && <Row label="BigQuery"><span className="font-mono text-[11px]">{trace.bq_table}</span></Row>}

            {trace.sql && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-ink-300 mb-1">SQL expression</div>
                <pre className="bg-ink-800/60 border border-ink-700/50 rounded p-2 text-[11px] font-mono whitespace-pre-wrap break-all">
                  {trace.sql}
                </pre>
              </div>
            )}

            <div>
              <div className="text-[10px] uppercase tracking-wider text-ink-300 mb-1">
                Source columns ({trace.source_columns.length})
              </div>
              <div className="space-y-2">
                {trace.source_columns.map((c) => (
                  <div key={c.column} className="border border-ink-700/50 rounded p-2 bg-ink-800/30">
                    <div className="font-mono text-[12px] text-ink-100">{c.column}</div>
                    {c.business_meaning && <div className="text-ink-300 mt-0.5">{c.business_meaning}</div>}
                    <div className="mt-1 flex flex-wrap gap-1.5 items-center">
                      {c.role && <Chip>{c.role}</Chip>}
                      {c.confirmed_by ? (
                        <Chip tone="green">confirmed by {c.confirmed_by}</Chip>
                      ) : (
                        <Chip tone="slate">heuristic (unconfirmed)</Chip>
                      )}
                      {c.confirmed_at && <span className="text-ink-500 text-[10px]">{c.confirmed_at.slice(0, 10)}</span>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {trace.joins.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-wider text-ink-300 mb-1">
                  Joins via approved edges ({trace.joins.length})
                </div>
                <div className="space-y-1.5">
                  {trace.joins.map((j) => (
                    <div key={j.from_edge_id} className="border border-ink-700/50 rounded p-2 bg-ink-800/30">
                      <div className="text-ink-100">→ {short(j.to_cube)}</div>
                      <div className="font-mono text-[10px] text-ink-300 break-all">{j.sql_clause}</div>
                      <div className="text-[10px] text-ink-500">edge {j.from_edge_id.slice(0, 8)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <div className="w-20 shrink-0 text-[10px] uppercase tracking-wider text-ink-300">{label}</div>
      <div className="flex flex-wrap gap-1.5 items-center text-ink-100">{children}</div>
    </div>
  );
}

function Chip({ children, tone = "accent" }: { children: React.ReactNode; tone?: "accent" | "amber" | "green" | "slate" }) {
  const tones: Record<string, string> = {
    accent: "bg-accent/15 text-accent-glow border-accent/30",
    amber: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    green: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    slate: "bg-ink-700/40 text-ink-300 border-ink-600/40",
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border ${tones[tone]}`}>{children}</span>
  );
}
