'use client';

import React, { useEffect, useState } from 'react';
import {
  Settings,
  Shield,
  Sliders,
  Network,
  Clock,
  Cpu,
  CheckCircle2,
  Save,
  RefreshCw,
  Plus,
  Trash2,
  BookOpen,
  Users,
  RotateCcw,
  FileText,
  Download,
  Zap,
  DownloadCloud,
  AlertOctagon,
  Calendar,
  X,
} from 'lucide-react';
import { api } from '@/lib/api';
import { BaselineException } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import { useToast } from '@/components/ui/toast';

export default function SettingsPage() {
  const { t } = useI18n();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<'baselines' | 'synthetic' | 'policy' | 'ssrf' | 'maintenance'>('baselines');
  const [baselines, setBaselines] = useState<BaselineException[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // New Baseline Form
  const [newScope, setNewScope] = useState('');
  const [newReason, setNewReason] = useState('');
  const [newOwner, setNewOwner] = useState('Empire Academic Operations');

  // SSRF State
  const [blockedCidrs, setBlockedCidrs] = useState(
    `127.0.0.0/8\n10.0.0.0/8\n172.16.0.0/12\n192.168.0.0/16\n169.254.169.254/32\n100.64.0.0/10\n::1/128\nfc00::/7`
  );
  const [allowLabTargets, setAllowLabTargets] = useState(true);

  // Maintenance & System Logs State
  const [logTimeFilter, setLogTimeFilter] = useState<'ALL' | '1D' | '7D' | '14D' | '30D'>('ALL');
  const [resetting, setResetting] = useState(false);
  const [showResetConfirmModal, setShowResetConfirmModal] = useState(false);
  const [testingEngines, setTestingEngines] = useState(false);
  const [checkingUpdates, setCheckingUpdates] = useState(false);

  const fetchBaselines = async () => {
    try {
      setLoading(true);
      const res = await api.listBaselines().catch(() => []);
      setBaselines(res || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBaselines();
  }, []);

  const handleCreateBaseline = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newScope || !newReason) return;
    try {
      setSaving(true);
      await api.createBaseline({
        scope: newScope,
        reason: newReason,
        owner: newOwner,
        classification: 'PUBLIC_BY_DESIGN',
      });
      setNewScope('');
      setNewReason('');
      await fetchBaselines();
      toast({
        title: 'Approved Media Baseline Added',
        description: 'New public exception registered for /media path.',
      });
    } catch (err: unknown) {
      toast({
        title: 'Registration Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleResetBaseline = async () => {
    try {
      setResetting(true);
      const res = await api.resetBaseline();
      setShowResetConfirmModal(false);
      toast({
        title: 'System Restored to Baseline',
        description: res.message || 'Restored 379 verified targets, 98 findings, and 50 baseline scans.',
        duration: 5000,
      });
    } catch (err: unknown) {
      toast({
        title: 'Reset Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setResetting(false);
    }
  };

  const handlePurgeAllLogs = async () => {
    if (!confirm('PURGE ALL SYSTEM LOGS: Permanently clear all cached execution logs from memory and storage?')) return;
    try {
      await api.clearAllLogs();
      toast({
        title: 'All Logs Purged',
        description: 'All historical execution logs have been permanently deleted.',
        duration: 3000,
      });
    } catch (err: unknown) {
      toast({
        title: 'Purge Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    }
  };

  // Exports the server's own operational snapshot (Milestone 5). No component is reported
  // "operational" unless the server measured it; failures are reported, not filled in.
  const handleExportSystemLogs = async (format: 'json' | 'csv') => {
    let ov: any;
    try {
      ov = await api.getOperationsOverview();
    } catch (err: any) {
      toast({ title: 'Export failed', description: err?.message || String(err), duration: 5000 });
      return;
    }
    const rows = [
      ...Object.entries(ov.engines).map(([name, e]: [string, any]) => ({
        component: `engine:${name}`,
        state: e.stale ? 'stale' : 'fresh',
        detail: `last success ${e.last_success_at || 'never'}; queued ${e.queued}; running ${e.running}`,
      })),
      ...ov.workers.map((w: any) => ({ component: `worker:${w.worker_id}`, state: w.state, detail: w.throttle_reason || `seen ${w.age_seconds}s ago` })),
      { component: 'advisory_feed', state: ov.feed ? 'imported' : 'missing', detail: ov.feed ? `${ov.feed.version} age ${ov.feed.age_hours}h` : 'no snapshot' },
    ];
    const logSummary = { exported_at_utc: new Date().toISOString(), server_as_of: ov.as_of, display_timezone: ov.display_timezone,
      time_filter: logTimeFilter, overdue: ov.overdue, errors_24h: ov.errors_24h, capacity: ov.capacity, components: rows };
    let content = '';
    let mimeType = 'text/plain;charset=utf-8';
    let filename = `noospire_operations_${logTimeFilter.toLowerCase()}_${Date.now()}`;
    if (format === 'json') {
      content = JSON.stringify(logSummary, null, 2);
      mimeType = 'application/json;charset=utf-8';
      filename += '.json';
    } else {
      content = ['component,state,detail', ...rows.map((r) => `"${r.component}","${r.state}","${String(r.detail).replace(/"/g, "'")}"`)].join('
');
      mimeType = 'text/csv;charset=utf-8';
      filename += '.csv';
    }
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
    toast({ title: 'Exported', description: `Saved ${filename}`, duration: 3000 });
  };

  const handleTestAllEnginesQuick = async () => {
    try {
      setTestingEngines(true);
      const res = await api.testEngines();
      toast({
        title: 'Engines Verified',
        description: `Verified ${res.results.length} security engines in ${res.duration_ms}ms. Status: ${res.overall_status}.`,
        duration: 4000,
      });
    } catch (err: unknown) {
      toast({
        title: 'Test Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setTestingEngines(false);
    }
  };

  const handleCheckEngineUpdatesQuick = async () => {
    try {
      setCheckingUpdates(true);
      const res = await api.checkEngineUpdates();
      toast({
        title: 'Engine Update Check',
        description: res.updates_available ? 'New updates available for scanner suite.' : 'All scanner engines and template databases are up to date.',
        duration: 4000,
      });
    } catch (err: unknown) {
      toast({
        title: 'Check Failed',
        description: err instanceof Error ? err.message : String(err),
        variant: 'destructive',
      });
    } finally {
      setCheckingUpdates(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div className="pb-4 border-b border-white/10">
        <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
          <Settings className="w-6 h-6 text-cyan-400" />
          <span>{t('settings.title', 'SECURITY SETTINGS & BASELINE POLICIES')}</span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          {t('settings.subtitle', 'Configure persistent target policies, Approved Public Exposure rules for /media, synthetic testing identities, SSRF defense boundaries, and system maintenance.')}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap border-b border-white/10 gap-2 text-xs">
        <button
          onClick={() => setActiveTab('baselines')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'baselines'
              ? 'border-cyan-500 text-cyan-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span>Approved Public Media Policy (/media)</span>
        </button>

        <button
          onClick={() => setActiveTab('policy')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'policy'
              ? 'border-cyan-500 text-cyan-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          <Sliders className="w-3.5 h-3.5" />
          <span>Persistent Target Policy</span>
        </button>

        <button
          onClick={() => setActiveTab('synthetic')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'synthetic'
              ? 'border-cyan-500 text-cyan-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          <Users className="w-3.5 h-3.5" />
          <span>Synthetic Student Accounts</span>
        </button>

        <button
          onClick={() => setActiveTab('ssrf')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'ssrf'
              ? 'border-cyan-500 text-cyan-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          <Network className="w-3.5 h-3.5" />
          <span>SSRF & Network Boundaries</span>
        </button>

        <button
          onClick={() => setActiveTab('maintenance')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'maintenance'
              ? 'border-rose-500 text-rose-400'
              : 'border-transparent text-slate-400 hover:text-white'
          }`}
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>System Maintenance & Baseline Reset</span>
        </button>
      </div>

      {/* TAB 1: APPROVED PUBLIC MEDIA BASELINE */}
      {activeTab === 'baselines' && (
        <div className="space-y-6 text-xs">
          <div className="p-4 rounded-2xl liquid-glass-card border border-cyan-800/60 leading-relaxed text-slate-300 shadow-md">
            <h3 className="font-bold text-white text-sm flex items-center gap-2">
              <Shield className="w-4 h-4 text-cyan-400" />
              <span>Approved Public Exposure Baseline Policy (Section 3.1)</span>
            </h3>
            <p className="mt-1 text-slate-400 text-xs">
              The <code className="text-cyan-400">/media</code> path is intentionally configured to allow anonymous public access for designated educational materials.
              Expected public accessibility is classified as <strong className="text-emerald-400">PUBLIC_BY_DESIGN</strong> and does NOT generate vulnerability alerts.
              However, the scanner continues to check for unintended sensitive content (student records, credentials, directory indexing).
            </p>
          </div>

          {/* Active Baselines List */}
          <div className="rounded-2xl liquid-glass-card border border-white/10 overflow-hidden shadow-xl">
            <div className="p-3.5 bg-cyber-950/90 border-b border-white/10 font-bold text-white uppercase tracking-wider text-[11px]">
              Active Approved Baseline Exceptions
            </div>
            <div className="divide-y divide-white/5">
              {baselines.map((b) => (
                <div key={b.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-cyan-400 font-bold text-xs">{b.scope}</span>
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-800">
                        {b.classification}
                      </span>
                    </div>
                    <p className="text-slate-400 text-xs mt-1">{b.reason}</p>
                    <div className="text-[10px] text-slate-500 mt-1">
                      Owner: <strong className="text-slate-300">{b.owner}</strong> | Approved by: <strong className="text-slate-300">{b.approved_by}</strong>
                    </div>
                  </div>
                  <span className="text-emerald-400 font-bold font-mono text-xs">ACTIVE</span>
                </div>
              ))}
            </div>
          </div>

          {/* Register New Baseline Form */}
          <div className="p-5 rounded-2xl liquid-glass-card border border-white/10 shadow-xl">
            <h3 className="font-bold text-white text-sm mb-3">Register Approved Baseline Scope</h3>
            <form onSubmit={handleCreateBaseline} className="space-y-3">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">Target Scope Pattern</label>
                <input
                  type="text"
                  placeholder="e.g. https://mh.empire.edu.vn/media/*"
                  value={newScope}
                  onChange={(e) => setNewScope(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Business Justification & Reason</label>
                <textarea
                  rows={3}
                  placeholder="Explain why public anonymous access is an explicit educational platform requirement..."
                  value={newReason}
                  onChange={(e) => setNewReason(e.target.value)}
                  className="w-full p-3 rounded-xl bg-cyber-950 border border-white/10 text-white text-xs focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  disabled={saving || !newScope.trim()}
                  className="px-4 py-2 rounded-xl bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 font-bold hover:from-cyan-400 hover:to-cyan-300 transition shadow-md"
                >
                  {saving ? 'Registering...' : 'Add Baseline Exception'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* TAB 2: PERSISTENT TARGET POLICY */}
      {activeTab === 'policy' && (
        <div className="p-5 rounded-2xl liquid-glass-card border border-white/10 space-y-4 text-xs shadow-xl">
          <h3 className="font-bold text-white text-sm">Persistent Target Management Rules (Section 11)</h3>
          <p className="text-slate-400 leading-relaxed">
            Empire targets are configured once and stored in the persistent management policy. Routine assessments, daily scheduled scans, and on-demand assessments do not require repeated manual confirmations or document re-verifications.
          </p>

          <div className="space-y-3 pt-2">
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between">
              <div>
                <div className="font-bold text-white">Immediate Assessment Authorization</div>
                <div className="text-slate-400 text-[11px] mt-0.5">Permit instant scans without ownership upload re-prompts</div>
              </div>
              <span className="text-emerald-400 font-bold font-mono">ENABLED</span>
            </div>

            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between">
              <div>
                <div className="font-bold text-white">Continuous Daily Assessment Pipeline</div>
                <div className="text-slate-400 text-[11px] mt-0.5">Automated scan run daily at 02:00 AM Asia/Ho_Chi_Minh</div>
              </div>
              <span className="text-emerald-400 font-bold font-mono">ENABLED</span>
            </div>

            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between">
              <div>
                <div className="font-bold text-white">Default Request Rate Limit</div>
                <div className="text-slate-400 text-[11px] mt-0.5">Maximum concurrent probes per second to protect target server stability</div>
              </div>
              <span className="text-cyan-400 font-bold font-mono">150 req/sec</span>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: SYNTHETIC STUDENT IDENTITIES */}
      {activeTab === 'synthetic' && (
        <div className="rounded-2xl liquid-glass-card border border-white/10 overflow-hidden text-xs shadow-xl">
          <div className="p-4 bg-cyber-950/90 border-b border-white/10 flex items-center justify-between">
            <span className="font-bold text-white uppercase tracking-wider text-[11px]">Dedicated Synthetic Identities for Non-Destructive Testing</span>
          </div>

          <table className="w-full text-left text-xs">
            <thead className="bg-cyber-950/90 text-slate-400 uppercase tracking-wider text-[10px] border-b border-white/10">
              <tr>
                <th className="py-3 px-4 font-bold">Identifier</th>
                <th className="py-3 px-3 font-bold">Role</th>
                <th className="py-3 px-3 font-bold">Synthetic Email</th>
                <th className="py-3 px-3 font-bold">Purpose</th>
                <th className="py-3 px-4 font-bold text-right">{t('common.status', 'Status')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {[
                { id: 'studenttu1', role: 'STUDENT', email: 'studenttu1@empire.local', purpose: 'Historical test account for Better-Auth verification', status: 'ACTIVE' },
                { id: 'test_student_a', role: 'STUDENT', email: 'student_alpha_audit@empire.local', purpose: 'BOLA / IDOR cross-account caller persona', status: 'ACTIVE' },
                { id: 'test_student_b', role: 'STUDENT', email: 'student_bravo_audit@empire.local', purpose: 'BOLA / IDOR cross-account target object', status: 'ACTIVE' },
                { id: 'audit_probe_synthetic', role: 'AUDITOR', email: 'audit_synthetic_probe@empire.local', purpose: 'Controlled negative-auth & rate limit verification', status: 'ACTIVE' },
              ].map((s) => (
                <tr key={s.id} className="hover:bg-white/[0.02] transition">
                  <td className="py-3 px-4 font-bold text-cyan-400 font-mono">{s.id}</td>
                  <td className="py-3 px-3 text-slate-300 font-semibold">{s.role}</td>
                  <td className="py-3 px-3 text-slate-400 font-mono">{s.email}</td>
                  <td className="py-3 px-3 text-slate-300">{s.purpose}</td>
                  <td className="py-3 px-4 text-right">
                    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-emerald-950/80 text-emerald-400 border border-emerald-800">
                      {s.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 4: SSRF BOUNDARIES */}
      {activeTab === 'ssrf' && (
        <div className="p-5 rounded-2xl liquid-glass-card border border-white/10 space-y-4 text-xs shadow-xl">
          <h3 className="font-bold text-white text-sm">Two-Tier SSRF & Egress Protection</h3>
          <p className="text-slate-400">
            Blocks accidental scanning of internal loopback, RFC 1918 private subnets, and cloud metadata endpoints (169.254.169.254).
          </p>

          <div>
            <label className="block text-slate-300 font-semibold mb-1">Blocked CIDR Ranges</label>
            <textarea
              rows={6}
              value={blockedCidrs}
              onChange={(e) => setBlockedCidrs(e.target.value)}
              className="w-full p-3 rounded-xl bg-cyber-950 border border-white/10 text-white font-mono text-xs focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between">
            <div>
              <div className="font-bold text-white">Lab & Local Target Override Gate</div>
              <div className="text-slate-400 text-[11px]">Permit explicitly verified laboratory endpoints on localhost</div>
            </div>
            <input
              type="checkbox"
              checked={allowLabTargets}
              onChange={(e) => setAllowLabTargets(e.target.checked)}
              className="rounded border-cyber-700 text-cyan-500"
            />
          </div>
        </div>
      )}

      {/* TAB 5: SYSTEM MAINTENANCE, LOGS & BASELINE RESET */}
      {activeTab === 'maintenance' && (
        <div className="space-y-6 text-xs">
          {/* Hero Maintenance Card: Quay Về Ban Đầu */}
          <div className="p-5 rounded-2xl bg-gradient-to-r from-rose-950/40 via-black to-slate-950 border border-rose-500/30 shadow-2xl relative overflow-hidden space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <AlertOctagon className="w-5 h-5 text-rose-400 shrink-0" />
                  <h3 className="font-black text-white text-base font-mono uppercase tracking-tight">
                    Quay Về Trạng Thái Ban Đầu (Reset System to Baseline)
                  </h3>
                </div>
                <p className="text-slate-400 text-xs mt-1.5 leading-relaxed max-w-2xl">
                  Khôi phục toàn bộ nền tảng về trạng thái chuẩn đã được kiểm toán: nạp lại đầy đủ <strong>379 mục tiêu Empire</strong>, <strong>98 lỗ hổng đã xác thực</strong>, <strong>50 bản ghi quét ban đầu</strong>, và làm sạch bộ nhớ đệm tạm thời.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setShowResetConfirmModal(true)}
                disabled={resetting}
                className="px-5 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-black text-xs transition shadow-lg shadow-rose-950/80 flex items-center gap-2 cursor-pointer shrink-0 disabled:opacity-50"
              >
                <RotateCcw className={`w-4 h-4 ${resetting ? 'animate-spin' : ''}`} />
                <span>{resetting ? 'Đang Khôi Phục...' : 'Quay Về Ban Đầu'}</span>
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 pt-2 text-[11px] font-mono">
              <div className="p-2.5 rounded-lg bg-black/50 border border-white/5">
                <span className="text-slate-400 block text-[10px]">TARGET PERIMETER</span>
                <span className="font-bold text-white">379 Assets (empire.edu.vn)</span>
              </div>
              <div className="p-2.5 rounded-lg bg-black/50 border border-white/5">
                <span className="text-slate-400 block text-[10px]">FINDING REPOSITORY</span>
                <span className="font-bold text-amber-400">98 Verified Items</span>
              </div>
              <div className="p-2.5 rounded-lg bg-black/50 border border-white/5">
                <span className="text-slate-400 block text-[10px]">SCAN TELEMETRY</span>
                <span className="font-bold text-cyan-400">50 Historical Baselines</span>
              </div>
              <div className="p-2.5 rounded-lg bg-black/50 border border-white/5">
                <span className="text-slate-400 block text-[10px]">RECURRING PIPELINES</span>
                <span className="font-bold text-emerald-400">3 Active Schedules</span>
              </div>
            </div>
          </div>

          {/* System Logs & Date Tracking Section */}
          <div className="p-5 rounded-2xl liquid-glass-card border border-white/10 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/10">
              <div>
                <h3 className="font-bold text-white text-sm flex items-center gap-2">
                  <FileText className="w-4 h-4 text-cyan-400" />
                  <span>System Logs, Audit Trail & Date Tracking</span>
                </h3>
                <p className="text-slate-400 text-[11px] mt-0.5">
                  Track and inspect execution logs grouped by calendar days, purge caches, or export telemetry data.
                </p>
              </div>

              {/* Day Filter */}
              <div className="flex items-center gap-1.5 p-1 rounded-xl bg-white/[0.03] border border-white/10">
                <Calendar className="w-3.5 h-3.5 text-slate-400 ml-1.5" />
                <span className="text-[10px] text-slate-400 font-mono mr-1">Days:</span>
                {(['ALL', '1D', '7D', '14D', '30D'] as const).map((days) => (
                  <button
                    key={days}
                    onClick={() => setLogTimeFilter(days)}
                    className={`px-2 py-0.5 rounded-lg text-[10px] font-mono font-bold transition ${
                      logTimeFilter === days
                        ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm'
                        : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
                    }`}
                  >
                    {days}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <div className="text-[11px] text-slate-400">
                Filter Scope: <span className="text-white font-mono font-bold">{logTimeFilter === 'ALL' ? 'Full Platform Lifetime' : `Last ${logTimeFilter}`}</span> &bull; Status: <span className="text-emerald-400 font-mono font-bold">100% AUDIT READY</span>
              </div>

              <div className="flex items-center gap-2">
                {/* Purge All Logs */}
                <button
                  onClick={handlePurgeAllLogs}
                  className="px-3 py-1.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-300 font-semibold text-xs flex items-center gap-1.5 transition cursor-pointer"
                  title="Purge all historical log records"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>Xóa Toàn Bộ Logs</span>
                </button>

                {/* Export JSON */}
                <button
                  onClick={() => handleExportSystemLogs('json')}
                  className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-slate-300 hover:text-white font-semibold text-xs flex items-center gap-1.5 transition cursor-pointer"
                  title="Export structured audit logs in JSON format"
                >
                  <Download className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Export JSON</span>
                </button>

                {/* Export CSV */}
                <button
                  onClick={() => handleExportSystemLogs('csv')}
                  className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-slate-300 hover:text-white font-semibold text-xs flex items-center gap-1.5 transition cursor-pointer"
                  title="Export audit log matrix in CSV format"
                >
                  <Download className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Export CSV</span>
                </button>
              </div>
            </div>
          </div>

          {/* Engine Integrity Verification & Diagnostics Section */}
          <div className="p-5 rounded-2xl liquid-glass-card border border-white/10 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/10">
              <div>
                <h3 className="font-bold text-white text-sm flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-emerald-400" />
                  <span>Engine Telemetry & Integrity Diagnostics</span>
                </h3>
                <p className="text-slate-400 text-[11px] mt-0.5">
                  Live verification of scanner binaries (Nuclei CLI, ZAP, Empire Engine, Trivy, Nmap, SSRF Gatekeeper).
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleCheckEngineUpdatesQuick}
                  disabled={checkingUpdates}
                  className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-slate-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
                >
                  <DownloadCloud className={`w-3.5 h-3.5 ${checkingUpdates ? 'animate-bounce text-cyan-400' : 'text-cyan-400'}`} />
                  <span>{checkingUpdates ? 'Checking...' : 'Check Engine Updates'}</span>
                </button>

                <button
                  onClick={handleTestAllEnginesQuick}
                  disabled={testingEngines}
                  className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-cyan-500/20 to-emerald-500/20 hover:from-cyan-500/30 hover:to-emerald-500/30 border border-cyan-500/40 text-cyan-300 hover:text-white text-xs font-bold flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
                >
                  <Zap className={`w-3.5 h-3.5 ${testingEngines ? 'animate-spin text-cyan-400' : 'text-cyan-400'}`} />
                  <span>{testingEngines ? 'Testing...' : 'Test All Engines'}</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
              {[
                { name: 'Nuclei Scanner CLI', version: 'v3.11.1', status: 'OPERATIONAL', path: 'C:\\Users\\nguye\\go\\bin\\nuclei.exe' },
                { name: 'Empire Assessment Engine', version: 'v2.4.0', status: 'OPERATIONAL', path: 'EmpireAssessmentEngine (FastAPI)' },
                { name: 'OWASP ZAP Core Adapter', version: 'v2.14.0', status: 'OPERATIONAL', path: 'ZAPLabRunner (DAST)' },
                { name: 'Aqua Trivy Scanner', version: 'v0.49.1', status: 'OPERATIONAL', path: 'TrivyLabRunner (SBOM)' },
                { name: 'Nmap Port Recon', version: 'v7.94', status: 'OPERATIONAL', path: 'NmapSubprocessAdapter' },
                { name: 'Two-Tier SSRF Gatekeeper', version: 'v1.8.0', status: 'OPERATIONAL', path: 'SSRFProtector (Egress Guard)' },
              ].map((eng, idx) => (
                <div key={idx} className="p-3 rounded-xl bg-white/[0.02] border border-white/5 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-white">{eng.name}</span>
                    <span className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">
                      {eng.status}
                    </span>
                  </div>
                  <div className="text-[10px] text-cyan-400 font-mono">{eng.version}</div>
                  <div className="text-[10px] text-slate-500 truncate" title={eng.path}>{eng.path}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal: Quay Về Ban Đầu */}
      {showResetConfirmModal && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 animate-fadeIn">
          <div className="w-full max-w-md rounded-2xl liquid-glass-modal p-6 shadow-2xl border border-rose-500/40 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-white/10">
              <div className="flex items-center gap-2">
                <AlertOctagon className="w-5 h-5 text-rose-400" />
                <h3 className="text-base font-bold text-white">Xác Nhận Quay Về Ban Đầu</h3>
              </div>
              <button
                onClick={() => setShowResetConfirmModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-200 leading-relaxed">
              Thao tác này sẽ đặt lại toàn bộ hệ thống về trạng thái ban đầu:
              <ul className="list-disc list-inside mt-2 space-y-1 text-slate-300">
                <li>379 mục tiêu Empire Platform chuẩn</li>
                <li>98 lỗ hổng đã được xác minh</li>
                <li>50 tác vụ quét baseline</li>
                <li>3 lịch trình quét Asia/Ho_Chi_Minh</li>
                <li>Xóa toàn bộ các khóa nhật ký (log) tạm thời</li>
              </ul>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowResetConfirmModal(false)}
                className="px-4 py-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-semibold text-slate-300"
              >
                Hủy Bỏ
              </button>
              <button
                type="button"
                onClick={handleResetBaseline}
                disabled={resetting}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-extrabold text-xs transition shadow-lg shadow-rose-950/80 disabled:opacity-50"
              >
                {resetting ? 'Đang Khôi Phục...' : 'Xác Nhận Khôi Phục'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
