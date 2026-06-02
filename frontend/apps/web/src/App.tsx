/**
 * App shell (Phase 10) — two surfaces.
 *
 *  • Admin   — projects live here. Open a project to manage its Datasets,
 *              Onboarding, Graph, Cube, and Settings (its own workspace).
 *  • Explore — consume a selected project: Ask (chat), Pivots, Dashboards.
 *
 * A project selector in the header sets the active workspace for both surfaces.
 */
import { useEffect, useMemo, useState } from "react";
import type { BrandConfig } from "@insnav/brand-runtime";
import { useAuth, LoginScreen } from "@insnav/auth";
import { ApiClient, type Project } from "@insnav/api-client";
import { DatasetsView } from "./views/DatasetsView";
import { GraphView } from "./views/GraphView";
import { CubeView } from "./views/CubeView";
import { ChatView } from "./views/ChatView";
import { ProjectsView } from "./views/ProjectsView";
import { OnboardingView } from "./views/OnboardingView";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

interface AppProps {
  brand: BrandConfig;
}

type Surface = "admin" | "explore";

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
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );

  const [surface, setSurface] = useState<Surface>("admin");
  const [projects, setProjects] = useState<Project[]>([]);
  const [project, setProject] = useState<Project | null>(null);

  const loadProjects = () =>
    client.listProjects().then(setProjects).catch(() => setProjects([]));
  useEffect(() => {
    void loadProjects();
  }, [client]);

  return (
    <div className="min-h-screen bg-ink-900 text-ink-100">
      <header className="border-b border-ink-700/60 px-6 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <img src={brand.logoUrl} alt="" className="h-8 w-8" />
          <div>
            <div className="text-sm font-semibold tracking-wide">{brand.displayName}</div>
            <div className="text-[11px] text-ink-300 font-mono">
              {auth.principal?.tenant_id} · phase 10
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <SurfaceToggle surface={surface} setSurface={setSurface} />
          <ProjectSelector
            projects={projects}
            project={project}
            onPick={(p) => {
              setProject(p);
              if (p && surface === "admin") setSurface("admin");
            }}
          />
          <AccountMenu />
        </div>
      </header>

      <main className="max-w-5xl mx-auto p-6">
        {surface === "admin" ? (
          project ? (
            <ProjectWorkspace
              project={project}
              onBack={() => setProject(null)}
            />
          ) : (
            <ProjectsView
              onOpen={(p) => {
                setProject(p);
                void loadProjects();
              }}
            />
          )
        ) : (
          <ExploreSurface project={project} />
        )}
      </main>
    </div>
  );
}

function SurfaceToggle({ surface, setSurface }: { surface: Surface; setSurface: (s: Surface) => void }) {
  return (
    <div className="flex items-center rounded-md border border-ink-700/60 overflow-hidden text-[12px]">
      {(["admin", "explore"] as Surface[]).map((s) => (
        <button
          key={s}
          onClick={() => setSurface(s)}
          className={[
            "px-3 py-1.5 capitalize transition-colors",
            surface === s ? "bg-accent text-accent-foreground font-semibold" : "bg-ink-800/40 text-ink-200 hover:bg-ink-700/60",
          ].join(" ")}
        >
          {s}
        </button>
      ))}
    </div>
  );
}

function ProjectSelector({
  projects,
  project,
  onPick,
}: {
  projects: Project[];
  project: Project | null;
  onPick: (p: Project | null) => void;
}) {
  return (
    <select
      value={project?.id ?? ""}
      onChange={(e) => onPick(projects.find((p) => p.id === e.target.value) ?? null)}
      className="bg-ink-900 border border-ink-700/60 rounded px-2 py-1.5 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent max-w-[180px]"
    >
      <option value="">— Projects —</option>
      {projects.map((p) => (
        <option key={p.id} value={p.id}>{p.name}</option>
      ))}
    </select>
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

// ---------- Admin: a single project's workspace ----------

type WorkspaceTab = "datasets" | "onboarding" | "graph" | "cube" | "settings";

function ProjectWorkspace({ project, onBack }: { project: Project; onBack: () => void }) {
  const [tab, setTab] = useState<WorkspaceTab>("datasets");
  const [onboardingDatasetId, setOnboardingDatasetId] = useState<string | null>(null);

  const tabs: Array<{ id: WorkspaceTab; label: string }> = [
    { id: "datasets", label: "Datasets" },
    { id: "onboarding", label: "Onboarding" },
    { id: "graph", label: "Graph" },
    { id: "cube", label: "Cube" },
    { id: "settings", label: "Settings" },
  ];

  const startOnboarding = (datasetId: string) => {
    setOnboardingDatasetId(datasetId);
    setTab("onboarding");
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[12px]">
          <button onClick={onBack} className="text-ink-300 hover:text-ink-100">← Projects</button>
          <span className="text-ink-500">/</span>
          <span className="font-semibold">{project.name}</span>
          <span className="text-[10px] uppercase tracking-wider text-ink-300 ml-1">{project.locale_default}</span>
        </div>
        <div className="flex items-center rounded-md border border-ink-700/60 overflow-hidden text-[12px]">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={[
                "px-3 py-1.5 transition-colors",
                tab === t.id ? "bg-accent text-accent-foreground font-semibold" : "bg-ink-800/40 text-ink-200 hover:bg-ink-700/60",
              ].join(" ")}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "datasets" && (
        <DatasetsView
          projectId={project.id}
          localeDefault={project.locale_default}
          onOnboard={startOnboarding}
        />
      )}
      {tab === "onboarding" && (
        onboardingDatasetId ? (
          <OnboardingView
            datasetId={onboardingDatasetId}
            onDone={() => {
              setOnboardingDatasetId(null);
              setTab("datasets");
            }}
          />
        ) : (
          <div className="text-[12px] text-ink-300 border border-ink-700/60 rounded-lg p-6 bg-ink-800/30">
            Upload a CSV in <span className="text-ink-100">Datasets</span>, then click{" "}
            <span className="text-accent-glow">Onboard</span> to start the agent-led interview.
          </div>
        )
      )}
      {tab === "graph" && <GraphView />}
      {tab === "cube" && <CubeView />}
      {tab === "settings" && <ProjectSettings project={project} />}
    </div>
  );
}

function ProjectSettings({ project }: { project: Project }) {
  return (
    <div className="space-y-3 text-[13px]">
      <h3 className="text-sm font-semibold">Settings</h3>
      <dl className="border border-ink-700/60 rounded-lg bg-ink-800/40 divide-y divide-ink-700/40">
        {[
          ["Name", project.name],
          ["Locale", project.locale_default],
          ["Status", project.status],
          ["Owner", project.owner_email],
          ["Members", `${project.members.length}`],
          ["Datasets", `${project.dataset_ids.length}`],
        ].map(([k, v]) => (
          <div key={k} className="flex justify-between px-4 py-2">
            <dt className="text-ink-300">{k}</dt>
            <dd className="text-ink-100 font-mono">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="text-[11px] text-ink-400">
        Member invitations require user accounts (Identity Platform) — a later add. The project
        owner manages it for now.
      </p>
    </div>
  );
}

// ---------- Explore: consume a project ----------

type ExploreTab = "ask" | "pivots" | "dashboards";

function ExploreSurface({ project }: { project: Project | null }) {
  const [tab, setTab] = useState<ExploreTab>("ask");
  if (!project) {
    return (
      <div className="text-[13px] text-ink-300 border border-ink-700/60 rounded-lg p-8 bg-ink-800/30 text-center">
        Pick a project from the selector above to explore its data.
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <div className="flex items-center justify-end">
        <div className="flex items-center rounded-md border border-ink-700/60 overflow-hidden text-[12px]">
          {(["ask", "pivots", "dashboards"] as ExploreTab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={[
                "px-3 py-1.5 capitalize transition-colors",
                tab === t ? "bg-accent text-accent-foreground font-semibold" : "bg-ink-800/40 text-ink-200 hover:bg-ink-700/60",
              ].join(" ")}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      {tab === "ask" && <ChatView projectId={project.id} />}
      {tab === "pivots" && <ComingSoon label="Pivot tables" />}
      {tab === "dashboards" && <ComingSoon label="Dashboards" />}
    </div>
  );
}

function ComingSoon({ label }: { label: string }) {
  return (
    <div className="text-[13px] text-ink-300 border border-dashed border-ink-700/60 rounded-lg p-10 bg-ink-800/20 text-center">
      <div className="text-2xl text-ink-500 mb-2">▦</div>
      {label} — coming next (PRD Phase 7/8). Your governed cube already powers <span className="text-ink-100">Ask</span>.
    </div>
  );
}
