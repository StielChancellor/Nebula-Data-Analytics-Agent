/**
 * Cohort builder (Phase 11 #2).
 *
 * Save named segments (filter-sets on one cube), then combine them with set
 * algebra — `(A & B) - C` — resolved into a governed Cube query. Every leaf
 * member is validated server-side; LLM-free.
 */
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@insnav/auth";
import {
  ApiClient,
  type PivotFields,
  type Segment,
  type CohortResolveResult,
} from "@insnav/api-client";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const short = (n: string) => n.split(".").pop() || n;
const cubeOf = (member: string) => member.split(".").slice(0, -1).join(".");
const OPERATORS = ["equals", "notEquals", "contains", "notContains", "gt", "lt", "gte", "lte", "set", "notSet"];

export function CohortsView({ projectId }: { projectId: string }) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );

  const [fields, setFields] = useState<PivotFields | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = () =>
    client.listCohorts(projectId).then(setSegments).catch(() => setSegments([]));

  useEffect(() => {
    let live = true;
    client.getPivotFields(projectId).then((f) => live && setFields(f)).catch(() => {});
    void reload();
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, projectId]);

  const dims = fields?.dimensions ?? [];
  const measures = fields?.measures ?? [];

  // --- new segment form ---
  const [name, setName] = useState("");
  const [member, setMember] = useState("");
  const [operator, setOperator] = useState("equals");
  const [values, setValues] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!member && dims[0]) setMember(dims[0].name);
  }, [dims, member]);

  const createSegment = async () => {
    if (!name.trim() || !member) return;
    setBusy(true);
    setError(null);
    try {
      await client.createCohort({
        project_id: projectId,
        name: name.trim(),
        cube: cubeOf(member),
        filters: [
          {
            member,
            operator,
            values: operator === "set" || operator === "notSet"
              ? []
              : values.split(",").map((v) => v.trim()).filter(Boolean),
          },
        ],
      });
      setName("");
      setValues("");
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    await client.deleteCohort(id).catch(() => {});
    await reload();
  };

  // --- resolve ---
  const [expression, setExpression] = useState("");
  const [resMeasures, setResMeasures] = useState<string[]>([]);
  const [resDim, setResDim] = useState<string>("");
  const [result, setResult] = useState<CohortResolveResult | null>(null);

  const resolve = async () => {
    setError(null);
    setResult(null);
    try {
      const r = await client.resolveCohort({
        project_id: projectId,
        expression: expression.trim(),
        measures: resMeasures,
        dimensions: resDim ? [resDim] : [],
      });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="space-y-5">
      {error && (
        <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-3 py-2">
          {error}
        </div>
      )}

      {/* segments */}
      <section className="border border-ink-700/60 rounded-lg bg-ink-800/30 p-4 space-y-3">
        <h3 className="text-sm font-semibold">Segments</h3>
        <div className="flex flex-wrap gap-2">
          {segments.length === 0 && <span className="text-[12px] text-ink-300">No segments yet.</span>}
          {segments.map((s) => (
            <span key={s.id} className="inline-flex items-center gap-2 text-[11px] border border-ink-700/60 rounded-full pl-3 pr-1.5 py-1 bg-ink-900">
              <span className="font-semibold text-ink-100">{s.name}</span>
              <span className="text-ink-400 font-mono">{short(s.cube)}</span>
              <button onClick={() => remove(s.id)} className="text-ink-400 hover:text-red-300 w-4 h-4 leading-none" aria-label={`Delete ${s.name}`}>×</button>
            </span>
          ))}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-5 gap-2 items-end pt-2 border-t border-ink-700/40">
          <Field label="Name">
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="High value"
                   className="bg-ink-900 border border-ink-700/60 rounded px-2 py-1.5 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent" />
          </Field>
          <Field label="Field">
            <select value={member} onChange={(e) => setMember(e.target.value)} className="bg-ink-900 border border-ink-700/60 rounded px-2 py-1.5 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent">
              {dims.map((d) => <option key={d.name} value={d.name}>{short(d.name)}</option>)}
            </select>
          </Field>
          <Field label="Operator">
            <select value={operator} onChange={(e) => setOperator(e.target.value)} className="bg-ink-900 border border-ink-700/60 rounded px-2 py-1.5 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent">
              {OPERATORS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </Field>
          <Field label="Values (comma-sep)">
            <input value={values} onChange={(e) => setValues(e.target.value)}
                   disabled={operator === "set" || operator === "notSet"}
                   placeholder="Mumbai, Pune" className="bg-ink-900 border border-ink-700/60 rounded px-2 py-1.5 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-40" />
          </Field>
          <button onClick={createSegment} disabled={busy || !name.trim() || !member}
                  className="text-[12px] px-3 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50">
            {busy ? "Saving…" : "Add segment"}
          </button>
        </div>
      </section>

      {/* set algebra */}
      <section className="border border-ink-700/60 rounded-lg bg-ink-800/30 p-4 space-y-3">
        <h3 className="text-sm font-semibold">Combine with set algebra</h3>
        <p className="text-[11px] text-ink-300">
          Use segment names with <code className="text-accent-glow">&amp;</code> (and),{" "}
          <code className="text-accent-glow">|</code> (or),{" "}
          <code className="text-accent-glow">-</code> (minus), and parentheses. Example:{" "}
          <code className="text-ink-200">(High value &amp; Active) - Churned</code>
        </p>
        <input value={expression} onChange={(e) => setExpression(e.target.value)}
               placeholder="(A & B) - C" className="bg-ink-900 border border-ink-700/60 rounded px-2 py-1.5 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent w-full font-mono" />
        <div className="flex flex-wrap gap-3 items-end">
          <Field label="Measure">
            <select multiple value={resMeasures}
                    onChange={(e) => setResMeasures(Array.from(e.target.selectedOptions).map((o) => o.value))}
                    className="bg-ink-900 border border-ink-700/60 rounded px-2 py-1.5 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent h-20 min-w-[160px]">
              {measures.map((m) => <option key={m.name} value={m.name}>{short(m.name)}</option>)}
            </select>
          </Field>
          <Field label="Break down by">
            <select value={resDim} onChange={(e) => setResDim(e.target.value)} className="bg-ink-900 border border-ink-700/60 rounded px-2 py-1.5 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent">
              <option value="">— none —</option>
              {dims.map((d) => <option key={d.name} value={d.name}>{short(d.name)}</option>)}
            </select>
          </Field>
          <button onClick={resolve} disabled={!expression.trim()}
                  className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50">
            Resolve cohort
          </button>
        </div>

        {result && (
          <div className="space-y-2 pt-2">
            <div className="text-[11px] text-ink-300">
              Segments used: {result.segments_used.join(", ") || "—"} · {result.rows.length} rows
            </div>
            <div className="overflow-auto max-h-72 border border-ink-700/50 rounded">
              <table className="w-full text-[11px]">
                <thead className="text-ink-300 text-[10px] uppercase tracking-wider bg-ink-800/50">
                  <tr>{result.columns.map((c) => <th key={c} className="text-left px-2 py-1">{short(c)}</th>)}</tr>
                </thead>
                <tbody>
                  {result.rows.map((r, ri) => (
                    <tr key={ri} className="border-t border-ink-700/40">
                      {(r as unknown[]).map((c, ci) => <td key={ci} className="px-2 py-1 font-mono">{String(c ?? "—")}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-[10px] uppercase tracking-wider text-ink-300">
      {label}
      <div className="mt-1">{children}</div>
    </label>
  );
}
