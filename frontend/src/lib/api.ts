import {
  ActiveThreadInfo,
  Asset,
  AssetSummary,
  AssetVerifyRequest,
  AssetVerifyResponse,
  BaselineException,
  BatchScanResponse,
  DetectionRule,
  EmpireModuleSummary,
  EngineDiagnosticItem,
  EngineHealthResponse,
  EngineTestResult,
  EngineUpdateCheckResult,
  Finding,
  OverviewMetrics,
  PaginatedResponse,
  ReportItem,
  ScanBatchCreate,
  ScanBatchRead,
  ScanJob,
  SecurityAlertItem,
  SystemResourcesInfo,
  ThreatIntelItem,
  TrackCurrentResponse,
  ChecklistCategory,
  ChecklistResultState,
  AutomationType,
  ChecklistDefinition,
  ChecklistResult,
  ChecklistAssessmentRun,
  ChecklistCoverageSummary,
} from './types';


export type {
  ActiveThreadInfo,
  BatchScanResponse,
  EngineDiagnosticItem,
  EngineHealthResponse,
  EngineTestResult,
  EngineUpdateCheckResult,
  PaginatedResponse,
  ScanBatchCreate,
  ScanBatchRead,
  SystemResourcesInfo,
  TrackCurrentResponse,
};


export interface EngineArtifact {
  id: string; asset_id: string; kind: string; filename: string; sha256: string; size_bytes: number;
  uploaded_by: string; uploaded_at: string; source_note?: string | null;
}

export interface WorkerReadiness { ready: boolean; fresh_workers: number; known_workers: number; reason: string | null }

export interface ExecutionLaunch {
  execution_id: string; batch_id: string | null; scan_id: string; status: string; queued_at: string;
  planned_executions: number; tracker: string; replayed: boolean; worker: WorkerReadiness;
}

export interface ExecutionAttemptInfo {
  attempt_id: string; attempt_no: number; fencing_token: number; worker_id: string; phase: string; status: string;
  started_at: string | null; heartbeat_at: string | null; finished_at: string | null; duration_ms: number | null;
  exit_code: number | null; error_class: string | null; error_detail: string | null;
}

export interface ExecutionDetail {
  execution_id: string; batch_id: string | null; scan_id: string; asset_id: string; engine_id: string;
  driver: string | null; driver_version: string | null; execution_mode: string;
  input: { artifact_id: string | null; sha256: string | null; filename?: string; url?: string };
  rules: { source: string | null; version: string | null; digest: string | null };
  trigger: string; actor_id: string | null;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'timed_out' | 'cancelled' | 'skipped' | 'unavailable';
  status_reason: string | null; error_class: string | null; finding_count: number | null; summary: Record<string, any>;
  output: { sha256: string | null; available: boolean }; worker_id: string | null;
  timestamps_utc: { queued_at: string | null; started_at: string | null; observed_at: string | null; finished_at: string | null };
  duration_ms: number | null; display_timezone: string;
  attempts?: ExecutionAttemptInfo[]; finding_ids?: string[]; worker?: WorkerReadiness;
}

export interface AdvisorySnapshotInfo {
  id: string; source: string; version_label: string; digest: string; record_count: number; ecosystems: string[];
  data_modified_max: string | null; is_active: boolean; imported_by: string; imported_at: string; age_hours: number;
}

const API_BASE = '/api/v1';
const CSRF_COOKIE = 'noospire_csrf';
const CSRF_HEADER = 'X-CSRF-Token';

/**
 * Error kinds the UI renders distinctly. Never mapped to success.
 * - unauthenticated / forbidden / not_found / validation: real FastAPI answers (status kept)
 * - upstream_unreachable / upstream_timeout: gateway could not reach FastAPI (502 / 503)
 * - misrouted: an API path answered with HTML (routing misconfiguration)
 * - network: the browser could not reach the gateway at all
 */
export type ApiErrorKind =
  | 'unauthenticated'
  | 'forbidden'
  | 'not_found'
  | 'conflict'
  | 'validation'
  | 'upstream_unreachable'
  | 'upstream_timeout'
  | 'misrouted'
  | 'server'
  | 'network'
  | 'access_denied'; // Cloudflare Access at the gateway (missing/expired token) — sign in again via Access

export type EngineName = 'sbom' | 'tls_health' | 'public_web';

export interface RunRequestBody {
  selection: { kind: 'all' | 'assets' | 'module'; asset_ids?: string[]; module?: string };
  engines?: EngineName[];
  profile?: 'light' | 'slow';
}

export interface PlanSummary {
  assets_in_scope: number;
  pairs: number;
  queue: number;
  defer: number;
  skip: number;
  reasons: Record<string, number>;
  estimated_work_seconds: number;
  backlog_seconds_before: number;
  slots: number;
  estimated_finish_at: string;
  fits_window: boolean;
  deferred_resume_at: string | null;
  window_seconds: number;
  theoretical_hourly_capacity: number | null;
}

export interface RunPlan {
  trigger: string;
  profile: string;
  engines: EngineName[];
  planned_at: string;
  summary: PlanSummary;
  items: Array<{ asset_id: string; asset_name: string; module: string | null; engine: EngineName; decision: 'queue' | 'defer' | 'skip';
    reason_code: string | null; reason: string | null; lane: string; available_at: string | null }>;
}

export interface RunStatus {
  batch_id: string;
  name: string;
  accepted_at: string;
  trigger: string;
  correlation_id: string | null;
  plan_summary: PlanSummary | null;
  by_status: Record<string, number>;
  finished: boolean;
  executions: Array<{ execution_id: string; asset_id: string; engine_id: string; status: string; lane: string;
    status_reason: string | null; plan_note: string | null; finding_count: number | null; queued_at: string; finished_at: string | null }>;
  tracker: string;
  replayed: boolean;
}

export interface MonitorSchedule {
  id: string;
  name: string;
  selection: RunRequestBody['selection'];
  engines: EngineName[];
  profile: 'light' | 'slow';
  interval_minutes: number;
  max_workers: number;
  is_active: boolean;
  revision: number;
  next_run_at: string | null;
  last_slot_at: string | null;
  last_run_at: string | null;
  last_batch_id: string | null;
  last_full_success_at: string | null;
  latest_result: { status: string | null; at: string | null; batch_id: string | null };
  running: boolean;
  pending_catchup: boolean;
  missed_slots: number;
  backlog: number;
  estimated_drain_at: string | null;
  overdue_reason: string | null;
  theoretical_hourly_capacity: number;
}

export interface ScheduleSlotInfo {
  id: string;
  slot_at: string;
  kind: 'scheduled' | 'catchup';
  status: string;
  claimed_by: string;
  launched_at: string | null;
  finished_at: string | null;
  batch_id: string | null;
  missed_before: number;
  coalesced_slots: number;
  reason: string | null;
  plan_summary: PlanSummary | Record<string, never>;
  result_summary: { by_status?: Record<string, number>; long_lane_pending?: number };
  correlation_id: string | null;
}

export interface CapacityInfo {
  emergency_stop_active: boolean;
  max_running_executions: number;
  per_host_hourly_quota: number;
  per_host_egress_bytes_hourly: number;
  updated_by: string | null;
  updated_at: string | null;
}

export interface EngineOps {
  last_success_at: string | null;
  latest_result: { status: string; at: string; execution_id: string } | null;
  staleness_seconds: number | null;
  stale: boolean;
  queued: number;
  running: number;
  queue_age_seconds: number;
}

export interface OperationsOverview {
  server_time: string;
  display_timezone: string;
  event_cursor: number;
  schedules: MonitorSchedule[];
  schedules_visible: boolean;
  engines: Record<EngineName, EngineOps>;
  stale_threshold_seconds: number;
  overdue: { queued_over_10m: number; running_lease_expired: number };
  errors_24h: { parse_errors: number; dead_letters: number };
  evidence: { newest_observation_at: string | null; age_seconds: number | null };
  feed: { source: string; version: string; digest: string; imported_at: string; age_hours: number } | null;
  workers: Array<{ worker_id: string; last_seen_at: string; age_seconds: number; state: string; active_executions: number; throttle_reason: string | null }>;
  workers_online: number;
  capacity: CapacityInfo;
}

export interface DashboardSummary {
  as_of: string;
  display_timezone: string;
  data_state: 'ok' | 'partial' | 'unknown';
  data_state_reasons: string[];
  last_real_data_at: string | null;
  window: { days: number; from_utc: string; to_utc: string; ict_days: string[] };
  services: { counts: Record<'up' | 'degraded' | 'down' | 'unknown' | 'stale', number>;
    items: Array<{ asset_id: string; name: string; module: string; status: string; observed_at: string | null; execution_id: string | null; stale: boolean; reason: string | null }> };
  workers: { online: number; total: number; throttled: number };
  risk: { open_by_severity: Record<string, number>; open_total: number };
  findings_per_day: Array<{ day: string; new: number; reopened: number; fixed: number }>;
  new_today: number;
}

export interface ModuleCard {
  module: string;
  assets: number;
  coverage_24h: { covered: number; total: number };
  service_health: Record<'up' | 'degraded' | 'down' | 'unknown', number>;
  open_findings: Record<string, number>;
  open_total: number;
  next_scheduled_run_at: string | null;
  links: { assets: string; findings: string; runs: string };
}

export interface ModuleHub {
  as_of: string;
  modules: ModuleCard[];
  assets_in_scope: number;
  assets_in_modules: number;
  assets_unassigned: number;
  scope: 'estate' | 'granted';
}

export interface FindingHistory {
  finding_id: string;
  title: string;
  status: string;
  severity: string;
  asset: { id: string; name: string | null; module: string | null };
  first_seen_at: string;
  last_seen_at: string;
  last_verified_at: string | null;
  source: { engine: string; driver?: string; driver_version?: string };
  confidence: string;
  owner: string | null;
  assignee: string | null;
  changes: Array<{ field: string; old: string | null; new: string | null; actor: string; reason: string | null; execution_id: string | null; at: string }>;
  observations: Array<{ execution_id: string; batch_id: string | null; outcome: string; status_before: string | null; status_after: string | null; reason: string | null; output_sha256: string | null; rule_digest: string | null; observed_at: string }>;
}

export interface RunDiffItem {
  finding_id: string; title: string; severity: string; asset_id: string; engine_id: string; outcome: string;
  status_before: string | null; status_after: string | null; reason: string | null; execution_id: string;
}

export interface RunsOfDay {
  day_ict: string;
  runs: Array<{ batch_id: string; name: string | null; accepted_at: string | null; trigger: string | null; correlation_id: string | null;
    by_status: Record<string, number>; finished: boolean; diff: Record<string, number>;
    skip_or_fail: Array<{ execution_id: string; engine_id: string; status: string; reason: string | null }> }>;
  totals: Record<string, number>;
}

export interface NotificationItem {
  id: string; kind: string; severity: string; title: string; message: string; object_type: string;
  object_id: string | null; link: string; created_at: string; read: boolean;
}

export interface ReportSnapshotInfo {
  id: string; title: string; scope: { kind: string; asset_ids: string[]; batch_id: string | null };
  template_version: string; snapshot_sha256: string; finding_count: number; execution_ids: string[];
  correlation_ids: string[]; previous_snapshot_id: string | null;
  files: Record<'json' | 'html' | 'pdf', { sha256: string; bytes: number }>; created_by: string; generated_at: string;
}

export class ApiError extends Error {
  status: number;
  kind: ApiErrorKind;
  code?: string;
  requestId?: string;
  detail?: any;
  constructor(message: string, status: number, kind: ApiErrorKind, extra: { code?: string; requestId?: string; detail?: any } = {}) {
    super(message);
    this.status = status;
    this.kind = kind;
    this.code = extra.code;
    this.requestId = extra.requestId;
    this.detail = extra.detail;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const m = document.cookie.split('; ').find((c) => c.startsWith(name + '='));
  return m ? decodeURIComponent(m.slice(name.length + 1)) : null;
}

function kindFor(status: number, code?: string): ApiErrorKind {
  if (code === 'UPSTREAM_UNREACHABLE') return 'upstream_unreachable';
  if (code === 'UPSTREAM_TIMEOUT') return 'upstream_timeout';
  if (code === 'MISROUTED') return 'misrouted';
  if (code && code.startsWith('ACCESS_')) return 'access_denied';
  if (status === 401) return 'unauthenticated';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 409) return 'conflict';
  if (status === 422 || status === 400) return 'validation';
  if (status === 502) return 'upstream_unreachable';
  if (status === 503 || status === 504) return 'upstream_timeout';
  return 'server';
}

class ApiClient {
  /** Session lives in an HttpOnly cookie; JS never sees or stores the token. */
  public getToken(): string | null {
    return null;
  }

  public setToken(_token: string): void {
    /* no-op: tokens are never persisted in browser storage */
  }

  private async fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers || {});
    if (options.body !== undefined && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    const method = (options.method || 'GET').toUpperCase();
    if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const csrf = readCookie(CSRF_COOKIE);
      if (csrf) headers.set(CSRF_HEADER, csrf);
    }

    let response: Response;
    try {
      response = await fetch(`${API_BASE}${endpoint}`, { ...options, headers, credentials: 'same-origin' });
    } catch (e: any) {
      throw new ApiError('Network error: the console cannot reach the gateway.', 0, 'network');
    }

    const contentType = response.headers.get('content-type') || '';
    const requestId = response.headers.get('x-request-id') || undefined;

    if (contentType.includes('text/html')) {
      throw new ApiError('API route answered with HTML (misrouted).', response.status || 502, 'misrouted', { requestId });
    }

    if (!response.ok) {
      let body: any = null;
      try {
        body = await response.json();
      } catch (_) {}
      const detail = body?.detail;
      const code = body?.code;
      const msg = typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : `HTTP ${response.status}`;
      const err = new ApiError(msg, response.status, kindFor(response.status, code), {
        code,
        requestId: body?.request_id || requestId,
        detail,
      });
      if (err.kind === 'unauthenticated' && typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        window.dispatchEvent(new CustomEvent('noospire:unauthenticated'));
      }
      throw err;
    }

    if (response.status === 204) {
      return {} as T;
    }
    return await response.json();
  }

  /** Low-level helper for pages that need a call not wrapped below (keeps auth + CSRF + errors). */
  public async request<T = any>(endpoint: string, options: RequestInit = {}): Promise<T> {
    return this.fetchJson<T>(endpoint, options);
  }

  // Metrics & Charts

  public async getOverviewMetrics(): Promise<OverviewMetrics> {
    return this.fetchJson<OverviewMetrics>('/metrics/overview');
  }

  public async getSeverityDist(): Promise<Record<string, number>> {
    return this.fetchJson<Record<string, number>>('/metrics/severity-distribution');
  }

  public async getVulnerabilityTrend(days: number = 14): Promise<Array<{ date: string; new_findings: number; fixed_findings: number; reopened_findings: number }>> {
    return this.fetchJson(`/metrics/charts/vulnerability-trend?days=${days}`);
  }

  public async getModuleRiskChart(): Promise<Array<{ module_key: string; module_name: string; risk_score: number; critical_count: number; high_count: number; medium_count: number; total_findings: number }>> {
    return this.fetchJson('/metrics/charts/module-risk');
  }

  public async getCoverageChart(): Promise<{ total_targets: number; assessed_today: number; pending_assessment: number; coverage_percentage: number }> {
    return this.fetchJson('/metrics/charts/coverage');
  }

  public async getRiskTrendChart(days: number = 14): Promise<Array<{ date: string; risk_score: number; active_findings: number }>> {
    return this.fetchJson(`/metrics/charts/risk-trend?days=${days}`);
  }

  public async getScannerPerformance(): Promise<Array<{ engine: string; total_executions: number; completed: number; failed: number; success_rate: number; avg_duration_seconds: number }>> {
    return this.fetchJson('/metrics/charts/scanner-performance');
  }

  public async getIntelligenceActivity(): Promise<{ total_cves_indexed: number; cisa_kev_active: number; high_epss_exploitable: number; detection_rules_active: number; last_sync: string }> {
    return this.fetchJson('/metrics/charts/intelligence-activity');
  }

  public async getRemediationProgress(): Promise<Record<string, number>> {
    return this.fetchJson('/metrics/charts/remediation-progress');
  }

  // Empire Modules View
  public async getEmpireModules(): Promise<EmpireModuleSummary[]> {
    return this.fetchJson<EmpireModuleSummary[]>('/empire-modules');
  }

  // Assets & Target Management
  public async listAssets(params?: {
    empire_module?: string;
    page?: number;
    size?: number;
    search?: string;
    status?: string;
    assessment_eligible?: boolean;
  } | string): Promise<{ items: Asset[]; total: number }> {
    if (typeof params === 'string') {
      const empireModule = params;
      const url = empireModule && empireModule !== 'ALL' ? `/assets?empire_module=${empireModule}&size=200` : '/assets?size=200';
      return this.fetchJson<{ items: Asset[]; total: number }>(url);
    }
    const query = new URLSearchParams();
    query.set('size', String(params?.size || 200));
    if (params?.page) query.set('page', String(params.page));
    if (params?.empire_module && params.empire_module !== 'ALL') query.set('empire_module', params.empire_module);
    if (params?.search) query.set('search', params.search);
    if (params?.status && params.status !== 'ALL') query.set('status', params.status);
    if (params?.assessment_eligible !== undefined) query.set('assessment_eligible', String(params.assessment_eligible));
    return this.fetchJson<{ items: Asset[]; total: number }>(`/assets?${query.toString()}`);
  }

  /** Fetch every inventory page; never label the first 200 rows as the whole estate. */
  public async listAllAssets(eligibleOnly = false): Promise<Asset[]> {
    const items: Asset[] = [];
    for (let page = 1; page <= 1000; page++) {
      const result = await this.listAssets({ page, size: 200, ...(eligibleOnly ? { assessment_eligible: true } : {}) });
      items.push(...result.items);
      if (items.length >= result.total) return items;
      if (result.items.length === 0) throw new Error('Inventory changed while loading. Refresh to reconcile the current selection.');
    }
    throw new Error('Inventory is too large for this view. Narrow the server selection.');
  }

  public async createAsset(data: Partial<Asset>): Promise<Asset> {
    return this.fetchJson<Asset>('/assets', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async bulkImportAssets(data: { import_type?: string; raw_content?: string; items?: any[] }): Promise<{ imported_count: number; skipped_duplicates: number; errors: string[]; imported_assets: Asset[] }> {
    return this.fetchJson('/assets/bulk-import', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async getAsset(assetId: string): Promise<Asset> {
    return this.fetchJson<Asset>(`/assets/${assetId}`);
  }

  public async getAssetSummary(assetId: string): Promise<AssetSummary> {
    return this.fetchJson<AssetSummary>(`/assets/${assetId}/summary`);
  }

  public async verifyAsset(
    assetId: string,
    options?: AssetVerifyRequest | string
  ): Promise<AssetVerifyResponse> {
    const payload: AssetVerifyRequest =
      typeof options === 'string'
        ? { verification_type: options as any, allow_private: true }
        : { verification_type: 'ADMIN_OVERRIDE', allow_private: true, ...options };

    return this.fetchJson<AssetVerifyResponse>(`/assets/${assetId}/verify`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  public async deleteAsset(assetId: string): Promise<void> {
    await this.fetchJson(`/assets/${assetId}`, { method: 'DELETE' });
  }

  // Scans & Live Tracking
  public async listScans(): Promise<{ items: ScanJob[]; total: number }> {
    return this.fetchJson<{ items: ScanJob[]; total: number }>('/scans?size=100');
  }

  public async dispatchScan(data: {
    asset_id: string;
    engine: string;
    profile: string;
    allow_private_targets?: boolean;
    timeout_seconds?: number;
  }): Promise<ScanJob> {
    return this.fetchJson<ScanJob>('/scans', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async getScan(scanId: string): Promise<ScanJob> {
    return this.fetchJson<ScanJob>(`/scans/${scanId}`);
  }

  public async cancelScan(scanId: string): Promise<any> {
    return this.fetchJson(`/scans/${scanId}/cancel`, { method: 'POST' });
  }

  public async getScanLogs(scanId: string, size: number = 500): Promise<Array<{ timestamp: string; level: string; message: string; source: string }>> {
    const data = await this.fetchJson<any>(`/scans/${scanId}/logs?size=${size}`);
    return Array.isArray(data) ? data : (data.items || []);
  }

  public async getScanLogPage(scanId: string, page = 1): Promise<{ items: Array<{ timestamp: string; level: string; message: string; source: string }>; total: number; page: number; pages: number }> {
    return this.fetchJson(`/scans/${scanId}/logs?size=100&page=${page}`);
  }

  public async getScanEvents(scanId: string, afterId: number = 0, limit: number = 200): Promise<{
    items: Array<{
      id: number;
      scan_id?: string;
      timestamp: string;
      level: string;
      message: string;
      source: string;
      event_type?: string;
      details?: Record<string, any>;
    }>;
    total: number;
  }> {
    return this.fetchJson(`/scans/${scanId}/events?after_id=${afterId}&limit=${limit}`);
  }

  // Batch Scans & Resource Optimization
  public async createBatchScan(data: ScanBatchCreate): Promise<BatchScanResponse> {
    return this.fetchJson<BatchScanResponse>('/scans/batch', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async listBatches(page: number = 1, size: number = 20): Promise<PaginatedResponse<ScanBatchRead>> {
    return this.fetchJson<PaginatedResponse<ScanBatchRead>>(`/scans/batches?page=${page}&size=${size}`);
  }

  public async getBatch(batchId: string): Promise<ScanBatchRead> {
    return this.fetchJson<ScanBatchRead>(`/scans/batch/${batchId}`);
  }

  public async cancelBatch(batchId: string): Promise<{ batch_id: string; status: string; cancelled_count: number }> {
    return this.fetchJson<{ batch_id: string; status: string; cancelled_count: number }>(`/scans/batch/${batchId}/cancel`, {
      method: 'POST',
    });
  }

  public async stopAllScans(): Promise<{ status: string; halted_count: number }> {
    return this.fetchJson<{ status: string; halted_count: number }>('/scans/stop-all', {
      method: 'POST',
    });
  }

  public async launchUltraScan(data?: {
    scope?: string | string[];
    profile?: string;
    engines?: string[];
    idempotency_key?: string;
    initiator?: string;
  }): Promise<{
    batch_id: string;
    name: string;
    status: string;
    accounted_inventory_rows: number;
    independent_execution_targets: number;
    engine_executions_count: number;
    shared_alias_count: number;
    excluded_count: number;
    tracker_link: string;
    snapshot_time: string;
    policy_revision: string;
    idempotency_recovered: boolean;
    message: string;
  }> {
    const headers: Record<string, string> = {};
    if (data?.idempotency_key) {
      headers['Idempotency-Key'] = data.idempotency_key;
    }
    return this.fetchJson('/scans/ultra', {
      method: 'POST',
      headers,
      body: JSON.stringify(data || { scope: 'ALL' }),
    });
  }

  public async getUltraScanFixture(): Promise<{
    accounted_inventory_rows: number;
    independent_execution_targets: number;
    engine_executions_count: number;
    shared_alias_count: number;
    excluded_count: number;
    policy_revision: string;
    items: any[];
    shared_result_links: any[];
    explained_exclusions: any[];
  }> {
    return this.fetchJson('/scans/ultra/fixture-379');
  }

  public async getTrackCurrent(): Promise<TrackCurrentResponse> {
    return this.fetchJson<TrackCurrentResponse>('/scans/trackcurrent');
  }

  // Findings & Remediation
  public async listFindings(filters?: { assetId?: string; module?: string; severity?: string; status?: string;
    statusGroup?: string; outcome?: string; day?: string; scanId?: string; executionId?: string }): Promise<{ items: Finding[]; total: number }> {
    const params = new URLSearchParams({ size: '100' });
    if (filters?.assetId) params.append('asset_id', filters.assetId);
    if (filters?.module) params.append('empire_module', filters.module);
    if (filters?.severity) params.append('severity', filters.severity);
    if (filters?.status) params.append('status_filter', filters.status);
    if (filters?.statusGroup) params.append('status_group', filters.statusGroup);
    if (filters?.outcome) params.append('outcome', filters.outcome);
    if (filters?.day) params.append('day', filters.day);
    if (filters?.scanId) params.append('scan_id', filters.scanId);
    if (filters?.executionId) params.append('execution_id', filters.executionId);
    return this.fetchJson<{ items: Finding[]; total: number }>(`/findings?${params.toString()}`);
  }

  public async getFinding(id: string): Promise<Finding> {
    return this.fetchJson<Finding>(`/findings/${id}`);
  }

  public async triageFinding(id: string, status: string, comment?: string, assignee?: string, retestStatus?: string): Promise<Finding> {
    return this.fetchJson<Finding>(`/findings/${id}/triage`, {
      method: 'POST',
      body: JSON.stringify({ status, comment, assignee, retest_status: retestStatus }),
    });
  }

  /** Recheck = queue the same approved defensive control again (Milestone 5). It never marks the
   *  finding fixed by itself; the engine does, only with equivalent new evidence. */
  public async retestFinding(id: string): Promise<{ status?: string; retest_status: string; notes: string; execution_id?: string | null }> {
    const key = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}`;
    const res = await this.recheckFinding(id, key);
    return {
      retest_status: 'RECHECK_QUEUED',
      execution_id: res.execution_id,
      notes: res.note || `Recheck queued as execution ${res.execution_id}. Status changes only when the engine re-evaluates the same input.`,
    };
  }

  // Approved Media Baselines
  public async listBaselines(): Promise<BaselineException[]> {
    return this.fetchJson<BaselineException[]>('/baselines');
  }

  public async createBaseline(data: Partial<BaselineException>): Promise<BaselineException> {
    return this.fetchJson<BaselineException>('/baselines', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Milestone 4: one planner for "run whole system", selections and the hourly schedule
  public async previewPlan(body: RunRequestBody): Promise<RunPlan> {
    return this.fetchJson<RunPlan>('/plans/preview', { method: 'POST', body: JSON.stringify(body) });
  }

  public async launchRun(body: RunRequestBody, idempotencyKey: string): Promise<RunStatus & { plan: RunPlan }> {
    return this.fetchJson('/runs', {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'Idempotency-Key': idempotencyKey },
    });
  }

  public async getRun(batchId: string): Promise<RunStatus> {
    return this.fetchJson<RunStatus>(`/runs/${batchId}`);
  }

  public async listMonitorSchedules(): Promise<{ server_time: string; display_timezone: string; items: MonitorSchedule[] }> {
    return this.fetchJson('/monitor-schedules');
  }

  public async createMonitorSchedule(body: Partial<MonitorSchedule>): Promise<MonitorSchedule> {
    return this.fetchJson<MonitorSchedule>('/monitor-schedules', { method: 'POST', body: JSON.stringify(body) });
  }

  public async updateMonitorSchedule(id: string, body: Partial<MonitorSchedule> & { expected_revision: number }): Promise<MonitorSchedule> {
    return this.fetchJson<MonitorSchedule>(`/monitor-schedules/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
  }

  public async listScheduleSlots(id: string, limit = 24): Promise<ScheduleSlotInfo[]> {
    return this.fetchJson<ScheduleSlotInfo[]>(`/monitor-schedules/${id}/slots?limit=${limit}`);
  }

  public async getCapacity(): Promise<CapacityInfo> {
    return this.fetchJson<CapacityInfo>('/operations/capacity');
  }

  public async putCapacity(body: Omit<CapacityInfo, 'updated_by' | 'updated_at' | 'emergency_stop_active'>): Promise<CapacityInfo> {
    return this.fetchJson<CapacityInfo>('/operations/capacity', { method: 'PUT', body: JSON.stringify(body) });
  }

  public async setEmergencyStop(active: boolean): Promise<CapacityInfo> {
    return this.fetchJson<CapacityInfo>('/operations/emergency-stop', { method: 'PUT', body: JSON.stringify({ active }) });
  }

  public async getOperationsOverview(): Promise<OperationsOverview> {
    return this.fetchJson<OperationsOverview>('/operations/overview');
  }

  // Milestone 5: console screens
  public async getDashboardSummary(days = 7): Promise<DashboardSummary> {
    return this.fetchJson<DashboardSummary>(`/dashboard/summary?days=${days}`);
  }

  public async getModuleHub(): Promise<ModuleHub> {
    return this.fetchJson<ModuleHub>('/modules/hub');
  }

  public async getFindingHistory(id: string): Promise<FindingHistory> {
    return this.fetchJson<FindingHistory>(`/findings/${id}/history`);
  }

  public async recheckFinding(id: string, idempotencyKey: string): Promise<{ execution_id: string | null; batch_id?: string; replayed: boolean; note?: string; tracker?: string }> {
    return this.fetchJson(`/findings/${id}/recheck`, { method: 'POST', headers: { 'Idempotency-Key': idempotencyKey } });
  }

  public async listRunsForDay(day?: string): Promise<RunsOfDay> {
    const q = day ? `?day=${encodeURIComponent(day)}` : '';
    return this.fetchJson<RunsOfDay>(`/runs${q}`);
  }

  public async getRunTree(batchId: string): Promise<any> {
    return this.fetchJson(`/runs/${batchId}/tree`);
  }

  public async getRunDiff(batchId: string): Promise<{ counts: Record<string, number>; items: RunDiffItem[] }> {
    return this.fetchJson(`/runs/${batchId}/diff`);
  }

  public async listHistory(params: Record<string, string | number | undefined>): Promise<any> {
    const q = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => { if (v !== undefined && v !== '') q.set(k, String(v)); });
    return this.fetchJson(`/history?${q.toString()}`);
  }

  public async previewHide(filter: Record<string, any>): Promise<{ would_hide: number; excluded_active: number; note: string }> {
    return this.fetchJson('/history/hide/preview', { method: 'POST', body: JSON.stringify(filter) });
  }

  public async hideHistory(filter: Record<string, any>, reason: string, confirmCount: number): Promise<{ hidden: number }> {
    return this.fetchJson('/history/hide', { method: 'POST', body: JSON.stringify({ ...filter, reason, confirm_count: confirmCount }) });
  }

  public async listNotifications(limit = 30, unreadOnly = false): Promise<{ items: NotificationItem[]; unread: number }> {
    return this.fetchJson(`/notifications?limit=${limit}${unreadOnly ? '&unread_only=true' : ''}`);
  }

  public async readNotification(id: string): Promise<NotificationItem> {
    return this.fetchJson(`/notifications/${id}/read`, { method: 'POST' });
  }

  public async readAllNotifications(): Promise<{ marked: number }> {
    return this.fetchJson('/notifications/read-all', { method: 'POST' });
  }

  public async deleteNotification(id: string): Promise<void> {
    await this.fetchJson(`/notifications/${id}`, { method: 'DELETE' });
  }

  public async listReportSnapshots(): Promise<ReportSnapshotInfo[]> {
    return this.fetchJson<ReportSnapshotInfo[]>('/report-snapshots');
  }

  public async createReportSnapshot(body: { title: string; asset_ids?: string[]; batch_id?: string; days?: number }): Promise<ReportSnapshotInfo> {
    return this.fetchJson<ReportSnapshotInfo>('/report-snapshots', { method: 'POST', body: JSON.stringify(body) });
  }

  public reportSnapshotUrl(id: string, format: 'pdf' | 'html' | 'json', inline = false): string {
    return `${API_BASE}/report-snapshots/${id}/download?format=${format}${inline ? '&inline=true' : ''}`;
  }

  public async getOperationsMetrics(hours = 24): Promise<any> {
    return this.fetchJson(`/operations/metrics?hours=${hours}`);
  }

  // Alerts & Notifications
  public async listAlerts(): Promise<SecurityAlertItem[]> {
    return this.fetchJson<SecurityAlertItem[]>('/alerts');
  }

  public async markAlertRead(alertId: string): Promise<any> {
    return this.fetchJson(`/alerts/${alertId}/read`, { method: 'POST' });
  }

  public async markAllAlertsRead(): Promise<any> {
    return this.fetchJson('/alerts/read-all', { method: 'POST' });
  }


  // Threat Intel (contract: /threat-intel/*; the former /intel/* routes never existed on the server)
  public async getIntelStatus(): Promise<any> {
    return this.fetchJson('/threat-intel/summary');
  }

  public async syncIntel(): Promise<{ job_id: string; status: string; results: Array<{ source: string; success: boolean }> }> {
    return this.fetchJson('/threat-intel/sync', { method: 'POST', body: JSON.stringify({}) });
  }

  public async lookupCve(cveId: string): Promise<ThreatIntelItem> {
    return this.fetchJson<ThreatIntelItem>(`/threat-intel/cve/${encodeURIComponent(cveId)}`);
  }

  public async getKevCatalog(limit = 200): Promise<{ items: ThreatIntelItem[]; total: number }> {
    const items = await this.fetchJson<ThreatIntelItem[]>(`/threat-intel/kev?limit=${limit}`);
    return { items, total: items.length };
  }

  // Detection Rules
  public async listRules(): Promise<{ items: DetectionRule[]; total: number }> {
    const res = await this.fetchJson<any>('/rules');
    if (Array.isArray(res)) {
      return { items: res, total: res.length };
    }
    return res || { items: [], total: 0 };
  }

  public async validateRule(yamlContent: string): Promise<{ valid: boolean; errors: string[]; parsed?: any }> {
    return this.fetchJson<{ valid: boolean; errors: string[]; parsed?: any }>('/rules/validate', {
      method: 'POST',
      body: JSON.stringify({ raw_yaml: yamlContent }),
    });
  }

  public async createRule(data: { raw_yaml: string }): Promise<DetectionRule> {
    return this.fetchJson<DetectionRule>('/rules', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async transitionRule(id: string, toStatus: string, comment?: string): Promise<any> {
    return this.fetchJson<any>(`/rules/${id}/lifecycle`, {
      method: 'POST',
      body: JSON.stringify({ to_status: toStatus, comment: comment || '' }),
    });
  }

  public async testRule(id: string): Promise<any> {
    return this.fetchJson<any>(`/rules/${id}/test`, {
      method: 'POST',
    });
  }

  // Reports
  public async listReports(): Promise<ReportItem[]> {
    return this.fetchJson<ReportItem[]>('/reports');
  }

  public async generateReport(data: {
    title?: string;
    report_type: string;
    asset_id?: string;
    scan_id?: string;
    formats?: string[];
  }): Promise<ReportItem> {
    return this.fetchJson<ReportItem>('/reports/generate', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async deleteReport(reportId: string): Promise<void> {
    await this.fetchJson(`/reports/${reportId}`, { method: 'DELETE' });
  }

  public getDownloadUrl(reportId: string, format: string): string {
    return `${API_BASE}/reports/${reportId}/download?format=${format}`;
  }

  // Defensive engine executions (Milestone 3)
  public async uploadArtifact(assetId: string, file: File, sourceNote?: string): Promise<EngineArtifact> {
    const q = new URLSearchParams({ kind: 'sbom', filename: file.name });
    if (sourceNote) q.set('source_note', sourceNote);
    return this.fetchJson<EngineArtifact>(`/assets/${assetId}/artifacts?${q.toString()}`, {
      method: 'POST',
      body: file,
      headers: { 'Content-Type': file.type || 'application/json' },
    });
  }

  public async launchExecution(
    body: { asset_id: string; engine: EngineName; artifact_id?: string },
    idempotencyKey: string,
  ): Promise<ExecutionLaunch> {
    return this.fetchJson<ExecutionLaunch>('/executions', {
      method: 'POST',
      body: JSON.stringify(body),
      headers: { 'Idempotency-Key': idempotencyKey },
    });
  }

  public async listExecutions(params: { assetId?: string; engine?: string; page?: number; size?: number } = {}): Promise<{ items: ExecutionDetail[]; total: number; page: number; pages: number }> {
    const q = new URLSearchParams({ page: String(params.page || 1), size: String(params.size || 20) });
    if (params.assetId) q.set('asset_id', params.assetId);
    if (params.engine) q.set('engine', params.engine);
    return this.fetchJson(`/executions?${q.toString()}`);
  }

  public async getExecution(id: string): Promise<ExecutionDetail> {
    return this.fetchJson<ExecutionDetail>(`/executions/${id}`);
  }

  public async cancelExecution(id: string): Promise<ExecutionDetail> {
    return this.fetchJson<ExecutionDetail>(`/executions/${id}/cancel`, { method: 'POST' });
  }

  public executionOutputUrl(id: string): string {
    return `${API_BASE}/executions/${id}/output`;
  }

  public async listAdvisorySnapshots(): Promise<AdvisorySnapshotInfo[]> {
    return this.fetchJson<AdvisorySnapshotInfo[]>('/threat-intel/advisory-snapshots');
  }

  public async importAdvisorySnapshot(file: File, source: string, versionLabel: string): Promise<AdvisorySnapshotInfo> {
    const q = new URLSearchParams({ source, version_label: versionLabel });
    return this.fetchJson<AdvisorySnapshotInfo>(`/threat-intel/advisory-snapshots?${q.toString()}`, {
      method: 'POST',
      body: file,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  public async approveHealthCheck(assetId: string, body: { url: string; allow_private: boolean; note?: string }): Promise<any> {
    return this.fetchJson(`/assets/${assetId}/health-check`, { method: 'PUT', body: JSON.stringify(body) });
  }

  public async listWorkers(): Promise<{ as_of: string; ready: boolean; reason: string | null; workers: any[] }> {
    return this.fetchJson('/engines/workers');
  }

  // Authentication (cookie session)
  public async login(username: string, password: string): Promise<{ access_token: string; token_type: string; user: any }> {
    return this.fetchJson<{ access_token: string; token_type: string; user: any }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
  }

  public async me(): Promise<{ id: string; username: string; email: string | null; role: string; is_owner: boolean }> {
    return this.fetchJson('/auth/me');
  }

  public async logout(): Promise<void> {
    await this.fetchJson('/auth/logout', { method: 'POST' });
  }

  /** API readiness through the gateway (DB reachable). Throws ApiError when not ready. */
  public async ready(): Promise<{ status: string; build: string; version: string; checks: Record<string, string>; time_utc: string }> {
    const res = await fetch('/healthz/ready', { credentials: 'same-origin' }).catch(() => {
      throw new ApiError('Network error: the console cannot reach the gateway.', 0, 'network');
    });
    const ctype = res.headers.get('content-type') || '';
    if (ctype.includes('text/html')) throw new ApiError('Readiness answered with HTML (misrouted).', res.status, 'misrouted');
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new ApiError(body?.detail || `HTTP ${res.status}`, res.status, kindFor(res.status, body?.code), { code: body?.code, requestId: body?.request_id });
    return body;
  }

  // Engine Health, Diagnostics & Updates
  public async getEngines(): Promise<EngineDiagnosticItem[]> {
    // Only what the server reports; missing fields stay missing (UI shows "unknown").
    const res = await this.getEngineHealth();
    return Array.isArray(res?.engines) ? (res.engines as any) : [];
  }

  public async getEngineHealth(): Promise<EngineHealthResponse> {
    return this.fetchJson<EngineHealthResponse>('/engines/health');
  }

  public async testEngines(): Promise<EngineTestResult> {
    return this.fetchJson<EngineTestResult>('/engines/test', { method: 'POST' });
  }

  public async checkEngineUpdates(): Promise<EngineUpdateCheckResult> {
    return this.fetchJson<EngineUpdateCheckResult>('/engines/check-updates', { method: 'POST' });
  }

  // Settings & System Reset
  public async getSettings(): Promise<any> {
    return this.fetchJson('/settings');
  }

  public async clearLogs(scanId: string): Promise<void> {
    await this.fetchJson(`/scans/${scanId}/logs`, { method: 'DELETE' });
  }

  public async clearAllLogs(): Promise<{ purged_count: number }> {
    return this.fetchJson('/logs/purge', { method: 'POST', body: JSON.stringify({ days: 0 }) });
  }

  public async resetBaseline(): Promise<{ message: string; assets: number; findings: number; scans: number; schedules?: number }> {
    return this.fetchJson('/system/reset', { method: 'POST' });
  }

  // =========================================================================
  // Checklist Assessment Engine (R1 / R6)
  // =========================================================================

  public async getChecklistDefinitions(category?: string): Promise<ChecklistDefinition[]> {
    const query = category ? `?category=${encodeURIComponent(category)}` : '';
    return this.fetchJson<ChecklistDefinition[]>(`/checklist/definitions${query}`);
  }

  public async getChecklistRuns(assetId?: string): Promise<ChecklistAssessmentRun[]> {
    const query = assetId ? `?asset_id=${encodeURIComponent(assetId)}` : '';
    return this.fetchJson<ChecklistAssessmentRun[]>(`/checklist/runs${query}`);
  }

  public async getChecklistRun(id: string): Promise<ChecklistAssessmentRun> {
    return this.fetchJson<ChecklistAssessmentRun>(`/checklist/runs/${id}`);
  }

  public async getChecklistRunResults(id: string): Promise<ChecklistResult[]> {
    return this.fetchJson<ChecklistResult[]>(`/checklist/runs/${id}/results`);
  }

  public async createChecklistRun(payload: { asset_id: string; profile?: string; mode?: string }): Promise<ChecklistAssessmentRun> {
    return this.fetchJson<ChecklistAssessmentRun>('/checklist/runs', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  public async reviewChecklistResult(
    runId: string,
    checkId: string,
    payload: { state?: ChecklistResultState; status?: ChecklistResultState; review_notes?: string; notes?: string }
  ): Promise<ChecklistResult> {
    const state = payload.state || payload.status || 'NEEDS_REVIEW';
    const review_notes = payload.review_notes !== undefined ? payload.review_notes : payload.notes;
    return this.fetchJson<ChecklistResult>(`/checklist/runs/${runId}/review/${checkId}`, {
      method: 'POST',
      body: JSON.stringify({ state, review_notes }),
    });
  }
}


export const api = new ApiClient();
