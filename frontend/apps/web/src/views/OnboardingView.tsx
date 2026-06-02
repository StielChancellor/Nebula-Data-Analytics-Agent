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
  type InterviewStep,
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
  const [checkedEdges, setCheckedEdges] = useState<Record<string, boolean>>({});
  const started = useRef(false);
  const transcriptRef = useRef<HTMLDivElement>(null);

  // Autoscroll the transcript to the newest turn (M2).
  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: "smooth" });
  }, [session?.transcript.length]);

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

  const reply = async (body: {
    answer?: string;
    semantics_patch?: ColumnSemantics[];
    confirmed_edge_ids?: string[];
  }) => {
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

      {/* Progress */}
      {session && !completion && <Stepper step={session.current_step} />}

      {/* Transcript */}
      <div ref={transcriptRef} className="space-y-2 max-h-80 overflow-y-auto pr-1">
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
          {agent.step === "joins" ? (
            <JoinsReview
              edges={(agent.context?.edges as JoinEdge[] | undefined) ?? []}
              checked={checkedEdges}
              setChecked={setCheckedEdges}
              busy={busy}
              onConfirm={() =>
                reply({
                  answer: "yes",
                  confirmed_edge_ids: Object.keys(checkedEdges).filter((k) => checkedEdges[k]),
                })
              }
            />
          ) : agent.question_type === "draft_review" ? (
            <>
              <DraftReview
                draft={draft}
                onEdit={editRow}
                onAccept={() => reply({ answer: "accept", semantics_patch: draft })}
                busy={busy}
              />
              <div className="flex items-start gap-2 pt-2 border-t border-ink-700/40">
                <input
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && text.trim() && void reply({ answer: text.trim() })}
                  placeholder="Or tell me in words — e.g. “amount is revenue, ignore notes”"
                  aria-label="Describe a correction"
                  className="flex-1 bg-ink-900 border border-ink-700/60 rounded px-3 py-2 text-[13px] focus:outline-none focus:ring-1 focus:ring-accent"
                />
                <button
                  onClick={() => text.trim() && reply({ answer: text.trim() })}
                  disabled={busy || !text.trim()}
                  className="text-[12px] px-3 py-2 rounded border border-ink-700/60 text-ink-200 hover:bg-ink-700/40 disabled:opacity-50"
                >
                  Apply
                </button>
              </div>
            </>
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
      <p className="text-[11px] text-ink-300 leading-relaxed">
        <span className="text-ink-200 font-medium">Measure</span> = a number you total or average ·{" "}
        <span className="text-ink-200 font-medium">Dimension</span> = a category you group by ·{" "}
        <span className="text-ink-200 font-medium">Time</span> = dates ·{" "}
        <span className="text-ink-200 font-medium">Identifier</span> = a key that links tables ·{" "}
        <span className="text-ink-200 font-medium">Ignore</span> = leave it out.
      </p>
      <div className="overflow-auto max-h-72">
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
                    <span className="text-ink-300">—</span>
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
                    <span className="text-ink-300">—</span>
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

const STEP_ORDER: InterviewStep[] = ["project_name", "grain", "draft_review", "joins", "confirm"];
const STEP_LABELS: Record<InterviewStep, string> = {
  project_name: "Name",
  grain: "Grain",
  draft_review: "Columns",
  joins: "Joins",
  confirm: "Confirm",
  done: "Done",
};

function Stepper({ step }: { step: InterviewStep }) {
  const idx = STEP_ORDER.indexOf(step);
  return (
    <ol className="flex items-center gap-1 text-[11px]" aria-label="Onboarding progress">
      {STEP_ORDER.map((s, i) => {
        const state = i < idx ? "done" : i === idx ? "current" : "todo";
        return (
          <li key={s} className="flex items-center gap-1">
            <span
              className={[
                "px-2 py-0.5 rounded",
                state === "current"
                  ? "bg-accent/20 text-accent-glow font-semibold"
                  : state === "done"
                  ? "text-emerald-300"
                  : "text-ink-300",
              ].join(" ")}
              aria-current={state === "current" ? "step" : undefined}
            >
              {state === "done" ? "✓ " : ""}{STEP_LABELS[s]}
            </span>
            {i < STEP_ORDER.length - 1 && <span className="text-ink-300">›</span>}
          </li>
        );
      })}
    </ol>
  );
}

interface JoinEdge {
  id: string;
  from_dataset: string;
  from_column: string;
  to_dataset: string;
  to_column: string;
  key_overlap_pct?: number;
  sample_overlap?: string[];
}

function JoinsReview({
  edges,
  checked,
  setChecked,
  onConfirm,
  busy,
}: {
  edges: JoinEdge[];
  checked: Record<string, boolean>;
  setChecked: (c: Record<string, boolean>) => void;
  onConfirm: () => void;
  busy: boolean;
}) {
  if (edges.length === 0) {
    return (
      <div className="space-y-3">
        <p className="text-[12px] text-ink-300">No cross-dataset joins were found for this project.</p>
        <button
          onClick={onConfirm}
          disabled={busy}
          className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Working…" : "Continue"}
        </button>
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-[12px] text-ink-300">
        I found these candidate joins. Tick the ones that are real relationships — only confirmed joins
        become governed cube joins.
      </p>
      <div className="space-y-2">
        {edges.map((e) => (
          <label
            key={e.id}
            className="flex items-start gap-2 border border-ink-700/50 rounded-lg p-2.5 cursor-pointer hover:border-accent/40"
          >
            <input
              type="checkbox"
              checked={!!checked[e.id]}
              onChange={(ev) => setChecked({ ...checked, [e.id]: ev.target.checked })}
              className="mt-0.5 accent-accent"
            />
            <div className="text-[12px]">
              <div className="font-mono text-ink-100">
                {e.from_column} ↔ {e.to_column}
              </div>
              <div className="text-[11px] text-ink-300">
                {typeof e.key_overlap_pct === "number"
                  ? `${Math.round(e.key_overlap_pct * 100)}% key overlap`
                  : ""}
                {e.sample_overlap && e.sample_overlap.length > 0
                  ? ` · e.g. ${e.sample_overlap.slice(0, 3).join(", ")}`
                  : ""}
              </div>
            </div>
          </label>
        ))}
      </div>
      <button
        onClick={onConfirm}
        disabled={busy}
        className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50"
      >
        {busy ? "Working…" : "Confirm joins"}
      </button>
    </div>
  );
}
