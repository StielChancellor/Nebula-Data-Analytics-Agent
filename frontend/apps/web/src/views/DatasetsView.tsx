/**
 * Datasets view: list existing datasets + drag-drop CSV upload.
 *
 * Phase 2 — single view, no sidebar nav yet. Phase 3+ wraps this in a real
 * router and shell layout.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "@insnav/auth";
import {
  ApiClient,
  type ColumnSpec,
  type DatasetListItem,
  type DatasetStatus,
  type RegionCode,
  uploadToGcs,
} from "@insnav/api-client";

const BQ_TYPES = ["STRING", "INT64", "NUMERIC", "FLOAT64", "DATE", "TIMESTAMP", "BOOL"];

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

interface DatasetsViewProps {
  projectId?: string;
  localeDefault?: RegionCode;
  onOnboard?: (datasetId: string) => void;
}

export function DatasetsView({ projectId, localeDefault = "US", onOnboard }: DatasetsViewProps = {}) {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );
  const [items, setItems] = useState<DatasetListItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const list = await client.listDatasets(projectId);
      setItems(list);
      setError(null);
      setLoaded(true);
    } catch (e) {
      // C5: surface failures instead of silently showing an empty state.
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }, [client, projectId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Datasets</h2>
          <p className="text-[12px] text-ink-300 mt-0.5">
            Upload a CSV — it lands in GCS, BigQuery loads it, profiler runs, status flips to <span className="font-mono">ready</span>.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={refresh}
            disabled={refreshing}
            className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60 hover:bg-ink-700/40 disabled:opacity-50"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button
            onClick={() => setShowUpload(true)}
            className="text-[12px] px-3 py-1.5 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90"
          >
            Upload CSV
          </button>
        </div>
      </div>

      {error && (
        <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-3 py-2 flex items-center justify-between">
          <span>Couldn't load datasets: {error}</span>
          <button onClick={() => void refresh()} className="underline hover:text-red-200">Retry</button>
        </div>
      )}

      {items.length > 0 ? (
        <DatasetTable items={items} client={client} onChanged={refresh} onOnboard={onOnboard} />
      ) : loaded && !error ? (
        <EmptyState onUpload={() => setShowUpload(true)} />
      ) : null}

      {showUpload && (
        <UploadDialog
          client={client}
          projectId={projectId}
          localeDefault={localeDefault}
          onClose={() => setShowUpload(false)}
          onUploaded={(datasetId, status) => {
            setShowUpload(false);
            void refresh();
            // A successful, project-scoped upload flows straight into onboarding.
            if (status === "ready" && projectId && onOnboard) onOnboard(datasetId);
          }}
        />
      )}
    </section>
  );
}

function EmptyState({ onUpload }: { onUpload: () => void }) {
  return (
    <div className="border border-dashed border-ink-700/60 rounded-lg p-10 text-center bg-ink-800/30">
      <div className="text-3xl text-ink-400 mb-2">∅</div>
      <div className="text-sm">No datasets yet</div>
      <p className="text-[12px] text-ink-300 mt-1">Upload your first CSV to get started.</p>
      <button
        onClick={onUpload}
        className="mt-4 text-[12px] px-4 py-1.5 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90"
      >
        Upload CSV
      </button>
    </div>
  );
}

const STATUS_STYLES: Record<DatasetStatus, string> = {
  queued: "bg-ink-700/40 text-ink-200",
  uploading: "bg-blue-900/30 text-blue-300",
  loading: "bg-blue-900/30 text-blue-300",
  profiling: "bg-amber-900/30 text-amber-300",
  ready: "bg-emerald-900/30 text-emerald-300",
  failed: "bg-red-900/40 text-red-300",
};

function DatasetTable({
  items,
  client,
  onChanged,
  onOnboard,
}: {
  items: DatasetListItem[];
  client: ApiClient;
  onChanged: () => void;
  onOnboard?: (datasetId: string) => void;
}) {
  const [busyId, setBusyId] = useState<string | null>(null);

  const del = async (id: string) => {
    if (!window.confirm("Delete this dataset? This removes its BigQuery table, file, edges, and cube entry.")) return;
    setBusyId(id);
    try {
      await client.deleteDataset(id);
      onChanged();
    } catch (e) {
      console.error("delete failed", e);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="border border-ink-700/60 rounded-lg overflow-hidden">
      <table className="w-full text-[12px]">
        <thead className="bg-ink-800/60 text-ink-300 text-[11px] uppercase tracking-wider">
          <tr>
            <th className="text-left px-3 py-2 font-medium">Label</th>
            <th className="text-left px-3 py-2 font-medium">Status</th>
            <th className="text-right px-3 py-2 font-medium">Rows</th>
            <th className="text-right px-3 py-2 font-medium">Columns</th>
            <th className="text-left px-3 py-2 font-medium">Locale</th>
            <th className="text-right px-3 py-2 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => (
            <tr key={d.id} className="border-t border-ink-700/40 hover:bg-ink-800/40">
              <td className="px-3 py-2 font-medium">{d.label}</td>
              <td className="px-3 py-2">
                <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-mono ${STATUS_STYLES[d.status]}`}>
                  {d.status}
                </span>
              </td>
              <td className="px-3 py-2 text-right font-mono numeric">
                {d.row_count?.toLocaleString() ?? "—"}
              </td>
              <td className="px-3 py-2 text-right font-mono numeric">{d.column_count ?? "—"}</td>
              <td className="px-3 py-2 text-ink-300">{d.locale_hint}</td>
              <td className="px-3 py-2 text-right whitespace-nowrap">
                {onOnboard && d.status === "ready" && (
                  <button
                    onClick={() => onOnboard(d.id)}
                    className="text-[11px] px-2 py-1 rounded bg-accent/15 text-accent-glow hover:bg-accent/25 mr-1"
                  >
                    Onboard
                  </button>
                )}
                <button
                  onClick={() => del(d.id)}
                  disabled={busyId === d.id}
                  className="text-[11px] px-2 py-1 rounded border border-red-900/50 text-red-300 hover:bg-red-950/40 disabled:opacity-50"
                >
                  {busyId === d.id ? "…" : "Delete"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type UploadPhase = "select" | "uploading" | "preview" | "completing" | "polling" | "done" | "error";

interface PreviewRow {
  name: string;
  bq_type: string;
  source_format: string | null;
  sample_values: string[];
}

interface UploadDialogProps {
  client: ApiClient;
  projectId?: string;
  localeDefault?: RegionCode;
  onClose: () => void;
  onUploaded: (datasetId: string, status: DatasetStatus) => void;
}

function UploadDialog({ client, projectId, localeDefault = "US", onClose, onUploaded }: UploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<UploadPhase>("select");
  const [progress, setProgress] = useState(0); // 0..1
  const [error, setError] = useState<string | null>(null);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [status, setStatus] = useState<DatasetStatus | null>(null);
  const [cols, setCols] = useState<PreviewRow[]>([]);

  // a11y: Escape closes the modal (H5).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const onPickFile = (f: File) => {
    setFile(f);
    setError(null);
    setPhase("select");
    setProgress(0);
  };

  // Step 1+2+preview: start → PUT → read-before-commit sniff. The user reviews
  // (and can override) the inferred per-column types before the BQ load.
  const onSubmit = async () => {
    if (!file) return;
    setError(null);
    try {
      const start = await client.startUpload(file.name, file.size, {
        locale_hint: localeDefault,
        ...(projectId ? { project_id: projectId } : {}),
      });
      setDatasetId(start.dataset_id);

      setPhase("uploading");
      await uploadToGcs(start.signed_url, file, (loaded, total) => setProgress(loaded / total));

      const pv = await client.previewUpload(start.dataset_id);
      setCols(
        pv.columns.map((c) => ({
          name: c.name,
          bq_type: c.inferred_bq_type,
          source_format: c.inferred_format,
          sample_values: c.sample_values,
        })),
      );
      setPhase("preview");
    } catch (e) {
      console.error("upload/preview failed", e);
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  };

  // Step 3+4: commit the (possibly overridden) schema → load + profile → poll.
  const confirmLoad = async () => {
    if (!datasetId) return;
    setError(null);
    try {
      setPhase("completing");
      const overrides: ColumnSpec[] = cols.map((c) => ({
        name: c.name,
        bq_type: c.bq_type,
        source_format: c.source_format,
      }));
      const done = await client.completeUpload(datasetId, overrides);
      let finalStatus: DatasetStatus = done.status;
      setStatus(finalStatus);

      setPhase("polling");
      for (let i = 0; i < 60; i += 1) {
        const cur = await client.getDataset(datasetId);
        finalStatus = cur.status;
        setStatus(finalStatus);
        if (finalStatus === "ready" || finalStatus === "failed") break;
        await new Promise((r) => setTimeout(r, 1000));
      }
      setPhase("done");
      onUploaded(datasetId, finalStatus);
    } catch (e) {
      console.error("load failed", e);
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-ink-900/70 grid place-items-center p-6"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-title"
        className={`w-full ${phase === "preview" ? "max-w-2xl" : "max-w-md"} border border-ink-700/60 rounded-lg bg-ink-800 p-6 space-y-4`}
      >
        <div className="flex items-center justify-between">
          <div id="upload-title" className="text-sm font-semibold">Upload CSV</div>
          <button onClick={onClose} aria-label="Close" className="text-ink-300 hover:text-ink-100 text-lg leading-none">×</button>
        </div>

        {phase === "select" && (
          <FileDropZone file={file} onPick={onPickFile} />
        )}

        {(phase === "uploading" || phase === "completing" || phase === "polling") && (
          <div className="space-y-2">
            <div className="text-[12px] text-ink-300">{phaseLabel(phase, status)}</div>
            <div className="h-2 bg-ink-900 rounded overflow-hidden">
              <div
                className="h-full bg-accent transition-all"
                style={{ width: `${Math.round(progress * 100)}%` }}
              />
            </div>
            <div className="text-[11px] text-ink-300 font-mono">
              {file && `${(file.size / 1024 / 1024).toFixed(1)} MB · ${(progress * 100).toFixed(0)}%`}
            </div>
            <div className="text-[11px] text-ink-300">First run can take ~30s while the engine warms up…</div>
          </div>
        )}

        {phase === "preview" && (
          <div className="space-y-2">
            <p className="text-[12px] text-ink-300">
              Here's what I read. Check the column types — fix any that look wrong (India dates &amp; ₹/lakh
              amounts are auto-detected), then load.
            </p>
            <div className="overflow-auto max-h-72 border border-ink-700/50 rounded">
              <table className="w-full text-[12px]">
                <thead className="bg-ink-900/60 text-ink-300 text-[11px] uppercase tracking-wider sticky top-0">
                  <tr>
                    <th className="text-left px-2 py-1">Column</th>
                    <th className="text-left px-2 py-1">Type</th>
                    <th className="text-left px-2 py-1">Samples</th>
                  </tr>
                </thead>
                <tbody>
                  {cols.map((c, i) => (
                    <tr key={c.name} className="border-t border-ink-700/40">
                      <td className="px-2 py-1 font-mono text-ink-100">{c.name}</td>
                      <td className="px-2 py-1">
                        <select
                          value={c.bq_type}
                          aria-label={`Type for ${c.name}`}
                          onChange={(e) =>
                            setCols((cs) => cs.map((r, idx) => (idx === i ? { ...r, bq_type: e.target.value } : r)))
                          }
                          className="bg-ink-900 border border-ink-700/60 rounded px-1.5 py-1 text-[12px] text-ink-100"
                        >
                          {BQ_TYPES.map((t) => (
                            <option key={t} value={t}>{t}</option>
                          ))}
                        </select>
                        {c.source_format && (
                          <span className="ml-1 text-[10px] text-ink-300">{c.source_format}</span>
                        )}
                      </td>
                      <td className="px-2 py-1 text-ink-300 font-mono truncate max-w-[16rem]">
                        {c.sample_values.slice(0, 3).join(", ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {error && (
          <div className="text-[12px] text-red-300 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
            {error}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-2">
          {phase === "select" && (
            <>
              <button onClick={onClose} className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60 hover:bg-ink-700/40">
                Cancel
              </button>
              <button
                onClick={onSubmit}
                disabled={!file}
                className="text-[12px] px-4 py-1.5 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Upload &amp; preview
              </button>
            </>
          )}
          {phase === "preview" && (
            <>
              <button onClick={onClose} className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60 hover:bg-ink-700/40">
                Cancel
              </button>
              <button
                onClick={confirmLoad}
                className="text-[12px] px-4 py-1.5 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90"
              >
                Looks right — load it
              </button>
            </>
          )}
          {phase === "error" && (
            <button onClick={() => setPhase("select")} className="text-[12px] px-3 py-1.5 rounded border border-ink-700/60">
              Try again
            </button>
          )}
        </div>

        {datasetId && (
          <div className="text-[10px] text-ink-300 font-mono pt-1">
            id: {datasetId}
          </div>
        )}
      </div>
    </div>
  );
}

function phaseLabel(phase: UploadPhase, status: DatasetStatus | null): string {
  if (phase === "uploading") return "Uploading to GCS…";
  if (phase === "completing") return "Starting BigQuery load + profile…";
  if (phase === "polling") return `Status: ${status ?? "…"}`;
  return phase;
}

function FileDropZone({ file, onPick }: { file: File | null; onPick: (f: File) => void }) {
  const [hover, setHover] = useState(false);
  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        setHover(true);
      }}
      onDragLeave={() => setHover(false)}
      onDrop={(e) => {
        e.preventDefault();
        setHover(false);
        const f = e.dataTransfer.files[0];
        if (f) onPick(f);
      }}
      className={[
        "block border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors",
        hover ? "border-accent bg-accent-soft/40" : "border-ink-700/60 hover:border-ink-500",
      ].join(" ")}
    >
      <input
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onPick(f);
        }}
      />
      {file ? (
        <div className="space-y-1">
          <div className="text-sm font-medium">{file.name}</div>
          <div className="text-[11px] text-ink-300 font-mono">
            {(file.size / 1024 / 1024).toFixed(2)} MB
          </div>
        </div>
      ) : (
        <div className="space-y-1 text-ink-300">
          <div className="text-2xl">⇪</div>
          <div className="text-[12px]">Drop a CSV here, or click to browse</div>
          <div className="text-[10px]">Max 5 GB</div>
        </div>
      )}
    </label>
  );
}
