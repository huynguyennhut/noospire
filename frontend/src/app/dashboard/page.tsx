'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
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
import { OverviewMetrics, Asset } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import DashboardSummaryPanel from '@/components/console/DashboardSummaryPanel';
import { useToast } from '@/components/ui/toast';
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

// No baseline/sample datasets: every number below comes from the API or is shown as unknown (—).
const EMPTY_SEVERITY: SeverityDistributionResponse = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 };

export default function DashboardPage() {
  const { t } = useI18n();
  const router = useRouter();
  const { toast } = useToast();

  // Filter & Control States (Defaults to 7 calendar days per product contract)
  const [timeRange, setTimeRange] = useState<TimeRangeDays>(7);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [lastSyncTime, setLastSyncTime] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  // Target Assets & Ultra Scan Selection
  const [assets, setAssets] = useState<Asset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string>('ALL');
  const [ultraLaunching, setUltraLaunching] = useState<boolean>(false);

  // Core Telemetry Datasets
  const [metrics, setMetrics] = useState<OverviewMetrics | null>(null);
  const [severityDist, setSeverityDist] = useState<SeverityDistributionResponse>(EMPTY_SEVERITY);
  const [vulnTrend, setVulnTrend] = useState<VulnerabilityTrendItem[]>([]);
  const [moduleRisk, setModuleRisk] = useState<ModuleRiskItem[]>([]);
  const [coverage, setCoverage] = useState<AssessmentCoverageResponse | null>(null);
  const [riskTrend, setRiskTrend] = useState<RiskTrendItem[]>([]);
  const [scannerPerf, setScannerPerf] = useState<ScannerPerformanceItem[]>([]);
  const [intelActivity, setIntelActivity] = useState<IntelligenceActivityResponse | null>(null);
  const [remediationProg, setRemediationProg] = useState<RemediationProgressResponse>({
    OPEN: 0, IN_REMEDIATION: 0, FIXED: 0, REOPENED: 0, ACCEPTED_RISK: 0, FALSE_POSITIVE: 0,
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
      const [m, dist, trend, mRisk, cov, rTrend, perf, intel, rem, assetsRes] = await Promise.all([
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
        api.listAssets().catch(() => ({ items: [], total: 0 })),
      ]);

      if (m && typeof m === 'object' && 'overall_risk_score' in m) setMetrics(m);
      if (dist && typeof dist === 'object') setSeverityDist(dist as SeverityDistributionResponse);
      if (Array.isArray(trend)) setVulnTrend(trend as VulnerabilityTrendItem[]);
      if (Array.isArray(mRisk)) setModuleRisk(mRisk as ModuleRiskItem[]);
      if (cov && typeof cov === 'object') setCoverage(cov as AssessmentCoverageResponse);
      if (Array.isArray(rTrend)) setRiskTrend(rTrend as RiskTrendItem[]);
      if (Array.isArray(perf)) setScannerPerf(perf as ScannerPerformanceItem[]);
      if (intel && typeof intel === 'object') setIntelActivity(intel as IntelligenceActivityResponse);
      if (rem && typeof rem === 'object') setRemediationProg(rem as RemediationProgressResponse);
      if (assetsRes && Array.isArray((assetsRes as any).items)) setAssets((assetsRes as any).items);

      setLastSyncTime(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Error communicating with security telemetry services.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const handleRunUltraScan = async () => {
    try {
      setUltraLaunching(true);
      const idempotencyKey = `ultra-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      const scopeParam = selectedAssetId === 'ALL' ? 'ALL' : [selectedAssetId];
      const res = await api.launchUltraScan({
        scope: scopeParam,
        idempotency_key: idempotencyKey,
        initiator: 'dashboard_owner_action',
      });
      toast({
        title: 'Ultra Scan Dispatched',
        description: `Batch ${res.batch_id} initiated across ${res.independent_execution_targets} targets (${res.engine_executions_count} engine executions).`,
        variant: 'success',
        duration: 5000,
      });
      router.push(res.tracker_link);
    } catch (err: unknown) {
      toast({
        title: 'Ultra Scan Launch Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
        duration: 6000,
      });
    } finally {
      setUltraLaunching(false);
    }
  };

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
  // No data (backend lost, owner-only metrics, empty estate) is UNKNOWN, never OPTIMAL/green.
  const posture = metrics?.risk_posture || 'UNKNOWN';
  const postureConfig: Record<string, { badge: 'critical' | 'high' | 'medium' | 'low' | 'info'; glow: 'rose' | 'amber' | 'cyan' | 'emerald'; text: string }> = {
    UNKNOWN: { badge: 'info', glow: 'cyan', text: t('posture.unknown', 'UNKNOWN') },
    CRITICAL: { badge: 'critical', glow: 'rose', text: t('posture.critical', 'CRITICAL') },
    ELEVATED: { badge: 'high', glow: 'amber', text: t('posture.elevated', 'ELEVATED') },
    MODERATE: { badge: 'medium', glow: 'cyan', text: t('posture.moderate', 'MODERATE') },
    OPTIMAL: { badge: 'low', glow: 'emerald', text: t('posture.secure', 'OPTIMAL') },
  };
  const activePosture = postureConfig[posture] || postureConfig.UNKNOWN;

  return (
    <div className="space-y-6 animate-fadeIn pb-12">
      <DashboardSummaryPanel />
      {/* =========================================================================
          TOP COMMAND HEADER & CONTROL TOOLBAR
      ========================================================================= */}
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4 pb-5 border-b border-white/10">
        <div>
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-gradient-to-b from-white/[0.09] via-white/[0.04] to-white/[0.01] border border-white/15 p-1 flex items-center justify-center shadow-[inset_0_1px_2px_rgba(255,255,255,0.2),0_4px_12px_rgba(0,0,0,0.5)] backdrop-blur-xl shrink-0">
              <Image
                src="/brand/logo-white-emblem.png"
                alt="NOOSFORGE Emblem"
                width={26}
                height={26}
                className="w-full h-full object-contain filter drop-shadow-[0_2px_4px_rgba(255,255,255,0.2)]"
                priority
              />
            </div>
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
            icon={<RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-white' : ''}`} />}
          >
            <span>{refreshing ? t('common.loading', 'Syncing...') : t('common.refresh', 'Sync Data')}</span>
          </Button>

          {/* Target Selector */}
          <select
            value={selectedAssetId}
            onChange={(e) => setSelectedAssetId(e.target.value)}
            className="bg-black/60 border border-white/10 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:border-cyan-500/50 backdrop-blur-md"
            title="Select target asset or run estate-wide"
          >
            <option value="ALL">{`All assets in scope (${assets.length})`}</option>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name || a.target_locator}
              </option>
            ))}
          </select>

          {/* Quick Action: Run Ultra Scan */}
          <Button
            variant="glass"
            size="md"
            onClick={handleRunUltraScan}
            disabled={ultraLaunching}
            className="border-cyan-500/40 text-cyan-300 hover:bg-cyan-950/40 hover:text-cyan-200 shadow-[0_0_15px_rgba(6,182,212,0.15)]"
            icon={<Zap className={`w-3.5 h-3.5 text-cyan-400 ${ultraLaunching ? 'animate-pulse' : ''}`} />}
          >
            <span>{ultraLaunching ? 'Launching Ultra Scan...' : 'Run Ultra Scan'}</span>
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
      <Card glow={activePosture.glow} className="relative overflow-hidden p-5 md:p-6 bg-gradient-to-r from-nf-900/90 via-nf-850/80 to-nf-900/90 border border-white/[0.08] backdrop-blur-xl">
        {/* Subtle Decorative Hero Watermark */}
        <div
          aria-hidden="true"
          className="absolute right-0 top-0 bottom-0 w-80 pointer-events-none select-none overflow-hidden opacity-[0.035] flex items-center justify-end pr-6"
        >
          <div
            className="w-56 h-56 bg-contain bg-no-repeat bg-right"
            style={{
              backgroundImage: 'url(/brand/logo-white.png)',
              maskImage: 'radial-gradient(ellipse at center, rgba(0,0,0,1) 20%, rgba(0,0,0,0) 75%)',
              WebkitMaskImage: 'radial-gradient(ellipse at center, rgba(0,0,0,1) 20%, rgba(0,0,0,0) 75%)',
            }}
          />
        </div>
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-6">
          <div className="flex flex-col sm:flex-row sm:items-center gap-5">
            {/* Risk Gauge Dial */}
            <div className="relative flex flex-col items-center justify-center p-3 rounded-2xl bg-nf-950/80 border border-white/10 shrink-0 w-32 h-32 backdrop-blur-md">
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
                {posture === 'OPTIMAL' && 'No open findings in the latest measured data (see data state above)'}
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
              <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Selected scope</span>
              <span className="text-sm font-mono font-bold text-white">
                {selectedAssetId === 'ALL' ? `${assets.length} asset(s)` : (assets.find((a) => a.id === selectedAssetId)?.target_locator || '—')}
              </span>
            </div>
            {lastSyncTime && (
              <div className="hidden sm:flex flex-col gap-1 border-l border-white/10 pl-4">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">Last Telemetry</span>
                <span className="text-sm font-mono font-bold text-slate-300 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-white" />
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
          subtitle="In your scope"
          icon={<Server className="w-4 h-4" />}
          accent="slate"
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
          icon={<Radio className="w-4 h-4 animate-pulse text-white" />}
          accent="slate"
          glow="none"
          trend={{ value: 'Live', positive: true }}
        />

        {/* Card 4: Failed Assessments */}
        <StatCard
          title="Failed Scans"
          value={metrics?.failed_assessments ?? 0}
          subtitle={metrics ? `${metrics.failed_assessments} failed` : 'unknown'}
          icon={<AlertTriangle className="w-4 h-4" />}
          accent={metrics && metrics.failed_assessments > 0 ? 'rose' : 'slate'}
          glow={metrics && metrics.failed_assessments > 0 ? 'rose' : 'none'}
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
        />

        {/* Card 9: Newly Discovered CVEs */}
        <StatCard
          title="Indexed CVEs"
          value={metrics?.newly_discovered_cves ?? 0}
          subtitle="NVD & OSV Feeds"
          icon={<Flame className="w-4 h-4" />}
          accent="slate"
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
                <PieChart className="w-4 h-4 text-white" />
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
                  { tier: 'INFO', count: severityDist['INFO'] || 0, color: 'bg-sky-500', text: 'text-sky-400', badge: 'info' },
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
                      <div className="w-full h-1.5 rounded-full bg-nf-950 overflow-hidden border border-white/5">
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
                { id: 'new', name: 'New Findings', color: '#F4F4F5', dataKey: 'new_findings' },
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
                <Layers className="w-4 h-4 text-white" />
                <CardTitle>Chart 3 — Security Risk by Empire Business Module</CardTitle>
              </div>
              <Link href="/empire-modules" className="text-xs text-nf-300 hover:text-white inline-flex items-center gap-1 font-semibold">
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
                <BarChart3 className="w-4 h-4 text-white" />
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
              <Link href="/threat-intel" className="text-xs text-nf-300 hover:text-white inline-flex items-center gap-1 font-semibold">
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
                <div className="text-[10px] text-nf-400 mt-0.5">Automated Daily Sync</div>
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
                <div className="text-2xl font-black text-white mt-1 font-mono">{intelActivity?.detection_rules_active ?? 12}</div>
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
              <Link href="/remediation" className="text-xs text-nf-300 hover:text-white inline-flex items-center gap-1 font-semibold">
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
