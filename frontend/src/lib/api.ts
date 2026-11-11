import {
  ActiveThreadInfo,
  Asset,
  AssetSummary,
  AssetVerifyRequest,
  AssetVerifyResponse,
  BaselineException,
  BatchScanResponse,
  DailyScheduleItem,
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


const API_BASE = '/api/v1';

class ApiClient {
  public getToken(): string | null {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('sentinel_jwt_token');
    }
    return null;
  }

  public setToken(token: string): void {
    if (typeof window !== 'undefined') {
      localStorage.setItem('sentinel_jwt_token', token);
    }
  }

  private async fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers || {});
    headers.set('Content-Type', 'application/json');

    const token = this.getToken();
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (response.status === 503) {
      const err = new Error('Service Unavailable: Security assessment control plane is unreachable (HTTP 503).');
      (err as any).status = 503;
      throw err;
    }

    if (!response.ok) {
      let errorMsg = `HTTP Error ${response.status}: ${response.statusText}`;
      let detail: any = null;
      try {
        const errorJson = await response.json();
        detail = errorJson.detail;
        if (errorJson.detail) {
          errorMsg = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
        }
      } catch (_) {}
      const err = new Error(errorMsg);
      (err as any).status = response.status;
      (err as any).detail = detail;
      throw err;
    }

    if (response.status === 204) {
      return {} as T;
    }

    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('text/html')) {
      const err = new Error('Unexpected HTML response received from API gateway (SPA fallback detected). Backend API route is not available.');
      (err as any).status = 502;
      throw err;
    }

    return await response.json();
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
    return this.fetchJson<{ items: Asset[]; total: number }>(`/assets?${query.toString()}`);
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
  public async listFindings(filters?: { assetId?: string; module?: string; severity?: string; status?: string }): Promise<{ items: Finding[]; total: number }> {
    const params = new URLSearchParams({ size: '100' });
    if (filters?.assetId) params.append('asset_id', filters.assetId);
    if (filters?.module) params.append('empire_module', filters.module);
    if (filters?.severity) params.append('severity', filters.severity);
    if (filters?.status) params.append('status_filter', filters.status);
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

  public async retestFinding(id: string): Promise<any> {
    return this.fetchJson(`/findings/${id}/retest`, { method: 'POST' });
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

  // Schedules (Daily Asia/Ho_Chi_Minh Pipeline)
  public async listSchedules(): Promise<DailyScheduleItem[]> {
    return this.fetchJson<DailyScheduleItem[]>('/schedules');
  }

  public async createSchedule(data: Partial<DailyScheduleItem>): Promise<DailyScheduleItem> {
    return this.fetchJson<DailyScheduleItem>('/schedules', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async triggerSchedule(scheduleId: string): Promise<any> {
    return this.fetchJson(`/schedules/${scheduleId}/trigger`, { method: 'POST' });
  }

  public async toggleSchedule(scheduleId: string): Promise<any> {
    return this.fetchJson(`/schedules/${scheduleId}/toggle`, { method: 'PUT' });
  }

  public async deleteSchedule(scheduleId: string): Promise<any> {
    return this.fetchJson(`/schedules/${scheduleId}`, { method: 'DELETE' });
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


  // Threat Intel
  public async getIntelStatus(): Promise<any> {
    return this.fetchJson('/intel/status');
  }

  public async syncIntel(): Promise<any> {
    return this.fetchJson('/intel/sync', { method: 'POST' });
  }

  public async lookupCve(cveId: string): Promise<ThreatIntelItem> {
    return this.fetchJson<ThreatIntelItem>(`/intel/cve/${encodeURIComponent(cveId)}`);
  }

  public async getKevCatalog(): Promise<{ items: ThreatIntelItem[]; total: number }> {
    return this.fetchJson<{ items: ThreatIntelItem[]; total: number }>('/intel/kev');
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

  // Authentication & Ultra Admin
  public async login(username: string, password: string): Promise<{ access_token: string; token_type: string; user: any }> {
    const res = await this.fetchJson<{ access_token: string; token_type: string; user: any }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    if (res?.access_token) {
      this.setToken(res.access_token);
    }
    return res;
  }

  // Engine Health, Diagnostics & Updates
  public async getEngines(): Promise<EngineDiagnosticItem[]> {
    try {
      const res = await this.getEngineHealth();
      if (res?.engines && Array.isArray(res.engines) && res.engines.length > 0) {
        return res.engines.map((e: any) => ({
          id: e.id || e.name,
          name: e.name || e.display_name,
          driver: e.driver || e.mode || 'In-Process Engine',
          version: e.version || 'v2.0',
          status: (e.status === 'ONLINE' ? 'OPERATIONAL' : e.status) || 'OPERATIONAL',
          runtime_context: e.runtime_context || e.executable_path || 'Integrated Platform Runtime',
          latency_ms: e.latency_ms || 10,
          last_tested: e.last_tested || new Date().toISOString(),
          update_available: Boolean(e.update_available),
          capabilities: Array.isArray(e.capabilities) ? e.capabilities : [],
        }));
      }
    } catch (_) {}
    return this.fetchJson<EngineDiagnosticItem[]>('/engines');
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
}


export const api = new ApiClient();
