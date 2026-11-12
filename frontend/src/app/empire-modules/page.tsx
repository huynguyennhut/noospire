'use client';

/**
 * EMPIRE BUSINESS MODULE HUB (Milestone 5). Every configured module is shown, including modules
 * with zero assets in the viewer's scope. Totals reconcile with the viewer's scope. Each card links
 * to the module's own assets, findings and runs. Load errors show the reason and a retry button.
 */

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { BookOpen, Cpu, Globe, RefreshCw, Server, Users, Wrench } from 'lucide-react';
import { api, ApiError, ModuleHub } from '@/lib/api';
import { useI18n } from '@/lib/i18n';

const TZ = 'Asia/Ho_Chi_Minh';

const META: Record<string, { vi: string; en: string; icon: React.ElementType }> = {
  STUDENT_MANAGEMENT: { vi: 'Học viên & định danh', en: 'Students & identity', icon: Users },
  LEARNING_MATERIALS: { vi: 'Học liệu', en: 'Learning materials', icon: BookOpen },
  SUPPORTING_TOOLS: { vi: 'Công cụ hỗ trợ', en: 'Supporting tools', icon: Wrench },
  API_SERVICES: { vi: 'API', en: 'APIs', icon: Cpu },
  WEB_APPLICATION: { vi: 'Ứng dụng web', en: 'Web applications', icon: Globe },
  SERVER_INFRASTRUCTURE: { vi: 'Hạ tầng', en: 'Infrastructure', icon: Server },
};

function ict(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', { timeZone: TZ, hour12: false }) + ' ICT';
}

export default function EmpireModulesPage() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => (vi ? a : b);
  const [hub, setHub] = useState<ModuleHub | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setHub(await api.getModuleHub());
      setError(null);
    } catch (e: any) {
      const rid = e instanceof ApiError && e.requestId ? ` · request ${e.requestId}` : '';
      setError(`${e?.kind || 'error'}: ${e?.message || e}${rid}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">EMPIRE BUSINESS MODULE HUB</h1>
          {hub && (
            <p className="text-xs text-slate-400 mt-1">
              {L('Trong phạm vi của bạn', 'In your scope')}: {hub.assets_in_scope} asset = {hub.assets_in_modules} {L('trong 6 module', 'in 6 modules')}
              {hub.assets_unassigned ? ` + ${hub.assets_unassigned} ${L('chưa gán module', 'unassigned')}` : ''} · {L('dữ liệu lúc', 'as of')} {ict(hub.as_of)}
              {hub.scope === 'granted' ? ` · ${L('chỉ các asset được cấp quyền', 'granted assets only')}` : ''}
            </p>
          )}
        </div>
        <button onClick={() => void load()} disabled={loading} className="px-3 py-1.5 rounded border border-slate-600 text-slate-200 text-sm flex items-center gap-1 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> {L('Tải lại', 'Reload')}
        </button>
      </div>

      {error && (
        <div role="alert" className="p-3 rounded border border-rose-700 bg-rose-950 text-rose-200 text-sm flex justify-between gap-3">
          <span>{L('Không tải được module hub', 'Module hub failed to load')} ({error})</span>
          <button onClick={() => void load()} className="underline">{L('Thử lại', 'Retry')}</button>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {hub?.modules.map((m) => {
          const meta = META[m.module] || { vi: m.module, en: m.module, icon: Server };
          const Icon = meta.icon;
          const h = m.service_health;
          return (
            <article key={m.module} className="p-4 rounded-xl border border-slate-700 bg-slate-900 text-sm text-slate-200 space-y-3">
              <header className="flex items-center gap-2">
                <Icon className="w-5 h-5 text-cyan-400" aria-hidden />
                <h2 className="font-semibold">{vi ? meta.vi : meta.en}</h2>
                <span className="ml-auto text-xs text-slate-400 font-mono">{m.module}</span>
              </header>
              <dl className="grid grid-cols-2 gap-2 text-xs">
                <div><dt className="text-slate-400">Asset</dt><dd className="text-lg font-semibold">{m.assets}</dd></div>
                <div>
                  <dt className="text-slate-400">{L('Coverage 24 giờ', 'Coverage 24 h')}</dt>
                  <dd>{m.assets ? `${m.coverage_24h.covered}/${m.coverage_24h.total}` : '—'}</dd>
                </div>
                <div>
                  <dt className="text-slate-400">{L('Sức khỏe dịch vụ', 'Service health')}</dt>
                  <dd>
                    <span className="text-emerald-300">{h.up} up</span> · <span className="text-amber-300">{h.degraded} {L('suy giảm', 'degraded')}</span> ·{' '}
                    <span className="text-rose-300">{h.down} down</span> · <span className="text-slate-400">{h.unknown} {L('chưa rõ', 'unknown')}</span>
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-400">{L('Finding đang mở', 'Open findings')}</dt>
                  <dd>
                    {m.open_total}
                    {m.open_total > 0 && (
                      <span className="text-slate-400"> ({Object.entries(m.open_findings).filter(([, n]) => n).map(([k, n]) => `${k} ${n}`).join(', ')})</span>
                    )}
                  </dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-slate-400">{L('Lịch chạy kế tiếp', 'Next scheduled run')}</dt>
                  <dd>{m.next_scheduled_run_at ? ict(m.next_scheduled_run_at) : L('không có lịch bao phủ module này', 'no schedule covers this module')}</dd>
                </div>
              </dl>
              {m.assets === 0 && (
                <p className="text-xs text-slate-500">{L('Chưa có asset nào trong phạm vi của bạn thuộc module này.', 'No asset in your scope belongs to this module yet.')}</p>
              )}
              <nav className="flex gap-3 text-xs">
                <Link className="underline text-cyan-300" href={m.links.assets}>{L('Asset', 'Assets')}</Link>
                <Link className="underline text-cyan-300" href={m.links.findings}>Findings</Link>
                <Link className="underline text-cyan-300" href={m.links.runs}>{L('Lượt chạy', 'Runs')}</Link>
              </nav>
            </article>
          );
        })}
      </div>
    </div>
  );
}
