/**
 * Agent-led onboarding (Phase 10) — "agent drafts, you review".
 *
 * The agent reads the file, asks for context, and presents an auto-classified
 * draft of every column. The user reviews/corrects it in a compact table (or
 * chats free-text), then confirms — which builds the project's cube + graph.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ApiClient,
  type AgentQuestion,
  type ColumnRole,
  type ColumnSemantics,
  type CompletionResult,
  type IngestSession,
  type LlmOption,
  type MeasureAgg,
} from "@insnav/api-client";
import { useAuth } from "@insnav/auth";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";
const ROLES: ColumnRole[] = ["dimension", "measure", "time", "identifier", "ignore"];
const AGGS: MeasureAgg[] = ["sum", "avg", "count", "min", "max", "count_distinct"];

export function OnboardingView({
  datasetId,
  onDone,
}: {
  datasetId: string;
  onDone: () => void;
}) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );

  const [session, setSession] = useState<IngestSession | null>(null);
  const [agent, setAgent] = useState<AgentQuestion | null>(null);
  const [completion, setCompletion] = useState<CompletionResult | null>(null);
  const [draft, setDraft] = useState<ColumnSemantics[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [models, setModels] = useState<LlmOption[]>([]);
  const [model, setModel] = useState<string>("");
  const started = useRef(false);

  useEffect(() => {
    client.listLlmOptions().then((o) => {
      setModels(o);
      setModel(o.find((m) => m.default)?.id ?? o[0]?.id ?? "");
    }).catch(() => setModels([]));
  }, [client]);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    setBusy(true);
    client
      .startIngestSession(datasetId)
      .then((r) => apply(r))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setBusy(false));
  }, [client, datasetId]);

  const apply = (r: { session: IngestSession; agent_message: AgentQuestion | null; completion: CompletionResult | null }) => {
    setSession(r.session);
    setAgent(r.agent_message);
    setCompletion(r.completion);
    if (r.agent_message?.question_type === "draft_review") {
      setDraft(r.agent_message.draft.map((d) => ({ ...d })));
    }
  };

  const reply = async (body: { answer?: string; semantics_patch?: ColumnSemantics[] }) => {
    if (!session) return;
    setBusy(true);
    setError(null);
    try {
      apply(await client.replyToIngest(session.id, { ...body, llm: model || undefined }));
      setText("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const editRow = (i: number, patch: Partial<ColumnSemantics>) =>
    setDraft((d) => d.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));

  return (
    <section className="space-y-4">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Onboarding</h2>
          <p className="text-[12px] text-ink-300 mt-0.5">
            The agent drafts how to read your data — you review &amp; confirm, then it builds the
            cube + graph.
          </p>
        </div>
        {models.length > 0 && (
          <label className="shrink-0 text-[11px] text-ink-300 flex items-center gap-2">
            Brain
            <select
              value={model}
              onChange={(e) => setModel(e.target.value)}
              className="bg-ink-900 border border-ink-700/60 rounded px-2 py-1 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id} disabled={!m.available}>
                  {m.label}{m.available ? "" : " (not configured)"}
                </option>
              ))}
            </select>
          </label>
        )}
      </header>

      {/* Transcript */}
      <div className="space-y-2">
        {session?.transcript.map((t, i) => (
          <div
            key={i}
            className={`text-[13px] rounded-lg px-3 py-2 max-w-[85%] ${
              t.role === "agent"
                ? "bg-ink-800/60 border border-ink-700/50 text-ink-100"
                : "bg-accent/15 text-accent-glow ml-auto"
            }`}
          >
            {t.text}
          </div>
        ))}
      </div>

      {error && (
        <div className="text-[12px] text-red-400 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
          {error}
        </div>
      )}

      {/* Completion */}
      {completion && (
        <div className="border border-emerald-900/60 bg-emerald-950/30 rounded-lg p-4 text-[13px] text-emerald-200 space-y-1">
          <div className="font-semibold">✓ Onboarding complete</div>
          <div className="text-[12px]">
            {completion.columns_confirmed} columns confirmed
            {completion.joins_approved > 0 ? `, ${completion.joins_approved} joins approved` : ""}
            {completion.cube_synced ? " · cube published" : ""}.
          </div>
          <button
            onClick={onDone}
            className="mt-2 text-[12px] px-3 py-1.5 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90"
          >
            Done
          </button>
        </div>
      )}

      {/* Current question */}
      {agent && !completion && (
        <div className="border border-ink-700/60 rounded-lg bg-ink-800/40 p-4 space-y-3">
          {agent.question_type === "draft_review" ? (
            <DraftReview
              draft={draft}
              onEdit={editRow}
              onAccept={() => reply({ answer: "accept", semantics_patch: draft })}
              busy={busy}
            />
          ) : agent.question_type === "confirm" ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => reply({ answer: "yes" })}
                disabled={busy}
                className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50"
              >
                {busy ? "Working…" : "Yes, proceed"}
              </button>
              <button
                onClick={() => reply({ answer: "not yet" })}
                disabled={busy}
                className="text-[12px] px-3 py-2 rounded border border-ink-700/60 text-ink-200 hover:bg-ink-700/40"
              >
                Not yet
              </button>
            </div>
          ) : (
            <div className="flex items-start gap-2">
              <input
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && text.trim() && void reply({ answer: text.trim() })}
                placeholder="Type your answer…"
                className="flex-1 bg-ink-900 border border-ink-700/60 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
              />
              <button
                onClick={() => reply({ answer: text.trim() })}
                disabled={busy || !text.trim()}
                className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50"
              >
                Send
              </button>
            </div>
          )}
        </div>
      )}

      {busy && !session && <div className="text-[12px] text-ink-300">Reading your file…</div>}
    </section>
  );
}

function DraftReview({
  draft,
  onEdit,
  onAccept,
  busy,
}: {
  draft: ColumnSemantics[];
  onEdit: (i: number, patch: Partial<ColumnSemantics>) => void;
  onAccept: () => void;
  busy: boolean;
}) {
  return (
    <div className="space-y-3">
      <div className="overflow-auto">
        <table className="w-full text-[12px]">
          <thead className="text-ink-300 text-[11px] uppercase tracking-wider">
            <tr>
              <th className="text-left px-2 py-1">Column</th>
              <th className="text-left px-2 py-1">Role</th>
              <th className="text-left px-2 py-1">Aggregation</th>
              <th className="text-left px-2 py-1">Revenue</th>
            </tr>
          </thead>
          <tbody>
            {draft.map((c, i) => (
              <tr key={c.column} className="border-t border-ink-700/40">
                <td className="px-2 py-1 font-mono text-ink-100">{c.column}</td>
                <td className="px-2 py-1">
                  <select
                    value={c.role}
                    onChange={(e) => onEdit(i, { role: e.target.value as ColumnRole })}
                    className="bg-ink-900 border border-ink-700/60 rounded px-1.5 py-1 text-[12px] text-ink-100"
                  >
                    {ROLES.map((r) => (
                      <option key={r} value={r}>{r}</option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1">
                  {c.role === "measure" ? (
                    <select
                      value={c.measure_aggregation ?? "sum"}
                      onChange={(e) => onEdit(i, { measure_aggregation: e.target.value as MeasureAgg })}
                      className="bg-ink-900 border border-ink-700/60 rounded px-1.5 py-1 text-[12px] text-ink-100"
                    >
                      {AGGS.map((a) => (
                        <option key={a} value={a}>{a}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="text-ink-500">—</span>
                  )}
                </td>
                <td className="px-2 py-1">
                  {c.role === "measure" ? (
                    <input
                      type="checkbox"
                      checked={!!c.is_revenue}
                      onChange={(e) => onEdit(i, { is_revenue: e.target.checked })}
                      className="accent-accent"
                    />
                  ) : (
                    <span className="text-ink-500">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button
        onClick={onAccept}
        disabled={busy}
        className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "Working…" : "Looks good — continue"}
      </button>
    </div>
  );
}
