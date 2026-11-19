'use client';

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Activity, ArrowUpRight, RefreshCw, Server, ShieldAlert } from 'lucide-react';
import { api, ApiError, DashboardSummary } from '@/lib/api';
import { subscribeEvents } from '@/lib/events';
import { useI18n } from '@/lib/i18n';

const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];
const SERIES = [
  { key: 'new', vi: 'Phát hiện mới', en: 'New findings', color: 'var(--severity-critical)' },
  { key: 'reopened', vi: 'Mở lại', en: 'Reopened', color: 'var(--severity-high)' },
  { key: 'fixed', vi: 'Đã xác minh sửa', en: 'Verified fixes', color: 'var(--severity-low)' },
] as const;
const SEVERITY_LABELS: Record<string, [string, string]> = {
  CRITICAL: ['Nghiêm trọng', 'Critical'], HIGH: ['Cao', 'High'], MEDIUM: ['Trung bình', 'Medium'],
  LOW: ['Thấp', 'Low'], INFO: ['Thông tin', 'Info'],
};

function ict(iso: string | null | undefined, vi: boolean): string {
  if (!iso || !Number.isFinite(Date.parse(iso))) return '—';
  return new Date(iso).toLocaleString(vi ? 'vi-VN' : 'en-GB', { timeZone: 'Asia/Ho_Chi_Minh', hour12: false }) + ' ICT';
}

function serviceReason(item: DashboardSummary['services']['items'][number], vi: boolean): string {
  const L = (a: string, b: string) => vi ? a : b;
  if (item.reason === 'no approved health endpoint') return L('Chưa cấu hình điểm đo sức khỏe', 'Health endpoint not configured');
  if (item.reason === 'never measured') return L('Đã cấu hình, chưa có phép đo', 'Configured, awaiting first measurement');
  if (item.reason?.startsWith('last check ')) return L('Lượt kiểm tra gần nhất chưa trả phép đo hợp lệ', 'Latest check did not return a valid measurement');
  if (item.stale && item.observed_at) return L('Phép đo đã quá 2 giờ', 'Measurement is over 2 hours old');
  return L('Chưa có phép đo hợp lệ', 'No valid measurement yet');
}

/** Shared by the live loader and rendering regressions; all values come from the API. */
export function DashboardSummaryContent({ summary: s, vi, cached = false }: { summary: DashboardSummary; vi: boolean; cached?: boolean }) {
  const L = (a: string, b: string) => vi ? a : b;
  const oldWorkers = Math.max(0, s.workers.total - s.workers.online);
  const unconfigured = s.services.items.filter(x => x.reason === 'no approved health endpoint').length;
  // A historical "up" measurement cannot establish current health after expiry.
  const healthCounts = { up: 0, degraded: 0, down: 0, unknown: 0 };
  for (const item of s.services.items) {
    if (!item.stale && (item.status === 'up' || item.status === 'degraded' || item.status === 'down')) healthCounts[item.status]++;
    else healthCounts.unknown++;
  }
  const maxRisk = Math.max(1, ...Object.values(s.risk.open_by_severity));
  const maxDay = Math.max(1, ...s.findings_per_day.flatMap(d => SERIES.map(series => d[series.key])));
  const healthStates = [
    { key: 'up', label: L('Hoạt động', 'Up'), color: 'var(--severity-low)' },
    { key: 'degraded', label: L('Suy giảm', 'Degraded'), color: 'var(--severity-medium)' },
    { key: 'down', label: L('Gián đoạn', 'Down'), color: 'var(--severity-critical)' },
    { key: 'unknown', label: L('Chưa xác định', 'Unknown'), color: 'var(--text-secondary)' },
  ] as const;
  const healthLabel = (status: string) => healthStates.find(x => x.key === status)?.label || L('Chưa xác định', 'Unknown');

  return <div className="space-y-4" data-testid="dashboard-summary-content" aria-label={cached ? L('Số liệu từ lần tải trước', 'Cached figures from the previous load') : undefined}>
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <article className="assessment-panel min-w-0 space-y-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold"><Activity className="w-4 h-4 text-[var(--text-secondary)]" />{L('Sức khỏe dịch vụ', 'Service health')}</h3>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
          {healthStates.map(state => <div key={state.key}><dt className="text-xs text-[var(--text-secondary)]">{state.label}</dt><dd className="text-xl font-semibold tabular-nums mt-0.5" style={{ color: healthCounts[state.key] ? state.color : 'var(--text-muted)' }}>{healthCounts[state.key]}</dd></div>)}
        </dl>
        {unconfigured > 0 && <p className="text-xs leading-relaxed text-[var(--text-secondary)]">{unconfigured} {L('mục tiêu chưa cấu hình điểm đo. Kết quả SBOM hoặc quan sát web không xác nhận sức khỏe dịch vụ.', 'target(s) have no health endpoint. SBOM or public web observations do not establish service health.')}</p>}
        {s.services.items.length === 0 ? <p className="assessment-muted">{L('Chưa có mục tiêu trong phạm vi của bạn.', 'No targets in your scope.')}</p> : <ul className="space-y-3 max-h-36 overflow-y-auto pr-1 border-t border-[var(--border-subtle)] pt-3">
          {s.services.items.map(item => <li key={item.asset_id}>
            <Link href={`/engine-runs/?asset=${item.asset_id}`} className="block rounded text-xs leading-relaxed focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--text-secondary)] hover:underline">
              <span className="block font-medium break-words">{item.name}</span>
              <span className="block text-[var(--text-secondary)] mt-1">{item.reason || item.stale ? serviceReason(item, vi) : healthLabel(item.status)}{item.observed_at && <> · {ict(item.observed_at, vi)}</>}</span>
            </Link>
          </li>)}
        </ul>}
      </article>

      <article className="assessment-panel min-w-0 flex flex-col gap-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold"><Server className="w-4 h-4 text-[var(--text-secondary)]" />{L('Tiến trình xử lý', 'Worker processes')}</h3>
        <div><p className="text-3xl font-semibold tabular-nums">{s.workers.online}</p><p className="text-sm text-[var(--text-secondary)] mt-1">{L('worker đang hoạt động', 'workers online')}</p></div>
        {s.workers.online === 0 && <p className="text-xs text-[var(--severity-critical)]">{L('Chưa nhận được tín hiệu worker; tác vụ có thể đang chờ.', 'No worker heartbeat; jobs may be waiting.')}</p>}
        {s.workers.throttled > 0 && <p className="text-xs text-[var(--text-secondary)]">{s.workers.throttled} {L('worker đang tạm dừng do tải.', 'workers paused due to load.')}</p>}
        {oldWorkers > 0 && <details className="text-xs text-[var(--text-secondary)] leading-relaxed"><summary className="cursor-pointer rounded focus-visible:outline focus-visible:outline-2">{oldWorkers} {L('bản ghi worker không còn gửi tín hiệu', 'worker records without a current heartbeat')}</summary><p className="mt-2">{L('Đây là lịch sử tiến trình đã đăng ký, không phải số worker cần chạy. Xem thời điểm hoạt động gần nhất trong trang vận hành.', 'These are registered process records, not the required worker count. Inspect last-seen times in operations.')}</p></details>}
        <Link className="assessment-link mt-auto justify-between" href="/schedules/">{L('Hàng đợi và lịch chạy', 'Queue and schedules')}<ArrowUpRight className="w-3.5 h-3.5" /></Link>
      </article>

      <article className="assessment-panel min-w-0 space-y-4">
        <h3 className="flex items-center gap-2 text-sm font-semibold"><ShieldAlert className="w-4 h-4 text-[var(--text-secondary)]" />{L('Phát hiện đang mở', 'Open findings')}</h3>
        <div className="flex items-end justify-between gap-3"><div><p className="text-3xl font-semibold tabular-nums">{s.risk.open_total}</p><p className="text-xs text-[var(--text-secondary)] mt-1">{L('cần theo dõi', 'under tracking')}</p></div><p className="text-xs text-[var(--text-secondary)]">{L('Mới hôm nay', 'New today')}: <b className="text-[var(--text-primary)] tabular-nums">{s.new_today}</b></p></div>
        <div className="space-y-3">
          {SEVERITIES.map(severity => <Link key={severity} href={`/findings/?status_group=open&severity=${severity}`} className="grid grid-cols-[6.5rem_minmax(0,1fr)_2ch] items-center gap-3 text-xs rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--text-secondary)] hover:underline">
            <span>{SEVERITY_LABELS[severity][vi ? 0 : 1]}</span>
            <span className="h-1.5 rounded-full bg-[var(--bg-surface-hover)] overflow-hidden" aria-hidden><span className="block h-full rounded-full" style={{ width: `${(s.risk.open_by_severity[severity] || 0) / maxRisk * 100}%`, background: `var(--severity-${severity.toLowerCase()})` }} /></span>
            <b className="text-right tabular-nums">{s.risk.open_by_severity[severity] || 0}</b>
          </Link>)}
        </div>
      </article>
    </div>

    <article className="assessment-panel space-y-4">
      <div className="flex flex-wrap justify-between items-start gap-3"><div><h3 className="text-sm font-semibold">{L('Lịch sử phát hiện và khắc phục', 'Findings and remediation activity')}</h3><p className="text-xs text-[var(--text-secondary)] mt-1">{L('Theo sự kiện quan sát · giờ Việt Nam (ICT). Chọn cột có dữ liệu để xem chi tiết.', 'Observation events · Vietnam time (ICT). Select a populated bar to inspect findings.')}</p></div><span className="text-xs text-[var(--text-secondary)]">{s.window.days} {L('ngày gần nhất', 'days')}</span></div>
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-[var(--text-secondary)]">{SERIES.map(series => <span key={series.key} className="inline-flex items-center gap-2"><span className="h-2 w-2 rounded-sm" style={{ background: series.color }} aria-hidden />{vi ? series.vi : series.en}</span>)}</div>
      <div className="grid grid-cols-7 gap-2 pt-5" role="list" aria-label={L('Sự kiện trong 7 ngày', 'Events over 7 days')}>
        {s.findings_per_day.map(day => <div role="listitem" key={day.day} className="min-w-0">
          <div className="h-32 flex items-end justify-center gap-1 border-b border-[var(--border-strong)]">
            {SERIES.map(series => day[series.key] > 0 ? <Link key={series.key} href={`/findings/?outcome=${series.key}&day=${day.day}`} aria-label={`${day.day}: ${day[series.key]} ${vi ? series.vi : series.en}`} title={`${day.day}: ${day[series.key]} ${vi ? series.vi : series.en}`} className="relative w-2 sm:w-3 rounded-t hover:opacity-75 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--text-secondary)]" style={{ height: `${day[series.key] / maxDay * 100}%`, background: series.color }}><span className="absolute bottom-full left-1/2 -translate-x-1/2 pb-1 text-[10px] font-medium tabular-nums text-[var(--text-primary)]">{day[series.key]}</span></Link> : <span key={series.key} className="h-px w-2 sm:w-3" aria-hidden />)}
          </div>
          <p className="text-center text-[10px] sm:text-xs text-[var(--text-secondary)] mt-2 tabular-nums">{day.day.slice(8)}/{day.day.slice(5, 7)}</p>
        </div>)}
      </div>
      {s.findings_per_day.every(day => !day.new && !day.reopened && !day.fixed) && <p className="text-xs text-[var(--text-secondary)]">{L('Chưa ghi nhận sự kiện trong khoảng thời gian này. Điều này không xác nhận hệ thống an toàn.', 'No events recorded in this window. This does not establish security.')}</p>}
    </article>
  </div>;
}

export default function DashboardSummaryPanel() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => vi ? a : b;
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [offline, setOffline] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const pending = useRef(false);
  const load = useCallback(async () => {
    if (pending.current) return;
    pending.current = true; setRefreshing(true);
    try { setSummary(await api.getDashboardSummary(7)); setOffline(null); }
    catch (error: any) { setOffline(`${error?.message || error}${error instanceof ApiError && error.requestId ? ` · ${error.requestId}` : ''}`); }
    finally { pending.current = false; setRefreshing(false); }
  }, []);
  useEffect(() => {
    void load();
    const interval = setInterval(() => void load(), 60_000);
    let timeout: ReturnType<typeof setTimeout> | null = null;
    const unsubscribe = subscribeEvents(message => { if (message.kind === 'event' && !timeout) timeout = setTimeout(() => { timeout = null; void load(); }, 1500); });
    return () => { clearInterval(interval); unsubscribe(); if (timeout) clearTimeout(timeout); };
  }, [load]);
  const notes = summary ? [
    !summary.workers.online ? L('Chưa có worker hoạt động.', 'No worker online.') : null,
    summary.services.counts.stale ? `${summary.services.counts.stale} ${L('mục tiêu chưa có phép đo sức khỏe mới.', 'target(s) have no fresh health measurement.')}` : null,
    !summary.last_real_data_at ? L('Chưa có lượt kiểm tra hoàn tất.', 'No completed check yet.') : null,
  ].filter(Boolean) : [];

  return <section aria-label={L('Tổng quan 7 ngày', '7-day overview')} className="space-y-4" aria-busy={refreshing}>
    <div className="assessment-panel space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-base font-semibold">{L('Tổng quan vận hành', 'Operations overview')}</h2><button disabled={refreshing} onClick={() => void load()} className="assessment-link disabled:opacity-50"><RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />{refreshing ? L('Đang cập nhật…', 'Refreshing…') : L('Cập nhật', 'Refresh')}</button></div>
      <div role="status" className="text-sm leading-relaxed">
        {offline ? <><p className="text-[var(--severity-critical)] font-medium">{L('Mất kết nối máy chủ', 'Backend unreachable')}</p><p className="text-xs text-[var(--text-secondary)] mt-1">{summary ? L('Số liệu bên dưới thuộc lần tải trước; chưa xác nhận được hiện trạng.', 'Figures below are from the previous load; current state cannot be confirmed.') : L('Chưa có dữ liệu để hiển thị. Kiểm tra kết nối và thử cập nhật lại.', 'No data to display. Check the connection and refresh again.')}</p><details className="text-xs text-[var(--text-secondary)] mt-2"><summary>{L('Chi tiết kết nối', 'Connection details')}</summary><p className="break-words mt-1">{offline}</p></details></> : summary ? <><p className="font-medium">{summary.data_state === 'ok' ? L('Dữ liệu vận hành đã cập nhật', 'Operational data updated') : L('Chưa đủ dữ liệu để kết luận sức khỏe hệ thống', 'Insufficient data to determine system health')}</p>{notes.length > 0 && <p className="text-xs text-[var(--text-secondary)] mt-1">{notes.join(' ')}</p>}</> : <p className="assessment-muted">{L('Đang tải số liệu vận hành…', 'Loading operational data…')}</p>}
      </div>
      {summary && <dl className="flex flex-wrap gap-x-6 gap-y-2 border-t border-[var(--border-subtle)] pt-3 text-xs text-[var(--text-secondary)]"><div><dt className="inline">{L('Cập nhật lúc', 'Updated')}: </dt><dd className="inline tabular-nums">{ict(summary.as_of, vi)}</dd></div><div><dt className="inline">{L('Sự kiện gần nhất', 'Latest recorded event')}: </dt><dd className="inline tabular-nums">{ict(summary.last_real_data_at, vi)}</dd></div></dl>}
    </div>
    {summary && <DashboardSummaryContent summary={summary} vi={vi} cached={Boolean(offline)} />}
  </section>;
}
