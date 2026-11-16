'use client';

import React, { useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  Server,
  Database,
  Cpu,
  Clock,
  RefreshCw,
  HardDrive,
  ShieldCheck,
  Zap,
  DownloadCloud,
  Play,
  X,
  Gauge,
  ExternalLink,
} from 'lucide-react';
import { api, EngineHealthResponse, EngineTestResult, EngineUpdateCheckResult } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { useToast } from '@/components/ui/toast';
import { Badge } from '@/components/ui/badge';

export default function SystemHealthPage() {
  const { t, locale } = useI18n();
  const L = (vi: string, en: string) => locale === 'vi' ? vi : en;
  const { toast } = useToast();
  const [healthData, setHealthData] = useState<any>(null);
  const [engineHealth, setEngineHealth] = useState<EngineHealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [testingEngines, setTestingEngines] = useState(false);
  const [testResult, setTestResult] = useState<EngineTestResult | null>(null);
  const [checkingUpdates, setCheckingUpdates] = useState(false);
  const [updateResult, setUpdateResult] = useState<EngineUpdateCheckResult | null>(null);
  const [showTestModal, setShowTestModal] = useState(false);
  const [showUpdateModal, setShowUpdateModal] = useState(false);

  const fetchHealth = async () => {
    try {
      setLoading(true);
      // No synthesized "healthy": a failed probe renders as offline with its reason.
      const [rootHealth, engines] = await Promise.all([
        api.ready().catch((err: any) => ({
          status: 'offline',
          reason: err?.kind || 'unknown',
          request_id: err?.requestId || null,
          version: null,
        })),
        api.getEngineHealth().catch(() => null),
      ]);
      setHealthData(rootHealth);
      setEngineHealth(engines);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  const handleTestAllEngines = async () => {
    try {
      setTestingEngines(true);
      const res = await api.testEngines();
      setTestResult(res);
      setShowTestModal(true);
      toast({
        title: 'Engine Self-Test Complete',
        description: `${res.overall_status} · ${res.duration_ms}ms. ${res.scope}`,
        variant: res.overall_status === 'PASS' ? 'default' : 'destructive',
        duration: 4000,
      });
    } catch (err: unknown) {
      toast({
        title: 'Engine Test Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setTestingEngines(false);
    }
  };

  const handleCheckUpdates = async () => {
    try {
      setCheckingUpdates(true);
      const res = await api.checkEngineUpdates();
      setUpdateResult(res);
      setShowUpdateModal(true);
      toast({
        title: 'Engine Updates Checked',
        description: res.note || L('Chưa xác minh phiên bản mới nhất.', 'Latest upstream versions have not been verified.'),
        duration: 4000,
      });
    } catch (err: unknown) {
      toast({
        title: 'Update Check Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setCheckingUpdates(false);
    }
  };


  // Only engines the server actually reports. No built-in placeholder list.
  const displayEngines: any[] = Array.isArray(engineHealth?.engines) ? engineHealth!.engines : [];
  const apiReady = healthData?.status === 'ready';
  const dbState: string = healthData?.checks?.database || (healthData ? 'unknown' : 'checking');
  const okEngines = displayEngines.filter((e: any) => e.status === 'OPERATIONAL').length;
  const defensiveEngines = displayEngines.filter((e: any) => e.status !== 'NOT_INTEGRATED').length;

  return (
    <div className="space-y-6">
      {/* Header with Engine Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="w-6 h-6 text-emerald-400" />
            <h1 className="text-2xl font-black tracking-tight text-[color:var(--text-primary)]">
              {t('health.title', 'SYSTEM HEALTH & ENGINE MANAGEMENT')}
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            {t('health.subtitle', 'Live diagnostics, real scanner adapter telemetry, self-test verification probes, and update checks.')}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Check Updates Button */}
          <button
            onClick={handleCheckUpdates}
            disabled={checkingUpdates}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-semibold text-slate-300 hover:text-[color:var(--text-primary)] transition shadow-sm cursor-pointer disabled:opacity-50"
            title="Show current driver versions; upstream versions are not queried"
          >
            <DownloadCloud className={`w-3.5 h-3.5 ${checkingUpdates ? 'animate-bounce text-[color:var(--text-secondary)]' : 'text-[color:var(--text-secondary)]'}`} />
            <span>{checkingUpdates ? L('Đang tải…', 'Loading…') : L('Phiên bản driver', 'Driver Versions')}</span>
          </button>

          {/* Test All Engines Button */}
          <button
            onClick={handleTestAllEngines}
            disabled={testingEngines}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-cyan-500/20 to-emerald-500/20 hover:from-cyan-500/30 hover:to-emerald-500/30 border border-cyan-500/30 text-xs font-bold text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)] transition shadow-sm cursor-pointer disabled:opacity-50"
            title="Run local SBOM matching and egress policy self-tests without customer probes"
          >
            <Zap className={`w-3.5 h-3.5 ${testingEngines ? 'animate-spin text-[color:var(--text-secondary)]' : 'text-[color:var(--text-secondary)]'}`} />
            <span>{testingEngines ? 'Testing Engines...' : 'Test All Engines'}</span>
          </button>

          {/* Refresh Telemetry */}
          <button
            onClick={fetchHealth}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-semibold text-slate-300 hover:text-[color:var(--text-primary)] transition shadow-sm cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-[color:var(--text-secondary)]' : ''}`} />
            <span>{t('common.refresh', 'Refresh')}</span>
          </button>
        </div>
      </div>

      {/* Main Status Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Gateway Health */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>FastAPI Gateway</span>
            <Server className={`w-4 h-4 ${apiReady ? 'text-emerald-400' : 'text-rose-400'}`} />
          </div>
          <div className={`text-xl font-black mt-2 font-mono ${apiReady ? 'text-emerald-400' : 'text-rose-400'}`}>
            {healthData?.status ? String(healthData.status).toUpperCase() : 'CHECKING'}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            {apiReady
              ? <>Version {healthData?.version} &bull; build {healthData?.build} &bull; as_of {healthData?.time_utc} UTC</>
              : <>Reason: {healthData?.reason || 'unknown'}{healthData?.request_id ? ` · request ${healthData.request_id}` : ''}</>}
          </div>
        </div>

        {/* Database Health */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>SQLAlchemy Persistence</span>
            <Database className="w-4 h-4 text-[color:var(--text-secondary)]" />
          </div>
          <div className={`text-xl font-black mt-2 font-mono ${dbState === 'ok' ? 'text-[color:var(--text-secondary)]' : 'text-rose-400'}`}>{dbState.toUpperCase()}</div>
          <div className="text-[11px] text-slate-400 mt-1">Reported by /healthz/ready</div>
        </div>

        {/* Security Engines Count */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Security Engines Status</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-xl font-black text-[color:var(--text-primary)] mt-2 font-mono flex items-center gap-2">
            <span>{engineHealth ? `${okEngines}/${defensiveEngines} OPERATIONAL` : 'UNKNOWN'}</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-1">{engineHealth ? 'Per-engine status from /engines/health' : 'Engine health not loaded'}</div>
        </div>

        {/* Operating Timezone */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Operating Timezone</span>
            <Clock className="w-4 h-4 text-[color:var(--text-secondary)]" />
          </div>
          <div className="text-xl font-black text-[color:var(--text-secondary)] mt-2 font-mono">Asia/Ho_Chi_Minh</div>
          <div className="text-[11px] text-slate-400 mt-1">ICT (UTC+07:00) &bull; {L('Múi giờ hiển thị', 'Display timezone')}</div>
        </div>
      </div>

      {/* Diagnostics Table */}
      <div className="rounded-2xl liquid-glass-card overflow-hidden shadow-xl border border-white/10">
        <div className="p-4 bg-cyber-950/90 border-b border-white/10 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-[color:var(--text-primary)] uppercase tracking-wider">Subsystem Diagnostics Matrix</span>
            <Badge>{displayEngines.length} Subsystems</Badge>
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            Source: <span className="text-[color:var(--text-primary)] font-bold">/api/v1/engines/health</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-cyber-950/90 text-slate-400 uppercase tracking-wider text-[10px] border-b border-white/10">
              <tr>
                <th className="py-3 px-4 font-bold">Subsystem Component</th>
                <th className="py-3 px-3 font-bold">Driver / Adapter</th>
                <th className="py-3 px-3 font-bold">Context / reason</th>
                <th className="py-3 px-3 font-bold">Last success</th>
                <th className="py-3 px-4 font-bold text-right">{t('common.status', 'Status')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {displayEngines.map((row) => {
                const tone = row.status === 'OPERATIONAL' ? 'emerald' : row.status === 'DEGRADED' ? 'amber' : row.status === 'NOT_INTEGRATED' ? 'slate' : 'rose';
                const dot = { emerald: 'bg-emerald-400', amber: 'bg-amber-400', slate: 'bg-slate-500', rose: 'bg-rose-500' }[tone];
                return (
                  <tr key={row.id || row.name} className="hover:bg-white/[0.02] transition">
                    <td className="py-3 px-4 font-bold text-[color:var(--text-primary)] flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} aria-hidden />
                      <span>{row.name}</span>
                    </td>
                    <td className="py-3 px-3 text-[color:var(--text-secondary)] font-mono text-[11px]">{row.driver || '—'} {row.version || ''}</td>
                    <td className="py-3 px-3 text-slate-400 text-[11px] max-w-xs" title={row.reason || row.runtime_context || ''}>
                      {row.reason || row.runtime_context || '—'}
                    </td>
                    <td className="py-3 px-3 font-mono text-[11px] text-slate-300">
                      {row.last_success_at ? new Date(row.last_success_at).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour12: false }) + ' ICT' : '—'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <Badge severity={row.status === 'OPERATIONAL' ? 'low' : row.status === 'DEGRADED' ? 'medium' : row.status === 'UNAVAILABLE' ? 'critical' : 'neutral'}>{row.status}</Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Engine Self-Test Results Modal */}
      {showTestModal && testResult && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 animate-fadeIn">
          <div className="w-full max-w-2xl rounded-2xl liquid-glass-modal p-6 shadow-2xl border border-white/15 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Zap className="w-5 h-5 text-[color:var(--text-secondary)]" />
                <h2 className="text-base font-bold text-[color:var(--text-primary)]">Security Engines Self-Test Verification</h2>
              </div>
              <button
                onClick={() => setShowTestModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-[color:var(--text-primary)] hover:bg-white/[0.06]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className={`p-3.5 rounded-xl border text-xs flex items-center justify-between ${testResult.overall_status === 'PASS' ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-rose-500/10 border-rose-500/30 text-rose-300'}`}>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>Overall Result: <strong>{testResult.overall_status}</strong> &bull; {testResult.duration_ms}ms</span>
              </div>
              <span className="text-[10px] font-mono text-slate-400">{new Date(testResult.timestamp).toLocaleTimeString()}</span>
            </div>

            <p className="text-xs text-slate-400">{testResult.scope}</p>
            <div className="divide-y divide-white/5 max-h-80 overflow-y-auto pr-1 text-xs space-y-1">
              {testResult.results.map((r, idx) => (
                <div key={idx} className="py-2.5 flex items-start justify-between gap-3">
                  <div>
                    <div className="font-bold text-[color:var(--text-primary)] flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full ${r.status === 'PASS' ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                      <span>{r.engine}</span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5">{r.message}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <Badge severity={r.status === 'PASS' ? 'low' : 'critical'}>{r.status}</Badge>
                    <div className="text-[10px] text-slate-500 font-mono mt-0.5">{r.latency_ms}ms</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="pt-3 border-t border-white/10 flex justify-end">
              <button
                onClick={() => setShowTestModal(false)}
                className="px-4 py-2 rounded-xl bg-white text-black font-extrabold text-xs hover:bg-slate-200 transition"
              >
                Close Results
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Engine Updates Check Modal */}
      {showUpdateModal && updateResult && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 animate-fadeIn">
          <div className="w-full max-w-xl rounded-2xl liquid-glass-modal p-6 shadow-2xl border border-white/15 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <DownloadCloud className="w-5 h-5 text-[color:var(--text-secondary)]" />
                <h2 className="text-base font-bold text-[color:var(--text-primary)]">Engine & Template Updates Inspection</h2>
              </div>
              <button
                onClick={() => setShowUpdateModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-[color:var(--text-primary)] hover:bg-white/[0.06]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-xs text-[color:var(--text-secondary)] flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-[color:var(--text-secondary)] shrink-0" />
              <span>
                {updateResult.note || L('Chưa xác minh phiên bản mới nhất.', 'Latest upstream versions have not been verified.')}
              </span>
            </div>

            <div className="divide-y divide-white/5 max-h-72 overflow-y-auto pr-1 text-xs space-y-2">
              {updateResult.engines.map((e, idx) => (
                <div key={idx} className="py-2.5 flex items-start justify-between gap-3">
                  <div>
                    <div className="font-bold text-[color:var(--text-primary)]">{e.engine}</div>
                    <p className="text-[11px] text-slate-400 mt-0.5">{e.notes}</p>
                    <div className="text-[10px] text-[color:var(--text-secondary)] font-mono mt-0.5">
                      Installed: {e.current_version} &bull; Latest: {e.latest_version ?? L('Chưa kiểm tra', 'Not checked')}
                    </div>
                  </div>
                  <Badge severity={e.has_update === null ? 'neutral' : e.has_update ? 'medium' : 'low'}>
                    {e.has_update === null ? L('CHƯA KIỂM TRA', 'NOT CHECKED') : e.has_update ? L('CÓ BẢN MỚI', 'UPDATE AVAILABLE') : L('ĐÃ KIỂM TRA', 'CHECKED')}
                  </Badge>
                </div>
              ))}
            </div>

            <div className="pt-3 border-t border-white/10 flex justify-end">
              <button
                onClick={() => setShowUpdateModal(false)}
                className="px-4 py-2 rounded-xl bg-white text-black font-extrabold text-xs hover:bg-slate-200 transition"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
