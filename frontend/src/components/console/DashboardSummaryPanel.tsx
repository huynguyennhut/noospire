'use client';

/**
 * Dashboard & Health summary (Milestone 5), scoped to the viewer's grants.
 * - Default window: 7 ICT days. "New today" counts observation events of the current ICT day.
 * - Separate cards for service health, workers and risk. Every chart/count opens a filtered list.
 * - Explicit as_of, data state (ok / partial / unknown) and offline state: nothing is shown green
 *   when the backend is unreachable or a measurement is missing.
 */

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { api, ApiError, DashboardSummary } from '@/lib/api';
import { subscribeEvents } from '@/lib/events';
import { useI18n } from '@/lib/i18n';

const TZ = 'Asia/Ho_Chi_Minh';
const SEVS = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const SEV_BAR: Record<string, string> = {
  CRITICAL: 'bg-rose-500', HIGH: 'bg-orange-500', MEDIUM: 'bg-amber-400', LOW: 'bg-sky-400', INFO: 'bg-slate-400',
};

function ict(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', { timeZone: TZ, hour12: false }) + ' ICT';
}

export default function DashboardSummaryPanel() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => (vi ? a : b);
  const router = useRouter();
  const [s, setS] = useState<DashboardSummary | null>(null);
  const [offline, setOffline] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setS(await api.getDashboardSummary(7));
      setOffline(null);
    } catch (e: any) {
      const rid = e instanceof ApiError && e.requestId ? ` · request ${e.requestId}` : '';
      setOffline(`${e?.kind || 'error'}: ${e?.message || e}${rid}`);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 60_000);
    let t: any = null;
    const unsub = subscribeEvents((m) => {
      if (m.kind === 'event' && !t) t = setTimeout(() => { t = null; void load(); }, 1500);
    });
    return () => { clearInterval(id); unsub(); if (t) clearTimeout(t); };
  }, [load]);

  const stateStyle = offline
    ? 'border-rose-700 bg-rose-950 text-rose-200'
    : s?.data_state === 'ok' ? 'border-emerald-700 bg-emerald-950 text-emerald-200'
    : s?.data_state === 'partial' ? 'border-amber-700 bg-amber-950 text-amber-200'
    : 'border-slate-600 bg-slate-900 text-slate-300';
  const maxDay = Math.max(1, ...(s?.findings_per_day.map((d) => d.new + d.reopened) || [1]));

  return (
    <section aria-label={L('Tổng quan 7 ngày', '7-day overview')} className="space-y-3">
      <div role="status" className={`p-2.5 rounded-lg border text-xs flex flex-wrap gap-x-4 gap-y-1 ${stateStyle}`}>
        {offline ? (
          <span>{L('Mất kết nối backend — số liệu dưới đây là lần tải cuối, không phải hiện trạng', 'Backend unreachable — figures below are the last load, not live')} ({offline})</span>
        ) : s ? (
          <>
            <span>{L('Trạng thái dữ liệu', 'Data state')}: <b>{s.data_state}</b></span>
            {s.data_state_reasons.length > 0 && <span>{s.data_state_reasons.join(' · ')}</span>}
            <span>as_of {ict(s.as_of)}</span>
            <span>{L('Dữ liệu thật gần nhất', 'Last real data')}: {ict(s.last_real_data_at)}</span>
          </>
        ) : (
          <span>{L('Đang tải…', 'Loading…')}</span>
        )}
        <button onClick={() => void load()} className="underline ml-auto">{L('Tải lại', 'Reload')}</button>
      </div>

      {s && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3 text-sm">
          {/* Service health */}
          <div className="p-3 rounded-xl border border-white/10 bg-black/30">
            <h2 className="text-xs uppercase tracking-wide text-slate-400 mb-2">{L('Sức khỏe dịch vụ', 'Service health')}</h2>
            <p className="text-slate-200">
              <span className="text-emerald-300">{s.services.counts.up} up</span> · <span className="text-amber-300">{s.services.counts.degraded} {L('suy giảm', 'degraded')}</span> ·{' '}
              <span className="text-rose-300">{s.services.counts.down} down</span> · <span className="text-slate-400">{s.services.counts.unknown} {L('chưa rõ', 'unknown')}</span>
            </p>
            <p className="text-xs text-amber-300 mt-1">{s.services.counts.stale ? `${s.services.counts.stale} ${L('chưa có phép đo mới', 'without a fresh measurement')}` : ''}</p>
            <ul className="mt-2 space-y-0.5 text-xs max-h-40 overflow-y-auto">
              {s.services.items.map((x) => (
                <li key={x.asset_id}>
                  <Link className="hover:underline" href={`/engine-runs/?asset=${x.asset_id}`}>
                    {x.name}: <b>{x.status}</b> · {x.observed_at ? `${L('quan sát', 'observed')} ${ict(x.observed_at)}` : x.reason}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
          {/* Workers */}
          <div className="p-3 rounded-xl border border-white/10 bg-black/30">
            <h2 className="text-xs uppercase tracking-wide text-slate-400 mb-2">Worker</h2>
            <p className={s.workers.online ? 'text-slate-200' : 'text-rose-300'}>
              {s.workers.online}/{s.workers.total} online{s.workers.throttled ? ` · ${s.workers.throttled} ${L('đang tạm dừng do tải', 'throttled')}` : ''}
            </p>
            <Link className="text-xs underline text-cyan-300" href="/schedules/">{L('Chi tiết hàng đợi và lịch', 'Queue and schedule details')}</Link>
          </div>
          {/* Risk */}
          <div className="p-3 rounded-xl border border-white/10 bg-black/30">
            <h2 className="text-xs uppercase tracking-wide text-slate-400 mb-2">{L('Rủi ro đang mở', 'Open risk')}</h2>
            <p className="text-slate-200">{s.risk.open_total} {L('finding đang mở', 'open findings')} · {L('mới hôm nay', 'new today')} <b>{s.new_today}</b></p>
            <div className="mt-2 space-y-1">
              {SEVS.map((k) => (
                <Link key={k} href={`/findings/?status_group=open&severity=${k}`} className="flex items-center gap-2 text-xs hover:underline focus:outline-none focus:ring-1 focus:ring-white/40 rounded">
                  <span className="w-16">{k}</span>
                  <span className={`h-2 rounded ${SEV_BAR[k]}`} style={{ width: `${Math.min(100, (s.risk.open_by_severity[k] || 0) * 8)}%`, minWidth: s.risk.open_by_severity[k] ? 4 : 0 }} aria-hidden />
                  <span>{s.risk.open_by_severity[k] || 0}</span>
                </Link>
              ))}
            </div>
          </div>
          {/* New per ICT day (event based) */}
          <div className="p-3 rounded-xl border border-white/10 bg-black/30 lg:col-span-3">
            <h2 className="text-xs uppercase tracking-wide text-slate-400 mb-2">
              {L('Finding mới / mở lại theo ngày (ICT, theo sự kiện quan sát)', 'New / reopened per day (ICT, by observation event)')}
            </h2>
            <div className="flex items-end gap-2 h-28" role="list">
              {s.findings_per_day.map((d) => (
                <button
                  key={d.day}
                  role="listitem"
                  onClick={() => router.push(`/findings/?outcome=new&day=${d.day}`)}
                  title={`${d.day}: ${d.new} new · ${d.reopened} reopened · ${d.fixed} fixed`}
                  aria-label={`${d.day}: ${d.new} ${L('mới', 'new')}, ${d.reopened} ${L('mở lại', 'reopened')}, ${d.fixed} ${L('đã sửa', 'fixed')}`}
                  className="flex-1 flex flex-col items-center justify-end h-full gap-1 focus:outline-none focus:ring-1 focus:ring-white/40 rounded hover:bg-white/5"
                >
                  <span className="text-[10px] text-slate-300">{d.new + d.reopened || ''}</span>
                  <span className="w-full bg-rose-500/80 rounded-t" style={{ height: `${((d.new + d.reopened) / maxDay) * 80}%` }} />
                  <span className="text-[10px] text-slate-500">{d.day.slice(5)}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
