export type SeverityLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO';

export type AssetType =
  | 'DOMAIN'
  | 'WEB_APP'
  | 'API_ENDPOINT'
  | 'PROJECT_ARCHIVE'
  | 'CONTAINER_IMAGE'
  | 'OBJECT_STORAGE'
  | 'SERVER';

export type EmpireModuleType =
  | 'STUDENT_MANAGEMENT'
  | 'LEARNING_MATERIALS'
  | 'SUPPORTING_TOOLS'
  | 'API_SERVICES'
  | 'WEB_APPLICATION'
  | 'SERVER_INFRASTRUCTURE';

export type VerificationStatus = 'PENDING' | 'VERIFIED' | 'FAILED' | 'REVOKED';

export type CriticalityTier = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type ExposureLevel = 'INTERNET' | 'INTERNAL' | 'ISOLATED';

export type ScanStatus =
  | 'PENDING'
  | 'QUEUED'
  | 'INITIALIZING'
  | 'RUNNING'
  | 'COMPLETING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'TIMED_OUT';

export type FindingLifecycleStatus =
  | 'NEW'
  | 'POTENTIAL'
  | 'CONFIRMED'
  | 'OPEN'
  | 'IN_REMEDIATION'
  | 'FIXED'
  | 'REOPENED'
  | 'ACCEPTED_RISK'
  | 'FALSE_POSITIVE'
  | 'NOT_AFFECTED';

export interface Asset {
  id: string;
  name: string;
  asset_type: AssetType;
  target_locator: string;
  empire_module: EmpireModuleType;
  environment: string;
  technology: string;
  approved_media_baseline: boolean;
  assessment_policy?: Record<string, any>;
  auth_profile?: Record<string, any>;
  excluded_endpoints?: string[];
  verification_status: VerificationStatus;
  verification_type: string;
  verification_token: string;
  verified_at?: string | null;
  criticality: CriticalityTier;
  exposure: ExposureLevel;
  description?: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
  critical_findings?: number;
  open_findings?: number;
}

export interface ScanJob {
  id: string;
  asset_id: string;
  engine: string;
  profile: string;
  status: ScanStatus;
  progress_percentage: number;
  target_locator: string;
  allow_private_targets: boolean;
  timeout_seconds: number;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
}

export interface Finding {
  id: string;
  scan_id: string;
  asset_id: string;
  fingerprint: string;
  empire_module?: EmpireModuleType | null;
  exposure_classification?: string | null;
  is_approved_baseline: boolean;
  scanner_engine: string;
  scanner_rule_id: string;
  title: string;
  description: string;
  severity: SeverityLevel;
  original_severity: string;
  cve_id?: string | null;
  cwe_id?: string | null;
  cvss_score?: number | null;
  cvss_vector?: string | null;
  epss_score?: number | null;
  epss_percentile?: number | null;
  is_kev: boolean;
  target_location: string;
  target_component?: string | null;
  evidence: Record<string, any>;
  raw_payload?: string | null;
  remediation?: string | null;
  references: string[];
  status: FindingLifecycleStatus | string;
  remediation_notes?: string | null;
  assignee?: string | null;
  retest_status?: string | null;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
}

export interface EmpireModuleSummary {
  module_key: EmpireModuleType;
  title: string;
  description: string;
  icon: string;
  asset_count: number;
  risk_score: number;
  risk_tier: string;
  total_findings: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
  open_remediation_count: number;
  fixed_count: number;
  latest_assessment?: string | null;
  next_scheduled_assessment: string;
}

export interface BaselineException {
  id: string;
  scope: string;
  classification: string;
  reason: string;
  owner: string;
  approved_by: string;
  is_active: boolean;
  created_at: string;
  evidence: Record<string, any>;
  review_history: Array<Record<string, any>>;
}

export interface DailyScheduleItem {
  id: string;
  name: string;
  profile: string;
  cron_expression: string;
  timezone: string;
  is_active: boolean;
  target_ids: string[];
  last_run_at?: string | null;
  next_run_at?: string | null;
  last_status?: string | null;
  target_group?: string;
  created_at?: string;
}

export interface SecurityAlertItem {
  id: string;
  severity: SeverityLevel;
  title: string;
  message: string;
  category: string;
  is_read: boolean;
  created_at: string;
  metadata_json: Record<string, any>;
}

export interface ThreatIntelItem {
  cve_id: string;
  title?: string | null;
  summary?: string | null;
  cvss_v3_score?: number | null;
  epss_score?: number | null;
  is_cisa_kev: boolean;
  cisa_kev_ransomware?: string | null;
  synced_at?: string | null;
}

export interface DetectionRule {
  id: string;
  name: string;
  description?: string | null;
  version: string;
  author: string;
  severity: string;
  status: 'draft' | 'in_review' | 'approved' | 'active' | 'deprecated';
  target_types: string[];
  raw_yaml: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ReportItem {
  id: string;
  title: string;
  report_type: string;
  target_scope: string;
  formats: string[];
  status: string;
  summary: {
    total_findings: number;
    critical_count: number;
    high_count: number;
    medium_count: number;
    low_count: number;
    info_count: number;
    cisa_kev_count: number;
    high_epss_count: number;
    overall_risk_score: number;
    risk_posture: string;
  };
  file_paths: Record<string, string>;
  created_by: string;
  created_at: string;
}

export interface OverviewMetrics {
  total_assets: number;
  targets_assessed_today: number;
  active_assessments: number;
  failed_assessments: number;
  critical_findings: number;
  high_findings: number;
  total_open_findings: number;
  fixed_findings: number;
  newly_discovered_cves: number;
  relevant_kev_count: number;
  overall_risk_score: number;
  risk_posture: string;
}

// ============================================================================
// ASSET MANAGEMENT & VERIFICATION CONTRACTS
// ============================================================================

export type VerificationType = 'DNS_TXT' | 'HTTP_WELL_KNOWN' | 'ADMIN_OVERRIDE';
export type VerificationStepStatus = 'PENDING' | 'RUNNING' | 'PASS' | 'FAIL' | 'INFO' | 'SKIPPED';

export interface SecurityHeadersPosture {
  strict_transport_security?: string | null;
  content_security_policy?: string | null;
  x_frame_options?: string | null;
  x_content_type_options?: string | null;
  referrer_policy?: string | null;
  [key: string]: string | null | undefined;
}

export interface TargetFingerprint {
  server?: string;
  reverse_proxy_waf?: string;
  framework?: string;
  technologies?: string[];
  security_headers?: SecurityHeadersPosture;
  active_security_headers_count?: number;
  title?: string;
  status_code?: number;
  headers?: Record<string, string>;
  [key: string]: unknown;
}

export interface VerificationStepResult {
  step: number;
  name: string;
  status: 'PASS' | 'FAIL' | 'INFO';
  detail: string;
  metadata?: Record<string, any>;
}

export interface AssetVerifyRequest {
  verification_type?: VerificationType;
  allow_private?: boolean;
}

export interface AssetVerifyResponse {
  asset_id: string;
  verification_status: VerificationStatus;
  verified: boolean;
  status: 'VERIFIED' | 'FAILED';
  message: string;
  steps: VerificationStepResult[];
  fingerprint: TargetFingerprint;
}

export interface AssetSummary {
  asset_id: string;
  name: string;
  target_locator: string;
  empire_module: EmpireModuleType | string;
  environment: string;
  critical_findings: number;
  high_findings: number;
  open_findings: number;
  fixed_findings: number;
  total_findings: number;
  last_assessment_at: string | null;
  last_scan_status: ScanStatus | string | null;
}

// ============================================================================
// Batch Scans & Live Telemetry Interfaces
// ============================================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page?: number;
  size?: number;
  pages?: number;
}

export interface ScanBatchCreate {
  name?: string;
  targets?: string | string[];
  profile?: string;
  profiles?: string[];
  engine?: string;
  engines?: string[];
  concurrency_limit?: number;
  allow_private_targets?: boolean;
  timeout_seconds?: number;
  description?: string;
}

export interface ScanBatchRead {
  id: string;
  name: string;
  status: string;
  total_scans: number;
  completed_scans: number;
  failed_scans: number;
  cancelled_scans: number;
  progress_percentage: number;
  target_count: number;
  engines: any;
  profiles: any;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  metadata_json?: any;
  scans?: ScanJob[];
}

export interface BatchScanResponse {
  batch_id: string;
  name: string;
  total_scans: number;
  target_count: number;
  status: string;
  scans: ScanJob[];
  message?: string;
}

export interface SystemResourcesInfo {
  cpu_percent: number;
  memory_percent: number;
  memory_available_mb: number;
  memory_used_mb?: number;
  cpu_count?: number;
  is_throttled?: boolean;
}

export interface ActiveThreadInfo {
  thread_id: number;
  scan_id: string;
  target_locator: string;
  profile: string;
  engine: string;
  stage: string;
  progress_percentage: number;
  started_at?: string | null;
  elapsed_seconds: number;
  last_log: string;
}

export interface TrackCurrentResponse {
  active_workers: number;
  max_concurrency: number;
  queued_count?: number;
  completed_count?: number;
  is_throttled: boolean;
  system_resources: SystemResourcesInfo;
  active_threads: ActiveThreadInfo[];
  active_worker_count?: number;
  running_scans?: any[];
  trackcurrent?: any;
}

export interface EngineDiagnosticItem {
  id: string;
  name: string;
  driver: string;
  version: string;
  status: 'OPERATIONAL' | 'AVAILABLE' | 'DEGRADED' | 'OUTDATED';
  runtime_context: string;
  latency_ms: number;
  last_tested: string;
  update_available: boolean;
  capabilities: string[];
}

export interface EngineHealthResponse {
  status: 'HEALTHY' | 'DEGRADED' | 'CRITICAL';
  engines_count: number;
  operational_count: number;
  timestamp: string;
  engines: EngineDiagnosticItem[];
}

export interface EngineTestResult {
  overall_status: 'PASS' | 'FAIL';
  duration_ms: number;
  timestamp: string;
  results: {
    engine: string;
    status: 'PASS' | 'FAIL';
    latency_ms: number;
    message: string;
  }[];
}

export interface EngineUpdateCheckResult {
  timestamp: string;
  updates_available: boolean;
  engines: {
    engine: string;
    current_version: string;
    latest_version: string;
    has_update: boolean;
    templates_updated: boolean;
    template_count?: number;
    notes?: string;
  }[];
}



