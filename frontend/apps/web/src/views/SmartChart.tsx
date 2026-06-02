/**
 * Smart chart-type auto-selection (Phase 8) + dependency-light renderers.
 *
 * Rule table on result shape (PRD): single number → KPI; 1 measure × 1 time →
 * line; 1+ measures × 1 dim → bar; else → table. Charts are CSS/SVG (no charting
 * lib) so they're robust and tiny. `chart_type` on the spec can force a type.
 */
import type { TileSpec } from "@insnav/api-client";

const short = (n: string) => n.split(".").pop() || n;
const toNum = (v: unknown): number => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};
const fmt = (v: unknown): string => {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString() : String(v);
};

export function autoChartType(spec: TileSpec, rows: unknown[][]): string {
  if (spec.chart_type && spec.chart_type !== "auto") return spec.chart_type;
  const m = spec.measures?.length ?? 0;
  const d = spec.dimensions?.length ?? 0;
  if (m >= 1 && d === 0 && !spec.time_dimension && rows.length <= 1) return "kpi";
  if (m >= 1 && spec.time_dimension) return "line";
  if (m >= 1 && d === 1) return "bar";
  return "table";
}

export function SmartChart({
  spec,
  columns,
  rows,
}: {
  spec: TileSpec;
  columns: string[];
  rows: unknown[][];
}) {
  const type = autoChartType(spec, rows);
  const idx: Record<string, number> = {};
  columns.forEach((c, i) => (idx[c] = i));
  const measures = spec.measures ?? [];
  const dims = spec.dimensions ?? [];
  const labelDim = spec.time_dimension || dims[0];
  const measure = measures[0];

  if (rows.length === 0) {
    return <div className="text-[12px] text-ink-300 py-6 text-center">No data.</div>;
  }

  const r0 = rows[0] ?? [];
  if (type === "kpi") {
    const val = measure ? r0[idx[measure] ?? 0] : r0[0];
    return (
      <div className="py-4 text-center">
        <div className="text-3xl font-semibold text-accent-glow font-mono numeric">{fmt(val)}</div>
        {measure && <div className="text-[11px] text-ink-300 mt-1">{short(measure)}</div>}
      </div>
    );
  }

  if (type === "bar" && measure && labelDim) {
    const mi = idx[measure] ?? 0;
    const di = idx[labelDim] ?? 0;
    const data = rows.map((r) => ({ label: String(r[di] ?? "—"), v: toNum(r[mi]) }));
    const max = Math.max(1, ...data.map((x) => Math.abs(x.v)));
    return (
      <div className="space-y-1.5 py-2">
        {data.slice(0, 20).map((x, i) => (
          <div key={i} className="flex items-center gap-2 text-[11px]">
            <div className="w-24 truncate text-ink-200" title={x.label}>{x.label}</div>
            <div className="flex-1 bg-ink-900 rounded h-3.5 overflow-hidden">
              <div className="h-full bg-accent" style={{ width: `${(Math.abs(x.v) / max) * 100}%` }} />
            </div>
            <div className="w-16 text-right font-mono numeric text-ink-200">{fmt(x.v)}</div>
          </div>
        ))}
      </div>
    );
  }

  if (type === "line" && measure && labelDim) {
    const mi = idx[measure] ?? 0;
    const di = idx[labelDim] ?? 0;
    const data = rows.map((r) => ({ label: String(r[di] ?? ""), v: toNum(r[mi]) }));
    const max = Math.max(1, ...data.map((x) => x.v));
    const min = Math.min(0, ...data.map((x) => x.v));
    const W = 320;
    const H = 120;
    const pts = data.map((x, i) => {
      const px = data.length > 1 ? (i / (data.length - 1)) * W : W / 2;
      const py = H - ((x.v - min) / (max - min || 1)) * H;
      return `${px.toFixed(1)},${py.toFixed(1)}`;
    });
    return (
      <div className="py-2">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-28" preserveAspectRatio="none">
          <polyline points={pts.join(" ")} fill="none" stroke="currentColor" strokeWidth="2" className="text-accent" />
        </svg>
        <div className="flex justify-between text-[10px] text-ink-300">
          <span>{data[0]?.label}</span>
          <span>{data[data.length - 1]?.label}</span>
        </div>
      </div>
    );
  }

  // table fallback
  return (
    <div className="overflow-auto max-h-64">
      <table className="w-full text-[11px]">
        <thead className="text-ink-300 text-[10px] uppercase tracking-wider">
          <tr>{columns.map((c) => <th key={c} className="text-left px-2 py-1">{short(c)}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 50).map((r, ri) => (
            <tr key={ri} className="border-t border-ink-700/40">
              {r.map((c, ci) => <td key={ci} className="px-2 py-1 font-mono numeric">{fmt(c)}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
