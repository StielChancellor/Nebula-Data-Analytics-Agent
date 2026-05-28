/**
 * Phase 0 shell app.
 *
 * What this demonstrates:
 * - brand-runtime wired in (Aurora teal accent visible)
 * - locale package exercised for both US and IN (proves Lakh/Crore + en-IN
 *   grouping work end-to-end)
 * - LICENSE/PRD/architecture readable from the shell
 *
 * What it does NOT do yet:
 * - Auth, chat, pivot, dashboards, charts, upload — those land in later
 *   phases per PRD build order.
 */
import { useState } from "react";
import type { BrandConfig } from "@insnav/brand-runtime";
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

const DEMO_VALUE = 12_400_000; // $12.4M / ₹1.24 Cr

export function App({ brand }: AppProps) {
  const [region, setRegion] = useState<RegionCode>(brand.regionDefault);
  const today = new Date();

  return (
    <div className="min-h-screen bg-ink-900 text-ink-100">
      <header className="border-b border-ink-700/60 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-md bg-accent/15 ring-1 ring-accent/30 grid place-items-center text-accent font-semibold">
            ✦
          </div>
          <div>
            <div className="text-sm font-semibold tracking-wide">{brand.displayName}</div>
            <div className="text-[11px] text-ink-300 font-mono">brand: {brand.brandId} · phase 0 shell</div>
          </div>
        </div>
        <RegionToggle region={region} setRegion={setRegion} />
      </header>

      <main className="max-w-5xl mx-auto p-6 space-y-6">
        <section>
          <h1 className="text-2xl font-semibold">Project Insights Navigator V2.0</h1>
          <p className="text-ink-300 mt-1">
            Phase 0 scaffold. Backend wires up next; this shell exists to verify the brand-runtime ↔ locale
            contract works end-to-end.
          </p>
        </section>

        <section className="grid grid-cols-2 gap-4">
          <Card label="Currency (full)" value={formatCurrency(DEMO_VALUE, region)} />
          <Card label="Currency (compact)" value={formatCurrencyCompact(DEMO_VALUE, region)} />
          <Card label="Number (grouped)" value={formatNumber(DEMO_VALUE, region)} />
          <Card label="Fiscal year + Q" value={`${fyLabel(today, region)} · ${fyQuarter(today, region)}`} />
        </section>

        <section className="text-[12px] text-ink-300 leading-relaxed border border-ink-700/60 rounded-md p-4 bg-ink-800/60">
          <strong className="text-ink-100">India non-negotiable (PRD §8):</strong> when region = IN, every number
          uses ₹, en-IN grouping (1,24,00,000), Lakh/Crore compaction, Apr-Mar FY default, Asia/Kolkata timezone.
          Toggle the region above to verify.
        </section>

        <NextSteps />
      </main>
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
        <li>Backend foundations: GCP wiring, Firebase Auth multi-tenant, bootstrap admin.</li>
        <li>CSV ingestion + profiler + schema catalog (Cloud Run job → BQ raw).</li>
        <li>Knowledge graph: edge proposals + admin confirmation UX (NetworkX + Firestore).</li>
        <li>Cube auto-generation from confirmed edges.</li>
        <li>Single-source MVP through the agent swarm (Orchestrator + Semantic + Critic + DQ).</li>
        <li>Pivot panel — every Nebula §2.1 + §2.2 feature in one PR.</li>
      </ol>
    </section>
  );
}
