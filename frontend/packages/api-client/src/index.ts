/**
 * @insnav/api-client
 *
 * Phase 2: hand-written typed methods for the endpoints we currently expose.
 * Phase 6+ replaces this with codegen from /v1/openapi.json (tools/openapi-codegen).
 */

export type RegionCode = "US" | "IN";

export type DatasetStatus =
  | "queued"
  | "uploading"
  | "loading"
  | "profiling"
  | "ready"
  | "failed";

export interface DatasetListItem {
  id: string;
  label: string;
  locale_hint: RegionCode;
  status: DatasetStatus;
  row_count: number | null;
  column_count: number | null;
  last_refreshed: string;
  scopes: string[];
}

export interface Dataset {
  id: string;
  tenant_id: string;
  brand: string;
  label: string;
  locale_hint: RegionCode;
  source_filename: string;
  source_size_bytes: number;
  gcs_blob_path: string;
  bq_table: string | null;
  status: DatasetStatus;
  row_count: number | null;
  column_count: number | null;
  created_at: string;
  updated_at: string;
  error: string | null;
}

export interface StartUploadResponse {
  dataset_id: string;
  signed_url: string;
  gcs_blob_path: string;
  expires_at: string;
}

export interface CompleteUploadResponse {
  dataset_id: string;
  status: DatasetStatus;
  bq_table: string | null;
  row_count: number | null;
  column_count: number | null;
  error: string | null;
  /** Phase 4: how many edges the auto-discoverer proposed for this dataset */
  new_edge_proposals: number;
}

// --- Phase 4: knowledge-graph edges ---

export type EdgeState = "proposed" | "approved" | "rejected";

export interface GraphEdge {
  id: string;
  tenant_id: string;
  from_dataset: string;
  from_column: string;
  to_dataset: string;
  to_column: string;
  similarity_score: number;
  key_overlap_pct: number;
  from_distinct_count: number | null;
  to_distinct_count: number | null;
  sample_overlap: string[];
  state: EdgeState;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

const DEFAULT_BASE = "/api";

export interface ApiClientOptions {
  baseUrl?: string;
  getToken?: () => string | null | Promise<string | null>;
}

export class ApiClient {
  private baseUrl: string;
  private getToken: () => string | null | Promise<string | null>;

  constructor(opts: ApiClientOptions = {}) {
    this.baseUrl = opts.baseUrl ?? DEFAULT_BASE;
    this.getToken = opts.getToken ?? (() => null);
  }

  private async authHeaders(): Promise<HeadersInit> {
    const token = await this.getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async get<T>(path: string): Promise<T> {
    const headers = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}${path}`, { headers, credentials: "include" });
    if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
    return (await res.json()) as T;
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const headers = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`POST ${path} -> ${res.status}: ${text}`);
    }
    return (await res.json()) as T;
  }

  // --- Typed convenience methods (replace with codegen later) ---

  listDatasets(): Promise<DatasetListItem[]> {
    return this.get("/v1/me/datasets");
  }

  getDataset(id: string): Promise<Dataset> {
    return this.get(`/v1/datasets/${id}`);
  }

  startUpload(filename: string, sizeBytes: number, opts: { label?: string; locale_hint?: RegionCode } = {}): Promise<StartUploadResponse> {
    return this.post("/v1/uploads/start", { filename, size_bytes: sizeBytes, ...opts });
  }

  completeUpload(datasetId: string): Promise<CompleteUploadResponse> {
    return this.post("/v1/uploads/complete", { dataset_id: datasetId });
  }

  // --- Edges ---
  listApprovedEdges(): Promise<GraphEdge[]> {
    return this.get("/v1/edges");
  }

  listEdgeProposals(): Promise<GraphEdge[]> {
    return this.get("/v1/edges/proposals");
  }

  approveEdge(id: string): Promise<GraphEdge> {
    return this.post(`/v1/edges/${id}/approve`, {});
  }

  rejectEdge(id: string): Promise<GraphEdge> {
    return this.post(`/v1/edges/${id}/reject`, {});
  }

  discoverEdges(datasetId: string): Promise<GraphEdge[]> {
    return this.post(`/v1/datasets/${datasetId}/discover-edges`, {});
  }

  // --- Cube schemas (Phase 5) ---
  listCubeSchemas(): Promise<CubeSchemaSummary[]> {
    return this.get("/v1/cube/schemas");
  }

  getCubeSchemaJson(datasetId: string): Promise<CubeSchemaFull> {
    return this.get(`/v1/cube/schemas/${datasetId}/json`);
  }

  /** Returns raw Cube .js text (Content-Type: application/javascript) */
  async getCubeSchemaJs(datasetId: string): Promise<string> {
    const headers = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/v1/cube/schemas/${datasetId}.js`, {
      headers,
      credentials: "include",
    });
    if (!res.ok) throw new Error(`GET cube/.js -> ${res.status}`);
    return res.text();
  }

  /** Publish the tenant's Cube model to GCS for the deployed Cube service. */
  syncCubeModel(): Promise<CubeSyncResult> {
    return this.post("/v1/cube/sync", {});
  }

  /** Ask the agent swarm a natural-language question. */
  chat(question: string, datasetIds: string[] = []): Promise<ChatAnswer> {
    return this.post("/v1/chat", { question, dataset_ids: datasetIds });
  }
}

// --- Chat / agent swarm (Phase 6) ---

export interface DataHealthBadge {
  status: "ok" | "warn" | "block";
  freshness: Array<{ source: string; last_refreshed: string | null }>;
  completeness: Array<{ source: string; row_count: number | null }>;
  coverage_rate: number | null;
  warnings: string[];
}

export interface ChatAnswer {
  kind: "answer" | "clarify" | "refuse";
  interpretation_echo: string;
  confidence: number;
  analysis_level: string;
  cube_query: Record<string, unknown> | null;
  columns: string[];
  rows: unknown[][];
  data_health: DataHealthBadge | null;
  method_used: string;
  caveats: string[];
  inputs_hash: string;
  message: string;
}

export interface CubeSyncResult {
  tenant_id: string;
  version: string;
  file_count: number;
  cube_names: string[];
}

// --- Cube types (Phase 5) ---

export type CubeRelationship = "one_to_one" | "one_to_many" | "many_to_one" | "many_to_many";
export type CubeColumnType = "string" | "number" | "time" | "boolean";
export type CubeMeasureType = "count" | "sum" | "avg" | "min" | "max" | "count_distinct";

export interface CubeSchemaSummary {
  dataset_id: string;
  dataset_label: string;
  cube_name: string;
  bq_table: string | null;
  dimension_count: number;
  measure_count: number;
  join_count: number;
  revenue_touching: boolean;
}

export interface CubeDimension {
  name: string;
  sql: string;
  type: CubeColumnType;
  primary_key: boolean;
  title: string | null;
  description: string | null;
}

export interface CubeMeasure {
  name: string;
  type: CubeMeasureType;
  sql: string | null;
  title: string | null;
  description: string | null;
  revenue_touching: boolean;
}

export interface CubeJoin {
  to_cube: string;
  sql_clause: string;
  relationship: CubeRelationship;
  from_edge_id: string;
  from_dataset_id: string;
  to_dataset_id: string;
}

export interface CubeSchemaFull {
  name: string;
  title: string;
  sql_table: string;
  description: string;
  dimensions: CubeDimension[];
  measures: CubeMeasure[];
  joins: CubeJoin[];
  dataset_id: string;
  tenant_id: string;
  generated_at: string;
  locale_hint: "US" | "IN";
}

/**
 * Upload a File to a GCS signed-URL using XMLHttpRequest so we get upload
 * progress events (fetch doesn't expose them).
 *
 * Phase 2: single-shot PUT (works for files up to a few GB). For files >
 * ~2 GB, swap to chunked PUTs with Content-Range — GCS resumable sessions
 * accept partial PUTs with 308 responses for in-progress, 200 when done.
 * That's a Phase 2.5 follow-up if real users hit the wall.
 */
export function uploadToGcs(
  signedUrl: string,
  file: File,
  onProgress?: (loaded: number, total: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", signedUrl);
    xhr.setRequestHeader("Content-Type", "text/csv");
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(e.loaded, e.total);
      };
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error(`GCS PUT failed: ${xhr.status} ${xhr.responseText}`));
    };
    xhr.onerror = () => reject(new Error("GCS PUT network error"));
    xhr.send(file);
  });
}
