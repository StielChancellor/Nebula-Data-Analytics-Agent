/**
 * Phase 1 shell app.
 *
 * Renders <LoginScreen/> when unauth'd; the brand demo (with Sign Out) when
 * auth'd. Demonstrates the full Phase 1 contract end-to-end:
 *   1. brand-runtime applies tokens before React mounts
 *   2. AuthProvider validates any stored JWT on boot
 *   3. Protected endpoints (/v1/me/datasets) are reached with the JWT
 *      attached automatically
 *   4. Locale formatting flips US ↔ IN at runtime (Lakh/Crore proof)
 */
import { useEffect, useState } from "react";
import type { BrandConfig } from "@insnav/brand-runtime";
import { useAuth, LoginScreen } from "@insnav/auth";
import {
  formatCurrency,
  formatCurrencyCompact,
  formatNumber,
  fyLabel,
  fyQuarter,
  type RegionCode,
} from "@insnav/locale";

interface AppProps {
  brand: BrandConfig;
}

const DEMO_VALUE = 12_400_000;

export function App({ brand }: AppProps) {
  const auth = useAuth();

  if (auth.status === "loading") {
    return <BootSplash />;
  }
  if (auth.status !== "authenticated" || !auth.principal) {
    return <LoginScreen brandName={brand.displayName} brandLogoUrl={brand.logoUrl} />;
  }
  return <AuthedShell brand={brand} />;
}

function BootSplash() {
  return (
    <div className="min-h-screen bg-ink-900 text-ink-300 grid place-items-center text-[12px]">
      Loading…
    </div>
  );
}

function AuthedShell({ brand }: { brand: BrandConfig }) {
  const auth = useAuth();
  const [region, setRegion] = useState<RegionCode>(brand.regionDefault);
  const [datasetsCount, setDatasetsCount] = useState<number | null>(null);
  const today = new Date();

  // Demonstrate that protected endpoints work
  useEffect(() => {
    if (!auth.token) return;
    fetch(`${import.meta.env.VITE_API_BASE || "/api"}/v1/me/datasets`, {
      headers: { Authorization: `Bearer ${auth.token}` },
    })
      .then((r) => r.json())
      .then((rows: unknown[]) => setDatasetsCount(rows.length))
      .catch(() => setDatasetsCount(null));
  }, [auth.token]);

  return (
    <div className="min-h-screen bg-ink-900 text-ink-100">
      <header className="border-b border-ink-700/60 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <img src={brand.logoUrl} alt="" className="h-8 w-8" />
          <div>
            <div className="text-sm font-semibold tracking-wide">{brand.displayName}</div>
            <div className="text-[11px] text-ink-300 font-mono">
              brand: {brand.brandId} · tenant: {auth.principal?.tenant_id} · phase 1
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <RegionToggle region={region} setRegion={setRegion} />
          <AccountMenu />
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-6 space-y-6">
        <section>
          <h1 className="text-2xl font-semibold">
            Welcome, <span className="text-accent-glow">{auth.principal?.email}</span>
          </h1>
          <p className="text-ink-300 mt-1">
            Phase 1 shell. Bootstrap admin auth wired end-to-end. Backend issues HS256 JWT;
            frontend stores it; /v1/me/datasets is reachable with it.
          </p>
        </section>

        <section className="grid grid-cols-2 gap-4">
          <Card label="Currency (full)" value={formatCurrency(DEMO_VALUE, region)} />
          <Card label="Currency (compact)" value={formatCurrencyCompact(DEMO_VALUE, region)} />
          <Card label="Number (grouped)" value={formatNumber(DEMO_VALUE, region)} />
          <Card label="Fiscal year + Q" value={`${fyLabel(today, region)} · ${fyQuarter(today, region)}`} />
        </section>

        <section className="text-[12px] text-ink-300 leading-relaxed border border-ink-700/60 rounded-md p-4 bg-ink-800/60">
          <strong className="text-ink-100">API check:</strong>{" "}
          <span className="font-mono">
            GET /v1/me/datasets → {datasetsCount === null ? "…" : `${datasetsCount} rows`}
          </span>
          {" (empty until Phase 2 ingestion lands)."}
        </section>

        <NextSteps />
      </main>
    </div>
  );
}

function AccountMenu() {
  const auth = useAuth();
  return (
    <button
      type="button"
      onClick={auth.logout}
      className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60 hover:bg-ink-700/40 transition-colors"
    >
      Sign out
    </button>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-ink-700/60 rounded-lg p-4 bg-ink-800/40">
      <div className="text-[11px] uppercase tracking-wider text-ink-300">{label}</div>
      <div className="mt-1 text-xl font-mono numeric text-accent-glow">{value}</div>
    </div>
  );
}

function RegionToggle({ region, setRegion }: { region: RegionCode; setRegion: (r: RegionCode) => void }) {
  const opts: RegionCode[] = ["US", "IN"];
  return (
    <div className="flex items-center rounded-md border border-ink-700/60 overflow-hidden text-[12px]">
      {opts.map((r) => (
        <button
          key={r}
          onClick={() => setRegion(r)}
          className={[
            "px-3 py-1.5 transition-colors",
            region === r
              ? "bg-accent text-accent-foreground font-semibold"
              : "bg-ink-800/40 text-ink-200 hover:bg-ink-700/60",
          ].join(" ")}
        >
          {r}
        </button>
      ))}
    </div>
  );
}

function NextSteps() {
  return (
    <section className="border border-ink-700/60 rounded-md p-4 bg-ink-800/40">
      <div className="text-[11px] uppercase tracking-wider text-ink-300 mb-2">Next phases (see PRD)</div>
      <ol className="text-[12px] space-y-1 text-ink-200 list-decimal list-inside">
        <li>Phase 1.5: Firebase Auth multi-tenant (swap bootstrap admin for real users).</li>
        <li>Phase 2: CSV ingestion + profiler + schema catalog (Cloud Run job → BQ raw).</li>
        <li>Phase 4: Knowledge graph: edge proposals + admin confirmation (NetworkX + Firestore).</li>
        <li>Phase 5: Cube auto-generation from confirmed edges.</li>
        <li>Phase 6: Single-source MVP through the agent swarm.</li>
        <li>Phase 7: Pivot panel — every Nebula §2.1 + §2.2 feature in one PR.</li>
      </ol>
    </section>
  );
}
