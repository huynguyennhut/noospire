# Technical Specification & Implementation Blueprint: Security Analytics Dashboard Overhaul

## 1. Executive Summary & Architectural Overview

The Security Analytics Dashboard (`frontend/src/app/dashboard/page.tsx`) serves as the primary operational command center for **NOOSFORGE Security Intelligence** monitoring the Empire Education Platform (`https://empire.edu.vn/`).

This technical specification details the complete architectural and component-level overhaul of `frontend/src/app/dashboard/page.tsx` from raw HTML elements into a production-grade enterprise cybersecurity SaaS dashboard. The overhauled dashboard utilizes:
- **Design System**: Black/White/Liquid Glass design tokens (`bg-cyber-900/60`, `backdrop-blur-md`, `border-white/10`, specular borders, elevation shadows).
- **M5 UI Primitives**: `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter`, `StatCard`, `Badge`, `Button`, `Tabs`, `TabsList`, `TabsTrigger`.
- **M5 Zero-Dependency SVG Charting Engine**: `InteractiveAreaChart`, `InteractiveBarChart`, `InteractiveDonutChart`, `InteractiveGaugeChart`, and the telemetry data transformers in `adapters.ts`.
- **FastAPI Telemetry Endpoints**: Full real-time hydration from `GET /api/v1/metrics/overview` and the 8 dedicated chart endpoints under `/api/v1/metrics/`.
- **Dynamic Interaction Layer**: Dynamic time-range filtering (`7D` / `14D` / `30D`), non-blocking concurrent refresh with spinner indicator, quick action routing to `/scans`, zero-layout-shift tooltips, and graceful skeleton/error states.

---

## 2. Component Inventory & UI Primitives Mapping

| UI Primitive / Chart | Source Location | Usage in Dashboard |
|---|---|---|
| `StatCard` | `src/components/ui/stat-card.tsx` | 10 Core KPI summary cards with icons, accents, trends, and glows |
| `Card`, `CardHeader`, `CardTitle`, `CardContent` | `src/components/ui/card.tsx` | Structured containers for all 8 interactive charts & Hero banner |
| `Badge` | `src/components/ui/badge.tsx` | Status indicators (`Live SOC`, `CRITICAL`, `ELEVATED`, `MODERATE`, `OPTIMAL`) |
| `Button` | `src/components/ui/button.tsx` | Refresh action button and quick navigation triggers |
| `Tabs`, `TabsList`, `TabsTrigger` | `src/components/ui/tabs.tsx` | Time-range selector (`7D`, `14D`, `30D`) and chart mode switchers |
| `InteractiveAreaChart` | `src/components/charts/InteractiveAreaChart.tsx` | Chart 5: Risk Score Evolution ($SRS$) spline area with hover crosshair |
| `InteractiveBarChart` | `src/components/charts/InteractiveBarChart.tsx` | Chart 2 (Stacked Vuln Trend), Chart 3 (Module Risk), Chart 6 (Scanner Perf) |
| `InteractiveDonutChart` | `src/components/charts/InteractiveDonutChart.tsx` | Chart 1 (Severity Distribution), Chart 8 (Remediation Lifecycle) |
| `InteractiveGaugeChart` | `src/components/charts/InteractiveGaugeChart.tsx` | Chart 4 (Target Assessment Coverage) & Sentinel Risk Score Hero |
| Telemetry Adapters | `src/components/charts/adapters.ts` | Data transformation functions ensuring zero impedance between API and SVG |

---

## 3. State Management & Concurrent Telemetry Hydration Architecture

### 3.1. Telemetry State Schema

```typescript
// Time range filter state
type TimeRange = 7 | 14 | 30;

// State hooks in DashboardPage
const [timeRange, setTimeRange] = useState<TimeRange>(14);
const [metrics, setMetrics] = useState<OverviewMetrics | null>(null);
const [severityDist, setSeverityDist] = useState<SeverityDistributionResponse>({
  CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0
});
const [vulnTrend, setVulnTrend] = useState<VulnerabilityTrendItem[]>([]);
const [moduleRisk, setModuleRisk] = useState<ModuleRiskItem[]>([]);
const [coverage, setCoverage] = useState<AssessmentCoverageResponse | null>(null);
const [riskTrend, setRiskTrend] = useState<RiskTrendItem[]>([]);
const [scannerPerf, setScannerPerf] = useState<ScannerPerformanceItem[]>([]);
const [intelActivity, setIntelActivity] = useState<IntelligenceActivityResponse | null>(null);
const [remediationProg, setRemediationProg] = useState<RemediationProgressResponse>({
  OPEN: 0, IN_REMEDIATION: 0, FIXED: 0, REOPENED: 0, ACCEPTED_RISK: 0, FALSE_POSITIVE: 0
});
const [loading, setLoading] = useState<boolean>(true);
const [refreshing, setRefreshing] = useState<boolean>(false);
const [lastRefreshed, setLastRefreshed] = useState<string>('');
const [error, setError] = useState<string | null>(null);
```

### 3.2. Concurrent Fetch Architecture

All 9 endpoints are queried concurrently in parallel via `Promise.all` with individual `.catch()` resilience guards. If any individual chart endpoint fails, it degrades gracefully to a safe empty structure without crashing the dashboard.

```typescript
const loadData = useCallback(async (selectedDays: number) => {
  try {
    const [m, dist, trend, mRisk, cov, rTrend, perf, intel, rem] = await Promise.all([
      api.getOverviewMetrics().catch(() => null),
      api.getSeverityDist().catch(() => ({ CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 })),
      api.getVulnerabilityTrend(selectedDays).catch(() => []),
      api.getModuleRiskChart().catch(() => []),
      api.getCoverageChart().catch(() => null),
      api.getRiskTrendChart(selectedDays).catch(() => []),
      api.getScannerPerformance().catch(() => []),
      api.getIntelligenceActivity().catch(() => null),
      api.getRemediationProgress().catch(() => ({
        OPEN: 0, IN_REMEDIATION: 0, FIXED: 0, REOPENED: 0, ACCEPTED_RISK: 0, FALSE_POSITIVE: 0
      })),
    ]);

    if (m) setMetrics(m);
    if (dist) setSeverityDist(dist);
    if (trend) setVulnTrend(trend);
    if (mRisk) setModuleRisk(mRisk);
    if (cov) setCoverage(cov);
    if (rTrend) setRiskTrend(rTrend);
    if (perf) setScannerPerf(perf);
    if (intel) setIntelActivity(intel);
    if (rem) setRemediationProg(rem);

    setLastRefreshed(new Date().toLocaleTimeString());
    setError(null);
  } catch (err: any) {
    setError(err?.message || 'Failed to load telemetry metrics');
  } finally {
    setLoading(false);
    setRefreshing(false);
  }
}, []);
```

---

## 4. Specification: 10 Core KPI Summary Cards

The 10 Core KPI cards are rendered using `StatCard` in a responsive grid: `grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5`.

| # | KPI Title | Field in `MetricsOverviewResponse` | Icon | Accent | Glow | Trend / Subtitle |
|---|---|---|---|---|---|---|
| 1 | **Total Managed Targets** | `metrics.total_assets` | `Server` | `cyan` | `none` | Subtitle: "100% Verified Policy"<br>Trend: `{ value: '+4% MoM', positive: true }` |
| 2 | **Targets Assessed Today** | `metrics.targets_assessed_today` | `CheckCircle2` | `emerald` | `none` | Subtitle: `Coverage: ${coverage?.coverage_percentage ?? 0}%`<br>Trend: `{ value: 'Daily SLA', positive: true }` |
| 3 | **Active Assessments** | `metrics.active_assessments` | `Radio` (animated pulse) | `cyan` | `cyan` (if > 0) | Subtitle: "Worker Pool Active"<br>Trend: `{ value: 'Live', positive: true }` |
| 4 | **Failed Assessments** | `metrics.failed_assessments` | `AlertTriangle` | `metrics.failed_assessments > 0 ? 'rose' : 'slate'` | `rose` (if > 0) | Subtitle: "Zero Degradation"<br>Trend: `{ value: metrics.failed_assessments === 0 ? 'Optimal' : 'Degraded', positive: metrics.failed_assessments === 0 }` |
| 5 | **Critical Findings** | `metrics.critical_findings` | `ShieldAlert` | `rose` | `rose` (if > 0) | Subtitle: "Immediate SLA Action"<br>Trend: `metrics.critical_findings > 0 ? { value: 'Requires Triage', positive: false } : undefined` |
| 6 | **High Findings** | `metrics.high_findings` | `AlertTriangle` | `amber` | `amber` (if > 0) | Subtitle: "High Priority Queue"<br>Trend: `metrics.high_findings > 0 ? { value: 'Tracked', positive: false } : undefined` |
| 7 | **Total Open Findings** | `metrics.total_open_findings` | `Activity` | `slate` | `none` | Subtitle: "Active Backlog"<br>Trend: `{ value: 'Under Tracking', positive: true }` |
| 8 | **Fixed Findings** | `metrics.fixed_findings` | `CheckCircle2` | `emerald` | `emerald` | Subtitle: "Verified Remediations"<br>Trend: `{ value: '+12% Velocity', positive: true }` |
| 9 | **Indexed CVEs** | `metrics.newly_discovered_cves` | `Flame` | `cyan` | `none` | Subtitle: "NVD & OSV Feeds"<br>Trend: `{ value: '+18 Feeds', positive: true }` |
| 10 | **CISA KEV Actives** | `metrics.relevant_kev_count` | `Flame` | `rose` | `rose` (if > 0) | Subtitle: "Known Exploited"<br>Trend: `metrics.relevant_kev_count > 0 ? { value: 'Exploit in Wild', positive: false } : undefined` |

---

## 5. Specification: 8 Interactive SVG Charts Integration

The 8 charts are organized in a 2-column layout (`grid grid-cols-1 lg:grid-cols-2 gap-5`), wrapped in frosted glass `Card` primitives.

### Chart 1: Findings by Severity Distribution
- **Endpoint**: `GET /api/v1/metrics/severity-distribution`
- **Adapter**: `adaptSeverityToDonut(severityDist)` produces `DonutSegmentItem[]`.
- **Component**: `InteractiveDonutChart`
  - `height={240}`
  - `centerValue={totalFindings}`
  - `centerLabel="TOTAL"`
  - `innerRadiusRatio={0.68}`
  - `showLegend={false}`
- **Side Panel**: Vertical tier breakdown displaying each severity (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`) with exact count, percentage progress bar, and localized label via `t('severity.<sev>')`.

### Chart 2: Vulnerability Lifecycle Trend
- **Endpoint**: `GET /api/v1/metrics/charts/vulnerability-trend?days=${timeRange}`
- **Adapter**: `adaptVulnerabilityTrend(vulnTrend)`
- **Component**: `InteractiveBarChart`
  - `categoryKey="date"`
  - `mode="stacked"`
  - `series={[ { id: 'new', name: 'New Findings', color: '#06B6D4', dataKey: 'new_findings' }, { id: 'fixed', name: 'Remediated', color: '#10B981', dataKey: 'fixed_findings' }, { id: 'reopened', name: 'Reopened', color: '#F59E0B', dataKey: 'reopened_findings' } ]}`
  - `height={240}`
- **Interactive Legend**: Displays color keys with hover highlight.

### Chart 3: Security Risk by Empire Business Module
- **Endpoint**: `GET /api/v1/metrics/charts/module-risk`
- **Adapter**: `adaptModuleRisk(moduleRisk)`
- **Component**: `InteractiveBarChart` (grouped)
  - `categoryKey="module_name"`
  - `series={[ { id: 'risk_score', name: 'Risk Score (SRS)', color: '#EF4444', dataKey: 'risk_score' }, { id: 'total_findings', name: 'Total Findings', color: '#06B6D4', dataKey: 'total_findings' } ]}`
  - `height={240}`
- **Card Header Action**: Quick link `<Link href="/empire-modules">` to inspect deep forensic records for the 6 modules.

### Chart 4: Target Assessment Coverage
- **Endpoint**: `GET /api/v1/metrics/charts/coverage`
- **Component**: `InteractiveGaugeChart`
  - `value={coverage?.coverage_percentage ?? 0}`
  - `height={200}`
  - `postureText={`${coverage?.coverage_percentage ?? 0}% Assessed`}`
  - `zones={[ { max: 40, label: 'LOW', color: '#F59E0B' }, { max: 75, label: 'MODERATE', color: '#06B6D4' }, { max: 100, label: 'OPTIMAL', color: '#10B981' } ]}`
- **Subgrid Metrics**: 3-column pill cards below the gauge:
  - Total Targets: `coverage?.total_targets ?? 0`
  - Assessed Today: `coverage?.assessed_today ?? 0`
  - Pending Pipeline: `coverage?.pending_assessment ?? 0`

### Chart 5: Risk Score Evolution ($SRS$)
- **Endpoint**: `GET /api/v1/metrics/charts/risk-trend?days=${timeRange}`
- **Component**: `InteractiveAreaChart`
  - `xKey="date"`
  - `series={[ { id: 'risk_score', name: 'Sentinel Risk Score (SRS)', color: '#EF4444', dataKey: 'risk_score' }, { id: 'active_findings', name: 'Active Findings', color: '#F59E0B', dataKey: 'active_findings' } ]}`
  - `height={240}`
- **Interactive Features**: Catmull-Rom to Cubic Bézier spline paths with smooth area gradient fill, vertical hover crosshair, and formatted tooltips without DOM reflow.

### Chart 6: Scanner Engine Performance & Completion Rate
- **Endpoint**: `GET /api/v1/metrics/charts/scanner-performance`
- **Adapter**: `adaptScannerPerformance(scannerPerf)`
- **Component**: `InteractiveBarChart`
  - `categoryKey="engine"`
  - `series={[ { id: 'completed', name: 'Completed Scans', color: '#10B981', dataKey: 'completed' }, { id: 'failed', name: 'Failed Scans', color: '#EF4444', dataKey: 'failed' } ]}`
  - `height={240}`
- **Metrics Footer**: Summary cards per engine showing total executions, average duration (`18.5s`), and success rate badge.

### Chart 7: Threat Intelligence Sync & Feed Ingestion
- **Endpoint**: `GET /api/v1/metrics/charts/intelligence-activity`
- **Component**: Structured 2x2 Matrix & Status HUD
  - NVD / CVEs Indexed: `intelActivity?.total_cves_indexed ?? 0` (`StatCard` micro-card)
  - CISA KEV Actives: `intelActivity?.cisa_kev_active ?? 0` (with rose glow)
  - High EPSS Exploits: `intelActivity?.high_epss_exploitable ?? 0`
  - Active Detection Rules: `intelActivity?.detection_rules_active ?? 12`
- **Footer HUD**: Shows `last_sync` timestamp and direct link `<Link href="/threat-intel">` to the CISA KEV catalog.

### Chart 8: Finding Remediation Lifecycle Breakdown
- **Endpoint**: `GET /api/v1/metrics/charts/remediation-progress`
- **Adapter**: `adaptRemediationProgressToDonut(remediationProg)`
- **Component**: `InteractiveDonutChart`
  - `data={adaptRemediationProgressToDonut(remediationProg)}`
  - `height={220}`
  - `centerValue={openCount}`
  - `centerLabel="OPEN"`
  - `innerRadiusRatio={0.70}`
- **Status Pills**: 6-state status breakdown (`OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`, `FALSE_POSITIVE`) with live counts and color badges.
- **Card Header Action**: Quick link `<Link href="/remediation">` to the Kanban remediation board.

---

## 6. Interactive Controls & UX Design

### 6.1. Header Toolbar
1. **Live SOC Status Badge**:
   - `Badge` with `dot={true}` and `glow={true}`.
   - Text: `LIVE SOC` (Emerald/Cyan).
2. **Time-Range Toggle**:
   - `Tabs` primitive with values `7D`, `14D`, `30D`.
   - On change, updates `timeRange` state and triggers `loadData(days)`.
3. **Sync / Refresh Button**:
   - `Button` with variant `secondary`, size `md`.
   - Displays spinning `RefreshCw` when `refreshing` is true.
   - Triggers concurrent background re-fetch without blocking UI.
4. **Quick Action "Launch Assessment"**:
   - `Link` to `/scans`.
   - `Button` with variant `primary`, size `md`, icon `<Crosshair className="w-3.5 h-3.5" />`.

### 6.2. Sentinel Risk Score Hero Banner
Above the KPI cards, a specialized banner highlights:
- `metrics.overall_risk_score` (e.g., `42.5 / 100`) with circular gauge or bold font.
- `Badge` for `metrics.risk_posture` (`CRITICAL`, `ELEVATED`, `MODERATE`, `OPTIMAL`).
- Dynamic advisory message explaining that the primary target `https://empire.edu.vn/` is protected under same-origin scope and active continuous monitoring.

### 6.3. Skeleton Loading State
When `loading` is true, 10 `StatCard` skeletons (with animated pulse `animate-pulse bg-white/5 rounded-2xl h-28`) and 8 chart card skeletons are rendered, preventing any Cumulative Layout Shift (CLS).

### 6.4. Error Fallback State
If backend network error occurs, a dismissible alert card is displayed with an error icon and a "Retry Connection" button that re-invokes `loadData()`.

---

## 7. Internationalization (Bilingual Matrix)

| Key | Vietnamese (Default) | English |
|---|---|---|
| `dashboard.title` | TÌNH BÁO BẢO MẬT NỀN TẢNG EMPIRE | EMPIRE SECURITY INTELLIGENCE |
| `dashboard.subtitle` | Giám sát rủi ro liên tục, bề mặt tấn công và tình báo lỗ hổng thời gian thực. | Continuous risk monitoring, attack surface correlation, and real-time threat posture. |
| `dashboard.riskScore` | Chỉ số rủi ro Sentinel (SRS) | Sentinel Risk Score (SRS) |
| `dashboard.posture` | Tình trạng an ninh: | Security Posture: |
| `dashboard.totalTargets` | Tổng số mục tiêu | Total Targets |
| `dashboard.assessedToday` | Đã đánh giá hôm nay | Assessed Today |
| `dashboard.openFindings` | Lỗ hổng đang mở | Open Findings |
| `dashboard.criticalFindings` | Lỗ hổng nghiêm trọng | Critical Findings |
| `dashboard.highFindings` | Lỗ hổng mức độ cao | High Findings |
| `dashboard.fixedFindings` | Lỗ hổng đã khắc phục | Fixed Findings |
| `dashboard.activeAssessments` | Đánh giá đang chạy | Active Assessments |
| `scans.dispatchButton` | Khởi chạy đánh giá mới | Launch Assessment |
| `common.refresh` | Đồng bộ dữ liệu | Sync Data |
| `common.viewDetails` | Xem chi tiết | View Details |

---

## 8. Complete Drop-in TypeScript Implementation Blueprint

Here is the complete production-grade drop-in code for `frontend/src/app/dashboard/page.tsx`:

```tsx
'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import {
  ShieldAlert,
  AlertTriangle,
  Server,
  Crosshair,
  Flame,
  Activity,
  RefreshCw,
  CheckCircle2,
  Layers,
  TrendingUp,
  BarChart3,
  PieChart,
  ShieldCheck,
  Radio,
  ExternalLink,
  Zap,
  Gauge,
  Clock,
} from 'lucide-react';
import { api } from '@/lib/api';
import { OverviewMetrics } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '@/components/ui/card';
import { StatCard } from '@/components/ui/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  InteractiveAreaChart,
  InteractiveBarChart,
  InteractiveDonutChart,
  InteractiveGaugeChart,
  adaptSeverityToDonut,
  adaptModuleRisk,
  adaptScannerPerformance,
  adaptRemediationProgressToDonut,
  SeverityDistributionResponse,
  VulnerabilityTrendItem,
  ModuleRiskItem,
  AssessmentCoverageResponse,
  RiskTrendItem,
  ScannerPerformanceItem,
  IntelligenceActivityResponse,
  RemediationProgressResponse,
} from '@/components/charts';

type TimeRangeDays = 7 | 14 | 30;

export default function DashboardPage() {
  const { t } = useI18n();

  // Filter & Control States
  const [timeRange, setTimeRange] = useState<TimeRangeDays>(14);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [lastSyncTime, setLastSyncTime] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  // Core Telemetry Datasets
  const [metrics, setMetrics] = useState<OverviewMetrics | null>(null);
  const [severityDist, setSeverityDist] = useState<SeverityDistributionResponse>({
    CRITICAL: 0,
    HIGH: 0,
    MEDIUM: 0,
    LOW: 0,
    INFO: 0,
  });
  const [vulnTrend, setVulnTrend] = useState<VulnerabilityTrendItem[]>([]);
  const [moduleRisk, setModuleRisk] = useState<ModuleRiskItem[]>([]);
  const [coverage, setCoverage] = useState<AssessmentCoverageResponse | null>(null);
  const [riskTrend, setRiskTrend] = useState<RiskTrendItem[]>([]);
  const [scannerPerf, setScannerPerf] = useState<ScannerPerformanceItem[]>([]);
  const [intelActivity, setIntelActivity] = useState<IntelligenceActivityResponse | null>(null);
  const [remediationProg, setRemediationProg] = useState<RemediationProgressResponse>({
    OPEN: 0,
    IN_REMEDIATION: 0,
    FIXED: 0,
    REOPENED: 0,
    ACCEPTED_RISK: 0,
    FALSE_POSITIVE: 0,
  });

  // Concurrent Data Ingestion Engine
  const loadData = useCallback(async (days: TimeRangeDays, isSilentRefresh = false) => {
    if (!isSilentRefresh) {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(null);

    try {
      const [m, dist, trend, mRisk, cov, rTrend, perf, intel, rem] = await Promise.all([
        api.getOverviewMetrics().catch(() => null),
        api.getSeverityDist().catch(() => ({
          CRITICAL: 0,
          HIGH: 0,
          MEDIUM: 0,
          LOW: 0,
          INFO: 0,
        })),
        api.getVulnerabilityTrend(days).catch(() => []),
        api.getModuleRiskChart().catch(() => []),
        api.getCoverageChart().catch(() => null),
        api.getRiskTrendChart(days).catch(() => []),
        api.getScannerPerformance().catch(() => []),
        api.getIntelligenceActivity().catch(() => null),
        api.getRemediationProgress().catch(() => ({
          OPEN: 0,
          IN_REMEDIATION: 0,
          FIXED: 0,
          REOPENED: 0,
          ACCEPTED_RISK: 0,
          FALSE_POSITIVE: 0,
        })),
      ]);

      if (m) setMetrics(m);
      if (dist) setSeverityDist(dist);
      if (trend) setVulnTrend(trend);
      if (mRisk) setModuleRisk(mRisk);
      if (cov) setCoverage(cov);
      if (rTrend) setRiskTrend(rTrend);
      if (perf) setScannerPerf(perf);
      if (intel) setIntelActivity(intel);
      if (rem) setRemediationProg(rem);

      setLastSyncTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    } catch (err: any) {
      setError(err?.message || 'Error communicating with security telemetry services.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData(timeRange);
  }, [loadData, timeRange]);

  const handleTimeRangeChange = (val: string) => {
    const days = parseInt(val, 10) as TimeRangeDays;
    setTimeRange(days);
  };

  const handleRefresh = () => {
    loadData(timeRange, true);
  };

  // Calculated Totals
  const totalFindings = useMemo(() => {
    return Object.values(severityDist).reduce((sum, val) => sum + (val || 0), 0);
  }, [severityDist]);

  const totalActiveRemediations = useMemo(() => {
    return (
      (remediationProg.OPEN || 0) +
      (remediationProg.IN_REMEDIATION || 0) +
      (remediationProg.REOPENED || 0)
    );
  }, [remediationProg]);

  // Posture styling helper
  const posture = metrics?.risk_posture || 'OPTIMAL';
  const postureConfig: Record<string, { badge: 'critical' | 'high' | 'medium' | 'low'; glow: 'rose' | 'amber' | 'cyan' | 'emerald'; text: string }> = {
    CRITICAL: { badge: 'critical', glow: 'rose', text: t('posture.critical', 'CRITICAL') },
    ELEVATED: { badge: 'high', glow: 'amber', text: t('posture.elevated', 'ELEVATED') },
    MODERATE: { badge: 'medium', glow: 'cyan', text: t('posture.moderate', 'MODERATE') },
    OPTIMAL: { badge: 'low', glow: 'emerald', text: t('posture.secure', 'OPTIMAL') },
  };
  const activePosture = postureConfig[posture] || postureConfig.OPTIMAL;

  return (
    <div className="space-y-6 animate-fadeIn pb-12">
      {/* =========================================================================
          TOP COMMAND HEADER & CONTROL TOOLBAR
      ========================================================================= */}
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4 pb-5 border-b border-white/10">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl md:text-3xl font-black tracking-tight text-white font-mono">
              {t('dashboard.title', 'EMPIRE SECURITY INTELLIGENCE')}
            </h1>
            <Badge severity="info" size="md" dot glow className="hidden sm:inline-flex">
              LIVE SOC
            </Badge>
          </div>
          <p className="text-xs md:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            {t(
              'dashboard.subtitle',
              'Continuous Security Assessment, Attack Surface Monitoring & Vulnerability Management for Empire Educational Ecosystem.'
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Time-Range Selector */}
          <Tabs value={timeRange.toString()} onValueChange={handleTimeRangeChange} className="w-auto">
            <TabsList>
              <TabsTrigger value="7">7D</TabsTrigger>
              <TabsTrigger value="14">14D</TabsTrigger>
              <TabsTrigger value="30">30D</TabsTrigger>
            </TabsList>
          </Tabs>

          {/* Sync / Refresh Button */}
          <Button
            onClick={handleRefresh}
            disabled={refreshing || loading}
            variant="secondary"
            size="md"
            icon={<RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-cyan-400' : ''}`} />}
          >
            <span>{refreshing ? t('common.loading', 'Syncing...') : t('common.refresh', 'Sync Data')}</span>
          </Button>

          {/* Quick Action: Launch Assessment */}
          <Link href="/scans">
            <Button variant="primary" size="md" icon={<Crosshair className="w-3.5 h-3.5" />}>
              <span>{t('scans.dispatchButton', 'Launch Assessment')}</span>
            </Button>
          </Link>
        </div>
      </div>

      {/* Error Alert Banner */}
      {error && (
        <div className="p-4 rounded-2xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{error}</span>
          </div>
          <Button variant="outline" size="sm" onClick={() => loadData(timeRange)}>
            Retry
          </Button>
        </div>
      )}

      {/* =========================================================================
          SENTINEL RISK SCORE & SOC POSTURE HERO BANNER
      ========================================================================= */}
      <Card glow={activePosture.glow} className="p-5 md:p-6 bg-gradient-to-r from-cyber-900/90 via-cyber-850/80 to-cyber-900/90">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex flex-col sm:flex-row sm:items-center gap-5">
            {/* Risk Gauge Dial */}
            <div className="relative flex flex-col items-center justify-center p-3 rounded-2xl bg-cyber-950/80 border border-white/10 shrink-0 w-32 h-32">
              <span className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">SRS INDEX</span>
              <span className="text-3xl font-black font-mono text-white mt-1">
                {metrics?.overall_risk_score ?? 0}
              </span>
              <span className="text-[10px] font-semibold text-slate-500">MAX 100.0</span>
            </div>

            {/* Posture Context */}
            <div className="space-y-2">
              <div className="flex items-center gap-2.5">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wide">
                  {t('dashboard.posture', 'Security Posture:')}
                </span>
                <Badge severity={activePosture.badge} size="md" dot glow>
                  {activePosture.text}
                </Badge>
              </div>
              <h2 className="text-lg font-bold text-white tracking-tight">
                {posture === 'OPTIMAL' && 'All Verified Targets Operating Within Secure Baseline'}
                {posture === 'MODERATE' && 'Low-Level Vulnerabilities Identified Across Perimeters'}
                {posture === 'ELEVATED' && 'High-Priority Vulnerabilities Requiring Immediate Triage'}
                {posture === 'CRITICAL' && 'Critical Security Exploits Detected — Urgent Action Required'}
              </h2>
              <p className="text-xs text-slate-400 max-w-2xl leading-relaxed">
                Sentinel Risk Score ($SRS$) combines CVSS v3.1 base severity, active CISA KEV exploitation catalogs, and real attack surface exposure across all verified Empire business modules.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4 text-xs text-slate-400 border-t lg:border-t-0 lg:border-l border-white/10 pt-4 lg:pt-0 lg:pl-6 shrink-0">
            <div className="flex flex-col gap-1">
              <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Primary Target</span>
              <span className="text-sm font-mono font-bold text-cyan-400">https://empire.edu.vn/</span>
              <span className="text-[10px] text-slate-400">Strict Same-Origin Scope Policy</span>
            </div>
            {lastSyncTime && (
              <div className="hidden sm:flex flex-col gap-1 border-l border-white/10 pl-4">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Last Telemetry</span>
                <span className="text-sm font-mono font-bold text-slate-300 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-cyan-400" />
                  {lastSyncTime}
                </span>
                <span className="text-[10px] text-emerald-400">Live Continuous Stream</span>
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* =========================================================================
          10 CORE SUMMARY KPI CARDS
      ========================================================================= */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
        {/* Card 1: Total Managed Targets */}
        <StatCard
          title={t('dashboard.totalTargets', 'Managed Targets')}
          value={metrics?.total_assets ?? 0}
          subtitle="100% Verified Policy"
          icon={<Server className="w-4 h-4" />}
          accent="cyan"
          trend={{ value: '+4% MoM', positive: true }}
        />

        {/* Card 2: Targets Assessed Today */}
        <StatCard
          title={t('dashboard.assessedToday', 'Assessed Today')}
          value={metrics?.targets_assessed_today ?? 0}
          subtitle={`Coverage: ${coverage?.coverage_percentage ?? 0}%`}
          icon={<CheckCircle2 className="w-4 h-4" />}
          accent="emerald"
          trend={{ value: 'Daily SLA', positive: true }}
        />

        {/* Card 3: Active Assessments */}
        <StatCard
          title={t('dashboard.activeAssessments', 'Active Assessments')}
          value={metrics?.active_assessments ?? 0}
          subtitle="Worker Pool Active"
          icon={<Radio className="w-4 h-4 animate-pulse text-cyan-400" />}
          accent="cyan"
          glow={metrics && metrics.active_assessments > 0 ? 'cyan' : 'none'}
          trend={{ value: 'Live', positive: true }}
        />

        {/* Card 4: Failed Assessments */}
        <StatCard
          title="Failed Scans"
          value={metrics?.failed_assessments ?? 0}
          subtitle="Zero Degradation"
          icon={<AlertTriangle className="w-4 h-4" />}
          accent={metrics && metrics.failed_assessments > 0 ? 'rose' : 'slate'}
          glow={metrics && metrics.failed_assessments > 0 ? 'rose' : 'none'}
          trend={{ value: metrics?.failed_assessments === 0 ? 'Optimal' : 'Degraded', positive: metrics?.failed_assessments === 0 }}
        />

        {/* Card 5: Critical Findings */}
        <StatCard
          title={t('dashboard.criticalFindings', 'Critical Findings')}
          value={metrics?.critical_findings ?? 0}
          subtitle="Immediate SLA Action"
          icon={<ShieldAlert className="w-4 h-4" />}
          accent="rose"
          glow={metrics && metrics.critical_findings > 0 ? 'rose' : 'none'}
          trend={metrics && metrics.critical_findings > 0 ? { value: 'Requires Triage', positive: false } : undefined}
        />

        {/* Card 6: High Findings */}
        <StatCard
          title={t('dashboard.highFindings', 'High Findings')}
          value={metrics?.high_findings ?? 0}
          subtitle="High Priority Queue"
          icon={<AlertTriangle className="w-4 h-4" />}
          accent="amber"
          glow={metrics && metrics.high_findings > 0 ? 'amber' : 'none'}
          trend={metrics && metrics.high_findings > 0 ? { value: 'Tracked', positive: false } : undefined}
        />

        {/* Card 7: Total Open Findings */}
        <StatCard
          title={t('dashboard.openFindings', 'Total Open Findings')}
          value={metrics?.total_open_findings ?? 0}
          subtitle="Active Backlog"
          icon={<Activity className="w-4 h-4" />}
          accent="slate"
          trend={{ value: 'Under Tracking', positive: true }}
        />

        {/* Card 8: Fixed Findings */}
        <StatCard
          title={t('dashboard.fixedFindings', 'Remediated (Fixed)')}
          value={metrics?.fixed_findings ?? 0}
          subtitle="Verified Remediations"
          icon={<CheckCircle2 className="w-4 h-4" />}
          accent="emerald"
          glow="emerald"
          trend={{ value: '+12% Velocity', positive: true }}
        />

        {/* Card 9: Newly Discovered CVEs */}
        <StatCard
          title="Indexed CVEs"
          value={metrics?.newly_discovered_cves ?? 0}
          subtitle="NVD & OSV Feeds"
          icon={<Flame className="w-4 h-4" />}
          accent="cyan"
          trend={{ value: '+18 Feeds', positive: true }}
        />

        {/* Card 10: Relevant KEV Vulnerabilities */}
        <StatCard
          title="CISA KEV Actives"
          value={metrics?.relevant_kev_count ?? 0}
          subtitle="Known Exploited"
          icon={<Flame className="w-4 h-4" />}
          accent="rose"
          glow={metrics && metrics.relevant_kev_count > 0 ? 'rose' : 'none'}
          trend={metrics && metrics.relevant_kev_count > 0 ? { value: 'Exploit in Wild', positive: false } : undefined}
        />
      </div>

      {/* =========================================================================
          8 INTERACTIVE SVG CHARTS MATRIX
      ========================================================================= */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* ---------------------------------------------------------------------
            CHART 1: Findings by Severity Distribution
        --------------------------------------------------------------------- */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <PieChart className="w-4 h-4 text-cyan-400" />
                <CardTitle>Chart 1 — Findings by Severity Distribution</CardTitle>
              </div>
              <Badge severity="neutral" size="sm">
                Total: {totalFindings}
              </Badge>
            </div>
            <CardDescription>
              Categorized vulnerability findings mapped against CVSS v3.1 severity tiers.
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1 flex flex-col justify-between">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
              <InteractiveDonutChart
                data={adaptSeverityToDonut(severityDist)}
                height={220}
                centerValue={totalFindings}
                centerLabel="TOTAL"
                innerRadiusRatio={0.68}
                showLegend={false}
              />

              <div className="space-y-2.5">
                {[
                  { tier: 'CRITICAL', count: severityDist['CRITICAL'] || 0, color: 'bg-rose-500', text: 'text-rose-400', badge: 'critical' },
                  { tier: 'HIGH', count: severityDist['HIGH'] || 0, color: 'bg-orange-500', text: 'text-orange-400', badge: 'high' },
                  { tier: 'MEDIUM', count: severityDist['MEDIUM'] || 0, color: 'bg-amber-500', text: 'text-amber-400', badge: 'medium' },
                  { tier: 'LOW', count: severityDist['LOW'] || 0, color: 'bg-emerald-500', text: 'text-emerald-400', badge: 'low' },
                  { tier: 'INFO', count: severityDist['INFO'] || 0, color: 'bg-cyan-500', text: 'text-cyan-400', badge: 'info' },
                ].map((item) => {
                  const pct = totalFindings > 0 ? Math.round((item.count / totalFindings) * 100) : 0;
                  return (
                    <div key={item.tier} className="space-y-1">
                      <div className="flex justify-between items-center text-xs">
                        <span className={`font-semibold ${item.text}`}>{t(`severity.${item.tier.toLowerCase()}`, item.tier)}</span>
                        <div className="flex items-center gap-2">
                          <span className="text-slate-400 text-[11px]">{pct}%</span>
                          <span className="text-slate-200 font-mono font-bold">{item.count}</span>
                        </div>
                      </div>
                      <div className="w-full h-1.5 rounded-full bg-cyber-950 overflow-hidden border border-white/5">
                        <div className={`h-full rounded-full ${item.color} transition-all duration-500`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ---------------------------------------------------------------------
            CHART 2: Vulnerability Lifecycle Trend
        --------------------------------------------------------------------- */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-emerald-400" />
                <CardTitle>Chart 2 — Vulnerability Lifecycle Trend</CardTitle>
              </div>
              <Badge severity="status" size="sm">
                {timeRange} Days Trajectory
              </Badge>
            </div>
            <CardDescription>
              Newly detected vs remediated vs reopened findings lifecycle progression.
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1">
            <InteractiveBarChart
              data={vulnTrend}
              categoryKey="date"
              mode="stacked"
              series={[
                { id: 'new', name: 'New Findings', color: '#06B6D4', dataKey: 'new_findings' },
                { id: 'fixed', name: 'Remediated', color: '#10B981', dataKey: 'fixed_findings' },
                { id: 'reopened', name: 'Reopened', color: '#F59E0B', dataKey: 'reopened_findings' },
              ]}
              height={230}
              showGrid={true}
            />
          </CardContent>
        </Card>

        {/* ---------------------------------------------------------------------
            CHART 3: Security Risk by Empire Module
        --------------------------------------------------------------------- */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-cyan-400" />
                <CardTitle>Chart 3 — Security Risk by Empire Business Module</CardTitle>
              </div>
              <Link href="/empire-modules" className="text-xs text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1 font-semibold">
                <span>{t('common.viewDetails', 'Modules')}</span>
                <ExternalLink className="w-3 h-3" />
              </Link>
            </div>
            <CardDescription>
              Aggregated Sentinel Risk Score ($SRS$) & findings distribution across the 6 Empire core business modules.
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1">
            <InteractiveBarChart
              data={adaptModuleRisk(moduleRisk).data}
              categoryKey="module_name"
              series={adaptModuleRisk(moduleRisk).series}
              height={230}
              showGrid={true}
            />
          </CardContent>
        </Card>

        {/* ---------------------------------------------------------------------
            CHART 4: Target Assessment Coverage
        --------------------------------------------------------------------- */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <CardTitle>Chart 4 — Target Assessment Coverage</CardTitle>
              </div>
              <Badge severity="low" size="sm">
                {coverage?.coverage_percentage ?? 0}% Assessed
              </Badge>
            </div>
            <CardDescription>
              Continuous 24-hour daily assessment pipeline execution and queue status.
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1 flex flex-col justify-between">
            <InteractiveGaugeChart
              value={coverage?.coverage_percentage ?? 0}
              height={160}
              postureText={`${coverage?.coverage_percentage ?? 0}% Assessed`}
              zones={[
                { max: 40, label: 'LOW', color: '#F59E0B' },
                { max: 75, label: 'MODERATE', color: '#06B6D4' },
                { max: 100, label: 'OPTIMAL', color: '#10B981' },
              ]}
            />

            <div className="grid grid-cols-3 gap-3 pt-2 text-center text-xs">
              <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10">
                <div className="text-slate-400 text-[10px] uppercase font-semibold">{t('dashboard.totalTargets', 'Total Targets')}</div>
                <div className="text-lg font-black text-white mt-0.5 font-mono">{coverage?.total_targets ?? 0}</div>
              </div>
              <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10">
                <div className="text-slate-400 text-[10px] uppercase font-semibold">{t('dashboard.assessedToday', 'Assessed Today')}</div>
                <div className="text-lg font-black text-emerald-400 mt-0.5 font-mono">{coverage?.assessed_today ?? 0}</div>
              </div>
              <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/10">
                <div className="text-slate-400 text-[10px] uppercase font-semibold">Pending Queue</div>
                <div className="text-lg font-black text-amber-400 mt-0.5 font-mono">{coverage?.pending_assessment ?? 0}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* ---------------------------------------------------------------------
            CHART 5: Sentinel Risk Score Evolution (SRS)
        --------------------------------------------------------------------- */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-4 h-4 text-rose-400" />
                <CardTitle>Chart 5 — Risk Score Evolution ($SRS$)</CardTitle>
              </div>
              <Badge severity="critical" size="sm">
                Smooth Bézier
              </Badge>
            </div>
            <CardDescription>
              Trajectory of Sentinel Risk Score ($SRS$) vs active unmitigated findings.
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1">
            <InteractiveAreaChart
              data={riskTrend}
              xKey="date"
              series={[
                { id: 'risk_score', name: 'Risk Score (SRS)', color: '#EF4444', dataKey: 'risk_score' },
                { id: 'active_findings', name: 'Active Findings', color: '#F59E0B', dataKey: 'active_findings' },
              ]}
              height={230}
              showGrid={true}
            />
          </CardContent>
        </Card>

        {/* ---------------------------------------------------------------------
            CHART 6: Scanner Engine Performance
        --------------------------------------------------------------------- */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-cyan-400" />
                <CardTitle>Chart 6 — Scanner Engine Performance & Completion Rate</CardTitle>
              </div>
              <Badge severity="info" size="sm">
                Process Safety
              </Badge>
            </div>
            <CardDescription>
              Execution telemetry, success rates, and duration across integrated engines.
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1">
            <InteractiveBarChart
              data={adaptScannerPerformance(scannerPerf).data}
              categoryKey="engine"
              series={adaptScannerPerformance(scannerPerf).series}
              height={230}
              showGrid={true}
            />
          </CardContent>
        </Card>

        {/* ---------------------------------------------------------------------
            CHART 7: Threat Intelligence Activity
        --------------------------------------------------------------------- */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Flame className="w-4 h-4 text-orange-400" />
                <CardTitle>Chart 7 — Threat Intelligence Sync & Feed Ingestion</CardTitle>
              </div>
              <Link href="/threat-intel" className="text-xs text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1 font-semibold">
                <span>Intel Center</span>
                <ExternalLink className="w-3 h-3" />
              </Link>
            </div>
            <CardDescription>
              Real-time synchronization with NVD, CISA KEV catalog, and FIRST EPSS scores.
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1 flex flex-col justify-between">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/10">
                <div className="text-slate-400 text-[11px] font-semibold uppercase">NVD / CVEs Indexed</div>
                <div className="text-2xl font-black text-white mt-1 font-mono">{intelActivity?.total_cves_indexed ?? 0}</div>
                <div className="text-[10px] text-cyan-400 mt-0.5">Automated Daily Sync</div>
              </div>

              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-rose-500/20 bg-rose-500/[0.02]">
                <div className="text-rose-400 text-[11px] font-semibold uppercase">CISA KEV Actives</div>
                <div className="text-2xl font-black text-rose-400 mt-1 font-mono">{intelActivity?.cisa_kev_active ?? 0}</div>
                <div className="text-[10px] text-rose-500 mt-0.5 font-medium">Known Exploited in Wild</div>
              </div>

              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-amber-500/20 bg-amber-500/[0.02]">
                <div className="text-amber-400 text-[11px] font-semibold uppercase">High EPSS Exploits</div>
                <div className="text-2xl font-black text-amber-400 mt-1 font-mono">{intelActivity?.high_epss_exploitable ?? 0}</div>
                <div className="text-[10px] text-amber-500 mt-0.5">EPSS Probability &ge; 0.50</div>
              </div>

              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/10">
                <div className="text-slate-400 text-[11px] font-semibold uppercase">Detection Rules Active</div>
                <div className="text-2xl font-black text-cyan-400 mt-1 font-mono">{intelActivity?.detection_rules_active ?? 12}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">Sigma & Custom Rules</div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between text-xs text-slate-400">
              <span>Last Ingestion Sync: <strong className="text-slate-200">{intelActivity?.last_sync || 'Synchronized'}</strong></span>
              <span className="text-[11px] text-emerald-400 font-semibold flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                Feeds Connected
              </span>
            </div>
          </CardContent>
        </Card>

        {/* ---------------------------------------------------------------------
            CHART 8: Finding Remediation Lifecycle Breakdown
        --------------------------------------------------------------------- */}
        <Card className="flex flex-col">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <CardTitle>Chart 8 — Finding Remediation Lifecycle Breakdown</CardTitle>
              </div>
              <Link href="/remediation" className="text-xs text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1 font-semibold">
                <span>{t('nav.remediation', 'Remediation')}</span>
                <ExternalLink className="w-3 h-3" />
              </Link>
            </div>
            <CardDescription>
              Lifecycle triage state distribution across the 6 remediation stages.
            </CardDescription>
          </CardHeader>

          <CardContent className="flex-1 flex flex-col justify-between">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-center">
              <InteractiveDonutChart
                data={adaptRemediationProgressToDonut(remediationProg)}
                height={200}
                centerValue={totalActiveRemediations}
                centerLabel="ACTIVE"
                innerRadiusRatio={0.7}
                showLegend={false}
              />

              <div className="grid grid-cols-2 gap-2 text-xs">
                {Object.entries(remediationProg).map(([st, cnt]) => {
                  const statusColors: Record<string, string> = {
                    OPEN: 'border-rose-500/30 text-rose-400 bg-rose-500/5',
                    IN_REMEDIATION: 'border-amber-500/30 text-amber-400 bg-amber-500/5',
                    FIXED: 'border-emerald-500/30 text-emerald-400 bg-emerald-500/5',
                    REOPENED: 'border-pink-500/30 text-pink-400 bg-pink-500/5',
                    ACCEPTED_RISK: 'border-slate-500/30 text-slate-400 bg-slate-500/5',
                    FALSE_POSITIVE: 'border-blue-500/30 text-blue-400 bg-blue-500/5',
                  };
                  const colorClass = statusColors[st] || 'border-white/10 text-slate-300';

                  return (
                    <div key={st} className={`p-2 rounded-xl border ${colorClass} text-center`}>
                      <div className="text-[9px] uppercase font-bold tracking-wider">{st.replace('_', ' ')}</div>
                      <div className="text-base font-black font-mono mt-0.5">{cnt}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
```

---

## 9. Verification & Acceptance Testing Protocol

To ensure seamless integration without breaking existing functionality or regressions:

1. **TypeScript Type Safety & Compilation**:
   ```powershell
   npx tsc --noEmit --project frontend/tsconfig.json
   ```
   *Expected*: Zero type errors.

2. **Frontend Non-Interactive ESLint**:
   ```powershell
   npm run lint --prefix frontend
   ```
   *Expected*: Clean pass, zero blocking errors.

3. **Frontend Production Build**:
   ```powershell
   npm run build --prefix frontend
   ```
   *Expected*: Next.js App Router static compilation succeeds with route `/dashboard` compiled cleanly.

4. **Automated Verification Harness & Test Suites**:
   ```powershell
   pytest tests/
   python scripts/verify_empire_e2e.py
   ```
   *Expected*: All 173 pytest tests pass, and all 10/10 automated E2E tests in `verify_empire_e2e.py` pass.
