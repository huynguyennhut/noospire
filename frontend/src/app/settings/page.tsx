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
  Palette,
  Sun,
  Moon,
} from 'lucide-react';
import { api, EngineHealthResponse } from '@/lib/api';
import { BaselineException } from '@/lib/types';
import { useI18n } from '@/lib/i18n';
import { useTheme } from '@/providers/ThemeProvider';
import { useToast } from '@/components/ui/toast';
import { Badge } from '@/components/ui/badge';

export default function SettingsPage() {
  const { t, locale } = useI18n();
  const L = (vi: string, en: string) => locale === 'vi' ? vi : en;
  const { theme, setTheme, toggleTheme, isDark } = useTheme();
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState<'appearance' | 'baselines' | 'synthetic' | 'policy' | 'ssrf' | 'maintenance'>('appearance');
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
  const [engineHealth, setEngineHealth] = useState<EngineHealthResponse | null>(null);
  const [engineHealthError, setEngineHealthError] = useState<string | null>(null);

  useEffect(() => {
    if (activeTab !== 'maintenance') return;
    let active = true;
    setEngineHealth(null);
    setEngineHealthError(null);
    api.getEngineHealth().then(result => {
      if (active) setEngineHealth(result);
    }).catch((error: unknown) => {
      if (active) setEngineHealthError(error instanceof Error ? error.message : String(error));
    });
    return () => { active = false; };
  }, [activeTab]);

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
        description: res.message || 'Development reset completed.',
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
      content = ['component,state,detail', ...rows.map((r) => `"${r.component}","${r.state}","${String(r.detail).replace(/"/g, "'")}"`)].join('\n');
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
        title: res.overall_status === 'PASS' ? L('Tự kiểm tra hoàn tất', 'Self-test complete') : L('Tự kiểm tra thất bại', 'Self-test failed'),
        description: `${res.overall_status} · ${res.duration_ms}ms. ${res.scope}`,
        variant: res.overall_status === 'PASS' ? 'default' : 'destructive',
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
        description: res.note || (res.updates_available ? L('Có bản cập nhật.', 'Updates available.') : L('Chưa xác minh phiên bản mới nhất.', 'Latest upstream versions have not been verified.')),
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
        <h1 className="text-2xl font-black tracking-tight text-[color:var(--text-primary)] flex items-center gap-2">
          <Settings className="w-6 h-6 text-[color:var(--text-secondary)]" />
          <span>{t('settings.title', 'SECURITY SETTINGS & BASELINE POLICIES')}</span>
        </h1>
        <p className="text-xs text-slate-400 mt-1">
          {t('settings.subtitle', 'Configure persistent target policies, Approved Public Exposure rules for /media, synthetic testing identities, SSRF defense boundaries, and system maintenance.')}
        </p>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap border-b border-white/10 gap-2 text-xs">
        <button
          onClick={() => setActiveTab('appearance')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'appearance'
              ? 'border-cyan-500 text-[color:var(--text-secondary)]'
              : 'border-transparent text-slate-400 hover:text-[color:var(--text-primary)]'
          }`}
        >
          <Palette className="w-3.5 h-3.5" />
          <span>{t('theme.appearance', 'Giao diện & Chủ đề / Theme & Appearance')}</span>
        </button>

        <button
          onClick={() => setActiveTab('baselines')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'baselines'
              ? 'border-cyan-500 text-[color:var(--text-secondary)]'
              : 'border-transparent text-slate-400 hover:text-[color:var(--text-primary)]'
          }`}
        >
          <BookOpen className="w-3.5 h-3.5" />
          <span>Approved Public Media Policy (/media)</span>
        </button>

        <button
          onClick={() => setActiveTab('policy')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'policy'
              ? 'border-cyan-500 text-[color:var(--text-secondary)]'
              : 'border-transparent text-slate-400 hover:text-[color:var(--text-primary)]'
          }`}
        >
          <Sliders className="w-3.5 h-3.5" />
          <span>Persistent Target Policy</span>
        </button>

        <button
          onClick={() => setActiveTab('synthetic')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'synthetic'
              ? 'border-cyan-500 text-[color:var(--text-secondary)]'
              : 'border-transparent text-slate-400 hover:text-[color:var(--text-primary)]'
          }`}
        >
          <Users className="w-3.5 h-3.5" />
          <span>Synthetic Student Accounts</span>
        </button>

        <button
          onClick={() => setActiveTab('ssrf')}
          className={`px-4 py-2 font-bold border-b-2 transition flex items-center gap-2 ${
            activeTab === 'ssrf'
              ? 'border-cyan-500 text-[color:var(--text-secondary)]'
              : 'border-transparent text-slate-400 hover:text-[color:var(--text-primary)]'
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
              : 'border-transparent text-slate-400 hover:text-[color:var(--text-primary)]'
          }`}
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>System Maintenance & Baseline Reset</span>
        </button>
      </div>

      {/* TAB: THEME & APPEARANCE (R6) */}
      {activeTab === 'appearance' && (
        <div className="space-y-6 text-xs">
          {/* Overview Info Card */}
          <div className="p-5 rounded-2xl liquid-glass-card border border-white/10 shadow-xl space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <Palette className="w-5 h-5 text-[color:var(--text-secondary)]" />
                <h3 className="font-bold text-[color:var(--text-primary)] text-base">
                  {t('theme.appearance', 'Giao diện & Chủ đề / Theme & Appearance')}
                </h3>
              </div>
              <Badge>{L('Hai chủ đề', 'Two themes')}</Badge>
            </div>
            <p className="text-slate-400 text-xs leading-relaxed max-w-3xl">
              {t('theme.appearanceDesc', 'Tùy chỉnh hệ thống giao diện Liquid Glass giữa chế độ Tối Obsidian và Sáng Ấm (Warm Invert Light).')}
            </p>
          </div>

          {/* Theme Selector Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Theme Card 1: Dark Obsidian */}
            <div
              onClick={() => {
                setTheme('obsidian-dark');
                toast({
                  title: t('theme.dark', 'Dark Obsidian (Default)'),
                  description: t('theme.obsidianPalette', 'Obsidian Space Black palette activated.'),
                });
              }}
              className={`p-5 rounded-2xl liquid-glass-card border transition-all cursor-pointer relative flex flex-col justify-between ${
                theme === 'obsidian-dark'
                  ? 'border-cyan-500 shadow-xl ring-2 ring-cyan-500/20'
                  : 'border-white/10 hover:border-white/20'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Moon className="w-4 h-4 text-[color:var(--text-secondary)]" />
                    <span className="font-bold text-[color:var(--text-primary)] text-sm">
                      {t('theme.dark', 'Dark Obsidian (Default)')}
                    </span>
                  </div>
                  {theme === 'obsidian-dark' && (
                    <span className="px-2 py-0.5 rounded-md bg-cyan-950 text-[color:var(--text-secondary)] border border-cyan-700 text-[10px] font-bold">
                      {t('theme.activeBadge', 'ĐANG SỬ DỤNG')}
                    </span>
                  )}
                </div>

                <p className="text-slate-400 text-xs mb-4">
                  {t('theme.obsidianPalette', 'Bảng màu Obsidian Space Black (#09090B), viền kính bán trong suốt và điểm nhấn cyan.')}
                </p>

                {/* Visual Swatch Preview */}
                <div className="rounded-xl overflow-hidden border border-white/15 p-3.5 bg-[#09090B] space-y-2.5 shadow-inner">
                  <div className="flex items-center justify-between">
                    <div className="h-2.5 w-20 rounded bg-white/20" />
                    <div className="h-2 w-8 rounded bg-cyan-400/80" />
                  </div>
                  <div className="p-3 rounded-lg bg-[#0C0C0E] border border-white/10 space-y-1.5 shadow-sm">
                    <div className="h-2 w-28 rounded bg-white/40" />
                    <div className="h-1.5 w-36 rounded bg-white/15" />
                  </div>
                  <div className="flex gap-2">
                    <span className="px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[9px] font-mono text-zinc-300">#09090B</span>
                    <span className="px-2 py-0.5 rounded bg-white/5 border border-white/10 text-[9px] font-mono text-[color:var(--text-secondary)]">Spec Cyan</span>
                  </div>
                </div>
              </div>

              <div className="mt-5 pt-3 border-t border-white/10 flex items-center justify-between">
                <span className="text-[11px] text-slate-400 font-mono">Obsidian palette</span>
                <button
                  type="button"
                  className={`px-3 py-1.5 rounded-xl font-bold text-xs transition ${
                    theme === 'obsidian-dark'
                      ? 'bg-cyan-500 text-black shadow-md'
                      : 'bg-white/10 text-[color:var(--text-primary)] hover:bg-white/20'
                  }`}
                >
                  {theme === 'obsidian-dark' ? '✓ ' + t('theme.activeBadge', 'ĐANG SỬ DỤNG') : t('theme.selectTheme', 'Chọn chủ đề này')}
                </button>
              </div>
            </div>

            {/* Theme Card 2: Warm Invert Light */}
            <div
              onClick={() => {
                setTheme('warm-light');
                toast({
                  title: t('theme.warm', 'Warm Invert Light'),
                  description: t('theme.warmPalette', 'Warm Linen Cream palette activated.'),
                });
              }}
              className={`p-5 rounded-2xl liquid-glass-card border transition-all cursor-pointer relative flex flex-col justify-between ${
                theme === 'warm-light'
                  ? 'border-amber-600 shadow-xl ring-2 ring-amber-500/20'
                  : 'border-white/10 hover:border-white/20'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Sun className="w-4 h-4 text-amber-500" />
                    <span className="font-bold text-[color:var(--text-primary)] text-sm">
                      {t('theme.warm', 'Warm Invert Light')}
                    </span>
                  </div>
                  {theme === 'warm-light' && (
                    <span className="px-2 py-0.5 rounded-md bg-amber-950 text-amber-400 border border-amber-700 text-[10px] font-bold">
                      {t('theme.activeBadge', 'ĐANG SỬ DỤNG')}
                    </span>
                  )}
                </div>

                <p className="text-slate-400 text-xs mb-4">
                  {t('theme.warmPalette', 'Bảng màu Linen Cream (#FAF8F5), bề mặt trắng sứ (#FFFFFF) và viền kính ấm áp.')}
                </p>

                {/* Visual Swatch Preview */}
                <div className="rounded-xl overflow-hidden border border-black/10 p-3.5 bg-[#FAF8F5] space-y-2.5 shadow-inner">
                  <div className="flex items-center justify-between">
                    <div className="h-2.5 w-20 rounded bg-black/30" />
                    <div className="h-2 w-8 rounded bg-amber-600/80" />
                  </div>
                  <div className="p-3 rounded-lg bg-[#FFFFFF] border border-black/10 space-y-1.5 shadow-sm">
                    <div className="h-2 w-28 rounded bg-black/60" />
                    <div className="h-1.5 w-36 rounded bg-black/20" />
                  </div>
                  <div className="flex gap-2">
                    <span className="px-2 py-0.5 rounded bg-black/5 border border-black/10 text-[9px] font-mono text-zinc-800">#FAF8F5</span>
                    <span className="px-2 py-0.5 rounded bg-black/5 border border-black/10 text-[9px] font-mono text-amber-800">Warm Linen</span>
                  </div>
                </div>
              </div>

              <div className="mt-5 pt-3 border-t border-white/10 flex items-center justify-between">
                <span className="text-[11px] text-slate-400 font-mono">Warm palette</span>
                <button
                  type="button"
                  className={`px-3 py-1.5 rounded-xl font-bold text-xs transition ${
                    theme === 'warm-light'
                      ? 'bg-amber-600 text-[color:var(--text-primary)] shadow-md'
                      : 'bg-white/10 text-[color:var(--text-primary)] hover:bg-white/20'
                  }`}
                >
                  {theme === 'warm-light' ? '✓ ' + t('theme.activeBadge', 'ĐANG SỬ DỤNG') : t('theme.selectTheme', 'Chọn chủ đề này')}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 1: APPROVED PUBLIC MEDIA BASELINE */}
      {activeTab === 'baselines' && (
        <div className="space-y-6 text-xs">
          <div className="p-4 rounded-2xl liquid-glass-card border border-cyan-800/60 leading-relaxed text-slate-300 shadow-md">
            <h3 className="font-bold text-[color:var(--text-primary)] text-sm flex items-center gap-2">
              <Shield className="w-4 h-4 text-[color:var(--text-secondary)]" />
              <span>Approved Public Exposure Baseline Policy (Section 3.1)</span>
            </h3>
            <p className="mt-1 text-slate-400 text-xs">
              The <code className="text-[color:var(--text-secondary)]">/media</code> path is intentionally configured to allow anonymous public access for designated educational materials.
              Expected public accessibility is classified as <strong className="text-emerald-400">PUBLIC_BY_DESIGN</strong> and does NOT generate vulnerability alerts.
              However, the scanner continues to check for unintended sensitive content (student records, credentials, directory indexing).
            </p>
          </div>

          {/* Active Baselines List */}
          <div className="rounded-2xl liquid-glass-card border border-white/10 overflow-hidden shadow-xl">
            <div className="p-3.5 bg-cyber-950/90 border-b border-white/10 font-bold text-[color:var(--text-primary)] uppercase tracking-wider text-[11px]">
              Active Approved Baseline Exceptions
            </div>
            <div className="divide-y divide-white/5">
              {baselines.map((b) => (
                <div key={b.id} className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[color:var(--text-secondary)] font-bold text-xs">{b.scope}</span>
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
            <h3 className="font-bold text-[color:var(--text-primary)] text-sm mb-3">Register Approved Baseline Scope</h3>
            <form onSubmit={handleCreateBaseline} className="space-y-3">
              <div>
                <label className="block text-slate-300 font-semibold mb-1">Target Scope Pattern</label>
                <input
                  type="text"
                  placeholder="e.g. https://mh.empire.edu.vn/media/*"
                  value={newScope}
                  onChange={(e) => setNewScope(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-cyber-950 border border-white/10 text-[color:var(--text-primary)] font-mono text-xs focus:outline-none focus:border-cyan-500"
                />
              </div>

              <div>
                <label className="block text-slate-300 font-semibold mb-1">Business Justification & Reason</label>
                <textarea
                  rows={3}
                  placeholder="Explain why public anonymous access is an explicit educational platform requirement..."
                  value={newReason}
                  onChange={(e) => setNewReason(e.target.value)}
                  className="w-full p-3 rounded-xl bg-cyber-950 border border-white/10 text-[color:var(--text-primary)] text-xs focus:outline-none focus:border-cyan-500"
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
          <h3 className="font-bold text-[color:var(--text-primary)] text-sm">Persistent Target Management Rules (Section 11)</h3>
          <p className="text-slate-400 leading-relaxed">
            Empire targets are configured once and stored in the persistent management policy. Routine assessments, daily scheduled scans, and on-demand assessments do not require repeated manual confirmations or document re-verifications.
          </p>

          <div className="space-y-3 pt-2">
            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between">
              <div>
                <div className="font-bold text-[color:var(--text-primary)]">Immediate Assessment Authorization</div>
                <div className="text-slate-400 text-[11px] mt-0.5">Permit instant scans without ownership upload re-prompts</div>
              </div>
              <span className="text-emerald-400 font-bold font-mono">ENABLED</span>
            </div>

            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between">
              <div>
                <div className="font-bold text-[color:var(--text-primary)]">Continuous Daily Assessment Pipeline</div>
                <div className="text-slate-400 text-[11px] mt-0.5">Automated scan run daily at 02:00 AM Asia/Ho_Chi_Minh</div>
              </div>
              <span className="text-emerald-400 font-bold font-mono">ENABLED</span>
            </div>

            <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between">
              <div>
                <div className="font-bold text-[color:var(--text-primary)]">Default Request Rate Limit</div>
                <div className="text-slate-400 text-[11px] mt-0.5">Maximum concurrent probes per second to protect target server stability</div>
              </div>
              <span className="text-[color:var(--text-secondary)] font-bold font-mono">150 req/sec</span>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: SYNTHETIC STUDENT IDENTITIES */}
      {activeTab === 'synthetic' && (
        <div className="rounded-2xl liquid-glass-card border border-white/10 overflow-hidden text-xs shadow-xl">
          <div className="p-4 bg-cyber-950/90 border-b border-white/10 flex items-center justify-between">
            <span className="font-bold text-[color:var(--text-primary)] uppercase tracking-wider text-[11px]">Dedicated Synthetic Identities for Non-Destructive Testing</span>
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
                  <td className="py-3 px-4 font-bold text-[color:var(--text-secondary)] font-mono">{s.id}</td>
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
          <h3 className="font-bold text-[color:var(--text-primary)] text-sm">Two-Tier SSRF & Egress Protection</h3>
          <p className="text-slate-400">
            Blocks accidental scanning of internal loopback, RFC 1918 private subnets, and cloud metadata endpoints (169.254.169.254).
          </p>

          <div>
            <label className="block text-slate-300 font-semibold mb-1">Blocked CIDR Ranges</label>
            <textarea
              rows={6}
              value={blockedCidrs}
              onChange={(e) => setBlockedCidrs(e.target.value)}
              className="w-full p-3 rounded-xl bg-cyber-950 border border-white/10 text-[color:var(--text-primary)] font-mono text-xs focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div className="p-3 rounded-xl bg-white/[0.02] border border-white/10 flex items-center justify-between">
            <div>
              <div className="font-bold text-[color:var(--text-primary)]">Lab & Local Target Override Gate</div>
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
          <div className="p-5 rounded-2xl liquid-glass-card border border-rose-500/30 shadow-2xl relative overflow-hidden space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <AlertOctagon className="w-5 h-5 text-rose-400 shrink-0" />
                  <h3 className="font-black text-[color:var(--text-primary)] text-base font-mono uppercase tracking-tight">
                    Quay Về Trạng Thái Ban Đầu (Reset System to Baseline)
                  </h3>
                </div>
                <p className="text-slate-400 text-xs mt-1.5 leading-relaxed max-w-2xl">
                  Chỉ dùng ở môi trường phát triển (production từ chối). Xóa dữ liệu thử và chỉ nạp lại dữ liệu demo tổng hợp khi bật <strong>SENTINEL_SEED_DEMO_DATA</strong>; đây <strong>không</strong> phải dữ liệu đã kiểm toán.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setShowResetConfirmModal(true)}
                disabled={resetting}
                className="px-5 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-[color:var(--text-primary)] font-black text-xs transition shadow-lg shadow-rose-950/80 flex items-center gap-2 cursor-pointer shrink-0 disabled:opacity-50"
              >
                <RotateCcw className={`w-4 h-4 ${resetting ? 'animate-spin' : ''}`} />
                <span>{resetting ? 'Đang Khôi Phục...' : 'Quay Về Ban Đầu'}</span>
              </button>
            </div>


          </div>

          {/* System Logs & Date Tracking Section */}
          <div className="p-5 rounded-2xl liquid-glass-card border border-white/10 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/10">
              <div>
                <h3 className="font-bold text-[color:var(--text-primary)] text-sm flex items-center gap-2">
                  <FileText className="w-4 h-4 text-[color:var(--text-secondary)]" />
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
                        ? 'bg-cyan-500/20 text-[color:var(--text-secondary)] border border-cyan-500/40 shadow-sm'
                        : 'text-slate-400 hover:text-[color:var(--text-primary)] hover:bg-white/[0.04]'
                    }`}
                  >
                    {days}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <div className="text-[11px] text-slate-400">
                Filter Scope: <span className="text-[color:var(--text-primary)] font-mono font-bold">{logTimeFilter === 'ALL' ? 'Full Platform Lifetime' : `Last ${logTimeFilter}`}</span> &bull; Status: <span className="text-emerald-400 font-mono font-bold">{L('Bộ lọc nhật ký', 'Log filter selection')}</span>
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
                  className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-slate-300 hover:text-[color:var(--text-primary)] font-semibold text-xs flex items-center gap-1.5 transition cursor-pointer"
                  title="Export structured audit logs in JSON format"
                >
                  <Download className="w-3.5 h-3.5 text-[color:var(--text-secondary)]" />
                  <span>Export JSON</span>
                </button>

                {/* Export CSV */}
                <button
                  onClick={() => handleExportSystemLogs('csv')}
                  className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-slate-300 hover:text-[color:var(--text-primary)] font-semibold text-xs flex items-center gap-1.5 transition cursor-pointer"
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
                <h3 className="font-bold text-[color:var(--text-primary)] text-sm flex items-center gap-2">
                  <Cpu className="w-4 h-4 text-emerald-400" />
                  <span>Engine Telemetry & Integrity Diagnostics</span>
                </h3>
                <p className="text-slate-400 text-[11px] mt-0.5">
                  {L('Trạng thái từ heartbeat worker và nguồn dữ liệu hiện có. Tự kiểm tra không quét hệ thống khách hàng.', 'Status from worker heartbeats and available inputs. Self-tests do not scan customer systems.')}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleCheckEngineUpdatesQuick}
                  disabled={checkingUpdates}
                  className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-slate-300 hover:text-[color:var(--text-primary)] text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
                >
                  <DownloadCloud className={`w-3.5 h-3.5 ${checkingUpdates ? 'animate-bounce text-[color:var(--text-secondary)]' : 'text-[color:var(--text-secondary)]'}`} />
                  <span>{checkingUpdates ? L('Đang tải…', 'Loading…') : L('Phiên bản driver', 'Driver Versions')}</span>
                </button>

                <button
                  onClick={handleTestAllEnginesQuick}
                  disabled={testingEngines}
                  className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-cyan-500/20 to-emerald-500/20 hover:from-cyan-500/30 hover:to-emerald-500/30 border border-cyan-500/40 text-[color:var(--text-secondary)] hover:text-[color:var(--text-primary)] text-xs font-bold flex items-center gap-1.5 transition cursor-pointer disabled:opacity-50"
                >
                  <Zap className={`w-3.5 h-3.5 ${testingEngines ? 'animate-spin text-[color:var(--text-secondary)]' : 'text-[color:var(--text-secondary)]'}`} />
                  <span>{testingEngines ? 'Testing...' : 'Test All Engines'}</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
              {engineHealthError && <p role="alert" className="col-span-full text-red-400">{engineHealthError}</p>}
              {!engineHealth && !engineHealthError && <p role="status" className="col-span-full text-slate-400">{L('Đang tải trạng thái engine…', 'Loading engine status…')}</p>}
              {engineHealth?.engines.map(eng => (
                <div key={eng.id} className="p-3 rounded-xl bg-white/[0.02] border border-white/5 space-y-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-bold text-[color:var(--text-primary)]">{eng.name}</span>
                    <Badge severity={eng.status === 'OPERATIONAL' ? 'low' : eng.status === 'DEGRADED' ? 'medium' : 'neutral'}>{eng.status}</Badge>
                  </div>
                  <div className="text-[10px] text-slate-400 font-mono">{eng.version ?? L('Chưa tích hợp', 'Not integrated')}</div>
                  <div className="text-[11px] text-slate-400">{eng.reason || L('Worker sẵn sàng.', 'Worker ready.')}</div>
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
                <h3 className="text-base font-bold text-[color:var(--text-primary)]">Xác Nhận Quay Về Ban Đầu</h3>
              </div>
              <button
                onClick={() => setShowResetConfirmModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-[color:var(--text-primary)]"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs text-rose-200 leading-relaxed">
              Thao tác này sẽ đặt lại toàn bộ hệ thống về trạng thái ban đầu:
              <ul className="list-disc list-inside mt-2 space-y-1 text-slate-300">
                <li>Dữ liệu demo tổng hợp (chỉ khi bật SENTINEL_SEED_DEMO_DATA)</li>
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
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-[color:var(--text-primary)] font-extrabold text-xs transition shadow-lg shadow-rose-950/80 disabled:opacity-50"
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
