'use client';

/**
 * Milestone 4 · Schedules & capacity.
 * - "Run whole system" and the hourly schedule use the same server planner (preview -> confirm -> 202).
 * - Countdown ticks every second from `next_run_at` + server clock offset; a tick never calls the API.
 * - Data refreshes on real change events from the shared stream (one EventSource per browser),
 *   with a bounded 60 s fallback refresh.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { Activity, AlertTriangle, CalendarClock, Gauge, Pause, Play, PlayCircle, Plus, RefreshCw, Server } from 'lucide-react';
import {
  api,
  ApiError,
  CapacityInfo,
  EngineName,
  MonitorSchedule,
  OperationsOverview,
  RunPlan,
  RunRequestBody,
  RunStatus,
  ScheduleSlotInfo,
} from '@/lib/api';
import { Asset } from '@/lib/types';
import { engineAssetIds } from '@/lib/assessment';
import { LiveEvent, StreamState, subscribeEvents } from '@/lib/events';
import { useI18n } from '@/lib/i18n';

const TZ = 'Asia/Ho_Chi_Minh';
const ENGINES: EngineName[] = ['public_web', 'tls_health', 'sbom'];

function ict(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', { timeZone: TZ, hour12: false }) + ' ICT';
}

function dur(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—';
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = s % 60;
  return h ? `${h}h ${String(m).padStart(2, '0')}m` : m ? `${m}m ${String(r).padStart(2, '0')}s` : `${r}s`;
}

function errText(e: any, vi: boolean): string {
  if (e instanceof ApiError || e?.kind) {
    const rid = e.requestId ? ` · request ${e.requestId}` : '';
    if (e.kind === 'forbidden') return (vi ? 'Không đủ quyền: ' : 'Not permitted: ') + e.message + rid;
    if (['network', 'upstream_unreachable', 'upstream_timeout', 'misrouted'].includes(e.kind))
      return (vi ? 'Không kết nối được API (' : 'API unreachable (') + e.kind + ')' + rid;
    return e.message + rid;
  }
  return String(e?.message || e);
}

const RESULT_STYLE: Record<string, string> = {
  completed: 'text-emerald-300 border-emerald-700 bg-emerald-950',
  partial: 'text-amber-300 border-amber-700 bg-amber-950',
  failed: 'text-rose-300 border-rose-700 bg-rose-950',
  no_work: 'text-[var(--text-primary)] border-[var(--border-strong)] bg-[var(--bg-surface-hover)]',
  launched: 'text-cyan-300 border-cyan-700 bg-cyan-950',
  coalesced: 'text-amber-300 border-amber-700 bg-amber-950',
};

function Badge({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-[var(--text-secondary)]">—</span>;
  return (
    <span className={`px-2 py-0.5 rounded border text-[11px] font-mono ${RESULT_STYLE[value] || 'text-[var(--text-primary)] border-[var(--border-strong)] bg-[var(--bg-surface-hover)]'}`}>
      {value}
    </span>
  );
}

function newKey(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

export default function SchedulesPage() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => (vi ? a : b);

  const [overview, setOverview] = useState<OperationsOverview | null>(null);
  const [metrics, setMetrics] = useState<any | null>(null);
  const [slots, setSlots] = useState<Record<string, ScheduleSlotInfo[]>>({});
  const [openSlots, setOpenSlots] = useState<string | null>(null);
  const [offsetMs, setOffsetMs] = useState(0); // server_time - client time
  const [now, setNow] = useState(Date.now());
  const [stream, setStream] = useState<StreamState>('connecting');
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [plan, setPlan] = useState<RunPlan | null>(null);
  const [planEngines, setPlanEngines] = useState<EngineName[]>(['public_web']);
  const [assets, setAssets] = useState<Asset[]>([]);
  const plannedRequest = useRef<RunRequestBody | null>(null);
  const [planProfile, setPlanProfile] = useState<'light' | 'slow'>('light');
  const [accepted, setAccepted] = useState<RunStatus | null>(null);
  const [cap, setCap] = useState<CapacityInfo | null>(null);
  const [form, setForm] = useState({ name: '', profile: 'light' as 'light' | 'slow', interval: 1440, workers: 1 });
  const [scheduleEngines, setScheduleEngines] = useState<EngineName[]>(['public_web']);
  const runKey = useRef<string | null>(null);
  const refreshTimer = useRef<any>(null);

  const load = useCallback(async () => {
    try {
      const [ov, inventory] = await Promise.all([api.getOperationsOverview(), api.listAllAssets()]);
      setAssets(inventory);
      setOverview(ov);
      setCap(ov.capacity);
      setOffsetMs(new Date(ov.server_time).getTime() - Date.now());
      setError(null);
      if (ov.schedules_visible) {
        setMetrics(await api.getOperationsMetrics(24).catch(() => null));
      }
    } catch (e) {
      setError(errText(e, vi));
    }
  }, [vi]);

  const loadSlots = useCallback(async (id: string) => {
    try {
      const rows = await api.listScheduleSlots(id, 24);
      setSlots((s) => ({ ...s, [id]: rows }));
    } catch (e) {
      setError(errText(e, vi));
    }
  }, [vi]);

  // Debounced refresh driven by real events.
  const scheduleRefresh = useCallback(() => {
    if (refreshTimer.current) return;
    refreshTimer.current = setTimeout(() => {
      refreshTimer.current = null;
      void load();
      if (openSlots) void loadSlots(openSlots);
    }, 1000);
  }, [load, loadSlots, openSlots]);

  useEffect(() => {
    void load();
    const fallback = setInterval(() => void load(), 60_000);
    const tick = setInterval(() => setNow(Date.now()), 1000); // countdown only; never fetches
    return () => {
      clearInterval(fallback);
      clearInterval(tick);
    };
  }, [load]);

  useEffect(
    () =>
      subscribeEvents((m) => {
        if (m.kind === 'state') {
          setStream(m.state);
          if (m.serverTime) setOffsetMs(new Date(m.serverTime).getTime() - Date.now());
        } else if (m.kind === 'event') {
          setEvents((ev) => [m.event, ...ev.filter((x) => x.id !== m.event.id)].slice(0, 25));
          scheduleRefresh();
        } else if (m.kind === 'reset') {
          scheduleRefresh();
        }
      }),
    [scheduleRefresh],
  );

  const serverNow = now + offsetMs;
  const owner = overview?.schedules_visible ?? false;

  async function preview() {
    setBusy(true);
    setAccepted(null);
    setError(null);
    try {
      runKey.current = newKey();
      plannedRequest.current = { selection: { kind: 'assets', asset_ids: engineAssetIds(assets, planEngines) }, engines: planEngines, profile: planProfile };
      setPlan(await api.previewPlan(plannedRequest.current));
    } catch (e) {
      setError(errText(e, vi));
    } finally {
      setBusy(false);
    }
  }

  async function confirmRun() {
    if (!plannedRequest.current || !runKey.current || busy) return;
    setBusy(true);
    try {
      const res = await api.launchRun(plannedRequest.current, runKey.current);
      setAccepted(res);
      setPlan(null);
      runKey.current = null;
      void load();
    } catch (e) {
      setError(errText(e, vi));
    } finally {
      setBusy(false);
    }
  }

  async function toggle(s: MonitorSchedule) {
    setBusy(true);
    try {
      await api.updateMonitorSchedule(s.id, { is_active: !s.is_active, expected_revision: s.revision });
      await load();
    } catch (e) {
      setError(errText(e, vi));
    } finally {
      setBusy(false);
    }
  }

  async function setProfile(s: MonitorSchedule, profile: 'light' | 'slow') {
    setBusy(true);
    try {
      await api.updateMonitorSchedule(s.id, { profile, expected_revision: s.revision });
      await load();
    } catch (e) {
      setError(errText(e, vi));
    } finally {
      setBusy(false);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createMonitorSchedule({
        name: form.name || L('Giám sát phạm vi đã duyệt', 'Approved-scope monitoring'),
        selection: { kind: 'assets', asset_ids: engineAssetIds(assets, scheduleEngines) },
        engines: scheduleEngines,
        profile: form.profile,
        interval_minutes: form.interval,
        max_workers: form.workers,
        is_active: true,
      });
      setNotice(L('Đã tạo lịch. Lượt đầu chạy ở slot kế tiếp.', 'Schedule created. First run at the next slot.'));
      await load();
    } catch (err) {
      setError(errText(err, vi));
    } finally {
      setBusy(false);
    }
  }

  async function emergencyStop() {
    if (!cap || busy) return;
    setBusy(true); setError(null);
    try { await api.setEmergencyStop(!cap.emergency_stop_active); await load(); }
    catch (e) { setError(errText(e, vi)); }
    finally { setBusy(false); }
  }

  async function saveCapacity(e: React.FormEvent) {
    e.preventDefault();
    if (!cap) return;
    setBusy(true);
    try {
      setCap(
        await api.putCapacity({
          max_running_executions: cap.max_running_executions,
          per_host_hourly_quota: cap.per_host_hourly_quota,
          per_host_egress_bytes_hourly: cap.per_host_egress_bytes_hourly,
        }),
      );
      setNotice(L('Đã lưu giới hạn công suất.', 'Capacity limits saved.'));
    } catch (err) {
      setError(errText(err, vi));
    } finally {
      setBusy(false);
    }
  }

  const streamLabel = useMemo(() => {
    const m: Record<StreamState, [string, string, string]> = {
      connecting: ['Đang kết nối luồng sự kiện', 'Connecting event stream', 'text-[var(--text-primary)]'],
      live: ['Trực tiếp', 'Live', 'text-emerald-300'],
      polling: ['Dự phòng: hỏi lại mỗi 10 giây', 'Fallback: polling every 10 s', 'text-amber-300'],
      offline: ['Mất kết nối, đang thử lại', 'Disconnected, retrying', 'text-rose-300'],
      auth_revoked: ['Phiên đã kết thúc, hãy đăng nhập lại', 'Session ended, sign in again', 'text-rose-300'],
    };
    const [a, b, c] = m[stream];
    return <span className={`text-xs ${c}`}>{L(a, b)}</span>;
  }, [stream, vi]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text-primary)] flex items-center gap-2">
            <CalendarClock className="w-5 h-5 text-cyan-400" />
            {L('Lịch kiểm tra & công suất', 'Schedules & capacity')}
          </h1>
          <p className="text-xs text-[var(--text-secondary)] mt-1">
            {L('Giờ server', 'Server time')}: {ict(new Date(serverNow).toISOString())} · {L('lưu UTC, hiển thị', 'stored UTC, shown in')} {TZ} · {streamLabel}
          </p>
        </div>
        <button onClick={() => void load()} className="px-3 py-1.5 rounded border border-[var(--border-strong)] text-[var(--text-primary)] text-sm flex items-center gap-1">
          <RefreshCw className="w-4 h-4" /> {L('Tải lại', 'Reload')}
        </button>
      </div>

      {error && (
        <div role="alert" className="p-3 rounded border border-rose-700 bg-rose-950 text-rose-200 text-sm flex justify-between gap-3">
          <span>{error}</span>
          <button onClick={() => void load()} className="underline">{L('Thử lại', 'Retry')}</button>
        </div>
      )}
      {notice && <div className="p-3 rounded border border-emerald-700 bg-emerald-950 text-emerald-200 text-sm">{notice}</div>}

      <section className="assessment-panel space-y-3">
        <div className="flex flex-wrap gap-3 items-center justify-between"><h2 className="font-semibold">{L('Điều khiển vận hành', 'Operations control')}</h2>{owner && cap && <button disabled={busy} onClick={() => void emergencyStop()} className="assessment-link disabled:opacity-40">{cap.emergency_stop_active ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}{cap.emergency_stop_active ? L('Tiếp tục hàng đợi', 'Resume queue') : L('Dừng khẩn toàn hệ thống', 'Emergency stop')}</button>}</div>
        <p role="status" className="text-sm">{cap?.emergency_stop_active ? L('Đang dừng khẩn: worker không nhận job mới; quan sát web đang chạy sẽ dừng.', 'Emergency stop active: workers do not claim new jobs; in-flight public web observations will stop.') : L('Lịch tự động dùng hàng đợi bền vững; worker và scheduler phải chạy để thực thi.', 'Automation uses the durable queue; workers and scheduler must be running.')}</p>
        <p className="assessment-muted">{L('Lịch mới mặc định hằng ngày; lịch đã lưu giữ nguyên chu kỳ. public_web kiểm tra URL được duyệt; TLS/health và SBOM cần đầu vào phù hợp. Hoàn tất job không đồng nghĩa đã đánh giá toàn diện.', 'New schedules default to daily; saved schedules retain their interval. public_web checks the approved URL; TLS/health and SBOM require appropriate inputs. Job completion does not mean comprehensive assessment.')}</p>
        <Link href="/engine-runs/" className="assessment-link">{L('Lượt chạy, nhật ký và bằng chứng', 'Runs, logs and evidence')} →</Link>
      </section>
      {/* Run eligible inventory through the same planner as schedules. */}
      <section className="p-4 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <PlayCircle className="w-5 h-5 text-cyan-400" />
          <h2 className="text-[var(--text-primary)] font-medium">{L('Đánh giá toàn bộ phạm vi đủ điều kiện', 'Assess all eligible targets')}</h2>
          <span className="text-xs text-[var(--text-secondary)]">{engineAssetIds(assets, planEngines).length} {L('mục tiêu đủ điều kiện cho engine đã chọn', 'eligible targets for selected engines')}</span>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-sm text-[var(--text-primary)]">
          {ENGINES.map((e) => (
            <label key={e} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={planEngines.includes(e)}
                onChange={(ev) => { setPlan(null); setPlanEngines((cur) => (ev.target.checked ? [...cur, e] : cur.filter((x) => x !== e))); }}
              />
              {e}
            </label>
          ))}
          <select value={planProfile} onChange={(e) => { setPlan(null); setPlanProfile(e.target.value as any); }} className="bg-[var(--bg-surface-hover)] border border-[var(--border-strong)] rounded px-2 py-1">
            <option value="light">{L('Nhẹ (kiểm tra nhanh)', 'Light (quick checks)')}</option>
            <option value="slow">{L('Chậm (1 worker, giãn cách theo host)', 'Slow (1 worker, host spacing)')}</option>
          </select>
          <button disabled={busy || !planEngines.length || !engineAssetIds(assets, planEngines).length || cap?.emergency_stop_active} onClick={() => void preview()} className="px-3 py-1.5 rounded bg-cyan-700 text-white disabled:opacity-50">
            {L('Xem trước tác động', 'Preview impact')}
          </button>
        </div>
        {plan && (
          <div className="p-3 rounded border border-cyan-800 bg-[var(--bg-primary)] text-sm text-[var(--text-primary)] space-y-2">
            <p>
              {L('Trong phạm vi', 'In scope')}: <b>{plan.summary.assets_in_scope}</b> asset · {plan.summary.pairs} {L('cặp asset/engine', 'asset/engine pairs')} ·{' '}
              <b className="text-emerald-300">{plan.summary.queue}</b> {L('chạy ngay', 'run now')} · <b className="text-amber-300">{plan.summary.defer}</b>{' '}
              {L('dời lịch', 'deferred')} · <b className="text-[var(--text-secondary)]">{plan.summary.skip}</b> {L('bỏ qua', 'skipped')}
            </p>
            {Object.keys(plan.summary.reasons).length > 0 && (
              <p className="text-xs text-[var(--text-secondary)]">
                {L('Lý do', 'Reasons')}: {Object.entries(plan.summary.reasons).map(([k, v]) => `${k} × ${v}`).join(' · ')}
              </p>
            )}
            <p className="text-xs text-[var(--text-secondary)]">
              {L('Ước tính xong lúc', 'Estimated finish')} {ict(plan.summary.estimated_finish_at)} ({plan.summary.slots} slot,{' '}
              {L('backlog trước đó', 'prior backlog')} {dur(plan.summary.backlog_seconds_before)}) ·{' '}
              {plan.summary.fits_window ? L('vừa trong cửa sổ 1 giờ', 'fits the 1-hour window') : L('vượt cửa sổ: việc dài chuyển sang hàng đợi dài', 'exceeds window: long work moved to the long lane')}
              {plan.summary.deferred_resume_at ? ` · ${L('tiếp tục lúc', 'resumes at')} ${ict(plan.summary.deferred_resume_at)}` : ''}
            </p>
            <div className="flex gap-2">
              <button disabled={busy || plan.summary.queue + plan.summary.defer === 0} onClick={() => void confirmRun()} className="px-3 py-1.5 rounded bg-emerald-700 text-white disabled:opacity-50">
                {L('Xác nhận chạy', 'Confirm run')}
              </button>
              <button onClick={() => setPlan(null)} className="px-3 py-1.5 rounded border border-[var(--border-strong)] text-[var(--text-primary)]">{L('Hủy', 'Cancel')}</button>
            </div>
          </div>
        )}
        {accepted && (
          <div className="p-3 rounded border border-emerald-700 bg-emerald-950 text-sm text-emerald-100">
            {accepted.replayed ? L('Yêu cầu đã được nhận trước đó', 'Already accepted earlier') : L('Đã nhận', 'Accepted')} · batch <code>{accepted.batch_id}</code> ·{' '}
            {ict(accepted.accepted_at)} · {L('mã tương quan', 'correlation')} <code>{accepted.correlation_id}</code> ·{' '}
            <Link className="underline" href={`/engine-runs/?run=${accepted.batch_id}`}>{L('Theo dõi', 'Track')}</Link>
          </div>
        )}
      </section>

      {/* Schedules */}
      {owner ? (
        <section className="space-y-3">
          <h2 className="text-[var(--text-primary)] font-medium flex items-center gap-2"><Activity className="w-4 h-4 text-cyan-400" />{L('Lịch định kỳ', 'Recurring schedules')}</h2>
          {overview && overview.schedules.length === 0 && (
            <p className="text-sm text-[var(--text-secondary)]">{L('Chưa có lịch. Tạo lịch đầu tiên bên dưới.', 'No schedule yet. Create the first one below.')}</p>
          )}
          {overview?.schedules.map((s) => {
            const next = s.next_run_at ? new Date(s.next_run_at).getTime() : null;
            const left = next !== null ? (next - serverNow) / 1000 : null;
            return (
              <div key={s.id} className="p-4 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-sm text-[var(--text-primary)] space-y-2">
                <div className="flex flex-wrap items-center gap-3">
                  <b>{s.name}</b>
                  <span className="text-xs text-[var(--text-secondary)]">{L('mỗi', 'every')} {s.interval_minutes} {L('phút', 'min')} · {s.engines.join(', ')} · {L('tối đa', 'max')} {s.max_workers} worker</span>
                  <select disabled={busy} value={s.profile} onChange={(e) => void setProfile(s, e.target.value as any)} className="bg-[var(--bg-surface-hover)] border border-[var(--border-strong)] rounded px-2 py-0.5 text-xs">
                    <option value="light">{L('nhẹ', 'light')}</option>
                    <option value="slow">{L('chậm', 'slow')}</option>
                  </select>
                  <button disabled={busy} onClick={() => void toggle(s)} className="ml-auto px-2 py-1 rounded border border-[var(--border-strong)] text-xs flex items-center gap-1">
                    {s.is_active ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                    {s.is_active ? L('Tạm dừng', 'Pause') : L('Bật lại', 'Resume')}
                  </button>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                  <div>
                    <div className="text-[var(--text-secondary)]">{L('Lần dự kiến tiếp theo', 'Next run')}</div>
                    <div>{s.is_active ? ict(s.next_run_at) : L('đang tạm dừng', 'paused')}</div>
                    {s.is_active && left !== null && (
                      <div className="font-mono text-cyan-300" aria-live="off">
                        {left > 0 ? `${L('còn', 'in')} ${dur(left)}` : L('đến hạn, chờ scheduler', 'due, waiting for scheduler')}
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="text-[var(--text-secondary)]">{L('Lần chạy trước', 'Last run')}</div>
                    <div>{ict(s.last_run_at)}</div>
                    <div className="text-[var(--text-secondary)] mt-1">{L('Tất cả job đã hoàn tất gần nhất', 'Last successful scheduled jobs')}</div>
                    <div>{ict(s.last_full_success_at)}</div>
                  </div>
                  <div>
                    <div className="text-[var(--text-secondary)]">{L('Kết quả mới nhất (kể cả partial)', 'Latest result (incl. partial)')}</div>
                    <div className="flex items-center gap-2"><Badge value={s.latest_result.status} /> {ict(s.latest_result.at)}</div>
                    {s.latest_result.batch_id && (
                      <Link className="underline text-cyan-300" href={`/engine-runs/?run=${s.latest_result.batch_id}`}>{L('Xem lượt chạy', 'Open run')}</Link>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap gap-4 text-xs text-[var(--text-primary)]">
                  <span>{s.running ? L('Đang chạy', 'Running') : L('Không có lượt đang chạy', 'Idle')}</span>
                  <span>{L('Slot bị lỡ/gộp', 'Missed/coalesced slots')}: <b>{s.missed_slots}</b>{s.pending_catchup ? ` · ${L('1 lượt bù đang chờ', '1 catch-up pending')}` : ''}</span>
                  <span>Backlog: <b>{s.backlog}</b>{s.estimated_drain_at ? ` · ${L('ước tính xong', 'est. drain')} ${ict(s.estimated_drain_at)}` : ''}</span>
                  <span>{L('Công suất lý thuyết', 'Theoretical capacity')}: {s.theoretical_hourly_capacity.toLocaleString()} / {L('giờ', 'hour')}</span>
                </div>
                {s.overdue_reason && (
                  <p className="text-xs text-amber-300 flex items-center gap-1"><AlertTriangle className="w-3 h-3" />{s.overdue_reason}</p>
                )}
                <button
                  className="text-xs underline text-[var(--text-primary)]"
                  onClick={() => {
                    const next = openSlots === s.id ? null : s.id;
                    setOpenSlots(next);
                    if (next) void loadSlots(next);
                  }}
                >
                  {openSlots === s.id ? L('Ẩn slot', 'Hide slots') : L('Xem các slot gần đây', 'Show recent slots')}
                </button>
                {openSlots === s.id && (
                  <table className="w-full text-xs mt-2">
                    <thead className="text-[var(--text-secondary)] text-left">
                      <tr><th>Slot (ICT)</th><th>{L('Loại', 'Kind')}</th><th>{L('Trạng thái', 'Status')}</th><th>{L('Lỡ trước đó', 'Missed before')}</th><th>{L('Gộp', 'Coalesced')}</th><th>{L('Kế hoạch', 'Plan')}</th><th>{L('Kết quả', 'Result')}</th></tr>
                    </thead>
                    <tbody>
                      {(slots[s.id] || []).map((x) => (
                        <tr key={x.id} className="border-t border-[var(--border-subtle)] align-top">
                          <td>{ict(x.slot_at)}</td>
                          <td>{x.kind}</td>
                          <td><Badge value={x.status} />{x.reason ? <div className="text-[var(--text-secondary)]">{x.reason}</div> : null}</td>
                          <td>{x.missed_before}</td>
                          <td>{x.coalesced_slots}</td>
                          <td>{'queue' in x.plan_summary ? `${x.plan_summary.queue}/${x.plan_summary.defer}/${x.plan_summary.skip}` : '—'}</td>
                          <td>{x.result_summary.by_status ? Object.entries(x.result_summary.by_status).map(([k, v]) => `${k}:${v}`).join(' ') : '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            );
          })}
          <p className="assessment-muted">{engineAssetIds(assets, scheduleEngines).length} {L('mục tiêu đủ điều kiện cho engine đã chọn; lưu danh sách cố định. SBOM dùng tệp mới nhất đã cung cấp. Lịch căn theo UTC; hằng ngày lúc 07:00 ICT (00:00 UTC). Không tự thay đổi lịch hiện có.', 'targets eligible for the selected engines; selection is stored explicitly. SBOM uses the latest supplied file. Slots align to UTC; daily at 07:00 ICT (00:00 UTC). Existing schedules are unchanged.')}</p>
          <form onSubmit={create} className="p-4 rounded border border-dashed border-[var(--border-strong)] flex flex-wrap items-end gap-3 text-sm text-[var(--text-primary)]">
            <label className="flex flex-col text-xs">{L('Tên', 'Name')}
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="bg-[var(--bg-surface-hover)] border border-[var(--border-strong)] rounded px-2 py-1" maxLength={200} />
            </label>
            <label className="flex flex-col text-xs">{L('Chu kỳ (phút)', 'Interval (min)')}
              <select value={form.interval} onChange={(e) => setForm({ ...form, interval: Number(e.target.value) })} className="bg-[var(--bg-surface-hover)] border border-[var(--border-strong)] rounded px-2 py-1">
                {[15, 30, 60, 120, 240, 720, 1440].map((m) => <option key={m} value={m}>{m === 1440 ? L('1440 — hằng ngày', '1440 — daily') : m}</option>)}
              </select>
            </label>
            <label className="flex flex-col text-xs">Profile
              <select value={form.profile} onChange={(e) => setForm({ ...form, profile: e.target.value as any })} className="bg-[var(--bg-surface-hover)] border border-[var(--border-strong)] rounded px-2 py-1">
                <option value="light">{L('nhẹ', 'light')}</option>
                <option value="slow">{L('chậm', 'slow')}</option>
              </select>
            </label>
            <label className="flex flex-col text-xs">{L('Số worker tối đa', 'Max workers')}
              <input type="number" min={1} max={32} value={form.workers} onChange={(e) => setForm({ ...form, workers: Number(e.target.value) })} className="bg-[var(--bg-surface-hover)] border border-[var(--border-strong)] rounded px-2 py-1 w-20" />
            </label>
            <fieldset disabled={busy} className="flex flex-wrap gap-2 text-xs"><legend>{L('Engine cho lịch mới', 'Engines for new schedule')}</legend>{ENGINES.map((e) => <label key={e} className="flex items-center gap-1"><input type="checkbox" checked={scheduleEngines.includes(e)} onChange={(event) => setScheduleEngines((old) => event.target.checked ? [...old, e] : old.filter((x) => x !== e))} />{e}</label>)}</fieldset>
            <button disabled={busy || !engineAssetIds(assets, scheduleEngines).length} className="px-3 py-1.5 rounded bg-cyan-700 text-white flex items-center gap-1 disabled:opacity-50"><Plus className="w-4 h-4" />{L('Tạo lịch', 'Create schedule')}</button>
          </form>
        </section>
      ) : (
        overview && <p className="text-sm text-[var(--text-secondary)]">{L('Chỉ chủ hệ thống xem và chỉnh lịch định kỳ.', 'Only the system owner sees and edits recurring schedules.')}</p>
      )}

      {/* Engines: staleness and queue age */}
      {overview && (
        <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="p-4 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-sm text-[var(--text-primary)]">
            <h2 className="font-medium mb-2 flex items-center gap-2"><Gauge className="w-4 h-4 text-cyan-400" />{L('Theo engine', 'Per engine')}</h2>
            <table className="w-full text-xs">
              <thead className="text-[var(--text-secondary)] text-left"><tr><th>Engine</th><th>{L('Thành công cuối', 'Last success')}</th><th>{L('Kết quả mới nhất', 'Latest')}</th><th>{L('Hàng đợi', 'Queue')}</th><th>{L('Tuổi hàng đợi', 'Queue age')}</th></tr></thead>
              <tbody>
                {ENGINES.map((e) => {
                  const x = overview.engines[e];
                  if (!x) return null;
                  return (
                    <tr key={e} className="border-t border-[var(--border-subtle)]">
                      <td className="font-mono">{e}</td>
                      <td>
                        {ict(x.last_success_at)}
                        {x.stale && <span className="ml-1 text-amber-300">({L('cũ', 'stale')})</span>}
                      </td>
                      <td>{x.latest_result ? <Badge value={x.latest_result.status} /> : '—'}</td>
                      <td>{x.queued} {L('chờ', 'queued')} · {x.running} {L('chạy', 'running')}</td>
                      <td>{dur(x.queue_age_seconds)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="text-[11px] text-[var(--text-secondary)] mt-2">{L('Ngưỡng cũ', 'Stale threshold')}: {dur(overview.stale_threshold_seconds)} · {L('bằng chứng mới nhất', 'newest evidence')} {ict(overview.evidence.newest_observation_at)}</p>
          </div>

          <div className="p-4 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-sm text-[var(--text-primary)] space-y-1">
            <h2 className="font-medium mb-2 flex items-center gap-2"><Server className="w-4 h-4 text-cyan-400" />{L('Vận hành', 'Operations')}</h2>
            <p>Worker online: <b>{overview.workers_online}</b> / {overview.workers.length}</p>
            {overview.workers.map((w) => (
              <p key={w.worker_id} className="text-xs text-[var(--text-secondary)]">
                <code>{w.worker_id}</code> · {w.state} · {L('thấy cách đây', 'seen')} {dur(w.age_seconds)} · {w.active_executions} {L('đang chạy', 'active')}
                {w.throttle_reason && <span className="block text-amber-300">{w.throttle_reason}</span>}
              </p>
            ))}
            <p>{L('Job quá hạn', 'Overdue jobs')}: {overview.overdue.queued_over_10m} {L('chờ > 10 phút', 'queued > 10 min')} · {overview.overdue.running_lease_expired} {L('mất lease', 'lease expired')}</p>
            <p>{L('Trong 24 giờ', 'Last 24 h')}: {overview.errors_24h.parse_errors} {L('lỗi parse', 'parse errors')} · {overview.errors_24h.dead_letters} dead letter</p>
            <p>{L('Nguồn advisory', 'Advisory feed')}: {overview.feed ? `${overview.feed.source} · ${overview.feed.version} · ${L('tuổi', 'age')} ${overview.feed.age_hours} h` : L('chưa nhập', 'not imported')}</p>
          </div>
        </section>
      )}

      {/* Capacity & metrics (owner) */}
      {owner && cap && (
        <section className="p-4 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-sm text-[var(--text-primary)] space-y-3">
          <h2 className="font-medium">{L('Công suất và số đo', 'Capacity and measurements')}</h2>
          <form onSubmit={saveCapacity} className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col text-xs">{L('Tối đa job chạy đồng thời', 'Max running executions')}
              <input type="number" min={1} max={64} value={cap.max_running_executions} onChange={(e) => setCap({ ...cap, max_running_executions: Number(e.target.value) })} className="bg-[var(--bg-surface-hover)] border border-[var(--border-strong)] rounded px-2 py-1 w-24" />
            </label>
            <label className="flex flex-col text-xs">{L('Quota mỗi host / giờ', 'Per-host quota / hour')}
              <input type="number" min={1} max={3600} value={cap.per_host_hourly_quota} onChange={(e) => setCap({ ...cap, per_host_hourly_quota: Number(e.target.value) })} className="bg-[var(--bg-surface-hover)] border border-[var(--border-strong)] rounded px-2 py-1 w-24" />
            </label>
            <label className="flex flex-col text-xs">{L('Ngân sách egress mỗi host / giờ (byte)', 'Per-host egress / hour (bytes)')}
              <input type="number" min={10000} value={cap.per_host_egress_bytes_hourly} onChange={(e) => setCap({ ...cap, per_host_egress_bytes_hourly: Number(e.target.value) })} className="bg-[var(--bg-surface-hover)] border border-[var(--border-strong)] rounded px-2 py-1 w-36" />
            </label>
            <button disabled={busy} className="px-3 py-1.5 rounded bg-cyan-700 text-white disabled:opacity-50">{L('Lưu', 'Save')}</button>
          </form>
          {metrics && (
            <>
              <table className="w-full text-xs">
                <thead className="text-[var(--text-secondary)] text-left">
                  <tr><th>Engine</th><th>{L('Lượt (24h)', 'Attempts (24h)')}</th><th>{L('Retry', 'Retries')}</th><th>p50 / p95 engine</th><th>p50 / p95 slot</th><th>{L('Trễ hàng đợi', 'Queue delay')} p50 / p95</th><th>CPU {L('TB', 'avg')}</th><th>RAM max</th><th>Byte in / out / egress</th><th>{L('Công suất lý thuyết / giờ', 'Theoretical / hour')}</th></tr>
                </thead>
                <tbody>
                  {ENGINES.map((e) => {
                    const m = metrics.engines[e];
                    if (!m) return null;
                    return (
                      <tr key={e} className="border-t border-[var(--border-subtle)]">
                        <td className="font-mono">{e}</td>
                        <td>{m.attempts}</td>
                        <td>{m.retries}</td>
                        <td>{m.duration_p50_s ?? '—'} / {m.duration_p95_s ?? '—'} s</td>
                        <td>{m.slot_p50_s ?? '—'} / {m.slot_p95_s ?? '—'} s</td>
                        <td>{m.queue_delay_p50_s ?? '—'} / {m.queue_delay_p95_s ?? '—'} s</td>
                        <td>{m.cpu_ms_avg ?? '—'} ms</td>
                        <td>{m.rss_bytes_max ? `${Math.round(m.rss_bytes_max / 1048576)} MB` : '—'}</td>
                        <td>{m.input_bytes} / {m.output_bytes} / {m.egress_bytes}</td>
                        <td>{m.theoretical_hourly_capacity?.toLocaleString() ?? '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="text-[11px] text-[var(--text-secondary)]">{metrics.capacity_formula}. {metrics.cpu_rss_note}.</p>
              {Object.keys(metrics.hosts_last_hour).length > 0 && (
                <table className="w-full text-xs">
                  <thead className="text-[var(--text-secondary)] text-left"><tr><th>Host</th><th>{L('Yêu cầu / quota (1 giờ)', 'Requests / quota (1 h)')}</th><th>Egress / {L('ngân sách', 'budget')}</th></tr></thead>
                  <tbody>
                    {Object.entries(metrics.hosts_last_hour).map(([h, v]: [string, any]) => (
                      <tr key={h} className={`border-t border-[var(--border-subtle)] ${v.over_budget ? 'text-amber-300' : ''}`}>
                        <td className="font-mono">{h}</td>
                        <td>{v.requests} / {v.quota}</td>
                        <td>{v.egress_bytes} / {v.egress_budget_bytes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </section>
      )}

      {/* Live events */}
      <section className="p-4 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] text-xs text-[var(--text-primary)]">
        <h2 className="font-medium text-sm text-[var(--text-primary)] mb-2">{L('Sự kiện gần đây', 'Recent events')}</h2>
        {events.length === 0 && <p className="text-[var(--text-secondary)]">{L('Chưa có sự kiện mới từ khi mở trang.', 'No new events since this page opened.')}</p>}
        <ul className="space-y-1">
          {events.map((e) => (
            <li key={e.id} className="flex flex-wrap gap-2">
              <span className="text-[var(--text-secondary)]">#{e.id}</span>
              <span>{ict(e.occurred_at)}</span>
              <span className="font-mono">{e.type}</span>
              <span>{e.message}</span>
              {e.batch_id && <Link className="underline text-cyan-300" href={`/engine-runs/?run=${e.batch_id}`}>{L('lượt chạy', 'run')}</Link>}
              {e.correlation_id && <span className="text-[var(--text-secondary)]">corr {e.correlation_id}</span>}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
