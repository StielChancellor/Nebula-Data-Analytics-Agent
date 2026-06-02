/**
 * Projects (Admin surface, Phase 10) — list + create + open a project workspace.
 *
 * A project is a self-contained workspace owning its own datasets, graph, cube,
 * locale, and onboarding. This is the entry point of the Admin surface.
 */
import { useEffect, useMemo, useState } from "react";
import { ApiClient, type Project, type RegionCode } from "@insnav/api-client";
import { useAuth } from "@insnav/auth";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function ProjectsView({ onOpen }: { onOpen: (p: Project) => void }) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );

  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [locale, setLocale] = useState<RegionCode>("US");

  const refresh = () => {
    setLoading(true);
    client
      .listProjects()
      .then((p) => setProjects(p))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(refresh, [client]);

  const create = async () => {
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const p = await client.createProject({ name: name.trim(), locale_default: locale });
      setName("");
      onOpen(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <section className="space-y-5">
      <header>
        <h2 className="text-lg font-semibold">Projects</h2>
        <p className="text-[12px] text-ink-300 mt-0.5">
          Each project is its own workspace — datasets, knowledge graph, cube model, locale,
          and onboarding live inside it.
        </p>
      </header>

      {/* Create */}
      <div className="border border-ink-700/60 rounded-lg bg-ink-800/40 p-4 space-y-3">
        <div className="text-[11px] uppercase tracking-wider text-ink-300">New project</div>
        <div className="flex items-end gap-2">
          <label className="flex-1 text-[11px] text-ink-300">
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void create()}
              placeholder="e.g. Marriott India"
              className="mt-1 w-full bg-ink-900 border border-ink-700/60 rounded px-3 py-2 text-sm text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </label>
          <label className="text-[11px] text-ink-300">
            Locale
            <select
              value={locale}
              onChange={(e) => setLocale(e.target.value as RegionCode)}
              className="mt-1 block bg-ink-900 border border-ink-700/60 rounded px-2 py-2 text-[12px] text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent"
            >
              <option value="US">US ($)</option>
              <option value="IN">India (₹, Lakh/Crore, Apr–Mar FY)</option>
            </select>
          </label>
          <button
            onClick={create}
            disabled={creating || !name.trim()}
            className="text-[12px] px-4 py-2 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50"
          >
            {creating ? "Creating…" : "Create"}
          </button>
        </div>
      </div>

      {error && (
        <div className="text-[12px] text-red-400 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
          {error}
        </div>
      )}

      {/* List */}
      {loading ? (
        <div className="text-[12px] text-ink-300">Loading…</div>
      ) : projects.length === 0 ? (
        <div className="text-[12px] text-ink-300">No projects yet — create one above to begin.</div>
      ) : (
        <div className="grid grid-cols-2 gap-3">
          {projects.map((p) => (
            <button
              key={p.id}
              onClick={() => onOpen(p)}
              className="text-left border border-ink-700/60 rounded-lg bg-ink-800/40 p-4 hover:border-accent/60 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold text-ink-100">{p.name}</div>
                <span className="text-[10px] uppercase tracking-wider text-ink-300">{p.status}</span>
              </div>
              <div className="text-[11px] text-ink-300 mt-1">
                {p.dataset_ids.length} dataset{p.dataset_ids.length === 1 ? "" : "s"} · {p.locale_default}
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
