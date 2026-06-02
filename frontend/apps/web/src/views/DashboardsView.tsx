/**
 * Dashboards (Phase 8) — pinned tiles that re-run on visit + read-only share.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClient, type Dashboard, type DashboardRun } from "@insnav/api-client";
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

  if (openId) {
    return <DashboardDetail client={client} id={openId} onBack={() => { setOpenId(null); refresh(); }} />;
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

function DashboardDetail({ client, id, onBack }: { client: ApiClient; id: string; onBack: () => void }) {
  const [run, setRun] = useState<DashboardRun | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setBusy(true);
    client.runDashboard(id).then(setRun).catch((e) => setError(String(e))).finally(() => setBusy(false));
  }, [client, id]);
  useEffect(load, [load]);

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
