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
  type DatasetListItem,
  type DatasetStatus,
  uploadToGcs,
} from "@insnav/api-client";

const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export function DatasetsView() {
  const auth = useAuth();
  const client = useMemo(
    () => new ApiClient({ baseUrl: API_BASE, getToken: auth.getToken }),
    [auth.getToken],
  );
  const [items, setItems] = useState<DatasetListItem[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [showUpload, setShowUpload] = useState(false);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const list = await client.listDatasets();
      setItems(list);
    } catch (e) {
      console.error("listDatasets failed", e);
    } finally {
      setRefreshing(false);
    }
  }, [client]);

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

      {items.length === 0 ? (
        <EmptyState onUpload={() => setShowUpload(true)} />
      ) : (
        <DatasetTable items={items} />
      )}

      {showUpload && (
        <UploadDialog
          client={client}
          onClose={() => setShowUpload(false)}
          onUploaded={() => {
            setShowUpload(false);
            void refresh();
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

function DatasetTable({ items }: { items: DatasetListItem[] }) {
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
            <th className="text-left px-3 py-2 font-medium">Updated</th>
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
              <td className="px-3 py-2 text-ink-300 font-mono text-[11px]">
                {new Date(d.last_refreshed).toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type UploadPhase = "select" | "uploading" | "completing" | "polling" | "done" | "error";

interface UploadDialogProps {
  client: ApiClient;
  onClose: () => void;
  onUploaded: () => void;
}

function UploadDialog({ client, onClose, onUploaded }: UploadDialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [phase, setPhase] = useState<UploadPhase>("select");
  const [progress, setProgress] = useState(0); // 0..1
  const [error, setError] = useState<string | null>(null);
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [status, setStatus] = useState<DatasetStatus | null>(null);

  const onPickFile = (f: File) => {
    setFile(f);
    setError(null);
    setPhase("select");
    setProgress(0);
  };

  const onSubmit = async () => {
    if (!file) return;
    setError(null);
    try {
      // Step 1: start
      const start = await client.startUpload(file.name, file.size, { locale_hint: "US" });
      setDatasetId(start.dataset_id);

      // Step 2: PUT to GCS with progress
      setPhase("uploading");
      await uploadToGcs(start.signed_url, file, (loaded, total) => {
        setProgress(loaded / total);
      });

      // Step 3: complete (kicks off BQ load + profile)
      setPhase("completing");
      const done = await client.completeUpload(start.dataset_id);
      setStatus(done.status);

      // Step 4: poll until ready (in the synchronous v1 flow, status will
      // be "ready" or "failed" immediately, but the loop handles future
      // async ingestion too)
      setPhase("polling");
      for (let i = 0; i < 60; i += 1) {
        const cur = await client.getDataset(start.dataset_id);
        setStatus(cur.status);
        if (cur.status === "ready" || cur.status === "failed") break;
        await new Promise((r) => setTimeout(r, 1000));
      }
      setPhase("done");
      onUploaded();
    } catch (e) {
      console.error("upload failed", e);
      setError(e instanceof Error ? e.message : String(e));
      setPhase("error");
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-ink-900/70 grid place-items-center p-6">
      <div className="w-full max-w-md border border-ink-700/60 rounded-lg bg-ink-800 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">Upload CSV</div>
          <button onClick={onClose} className="text-ink-300 hover:text-ink-100 text-lg leading-none">×</button>
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
          </div>
        )}

        {error && (
          <div className="text-[12px] text-red-400 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
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
                className="text-[12px] px-4 py-1.5 rounded bg-accent text-accent-foreground font-semibold hover:opacity-90 disabled:opacity-50"
              >
                Upload
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
