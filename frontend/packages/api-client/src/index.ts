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
  project_id: string | null;
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
  project_id: string | null;
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
  error_detail?: IngestError | null;
  preview?: Record<string, unknown> | null;
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
  error_detail?: IngestError | null;
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
    const res = await fetch(`${this.baseUrl}${path}`, { headers });
    if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
    return (await res.json()) as T;
  }

  async post<T>(path: string, body: unknown): Promise<T> {
    const headers = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`POST ${path} -> ${res.status}: ${text}`);
    }
    return (await res.json()) as T;
  }

  async patch<T>(path: string, body: unknown): Promise<T> {
    const headers = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "PATCH",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(`PATCH ${path} -> ${res.status}: ${text}`);
    }
    return (await res.json()) as T;
  }

  async del<T>(path: string): Promise<T | null> {
    const headers = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}${path}`, { method: "DELETE", headers });
    if (!res.ok) throw new Error(`DELETE ${path} -> ${res.status}`);
    const text = await res.text();
    return text ? (JSON.parse(text) as T) : null;
  }

  // --- Typed convenience methods (replace with codegen later) ---

  listDatasets(projectId?: string): Promise<DatasetListItem[]> {
    return this.get(`/v1/me/datasets${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`);
  }

  getDataset(id: string): Promise<Dataset> {
    return this.get(`/v1/datasets/${id}`);
  }

  startUpload(
    filename: string,
    sizeBytes: number,
    opts: { label?: string; locale_hint?: RegionCode; project_id?: string } = {},
  ): Promise<StartUploadResponse> {
    return this.post("/v1/uploads/start", { filename, size_bytes: sizeBytes, ...opts });
  }

  /** Read-before-commit: sniff the uploaded blob and return an overridable schema. */
  previewUpload(datasetId: string): Promise<PreviewResponse> {
    return this.post("/v1/uploads/preview", { dataset_id: datasetId });
  }

  completeUpload(datasetId: string, schemaOverrides?: ColumnSpec[]): Promise<CompleteUploadResponse> {
    return this.post("/v1/uploads/complete", {
      dataset_id: datasetId,
      ...(schemaOverrides ? { schema_overrides: schemaOverrides } : {}),
    });
  }

  /** Fully delete a dataset (BQ table + GCS blob + edges + Firestore + cube re-sync). */
  deleteDataset(id: string): Promise<DeleteDatasetResult | null> {
    return this.del(`/v1/datasets/${id}`);
  }

  // --- Projects (Phase 10) ---
  listProjects(): Promise<Project[]> {
    return this.get("/v1/projects");
  }
  getProject(id: string): Promise<Project> {
    return this.get(`/v1/projects/${id}`);
  }
  createProject(body: { name: string; description?: string; locale_default?: RegionCode }): Promise<Project> {
    return this.post("/v1/projects", body);
  }
  updateProject(id: string, body: Partial<{ name: string; description: string; locale_default: RegionCode; status: ProjectStatus }>): Promise<Project> {
    return this.patch(`/v1/projects/${id}`, body);
  }
  deleteProject(id: string): Promise<void> {
    return this.del(`/v1/projects/${id}`).then(() => undefined);
  }

  // --- Pivot (Phase 7) ---
  getPivotFields(projectId: string): Promise<PivotFields> {
    return this.get(`/v1/pivot/fields?project_id=${encodeURIComponent(projectId)}`);
  }
  pivotQuery(req: PivotQueryRequest): Promise<PivotResult> {
    return this.post("/v1/pivot/query", req);
  }

  // --- Dashboards (Phase 8) ---
  listDashboards(projectId: string): Promise<Dashboard[]> {
    return this.get(`/v1/dashboards?project_id=${encodeURIComponent(projectId)}`);
  }
  createDashboard(projectId: string, name: string): Promise<Dashboard> {
    return this.post("/v1/dashboards", { project_id: projectId, name });
  }
  getDashboard(id: string): Promise<Dashboard> {
    return this.get(`/v1/dashboards/${id}`);
  }
  addTile(dashboardId: string, title: string, spec: TileSpec): Promise<Dashboard> {
    return this.post(`/v1/dashboards/${dashboardId}/tiles`, { title, spec });
  }
  removeTile(dashboardId: string, tileId: string): Promise<Dashboard> {
    return this.del(`/v1/dashboards/${dashboardId}/tiles/${tileId}`) as Promise<Dashboard>;
  }
  runDashboard(id: string): Promise<DashboardRun> {
    return this.post(`/v1/dashboards/${id}/run`, {});
  }
  shareDashboard(id: string): Promise<Dashboard> {
    return this.post(`/v1/dashboards/${id}/share`, {});
  }
  deleteDashboard(id: string): Promise<void> {
    return this.del(`/v1/dashboards/${id}`).then(() => undefined);
  }

  // --- Agent-led onboarding (Phase 10) ---
  startIngestSession(datasetId: string, llm?: string): Promise<SessionResponse> {
    return this.post("/v1/ingest/sessions", { dataset_id: datasetId, llm });
  }
  replyToIngest(sessionId: string, body: IngestReply): Promise<SessionResponse> {
    return this.post(`/v1/ingest/sessions/${sessionId}/reply`, body);
  }
  getIngestSession(sessionId: string): Promise<SessionResponse> {
    return this.get(`/v1/ingest/sessions/${sessionId}`);
  }

  // --- Edges ---
  listApprovedEdges(projectId?: string): Promise<GraphEdge[]> {
    return this.get(`/v1/edges${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`);
  }

  listEdgeProposals(projectId?: string): Promise<GraphEdge[]> {
    return this.get(`/v1/edges/proposals${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`);
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
  listCubeSchemas(projectId?: string): Promise<CubeSchemaSummary[]> {
    return this.get(`/v1/cube/schemas${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`);
  }

  getCubeSchemaJson(datasetId: string): Promise<CubeSchemaFull> {
    return this.get(`/v1/cube/schemas/${datasetId}/json`);
  }

  /** Returns raw Cube .js text (Content-Type: application/javascript) */
  async getCubeSchemaJs(datasetId: string): Promise<string> {
    const headers = await this.authHeaders();
    const res = await fetch(`${this.baseUrl}/v1/cube/schemas/${datasetId}.js`, {
      headers,
    });
    if (!res.ok) throw new Error(`GET cube/.js -> ${res.status}`);
    return res.text();
  }

  /** Publish a project's (or the tenant's) Cube model to GCS for the Cube service. */
  syncCubeModel(projectId?: string): Promise<CubeSyncResult> {
    return this.post(`/v1/cube/sync${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`, {});
  }

  /** Ask the agent swarm a natural-language question, scoped to a project. */
  chat(question: string, opts: { datasetIds?: string[]; llm?: string; projectId?: string } = {}): Promise<ChatAnswer> {
    return this.post("/v1/chat", {
      question,
      dataset_ids: opts.datasetIds ?? [],
      llm: opts.llm,
      project_id: opts.projectId,
    });
  }

  /** Available LLM "brains" for the dropdown. */
  listLlmOptions(): Promise<LlmOption[]> {
    return this.get("/v1/llm/options");
  }

  // --- Phase 11: PhD differentiators ---

  /** Column-level lineage trace for a cube field. */
  getLineage(projectId: string, field: string): Promise<LineageTrace> {
    return this.get(
      `/v1/lineage?project_id=${encodeURIComponent(projectId)}&field=${encodeURIComponent(field)}`,
    );
  }

  /** Metric registry — every governed measure + provenance. */
  getMetrics(projectId: string): Promise<MetricRegistry> {
    return this.get(`/v1/metrics?project_id=${encodeURIComponent(projectId)}`);
  }

  /** Reproducible Jupyter notebook (.ipynb JSON) for a governed query. */
  exportNotebook(req: NotebookRequest): Promise<Record<string, unknown>> {
    return this.post("/v1/notebook", req);
  }

  /** Cost preview — estimated scan size before running. */
  estimateCost(req: PivotQueryRequest): Promise<CostEstimate> {
    return this.post("/v1/pivot/estimate", req);
  }

  // Cohorts (set algebra)
  listCohorts(projectId: string): Promise<Segment[]> {
    return this.get(`/v1/cohorts?project_id=${encodeURIComponent(projectId)}`);
  }
  createCohort(body: {
    project_id: string;
    name: string;
    cube: string;
    filters: Array<{ member: string; operator: string; values: string[] }>;
  }): Promise<Segment> {
    return this.post("/v1/cohorts", body);
  }
  deleteCohort(id: string): Promise<void> {
    return this.del(`/v1/cohorts/${id}`).then(() => undefined);
  }
  resolveCohort(req: CohortResolveRequest): Promise<CohortResolveResult> {
    return this.post("/v1/cohorts/resolve", req);
  }

  // Snapshots + diff
  captureSnapshot(projectId: string, spec: TileSpec, label = ""): Promise<Snapshot> {
    return this.post("/v1/snapshots", { project_id: projectId, label, spec });
  }
  listSnapshots(projectId: string): Promise<SnapshotMeta[]> {
    return this.get(`/v1/snapshots?project_id=${encodeURIComponent(projectId)}`);
  }
  deleteSnapshot(id: string): Promise<void> {
    return this.del(`/v1/snapshots/${id}`).then(() => undefined);
  }
  diffSnapshots(a: string, b: string): Promise<SnapshotDiff> {
    return this.post("/v1/snapshots/diff", { a, b });
  }

  /** On-demand assumption re-check for a tile spec. */
  checkAssumptions(projectId: string, spec: TileSpec): Promise<AssumptionReport> {
    return this.post("/v1/assumptions/check", { project_id: projectId, spec });
  }
}

export interface LlmOption {
  id: string;
  label: string;
  provider: string;
  model: string;
  available: boolean;
  default: boolean;
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
  /** Phase 9: specialist (stats/maths) result envelope, when an analysis ran. */
  analysis: AnalysisResult | null;
}

export interface AnalysisResult {
  method_used: string;
  result: Record<string, unknown>;
  assumptions_checked: string[];
  confidence: number;
  caveats: string[];
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

// ===================== Phase 10: Projects + Onboarding =====================

export type ProjectStatus = "draft" | "active" | "archived";

export interface ProjectMember {
  email: string;
  role: "owner" | "admin" | "viewer";
}

export interface Project {
  id: string;
  tenant_id: string;
  brand: string;
  name: string;
  description: string;
  owner_email: string;
  members: ProjectMember[];
  locale_default: RegionCode;
  status: ProjectStatus;
  dataset_ids: string[];
  created_at: string;
  updated_at: string;
}

export type ColumnRole = "dimension" | "measure" | "time" | "identifier" | "ignore";
export type MeasureAgg = "sum" | "avg" | "count" | "min" | "max" | "count_distinct";

export interface ColumnSemantics {
  column: string;
  role: ColumnRole;
  business_meaning?: string;
  is_revenue?: boolean;
  is_cost?: boolean;
  measure_aggregation?: MeasureAgg | null;
  date_granularity?: string | null;
  join_key?: boolean;
  display_title?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
}

export type InterviewStep =
  | "project_name" | "grain" | "draft_review" | "joins" | "confirm" | "done";
export type QuestionType = "free_text" | "single_choice" | "confirm" | "draft_review";

export interface AgentQuestion {
  step: InterviewStep;
  prompt: string;
  question_type: QuestionType;
  choices: string[];
  target_column: string | null;
  draft: ColumnSemantics[];
  context: Record<string, unknown>;
}

export interface TranscriptEntry {
  role: "agent" | "user";
  step: InterviewStep;
  text: string;
  ts: string;
}

export interface IngestSession {
  id: string;
  tenant_id: string;
  project_id: string | null;
  dataset_id: string;
  status: "in_progress" | "completed" | "abandoned";
  current_step: InterviewStep;
  columns_remaining: string[];
  current_column: string | null;
  semantics: Record<string, ColumnSemantics>;
  grain_description: string | null;
  confirmed_join_edge_ids: string[];
  transcript: TranscriptEntry[];
  created_at: string;
  updated_at: string;
}

export interface CompletionResult {
  project_id: string | null;
  cube_synced: boolean;
  columns_confirmed: number;
  joins_approved: number;
}

export interface SessionResponse {
  session: IngestSession;
  agent_message: AgentQuestion | null;
  completion: CompletionResult | null;
}

export interface IngestReply {
  answer?: string;
  semantics_patch?: ColumnSemantics[];
  confirmed_edge_ids?: string[];
  llm?: string;
}

// ---- robust ingestion ----

export interface ColumnSpec {
  name: string;
  bq_type: string;
  source_format?: string | null;
}

export interface PreviewColumn {
  name: string;
  inferred_bq_type: string;
  inferred_format: string | null;
  sample_values: string[];
  nullable: boolean;
}

export interface PreviewResponse {
  dataset_id: string;
  encoding: string;
  delimiter: string;
  has_header: boolean;
  columns: PreviewColumn[];
  row_sample: string[][];
  truncated: boolean;
}

export interface IngestError {
  stage: "upload" | "preview" | "load" | "profile" | "discover";
  reason: string;
  message: string;
  hint: string | null;
  sample_bad_rows: string[];
}

export interface DeleteDatasetResult {
  dataset_id: string;
  deleted: boolean;
  edges: number;
  bq_table: boolean;
  gcs_blob: boolean;
  firestore: boolean;
  cube_resynced: boolean;
}

// ===================== Phase 7: Pivot =====================

export interface PivotField {
  name: string;
  title: string;
  type: string;
  revenue: boolean;
}

export interface PivotFields {
  measures: PivotField[];
  dimensions: PivotField[];
  time_dimensions: PivotField[];
}

export interface PivotQueryRequest {
  project_id: string;
  measures?: string[];
  dimensions?: string[];
  time_dimension?: string | null;
  granularity?: string | null;
  filters?: Array<{ member: string; operator: string; values: string[] }>;
  order?: Record<string, "asc" | "desc">;
  limit?: number | null;
}

export interface PivotResult {
  columns: string[];
  rows: unknown[][];
  cube_query: Record<string, unknown>;
}

// ===================== Phase 8: Dashboards =====================

export interface TileSpec {
  measures?: string[];
  dimensions?: string[];
  time_dimension?: string | null;
  granularity?: string | null;
  filters?: Array<{ member: string; operator: string; values: string[] }>;
  order?: Record<string, "asc" | "desc">;
  limit?: number | null;
  chart_type?: string;
}

export interface Tile {
  id: string;
  title: string;
  spec: TileSpec;
}

export interface Dashboard {
  id: string;
  tenant_id: string;
  project_id: string;
  name: string;
  created_by: string;
  tiles: Tile[];
  share_token: string | null;
  created_at: string;
  updated_at: string;
}

export interface TileResult {
  tile_id: string;
  title: string;
  spec: TileSpec;
  columns: string[];
  rows: unknown[][];
  chart_type: string;
  error: string | null;
}

export interface DashboardRun {
  dashboard_id: string;
  name: string;
  tiles: TileResult[];
}

// ===================== Phase 11: PhD differentiators =====================

export interface SourceColumn {
  column: string;
  role: string | null;
  business_meaning: string | null;
  confirmed_by: string | null;
  confirmed_at: string | null;
}

export interface JoinProvenance {
  to_cube: string;
  from_edge_id: string;
  sql_clause: string;
}

export interface LineageTrace {
  field: string;
  kind: string;
  aggregation: string | null;
  revenue_touching: boolean;
  cube: string;
  dataset_id: string;
  dataset_label: string;
  bq_table: string | null;
  locale: string;
  sql: string | null;
  source_columns: SourceColumn[];
  joins: JoinProvenance[];
}

export interface MetricEntry {
  name: string;
  title: string;
  aggregation: string;
  revenue_touching: boolean;
  definition_sql: string | null;
  cube: string;
  dataset_id: string;
  dataset_label: string;
  owner: string | null;
  effective_at: string | null;
}

export interface MetricRegistry {
  project_id: string;
  metrics: MetricEntry[];
}

export interface NotebookRequest {
  project_id: string;
  title?: string;
  measures?: string[];
  dimensions?: string[];
  time_dimension?: string | null;
  granularity?: string | null;
  filters?: Array<{ member: string; operator: string; values: string[] }>;
  order?: Record<string, "asc" | "desc">;
  limit?: number | null;
}

export interface CostEstimate {
  estimated_bytes: number;
  estimated_gb: number;
  estimated_usd: number;
  threshold_gb: number;
  exceeds_threshold: boolean;
  per_cube: Array<{
    cube: string;
    table: string;
    referenced_columns: string[];
    total_columns: number;
    bytes_estimate: number;
  }>;
  method: string;
}

export interface Segment {
  id: string;
  tenant_id: string;
  project_id: string;
  name: string;
  cube: string;
  filters: Array<{ member: string; operator: string; values: string[] }>;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface CohortResolveRequest {
  project_id: string;
  expression: string;
  measures?: string[];
  dimensions?: string[];
  time_dimension?: string | null;
  granularity?: string | null;
  order?: Record<string, "asc" | "desc">;
  limit?: number | null;
}

export interface CohortResolveResult {
  columns: string[];
  rows: unknown[][];
  cube_query: Record<string, unknown>;
  filter_tree: Record<string, unknown>;
  segments_used: string[];
}

export interface Snapshot {
  id: string;
  tenant_id: string;
  project_id: string;
  label: string;
  spec: TileSpec;
  columns: string[];
  rows: unknown[][];
  captured_at: string;
}

export interface SnapshotMeta {
  id: string;
  label: string;
  captured_at: string;
  spec: TileSpec;
  row_count: number;
}

export interface SnapshotDiff {
  baseline: { id: string; label: string; captured_at: string };
  comparison: { id: string; label: string; captured_at: string };
  diff: {
    dimensions: string[];
    measures: string[];
    added: string[][];
    removed: string[][];
    changed: Array<{
      key: string[];
      deltas: Record<string, { from: number; to: number; delta: number; pct: number | null }>;
    }>;
    summary: { added: number; removed: number; changed: number };
  };
}

export interface AssumptionWarning {
  level: "warn" | "info";
  code: string;
  message: string;
}

export interface AssumptionReport {
  warnings: AssumptionWarning[];
  ok: boolean;
}
