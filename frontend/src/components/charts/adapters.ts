import { DonutSegmentItem, BarSeriesConfig, AreaSeriesConfig } from './types';

export type SeverityDistributionResponse = Record<
  'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO',
  number
>;

export interface VulnerabilityTrendItem {
  date: string;
  new_findings: number;
  fixed_findings: number;
  reopened_findings: number;
}

export interface ModuleRiskItem {
  module_key: string;
  module_name: string;
  risk_score: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  total_findings: number;
}

export interface AssessmentCoverageResponse {
  total_targets: number;
  assessed_today: number;
  pending_assessment: number;
  coverage_percentage: number;
}

export interface RiskTrendItem {
  date: string;
  risk_score: number;
  active_findings: number;
}

export interface ScannerPerformanceItem {
  engine: string;
  total_executions: number;
  completed: number;
  failed: number;
  success_rate: number;
  avg_duration_seconds: number;
}

export interface IntelligenceActivityResponse {
  total_cves_indexed: number;
  cisa_kev_active: number;
  high_epss_exploitable: number;
  detection_rules_active: number;
  last_sync: string;
}

export type RemediationProgressResponse = Record<
  'OPEN' | 'IN_REMEDIATION' | 'FIXED' | 'REOPENED' | 'ACCEPTED_RISK' | 'FALSE_POSITIVE',
  number
>;

/**
 * Transforms /api/v1/metrics/severity-distribution into InteractiveDonutChart segments
 */
export function adaptSeverityToDonut(dist: SeverityDistributionResponse | any): DonutSegmentItem[] {
  const SEVERITY_COLORS: Record<string, string> = {
    CRITICAL: '#F43F5E', // Rose
    HIGH: '#F97316',     // Orange
    MEDIUM: '#F59E0B',   // Amber
    LOW: '#10B981',      // Emerald
    INFO: '#0EA5E9',     // Sky
  };

  if (!dist || typeof dist !== 'object') return [];

  const order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'] as const;
  return order
    .filter((sev) => Number(dist[sev]) > 0 || Object.values(dist).every((v) => !v || v === 0))
    .map((sev) => ({
      id: sev,
      label: sev,
      value: Number(dist[sev]) || 0,
      color: SEVERITY_COLORS[sev] || '#64748B',
    }));
}

/**
 * Transforms /api/v1/metrics/charts/vulnerability-trend into InteractiveAreaChart props
 */
export function adaptVulnerabilityTrend(data: VulnerabilityTrendItem[]): {
  data: VulnerabilityTrendItem[];
  series: AreaSeriesConfig[];
} {
  return {
    data: Array.isArray(data) ? data : [],
    series: [
      { id: 'new', name: 'New Findings', color: '#E4E4E7', dataKey: 'new_findings' },
      { id: 'fixed', name: 'Remediated', color: '#10B981', dataKey: 'fixed_findings' },
      { id: 'reopened', name: 'Reopened', color: '#F59E0B', dataKey: 'reopened_findings', dashed: true },
    ],
  };
}

/**
 * Transforms /api/v1/metrics/charts/module-risk into InteractiveBarChart props
 */
export function adaptModuleRisk(data: ModuleRiskItem[]): {
  data: ModuleRiskItem[];
  series: BarSeriesConfig[];
} {
  return {
    data: Array.isArray(data) ? data : [],
    series: [
      { id: 'risk_score', name: 'Risk Score (SRS)', color: '#F43F5E', dataKey: 'risk_score' },
      { id: 'total_findings', name: 'Total Findings', color: '#D4D4D8', dataKey: 'total_findings' },
    ],
  };
}

/**
 * Transforms /api/v1/metrics/charts/scanner-performance into InteractiveBarChart props
 */
export function adaptScannerPerformance(data: ScannerPerformanceItem[]): {
  data: ScannerPerformanceItem[];
  series: BarSeriesConfig[];
} {
  return {
    data: Array.isArray(data) ? data : [],
    series: [
      { id: 'completed', name: 'Completed Scans', color: '#10B981', dataKey: 'completed' },
      { id: 'failed', name: 'Failed Scans', color: '#EF4444', dataKey: 'failed' },
    ],
  };
}

/**
 * Transforms /api/v1/metrics/charts/remediation-progress into horizontal InteractiveBarChart or Donut
 */
export function adaptRemediationProgressToDonut(data: RemediationProgressResponse | any): DonutSegmentItem[] {
  const STATUS_COLORS: Record<string, string> = {
    OPEN: '#EF4444',
    IN_REMEDIATION: '#F59E0B',
    FIXED: '#10B981',
    REOPENED: '#EC4899',
    ACCEPTED_RISK: '#64748B',
    FALSE_POSITIVE: '#3B82F6',
  };

  if (!data) return [];

  // Handle if data is array of objects
  if (Array.isArray(data)) {
    return data
      .filter((item) => typeof item === 'object' && item !== null && (item.count || item.value))
      .map((item) => {
        const rawKey = String(item.status || item.label || 'UNKNOWN').toUpperCase().replace(/\s+/g, '_');
        const countVal = Number(item.count || item.value || 0);
        return {
          id: rawKey,
          label: String(item.status || item.label || rawKey),
          value: countVal,
          color: STATUS_COLORS[rawKey] || '#64748B',
        };
      });
  }

  // Handle if data is dictionary of status -> number
  return Object.entries(data)
    .filter(([_, count]) => typeof count === 'number' && count > 0)
    .map(([status, count]) => ({
      id: status,
      label: status.replace(/_/g, ' '),
      value: count as number,
      color: STATUS_COLORS[status] || '#64748B',
    }));
}
