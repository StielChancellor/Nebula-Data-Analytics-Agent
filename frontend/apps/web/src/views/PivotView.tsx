/**
 * Pivot panel (Phase 7) — drag fields onto Rows / Columns / Values shelves and
 * the governed cube computes a crosstab. No LLM: pure user-driven field
 * selection → deterministic Cube query. Table ↕ Chart toggle, Copy-as-TSV.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiClient,
  type PivotField,
  type PivotFields,
  type PivotResult,
} from "@insnav/api-client";
import { useAuth } from "@insnav/auth";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

type Shelf = "rows" | "cols" | "values";
const short = (n: string) => n.split(".").pop() || n;

export function PivotView({ projectId }: { projectId: string }) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );

  const [fields, setFields] = useState<PivotFields | null>(null);
  const [rows, setRows] = useState<string[]>([]);
  const [cols, setCols] = useState<string[]>([]);
  const [values, setValues] = useState<string[]>([]);
  const [result, setResult] = useState<PivotResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"table" | "chart">("table");
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    client
      .getPivotFields(projectId)
      .then(setFields)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [client, projectId]);

  // Run the query (debounced) whenever the shelves change.
  useEffect(() => {
    if (values.length === 0 && rows.length === 0 && cols.length === 0) {
      setResult(null);
      return;
    }
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      setBusy(true);
      setError(null);
      client
        .pivotQuery({ project_id: projectId, measures: values, dimensions: [...rows, ...cols] })
        .then(setResult)
        .catch((e) => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setBusy(false));
    }, 400);
  }, [client, projectId, rows, cols, values]);

  // Which shelf a field currently lives on (so the palette can grey it out).
  const placed = new Set([...rows, ...cols, ...values]);

  const onDrop = (shelf: Shelf, name: string, isMeasure: boolean) => {
    // measures only on Values; dimensions only on Rows/Cols
    if (isMeasure && shelf !== "values") return;
    if (!isMeasure && shelf === "values") return;
    setRows((r) => r.filter((x) => x !== name));
    setCols((c) => c.filter((x) => x !== name));
    setValues((v) => v.filter((x) => x !== name));
    if (shelf === "rows") setRows((r) => [...r, name]);
    if (shelf === "cols") setCols((c) => [...c, name]);
    if (shelf === "values") setValues((v) => [...v, name]);
  };

  const removeFrom = (shelf: Shelf, name: string) => {
    if (shelf === "rows") setRows((r) => r.filter((x) => x !== name));
    if (shelf === "cols") setCols((c) => c.filter((x) => x !== name));
    if (shelf === "values") setValues((v) => v.filter((x) => x !== name));
  };

  const grid = useMemo(
    () => (result ? buildCrosstab(result, rows, cols, values) : null),
    [result, rows, cols, values],
  );

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold">Pivot</h2>
        <p className="text-[12px] text-ink-300 mt-0.5">
          Drag fields onto Rows, Columns &amp; Values. The governed cube computes the crosstab.
        </p>
      </header>

      {error && (
        <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
          {error}
        </div>
      )}

      <div className="grid grid-cols-[200px_1fr] gap-4">
        {/* Field palette */}
        <div className="border border-ink-700/60 rounded-lg bg-ink-800/40 p-3 space-y-3 self-start">
          <FieldGroup title="Measures" fields={fields?.measures ?? []} placed={placed} measure />
          <FieldGroup
            title="Dimensions"
            fields={[...(fields?.dimensions ?? []), ...(fields?.time_dimensions ?? [])]}
            placed={placed}
          />
          {!fields && <div className="text-[11px] text-ink-300">Loading fields…</div>}
        </div>

        {/* Shelves + result */}
        <div className="space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <ShelfBox label="Rows" items={rows} onDrop={onDrop} which="rows" onRemove={removeFrom} />
            <ShelfBox label="Columns" items={cols} onDrop={onDrop} which="cols" onRemove={removeFrom} />
            <ShelfBox label="Values" items={values} onDrop={onDrop} which="values" onRemove={removeFrom} />
          </div>

          <div className="flex items-center justify-between">
            <div className="text-[11px] text-ink-300">{busy ? "Computing…" : grid ? `${grid.body.length} rows` : ""}</div>
            <div className="flex items-center gap-2">
              {grid && (
                <button
                  onClick={() => copyTsv(grid)}
                  className="text-[11px] px-2 py-1 rounded border border-ink-700/60 text-ink-200 hover:bg-ink-700/40"
                >
                  Copy TSV
                </button>
              )}
              <div className="flex items-center rounded border border-ink-700/60 overflow-hidden text-[11px]">
                {(["table", "chart"] as const).map((v) => (
                  <button
                    key={v}
                    onClick={() => setView(v)}
                    className={`px-2 py-1 capitalize ${view === v ? "bg-accent text-accent-foreground font-semibold" : "bg-ink-800/40 text-ink-200"}`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {!grid ? (
            <div className="border border-dashed border-ink-700/60 rounded-lg p-10 text-center text-[12px] text-ink-300 bg-ink-800/20">
              Drag a measure onto <span className="text-ink-100">Values</span> and a dimension onto{" "}
              <span className="text-ink-100">Rows</span> to begin.
            </div>
          ) : view === "table" ? (
            <PivotTable grid={grid} />
          ) : (
            <PivotChart grid={grid} />
          )}
        </div>
      </div>
    </section>
  );
}

// ---------- palette + shelves ----------

function FieldGroup({
  title,
  fields,
  placed,
  measure = false,
}: {
  title: string;
  fields: PivotField[];
  placed: Set<string>;
  measure?: boolean;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wider text-ink-300 mb-1">{title}</div>
      <div className="space-y-1">
        {fields.map((f) => (
          <div
            key={f.name}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData("field", f.name);
              e.dataTransfer.setData("measure", measure ? "1" : "0");
            }}
            className={`text-[12px] px-2 py-1 rounded border cursor-grab truncate ${
              placed.has(f.name)
                ? "border-ink-700/40 text-ink-300 bg-ink-900/40"
                : "border-ink-700/60 text-ink-100 bg-ink-900 hover:border-accent/50"
            }`}
            title={f.name}
          >
            {measure && f.revenue ? "₹ " : ""}{short(f.name)}
          </div>
        ))}
        {fields.length === 0 && <div className="text-[11px] text-ink-300">—</div>}
      </div>
    </div>
  );
}

function ShelfBox({
  label,
  items,
  which,
  onDrop,
  onRemove,
}: {
  label: string;
  items: string[];
  which: Shelf;
  onDrop: (s: Shelf, name: string, isMeasure: boolean) => void;
  onRemove: (s: Shelf, name: string) => void;
}) {
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const name = e.dataTransfer.getData("field");
        const isMeasure = e.dataTransfer.getData("measure") === "1";
        if (name) onDrop(which, name, isMeasure);
      }}
      className={`min-h-[64px] rounded-lg border p-2 ${over ? "border-accent bg-accent-soft/30" : "border-ink-700/60 bg-ink-800/30"}`}
    >
      <div className="text-[10px] uppercase tracking-wider text-ink-300 mb-1">{label}</div>
      <div className="flex flex-wrap gap-1">
        {items.map((n) => (
          <span key={n} className="text-[11px] px-1.5 py-0.5 rounded bg-accent/15 text-accent-glow flex items-center gap-1">
            {short(n)}
            <button onClick={() => onRemove(which, n)} aria-label={`Remove ${short(n)}`} className="hover:text-red-300">×</button>
          </span>
        ))}
        {items.length === 0 && <span className="text-[11px] text-ink-300">drop here</span>}
      </div>
    </div>
  );
}

// ---------- crosstab build + render ----------

interface Grid {
  rowDimNames: string[];
  colHeaders: string[][]; // each = colKey tuple + measure label rendered as one header cell
  body: { rowKey: string[]; cells: (string | number | null)[] }[];
  flatHeader: string[]; // full header row as text (for TSV)
}

function buildCrosstab(result: PivotResult, rowDims: string[], colDims: string[], measures: string[]): Grid {
  const idx: Record<string, number> = {};
  result.columns.forEach((c, i) => (idx[c] = i));
  const get = (row: unknown[], name: string) => (idx[name] != null ? row[idx[name]] : null);

  const rowKeyOf = (row: unknown[]) => rowDims.map((d) => String(get(row, d) ?? ""));
  const colKeyOf = (row: unknown[]) => colDims.map((d) => String(get(row, d) ?? ""));
  const keyStr = (k: string[]) => k.join("||");

  const rowKeys: string[][] = [];
  const seenRow = new Set<string>();
  const colKeys: string[][] = [];
  const seenCol = new Set<string>();
  // measure value indexed by rowKey -> colKey -> measure
  const cube: Record<string, Record<string, Record<string, string | number | null>>> = {};

  for (const r of result.rows) {
    const rk = rowKeyOf(r);
    const ck = colKeyOf(r);
    const rs = keyStr(rk);
    const cs = keyStr(ck);
    if (!seenRow.has(rs)) {
      seenRow.add(rs);
      rowKeys.push(rk);
    }
    if (!seenCol.has(cs)) {
      seenCol.add(cs);
      colKeys.push(ck);
    }
    cube[rs] ??= {};
    cube[rs][cs] ??= {};
    for (const m of measures) cube[rs][cs][m] = get(r, m) as string | number | null;
  }
  // No column dims → single empty column group.
  const effectiveColKeys = colDims.length === 0 ? [[]] : colKeys;

  const colHeaders: string[][] = [];
  for (const ck of effectiveColKeys) {
    for (const m of measures.length ? measures : ["(value)"]) {
      colHeaders.push([...ck.map(short), short(m)]);
    }
  }

  const body = rowKeys.map((rk) => {
    const rs = keyStr(rk);
    const cells: (string | number | null)[] = [];
    for (const ck of effectiveColKeys) {
      const cs = keyStr(ck);
      for (const m of measures.length ? measures : ["(value)"]) {
        cells.push(cube[rs]?.[cs]?.[m] ?? null);
      }
    }
    return { rowKey: rk, cells };
  });

  const flatHeader = [...rowDims.map(short), ...colHeaders.map((h) => h.join(" / "))];
  return { rowDimNames: rowDims.map(short), colHeaders, body, flatHeader };
}

function PivotTable({ grid }: { grid: Grid }) {
  return (
    <div className="overflow-auto border border-ink-700/60 rounded-lg max-h-[60vh]">
      <table className="w-full text-[12px]">
        <thead className="bg-ink-800/60 text-ink-300 text-[11px] uppercase tracking-wider sticky top-0">
          <tr>
            {grid.rowDimNames.map((d) => (
              <th key={d} className="text-left px-3 py-2 font-medium">{d}</th>
            ))}
            {grid.colHeaders.map((h, i) => (
              <th key={i} className="text-right px-3 py-2 font-medium">{h.join(" · ")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.body.map((r, ri) => (
            <tr key={ri} className="border-t border-ink-700/40 hover:bg-ink-800/40">
              {r.rowKey.map((v, i) => (
                <td key={i} className="px-3 py-1.5 text-ink-100">{v}</td>
              ))}
              {r.cells.map((c, i) => (
                <td key={i} className="px-3 py-1.5 text-right font-mono numeric">{fmt(c)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PivotChart({ grid }: { grid: Grid }) {
  // Simple horizontal bar of the first value column by the first row dim.
  const vals = grid.body.map((r) => ({ label: r.rowKey.join(" / ") || "—", v: toNum(r.cells[0]) }));
  const max = Math.max(1, ...vals.map((x) => Math.abs(x.v)));
  return (
    <div className="border border-ink-700/60 rounded-lg p-4 space-y-1.5 max-h-[60vh] overflow-auto">
      {vals.map((x, i) => (
        <div key={i} className="flex items-center gap-2 text-[12px]">
          <div className="w-32 truncate text-ink-200">{x.label}</div>
          <div className="flex-1 bg-ink-900 rounded h-4 overflow-hidden">
            <div className="h-full bg-accent" style={{ width: `${(Math.abs(x.v) / max) * 100}%` }} />
          </div>
          <div className="w-20 text-right font-mono numeric text-ink-200">{fmt(x.v)}</div>
        </div>
      ))}
    </div>
  );
}

function fmt(v: string | number | null | undefined): string {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? n.toLocaleString() : String(v);
}
function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}
function copyTsv(grid: Grid) {
  const lines = [grid.flatHeader.join("\t")];
  for (const r of grid.body) lines.push([...r.rowKey, ...r.cells.map((c) => (c ?? "")).map(String)].join("\t"));
  void navigator.clipboard.writeText(lines.join("\n"));
}
