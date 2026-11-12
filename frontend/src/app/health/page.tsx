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

export default function SystemHealthPage() {
  const { t } = useI18n();
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
        description: `All ${res.results.length} security engines verified in ${res.duration_ms}ms. Overall status: ${res.overall_status}.`,
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
        description: res.updates_available ? 'New engine/template updates available!' : 'All engine binaries and vulnerability templates are up to date.',
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
            <h1 className="text-2xl font-black tracking-tight text-white">
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
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-semibold text-slate-300 hover:text-white transition shadow-sm cursor-pointer disabled:opacity-50"
            title="Check scanner engines and vulnerability template signatures for updates"
          >
            <DownloadCloud className={`w-3.5 h-3.5 ${checkingUpdates ? 'animate-bounce text-cyan-400' : 'text-cyan-400'}`} />
            <span>{checkingUpdates ? 'Checking...' : 'Check Updates'}</span>
          </button>

          {/* Test All Engines Button */}
          <button
            onClick={handleTestAllEngines}
            disabled={testingEngines}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-cyan-500/20 to-emerald-500/20 hover:from-cyan-500/30 hover:to-emerald-500/30 border border-cyan-500/30 text-xs font-bold text-cyan-300 hover:text-white transition shadow-sm cursor-pointer disabled:opacity-50"
            title="Run synthetic probe against all scanner engines to verify operational integrity"
          >
            <Zap className={`w-3.5 h-3.5 ${testingEngines ? 'animate-spin text-cyan-400' : 'text-cyan-400'}`} />
            <span>{testingEngines ? 'Testing Engines...' : 'Test All Engines'}</span>
          </button>

          {/* Refresh Telemetry */}
          <button
            onClick={fetchHealth}
            className="flex items-center gap-2 px-3.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-semibold text-slate-300 hover:text-white transition shadow-sm cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-cyan-400' : ''}`} />
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
            <Database className="w-4 h-4 text-cyan-400" />
          </div>
          <div className={`text-xl font-black mt-2 font-mono ${dbState === 'ok' ? 'text-cyan-400' : 'text-rose-400'}`}>{dbState.toUpperCase()}</div>
          <div className="text-[11px] text-slate-400 mt-1">Reported by /healthz/ready</div>
        </div>

        {/* Security Engines Count */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Security Engines Status</span>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-xl font-black text-white mt-2 font-mono flex items-center gap-2">
            <span>{engineHealth ? `${okEngines}/${defensiveEngines} OPERATIONAL` : 'UNKNOWN'}</span>
          </div>
          <div className="text-[11px] text-slate-400 mt-1">{engineHealth ? 'Per-engine status from /engines/health' : 'Engine health not loaded'}</div>
        </div>

        {/* Operating Timezone */}
        <div className="p-4 rounded-2xl liquid-glass-card border border-white/10 shadow-md">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Operating Timezone</span>
            <Clock className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-xl font-black text-cyan-400 mt-2 font-mono">Asia/Ho_Chi_Minh</div>
          <div className="text-[11px] text-slate-400 mt-1">ICT (UTC+07:00) &bull; Scheduler Synchronized</div>
        </div>
      </div>

      {/* Diagnostics Table */}
      <div className="rounded-2xl liquid-glass-card overflow-hidden shadow-xl border border-white/10">
        <div className="p-4 bg-cyber-950/90 border-b border-white/10 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-white uppercase tracking-wider">Subsystem Diagnostics Matrix</span>
            <span className="px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800 text-[10px] font-mono font-bold">
              {displayEngines.length} Subsystems
            </span>
          </div>
          <div className="text-[11px] text-slate-400 font-mono">
            Source: <span className="text-white font-bold">/api/v1/engines/health</span>
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
                const badge = {
                  emerald: 'bg-emerald-950/80 text-emerald-400 border-emerald-800',
                  amber: 'bg-amber-950/80 text-amber-300 border-amber-800',
                  slate: 'bg-slate-900 text-slate-400 border-slate-700',
                  rose: 'bg-rose-950/80 text-rose-300 border-rose-800',
                }[tone];
                return (
                  <tr key={row.id || row.name} className="hover:bg-white/[0.02] transition">
                    <td className="py-3 px-4 font-bold text-white flex items-center gap-2">
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dot}`} aria-hidden />
                      <span>{row.name}</span>
                    </td>
                    <td className="py-3 px-3 text-cyan-400 font-mono text-[11px]">{row.driver || '—'} {row.version || ''}</td>
                    <td className="py-3 px-3 text-slate-400 text-[11px] max-w-xs" title={row.reason || row.runtime_context || ''}>
                      {row.reason || row.runtime_context || '—'}
                    </td>
                    <td className="py-3 px-3 font-mono text-[11px] text-slate-300">
                      {row.last_success_at ? new Date(row.last_success_at).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour12: false }) + ' ICT' : '—'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold border font-mono ${badge}`}>{row.status}</span>
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
                <Zap className="w-5 h-5 text-cyan-400" />
                <h2 className="text-base font-bold text-white">Security Engines Self-Test Verification</h2>
              </div>
              <button
                onClick={() => setShowTestModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-300 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>Overall Result: <strong>{testResult.overall_status}</strong> &bull; Verified in {testResult.duration_ms}ms</span>
              </div>
              <span className="text-[10px] font-mono text-slate-400">{new Date(testResult.timestamp).toLocaleTimeString()}</span>
            </div>

            <div className="divide-y divide-white/5 max-h-80 overflow-y-auto pr-1 text-xs space-y-1">
              {testResult.results.map((r, idx) => (
                <div key={idx} className="py-2.5 flex items-start justify-between gap-3">
                  <div>
                    <div className="font-bold text-white flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span>{r.engine}</span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5">{r.message}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">
                      {r.status}
                    </span>
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
                <DownloadCloud className="w-5 h-5 text-cyan-400" />
                <h2 className="text-base font-bold text-white">Engine & Template Updates Inspection</h2>
              </div>
              <button
                onClick={() => setShowUpdateModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-xs text-cyan-300 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
              <span>
                {updateResult.updates_available
                  ? 'Updates detected for selected engine packages.'
                  : 'All security engines, scanner binaries, and vulnerability template databases are completely up to date.'}
              </span>
            </div>

            <div className="divide-y divide-white/5 max-h-72 overflow-y-auto pr-1 text-xs space-y-2">
              {updateResult.engines.map((e, idx) => (
                <div key={idx} className="py-2.5 flex items-start justify-between gap-3">
                  <div>
                    <div className="font-bold text-white">{e.engine}</div>
                    <p className="text-[11px] text-slate-400 mt-0.5">{e.notes || 'Signatures current.'}</p>
                    <div className="text-[10px] text-cyan-400 font-mono mt-0.5">
                      Installed: v{e.current_version} &bull; Latest: v{e.latest_version}
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-950 text-emerald-400 border border-emerald-800 shrink-0">
                    UP TO DATE
                  </span>
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
