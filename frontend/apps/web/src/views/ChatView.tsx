/**
 * Chat view (Phase 6) — ask the agent swarm a question, get a governed answer.
 *
 * Shows everything the PRD requires for trust: the interpretation echo, the
 * data-health badge, the Cube query that ran (show-your-work), and the result.
 * Clarify/refuse answers render their message instead of forcing a result.
 */
import { useMemo, useState } from "react";
import { ApiClient, type ChatAnswer } from "@insnav/api-client";
import { useAuth } from "@insnav/auth";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function ChatView() {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );

  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<ChatAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ask = async () => {
    if (!question.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setAnswer(await client.chat(question.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold">Ask your data</h2>
        <p className="text-[12px] text-ink-300 mt-0.5">
          The agent selects governed measures &amp; dimensions; Cube compiles the SQL. Every
          answer shows what it understood, the data health, and the exact query it ran.
        </p>
      </header>

      <div className="flex items-start gap-2">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void ask();
          }}
          placeholder="e.g. total revenue by city"
          rows={2}
          className="flex-1 bg-ink-900 border border-ink-700/60 rounded px-3 py-2 text-sm resize-y focus:outline-none focus:ring-1 focus:ring-accent"
        />
        <button
          onClick={ask}
          disabled={busy || !question.trim()}
          className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Thinking…" : "Ask"}
        </button>
      </div>

      {error && (
        <div className="text-[12px] text-red-400 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
          {error}
        </div>
      )}

      {answer && <AnswerCard answer={answer} />}
    </section>
  );
}

function AnswerCard({ answer }: { answer: ChatAnswer }) {
  if (answer.kind !== "answer") {
    const tone =
      answer.kind === "refuse" ? "text-red-300 border-red-900/60 bg-red-950/30" : "text-amber-300 border-amber-900/60 bg-amber-950/30";
    return (
      <div className={`border rounded-lg p-4 text-[13px] ${tone}`}>
        <div className="uppercase text-[10px] tracking-wider mb-1">{answer.kind}</div>
        {answer.message}
      </div>
    );
  }

  return (
    <div className="border border-ink-700/60 rounded-lg bg-ink-800/40 divide-y divide-ink-700/40">
      {/* Interpretation echo + confidence + health */}
      <div className="p-4 space-y-2">
        <div className="flex items-center justify-between gap-3">
          <div className="text-sm">
            <span className="text-ink-300">I read this as:</span>{" "}
            <span className="text-ink-100">{answer.interpretation_echo}</span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge label={`${Math.round(answer.confidence * 100)}% conf`} tone="accent" />
            {answer.data_health && (
              <Badge
                label={`data: ${answer.data_health.status}`}
                tone={answer.data_health.status === "ok" ? "green" : "amber"}
              />
            )}
            <Badge label={answer.analysis_level} tone="ink" />
          </div>
        </div>
        {answer.data_health?.warnings.map((w, i) => (
          <div key={i} className="text-[11px] text-amber-300">⚠ {w}</div>
        ))}
        {answer.caveats.map((c, i) => (
          <div key={i} className="text-[11px] text-ink-300">· {c}</div>
        ))}
      </div>

      {/* Result table */}
      {answer.rows.length > 0 && (
        <div className="p-4 overflow-auto">
          <table className="w-full text-[12px]">
            <thead className="text-ink-300 text-[11px] uppercase tracking-wider">
              <tr>
                {answer.columns.map((c) => (
                  <th key={c} className="text-left px-2 py-1 font-medium">{c.split(".").pop()}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {answer.rows.map((row, ri) => (
                <tr key={ri} className="border-t border-ink-700/40">
                  {row.map((cell, ci) => (
                    <td key={ci} className="px-2 py-1 font-mono numeric">{String(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Show-your-work: the Cube query */}
      {answer.cube_query && (
        <details className="p-4">
          <summary className="text-[11px] uppercase tracking-wider text-ink-300 cursor-pointer">
            Cube query (show your work)
          </summary>
          <pre className="mt-2 text-[11px] font-mono text-ink-200 whitespace-pre-wrap">
            {JSON.stringify(answer.cube_query, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}

function Badge({ label, tone }: { label: string; tone: "accent" | "green" | "amber" | "ink" }) {
  const cls = {
    accent: "bg-accent/15 text-accent-glow",
    green: "bg-emerald-900/30 text-emerald-300",
    amber: "bg-amber-900/30 text-amber-300",
    ink: "bg-ink-700/40 text-ink-200",
  }[tone];
  return <span className={`inline-block px-2 py-0.5 rounded text-[11px] ${cls}`}>{label}</span>;
}
