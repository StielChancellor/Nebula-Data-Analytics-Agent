/**
 * Cube tab — auto-generated Cube schemas per dataset.
 *
 * PRD § L3 + Phase 5: every approved graph edge becomes a Cube join. Every
 * dataset becomes a Cube. Schemas are computed on demand from the current
 * Firestore state (datasets + column profiles + approved edges).
 *
 * View click → modal with the raw Cube .js the backend would emit. Phase 5b
 * will wire these into a deployed Cube service; until then this is the
 * proof that the generator works end-to-end.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClient, type CubeSchemaSummary } from "@insnav/api-client";
import { useAuth } from "@insnav/auth";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function CubeView() {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: () => auth.token }),
    [auth.token],
  );

  const [items, setItems] = useState<CubeSchemaSummary[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [viewing, setViewing] = useState<{ id: string; label: string } | null>(null);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const list = await client.listCubeSchemas();
      setItems(list);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }, [client]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <section className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Cube schemas</h2>
          <p className="text-[12px] text-ink-300 mt-0.5">
            Auto-generated from approved graph edges + dataset profiles. Every join here
            traces to a confirmed edge (PRD §2). View any schema to see the raw Cube .js.
          </p>
        </div>
        <button
          onClick={refresh}
          disabled={refreshing}
          className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60 hover:bg-ink-700/40 disabled:opacity-50"
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      {error && (
        <div className="text-[12px] text-red-400 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
          {error}
        </div>
      )}

      {items.length === 0 ? (
        <div className="border border-dashed border-ink-700/60 rounded p-6 text-center text-[12px] text-ink-300">
          No ready datasets yet — upload a CSV first, then come back here.
        </div>
      ) : (
        <SchemaTable
          items={items}
          onView={(s) => setViewing({ id: s.dataset_id, label: s.dataset_label })}
        />
      )}

      {viewing && (
        <SchemaModal
          client={client}
          datasetId={viewing.id}
          datasetLabel={viewing.label}
          onClose={() => setViewing(null)}
        />
      )}
    </section>
  );
}

function SchemaTable({
  items,
  onView,
}: {
  items: CubeSchemaSummary[];
  onView: (s: CubeSchemaSummary) => void;
}) {
  return (
    <div className="border border-ink-700/60 rounded-lg overflow-hidden">
      <table className="w-full text-[12px]">
        <thead className="bg-ink-800/60 text-ink-300 text-[11px] uppercase tracking-wider">
          <tr>
            <th className="text-left px-3 py-2 font-medium">Dataset</th>
            <th className="text-left px-3 py-2 font-medium">Cube</th>
            <th className="text-right px-3 py-2 font-medium">Dims</th>
            <th className="text-right px-3 py-2 font-medium">Measures</th>
            <th className="text-right px-3 py-2 font-medium">Joins</th>
            <th className="text-left px-3 py-2 font-medium">Notes</th>
            <th className="text-right px-3 py-2 font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {items.map((s) => (
            <tr key={s.dataset_id} className="border-t border-ink-700/40 hover:bg-ink-800/40">
              <td className="px-3 py-2 font-medium">{s.dataset_label}</td>
              <td className="px-3 py-2 font-mono text-[11px] text-ink-200">{s.cube_name}</td>
              <td className="px-3 py-2 text-right font-mono numeric">{s.dimension_count}</td>
              <td className="px-3 py-2 text-right font-mono numeric">{s.measure_count}</td>
              <td className="px-3 py-2 text-right font-mono numeric">{s.join_count}</td>
              <td className="px-3 py-2">
                {s.revenue_touching ? (
                  <span className="inline-block px-2 py-0.5 rounded text-[11px] bg-amber-900/30 text-amber-300">
                    revenue-touching
                  </span>
                ) : (
                  <span className="text-ink-400 text-[11px]">—</span>
                )}
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  onClick={() => onView(s)}
                  className="text-[12px] px-3 py-1 rounded border border-ink-700/60 hover:bg-ink-700/40"
                >
                  View .js
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SchemaModal({
  client,
  datasetId,
  datasetLabel,
  onClose,
}: {
  client: ApiClient;
  datasetId: string;
  datasetLabel: string;
  onClose: () => void;
}) {
  const [text, setText] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    client
      .getCubeSchemaJs(datasetId)
      .then((t) => {
        if (!cancelled) setText(t);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, datasetId]);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // permissions denied; ignore silently
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-ink-900/70 grid place-items-center p-6">
      <div className="w-full max-w-3xl max-h-[80vh] flex flex-col border border-ink-700/60 rounded-lg bg-ink-800 overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink-700/60">
          <div className="min-w-0">
            <div className="text-sm font-semibold truncate">Cube schema · {datasetLabel}</div>
            <div className="text-[11px] text-ink-300 font-mono truncate">{datasetId}</div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onCopy}
              disabled={!text}
              className="text-[12px] px-3 py-1 rounded border border-ink-700/60 hover:bg-ink-700/40 disabled:opacity-50"
            >
              Copy
            </button>
            <button onClick={onClose} className="text-ink-300 hover:text-ink-100 text-lg leading-none px-2">×</button>
          </div>
        </div>
        <div className="flex-1 overflow-auto p-4">
          {loading && <div className="text-[12px] text-ink-300">Generating…</div>}
          {error && <div className="text-[12px] text-red-400">{error}</div>}
          {!loading && !error && (
            <pre className="text-[11px] font-mono leading-relaxed text-ink-100 whitespace-pre-wrap">
              {text}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
