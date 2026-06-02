/**
 * Dashboards (Phase 8) — pinned tiles that re-run on visit + read-only share.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiClient,
  type Dashboard,
  type DashboardRun,
  type AssumptionWarning,
} from "@insnav/api-client";
import { useAuth } from "@insnav/auth";
import { SmartChart } from "./SmartChart";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function DashboardsView({ projectId }: { projectId: string }) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );

  const [list, setList] = useState<Dashboard[]>([]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");

  const refresh = useCallback(() => {
    client.listDashboards(projectId).then(setList).catch((e) => setError(String(e)));
  }, [client, projectId]);
  useEffect(refresh, [refresh]);

  const [generating, setGenerating] = useState(false);

  const create = async () => {
    if (!name.trim()) return;
    try {
      const d = await client.createDashboard(projectId, name.trim());
      setName("");
      refresh();
      setOpenId(d.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  // Phase 12: X-ray — auto-generate a starter dashboard from the cube.
  const autoGenerate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const r = await client.xrayDashboard(projectId, "Starter dashboard");
      refresh();
      setOpenId(r.dashboard_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  };

  if (openId) {
    return (
      <DashboardDetail
        client={client}
        id={openId}
        projectId={projectId}
        onBack={() => { setOpenId(null); refresh(); }}
      />
    );
  }

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold">Dashboards</h2>
        <p className="text-[12px] text-ink-300 mt-0.5">
          Pin pivots as tiles; they re-run on every visit. Share read-only links.
        </p>
      </header>

      {error && <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">{error}</div>}

      <div className="flex items-end gap-2">
        <label className="text-[11px] text-ink-300 flex-1">
          New dashboard
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void create()}
            placeholder="e.g. Revenue overview"
            className="mt-1 w-full bg-ink-900 border border-ink-700/60 rounded px-3 py-2 text-sm text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </label>
        <button onClick={create} disabled={!name.trim()} className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50">
          Create
        </button>
        <button onClick={autoGenerate} disabled={generating} className="text-[12px] px-4 py-2 rounded border border-accent/50 text-accent-glow hover:bg-accent/15 disabled:opacity-50" title="Auto-generate a starter dashboard from your cube (X-ray)">
          {generating ? "Generating…" : "✨ Auto-generate"}
        </button>
      </div>

      {list.length === 0 ? (
        <div className="text-[12px] text-ink-300 border border-dashed border-ink-700/60 rounded-lg p-8 text-center bg-ink-800/20">
          No dashboards yet. Create one, then pin tiles from the <span className="text-ink-100">Pivot</span> tab.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {list.map((d) => (
            <button key={d.id} onClick={() => setOpenId(d.id)} className="text-left border border-ink-700/60 rounded-lg bg-ink-800/40 p-4 hover:border-accent/60">
              <div className="text-sm font-semibold">{d.name}</div>
              <div className="text-[11px] text-ink-300 mt-1">
                {d.tiles.length} tile{d.tiles.length === 1 ? "" : "s"}{d.share_token ? " · shared" : ""}
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function DashboardDetail({
  client,
  id,
  projectId,
  onBack,
}: {
  client: ApiClient;
  id: string;
  projectId: string;
  onBack: () => void;
}) {
  const [run, setRun] = useState<DashboardRun | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [assumptions, setAssumptions] = useState<Record<string, AssumptionWarning[]>>({});
  const [checking, setChecking] = useState(false);

  const load = useCallback(() => {
    setBusy(true);
    setAssumptions({});
    client.runDashboard(id).then(setRun).catch((e) => setError(String(e))).finally(() => setBusy(false));
  }, [client, id]);
  useEffect(load, [load]);

  // Phase 11 #5: re-check each tile's statistical assumptions on demand.
  const checkAssumptions = async () => {
    if (!run) return;
    setChecking(true);
    const out: Record<string, AssumptionWarning[]> = {};
    await Promise.all(
      run.tiles.map(async (t) => {
        if (t.error) return;
        try {
          const rep = await client.checkAssumptions(projectId, t.spec);
          if (rep.warnings.length) out[t.tile_id] = rep.warnings;
        } catch {
          /* ignore per-tile */
        }
      }),
    );
    setAssumptions(out);
    setChecking(false);
  };

  const share = async () => {
    try {
      const d = await client.shareDashboard(id);
      if (d.share_token) {
        const url = `${window.location.origin}/?share=${d.share_token}`;
        setShareUrl(url);
        void navigator.clipboard.writeText(url);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const removeTile = async (tileId: string) => {
    await client.removeTile(id, tileId);
    load();
  };

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[12px]">
          <button onClick={onBack} className="text-ink-300 hover:text-ink-100">← Dashboards</button>
          <span className="text-ink-500">/</span>
          <span className="font-semibold">{run?.name ?? "…"}</span>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60 hover:bg-ink-700/40">Refresh</button>
          <button onClick={checkAssumptions} disabled={checking || !run} className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60 hover:bg-ink-700/40 disabled:opacity-50" title="Re-check each tile's statistical assumptions">
            {checking ? "Checking…" : "Check assumptions"}
          </button>
          <button onClick={share} className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60 hover:bg-ink-700/40">Share link</button>
        </div>
      </div>

      {shareUrl && (
        <div className="text-[11px] text-emerald-300 border border-emerald-900/50 bg-emerald-950/30 rounded px-2 py-1">
          Read-only link copied: <span className="font-mono">{shareUrl}</span>
        </div>
      )}
      {error && <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">{error}</div>}

      {busy && !run ? (
        <div className="text-[12px] text-ink-300">Running tiles…</div>
      ) : run && run.tiles.length === 0 ? (
        <div className="text-[12px] text-ink-300 border border-dashed border-ink-700/60 rounded-lg p-8 text-center bg-ink-800/20">
          No tiles yet. Go to <span className="text-ink-100">Pivot</span>, build a view, and click <span className="text-accent-glow">Pin to dashboard</span>.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {run?.tiles.map((t) => (
            <div key={t.tile_id} className="border border-ink-700/60 rounded-lg bg-ink-800/40 p-3">
              <div className="flex items-center justify-between mb-1">
                <div className="text-[12px] font-medium text-ink-100">{t.title}</div>
                <button onClick={() => removeTile(t.tile_id)} aria-label="Remove tile" className="text-[11px] text-ink-300 hover:text-red-300">×</button>
              </div>
              {(assumptions[t.tile_id] ?? []).length > 0 && (
                <div className="mb-2 space-y-1">
                  {assumptions[t.tile_id]!.map((w, i) => (
                    <div
                      key={i}
                      className={`text-[10px] px-2 py-1 rounded border flex items-start gap-1 ${
                        w.level === "warn"
                          ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                          : "bg-ink-700/40 text-ink-300 border-ink-600/40"
                      }`}
                    >
                      <span>{w.level === "warn" ? "⚠" : "ℹ"}</span>
                      <span>{w.message}</span>
                    </div>
                  ))}
                </div>
              )}
              {t.error ? (
                <div className="text-[11px] text-amber-300">{t.error}</div>
              ) : (
                <SmartChart spec={t.spec} columns={t.columns} rows={t.rows} />
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
