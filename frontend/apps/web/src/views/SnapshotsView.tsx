/**
 * Snapshots + diff (Phase 11 #3).
 *
 * Capture a governed query's result at a point in time, then diff two captures:
 * "what changed in metric X between yesterday and today" — rows aligned by
 * dimension key, per-measure deltas computed in code.
 */
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@insnav/auth";
import {
  ApiClient,
  type PivotFields,
  type SnapshotMeta,
  type SnapshotDiff,
} from "@insnav/api-client";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const short = (n: string) => n.split(".").pop() || n;
const num = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 2 });

export function SnapshotsView({ projectId }: { projectId: string }) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );

  const [fields, setFields] = useState<PivotFields | null>(null);
  const [snaps, setSnaps] = useState<SnapshotMeta[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = () =>
    client.listSnapshots(projectId).then(setSnaps).catch(() => setSnaps([]));

  useEffect(() => {
    client.getPivotFields(projectId).then(setFields).catch(() => {});
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, projectId]);

  const measures = fields?.measures ?? [];
  const dims = fields?.dimensions ?? [];

  const [capMeasures, setCapMeasures] = useState<string[]>([]);
  const [capDim, setCapDim] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  const capture = async () => {
    if (capMeasures.length === 0 && !capDim) return;
    setBusy(true);
    setError(null);
    try {
      await client.captureSnapshot(
        projectId,
        { measures: capMeasures, dimensions: capDim ? [capDim] : [] },
        label.trim() || new Date().toISOString().slice(0, 16).replace("T", " "),
      );
      setLabel("");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [diff, setDiff] = useState<SnapshotDiff | null>(null);

  const runDiff = async () => {
    setError(null);
    setDiff(null);
    try {
      setDiff(await client.diffSnapshots(a, b));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const inputCls = "bg-ink-900 border border-ink-700/60 rounded px-2 py-1.5 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent";

  return (
    <div className="space-y-5">
      {error && (
        <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-3 py-2">{error}</div>
      )}

      <section className="border border-ink-700/60 rounded-lg bg-ink-800/30 p-4 space-y-3">
        <h3 className="text-sm font-semibold">Capture a snapshot</h3>
        <div className="flex flex-wrap gap-3 items-end">
          <label className="block text-[10px] uppercase tracking-wider text-ink-300">
            Measures
            <select multiple value={capMeasures}
                    onChange={(e) => setCapMeasures(Array.from(e.target.selectedOptions).map((o) => o.value))}
                    className={`${inputCls} mt-1 h-20 min-w-[160px]`}>
              {measures.map((m) => <option key={m.name} value={m.name}>{short(m.name)}</option>)}
            </select>
          </label>
          <label className="block text-[10px] uppercase tracking-wider text-ink-300">
            Break down by
            <select value={capDim} onChange={(e) => setCapDim(e.target.value)} className={`${inputCls} mt-1 block`}>
              <option value="">— none —</option>
              {dims.map((d) => <option key={d.name} value={d.name}>{short(d.name)}</option>)}
            </select>
          </label>
          <label className="block text-[10px] uppercase tracking-wider text-ink-300">
            Label
            <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="today"
                   className={`${inputCls} mt-1 block`} />
          </label>
          <button onClick={capture} disabled={busy || (capMeasures.length === 0 && !capDim)}
                  className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50">
            {busy ? "Capturing…" : "Capture"}
          </button>
        </div>
      </section>

      <section className="border border-ink-700/60 rounded-lg bg-ink-800/30 p-4 space-y-3">
        <div className="flex items-baseline justify-between">
          <h3 className="text-sm font-semibold">Diff snapshots</h3>
          <span className="text-[11px] text-ink-300">{snaps.length} captured</span>
        </div>
        <div className="flex flex-wrap gap-3 items-end">
          <label className="block text-[10px] uppercase tracking-wider text-ink-300">
            Baseline
            <select value={a} onChange={(e) => setA(e.target.value)} className={`${inputCls} mt-1 block min-w-[200px]`}>
              <option value="">— pick —</option>
              {snaps.map((s) => <option key={s.id} value={s.id}>{s.label} · {s.captured_at.slice(0, 16)}</option>)}
            </select>
          </label>
          <label className="block text-[10px] uppercase tracking-wider text-ink-300">
            Comparison
            <select value={b} onChange={(e) => setB(e.target.value)} className={`${inputCls} mt-1 block min-w-[200px]`}>
              <option value="">— pick —</option>
              {snaps.map((s) => <option key={s.id} value={s.id}>{s.label} · {s.captured_at.slice(0, 16)}</option>)}
            </select>
          </label>
          <button onClick={runDiff} disabled={!a || !b || a === b}
                  className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50">
            Diff
          </button>
        </div>

        {diff && (
          <div className="space-y-3 pt-2">
            <div className="flex gap-2 text-[11px]">
              <Stat label="changed" v={diff.diff.summary.changed} tone="amber" />
              <Stat label="added" v={diff.diff.summary.added} tone="green" />
              <Stat label="removed" v={diff.diff.summary.removed} tone="red" />
            </div>
            {diff.diff.changed.length > 0 && (
              <div className="overflow-auto max-h-72 border border-ink-700/50 rounded">
                <table className="w-full text-[11px]">
                  <thead className="text-ink-300 text-[10px] uppercase tracking-wider bg-ink-800/50">
                    <tr>
                      <th className="text-left px-2 py-1">{diff.diff.dimensions.map(short).join(" / ") || "row"}</th>
                      {diff.diff.measures.map((m) => <th key={m} className="text-right px-2 py-1">{short(m)}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {diff.diff.changed.map((ch, i) => (
                      <tr key={i} className="border-t border-ink-700/40">
                        <td className="px-2 py-1 font-mono">{ch.key.join(" / ") || "—"}</td>
                        {diff.diff.measures.map((m) => {
                          const d = ch.deltas[m];
                          if (!d) return <td key={m} className="px-2 py-1 text-right text-ink-500">—</td>;
                          const up = d.delta >= 0;
                          return (
                            <td key={m} className="px-2 py-1 text-right font-mono">
                              <span className={up ? "text-emerald-300" : "text-red-300"}>
                                {up ? "▲" : "▼"} {num(d.delta)}
                              </span>
                              {d.pct != null && <span className="text-ink-500"> ({num(d.pct)}%)</span>}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {(diff.diff.added.length > 0 || diff.diff.removed.length > 0) && (
              <div className="grid grid-cols-2 gap-3 text-[11px]">
                <KeyList title="Added rows" tone="green" keys={diff.diff.added} />
                <KeyList title="Removed rows" tone="red" keys={diff.diff.removed} />
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function Stat({ label, v, tone }: { label: string; v: number; tone: "amber" | "green" | "red" }) {
  const tones = { amber: "text-amber-300", green: "text-emerald-300", red: "text-red-300" };
  return (
    <span className="border border-ink-700/60 rounded px-2 py-1 bg-ink-900">
      <span className={`font-mono font-semibold ${tones[tone]}`}>{v}</span> <span className="text-ink-300">{label}</span>
    </span>
  );
}

function KeyList({ title, tone, keys }: { title: string; tone: "green" | "red"; keys: string[][] }) {
  if (keys.length === 0) return null;
  const tones = { green: "text-emerald-300", red: "text-red-300" };
  return (
    <div>
      <div className={`text-[10px] uppercase tracking-wider mb-1 ${tones[tone]}`}>{title}</div>
      <ul className="space-y-0.5 font-mono text-ink-200 max-h-40 overflow-auto">
        {keys.map((k, i) => <li key={i}>{k.join(" / ") || "—"}</li>)}
      </ul>
    </div>
  );
}
