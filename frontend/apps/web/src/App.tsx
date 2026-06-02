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
import { ApiClient, type Project, type ProjectStatus } from "@insnav/api-client";
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
      {tab === "graph" && <GraphView projectId={project.id} />}
      {tab === "cube" && <CubeView projectId={project.id} />}
      {tab === "settings" && <ProjectSettings project={project} onChanged={onBack} />}
    </div>
  );
}

function ProjectSettings({ project, onChanged }: { project: Project; onChanged: () => void }) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );
  const [name, setName] = useState(project.name);
  const [status, setStatus] = useState<ProjectStatus>(project.status);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const save = async () => {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await client.updateProject(project.id, { name: name.trim(), status });
      setSaved(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (
      !window.confirm(
        `Delete project “${project.name}”? This permanently deletes its ${project.dataset_ids.length} dataset(s) — BigQuery tables, files, graph edges, and cube — and cannot be undone.`,
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await client.deleteProject(project.id);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 text-[13px] max-w-lg">
      <h3 className="text-sm font-semibold">Settings</h3>

      {error && (
        <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
          {error}
        </div>
      )}

      <div className="border border-ink-700/60 rounded-lg bg-ink-800/40 p-4 space-y-3">
        <label className="block text-[11px] text-ink-300">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="mt-1 w-full bg-ink-900 border border-ink-700/60 rounded px-3 py-2 text-sm text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent"
          />
        </label>
        <label className="block text-[11px] text-ink-300">
          Status
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as ProjectStatus)}
            className="mt-1 block bg-ink-900 border border-ink-700/60 rounded px-2 py-2 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent"
          >
            <option value="draft">draft</option>
            <option value="active">active</option>
            <option value="archived">archived</option>
          </select>
        </label>
        <div className="flex items-center gap-3">
          <button
            onClick={save}
            disabled={busy || !name.trim()}
            className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? "Saving…" : "Save"}
          </button>
          {saved && <span className="text-[12px] text-emerald-300">Saved ✓</span>}
        </div>
      </div>

      <dl className="border border-ink-700/60 rounded-lg bg-ink-800/40 divide-y divide-ink-700/40">
        {[
          ["Locale", project.locale_default],
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
      <p className="text-[11px] text-ink-300">
        Member invitations require user accounts (Identity Platform) — a later add.
      </p>

      <div className="border border-red-900/50 rounded-lg p-4">
        <div className="text-[12px] text-red-300 font-semibold mb-1">Danger zone</div>
        <p className="text-[11px] text-ink-300 mb-2">
          Deleting a project removes all its datasets, graph, and cube. This can't be undone.
        </p>
        <button
          onClick={remove}
          disabled={busy}
          className="text-[12px] px-3 py-1.5 rounded border border-red-900/60 text-red-300 hover:bg-red-950/40 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Delete project
        </button>
      </div>
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
      <div className="text-2xl text-ink-300 mb-2">▦</div>
      {label} — coming next (PRD Phase 7/8). Your governed cube already powers <span className="text-ink-100">Ask</span>.
    </div>
  );
}
