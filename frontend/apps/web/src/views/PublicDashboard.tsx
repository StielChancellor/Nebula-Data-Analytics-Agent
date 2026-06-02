/**
 * Public read-only dashboard viewer (Phase 8 share link) — no auth.
 * Reached via ?share=<token>; calls GET /v1/public/dashboards/{token}.
 */
import { useEffect, useState } from "react";
import type { BrandConfig } from "@insnav/brand-runtime";
import type { DashboardRun } from "@insnav/api-client";
import { SmartChart } from "./SmartChart";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function PublicDashboard({ token, brand }: { token: string; brand: BrandConfig }) {
  const [run, setRun] = useState<DashboardRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/v1/public/dashboards/${encodeURIComponent(token)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status}`))))
      .then(setRun)
      .catch(() => setError("This shared dashboard is unavailable or the link is invalid."));
  }, [token]);

  return (
    <div className="min-h-screen bg-ink-900 text-ink-100">
      <header className="border-b border-ink-700/60 px-6 py-3 flex items-center gap-3">
        <img src={brand.logoUrl} alt="" className="h-7 w-7" />
        <div className="text-sm font-semibold">{run?.name ?? brand.displayName}</div>
        <span className="ml-auto text-[11px] text-ink-300">Shared dashboard · read-only</span>
      </header>
      <main className="max-w-5xl mx-auto p-6">
        {error ? (
          <div className="text-[13px] text-red-300 border border-red-900/60 bg-red-950/40 rounded p-4">{error}</div>
        ) : !run ? (
          <div className="text-[12px] text-ink-300">Loading…</div>
        ) : run.tiles.length === 0 ? (
          <div className="text-[12px] text-ink-300">This dashboard has no tiles.</div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {run.tiles.map((t) => (
              <div key={t.tile_id} className="border border-ink-700/60 rounded-lg bg-ink-800/40 p-3">
                <div className="text-[12px] font-medium text-ink-100 mb-1">{t.title}</div>
                {t.error ? (
                  <div className="text-[11px] text-amber-300">{t.error}</div>
                ) : (
                  <SmartChart spec={t.spec} columns={t.columns} rows={t.rows} />
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
