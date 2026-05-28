/**
 * Phase 2 shell app.
 *
 * Renders <LoginScreen/> when unauth'd. When auth'd: a tabbed shell with
 * "Locale demo" + "Datasets" — the latter is the real upload + list view
 * built in Phase 2.
 */
import { useState } from "react";
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
import { DatasetsView } from "./views/DatasetsView";
import { GraphView } from "./views/GraphView";
import { CubeView } from "./views/CubeView";

interface AppProps {
  brand: BrandConfig;
}

const DEMO_VALUE = 12_400_000;

type Tab = "datasets" | "graph" | "cube" | "demo";

export function App({ brand }: AppProps) {
  const auth = useAuth();

  if (auth.status === "loading") return <BootSplash />;
  if (auth.status !== "authenticated" || !auth.principal)
    return <LoginScreen brandName={brand.displayName} brandLogoUrl={brand.logoUrl} />;

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
  const [tab, setTab] = useState<Tab>("datasets");

  return (
    <div className="min-h-screen bg-ink-900 text-ink-100">
      <header className="border-b border-ink-700/60 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <img src={brand.logoUrl} alt="" className="h-8 w-8" />
          <div>
            <div className="text-sm font-semibold tracking-wide">{brand.displayName}</div>
            <div className="text-[11px] text-ink-300 font-mono">
              brand: {brand.brandId} · tenant: {auth.principal?.tenant_id} · phase 2
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Tabs tab={tab} setTab={setTab} />
          <AccountMenu />
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-6 space-y-6">
        {tab === "datasets" && <DatasetsView />}
        {tab === "graph" && <GraphView />}
        {tab === "cube" && <CubeView />}
        {tab === "demo" && <LocaleDemoView brand={brand} />}
      </main>
    </div>
  );
}

function Tabs({ tab, setTab }: { tab: Tab; setTab: (t: Tab) => void }) {
  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "datasets", label: "Datasets" },
    { id: "graph", label: "Graph" },
    { id: "cube", label: "Cube" },
    { id: "demo", label: "Locale demo" },
  ];
  return (
    <div className="flex items-center rounded-md border border-ink-700/60 overflow-hidden text-[12px]">
      {tabs.map((t) => (
        <button
          key={t.id}
          onClick={() => setTab(t.id)}
          className={[
            "px-3 py-1.5 transition-colors",
            tab === t.id
              ? "bg-accent text-accent-foreground font-semibold"
              : "bg-ink-800/40 text-ink-200 hover:bg-ink-700/60",
          ].join(" ")}
        >
          {t.label}
        </button>
      ))}
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

function LocaleDemoView({ brand }: { brand: BrandConfig }) {
  const [region, setRegion] = useState<RegionCode>(brand.regionDefault);
  const today = new Date();
  return (
    <div className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold">Locale demo</h1>
        <p className="text-ink-300 mt-1">
          Toggle the region to verify Lakh/Crore + en-IN grouping + Apr-Mar FY work end-to-end.
        </p>
      </section>

      <RegionToggle region={region} setRegion={setRegion} />

      <section className="grid grid-cols-2 gap-4">
        <Card label="Currency (full)" value={formatCurrency(DEMO_VALUE, region)} />
        <Card label="Currency (compact)" value={formatCurrencyCompact(DEMO_VALUE, region)} />
        <Card label="Number (grouped)" value={formatNumber(DEMO_VALUE, region)} />
        <Card label="Fiscal year + Q" value={`${fyLabel(today, region)} · ${fyQuarter(today, region)}`} />
      </section>
    </div>
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
    <div className="flex items-center rounded-md border border-ink-700/60 overflow-hidden text-[12px] w-fit">
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
