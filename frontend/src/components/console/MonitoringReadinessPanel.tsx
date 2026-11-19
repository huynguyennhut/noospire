'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { Pause, Play } from 'lucide-react';
import { api, MonitorSchedule, OperationsOverview, RunRequestBody, RunStatus } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { Button } from '@/components/ui/button';

function resultLabel(status: string | null | undefined, vi: boolean): string {
  if (!status) return vi ? 'Chưa có lượt chạy' : 'No execution yet';
  if (!vi) return status.replaceAll('_', ' ');
  return ({ succeeded: 'Hoàn thành', completed: 'Hoàn thành', partial: 'Hoàn thành một phần',
    failed: 'Thất bại', timed_out: 'Quá thời gian', cancelled: 'Đã hủy', queued: 'Đang chờ',
    running: 'Đang xử lý', unavailable: 'Chưa sẵn sàng', no_work: 'Không có kiểm tra được chạy',
  } as Record<string, string>)[status] || status;
}

export function ScheduleStatus({ schedule: s, vi }: { schedule: MonitorSchedule; vi: boolean }) {
  const L = (a: string, b: string) => vi ? a : b;
  const time = (value: string | null) => value ? new Date(value).toLocaleString(vi ? 'vi-VN' : 'en-GB', { timeZone: 'Asia/Ho_Chi_Minh' }) + ' ICT' : '—';
  return <div className="min-w-0 space-y-1">
    <h3 className="font-semibold break-words">{s.name}</h3>
    <p className="text-sm">{s.is_active ? L('Tự động quét: Bật', 'Automatic scanning: On') : L('Tự động quét: Tạm dừng', 'Automatic scanning: Paused')} · {L('mỗi', 'every')} {s.interval_minutes} {L('phút', 'minutes')}</p>
    <p className="assessment-muted">{L('Lần tiếp theo', 'Next run')}: {s.is_active ? time(s.next_run_at) : L('Đang tạm dừng', 'Paused')}</p>
    <p className="assessment-muted">{L('Lần gần nhất', 'Last run')}: {time(s.last_run_at)} · {s.running ? L('Đang xử lý', 'Running') : resultLabel(s.latest_result.status, vi)}</p>
    {!!s.backlog && <p className="assessment-muted">{L('Đang chờ', 'Pending')}: {s.backlog}</p>}
    {s.overdue_reason && <p role="alert" className="assessment-alert">{s.overdue_reason}</p>}
    {s.last_batch_id && <Link className="assessment-link text-sm" href={`/engine-runs/?run=${s.last_batch_id}`}>{L('Kết quả & log lần gần nhất', 'Latest results & logs')} →</Link>}
    {s.latest_result.report_id && <Link className="assessment-link text-sm ml-2" href={`/reports/?report=${s.latest_result.report_id}`}>{L('Báo cáo tự động', 'Automatic report')} →</Link>}
  </div>;
}

/** Ordinary scans use the saved scope without asking for another approval. */
export default function MonitoringReadinessPanel() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => vi ? a : b;
  const [data, setData] = useState<{ ops: OperationsOverview; eligible: number; all: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [accepted, setAccepted] = useState<RunStatus | null>(null);
  const loading = useRef(false);
  const acting = useRef(false);
  const intents = useRef(new Map<string, { key: string; body: RunRequestBody }>());
  const load = useCallback(async () => {
    if (loading.current) return;
    loading.current = true;
    try {
      const [ops, eligible, all] = await Promise.all([
        api.getOperationsOverview(), api.listAssets({ assessment_eligible: true, size: 1 }), api.listAssets({ size: 1 }),
      ]);
      setData({ ops, eligible: eligible.total, all: all.total }); setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { loading.current = false; }
  }, []);
  useEffect(() => { void load(); const timer = setInterval(() => void load(), 15000); return () => clearInterval(timer); }, [load]);

  async function act(s: MonitorSchedule, action: 'run' | 'toggle') {
    if (acting.current) return;
    acting.current = true; setBusy(s.id); setActionError(null);
    try {
      if (action === 'toggle') {
        await api.updateMonitorSchedule(s.id, { is_active: !s.is_active, expected_revision: s.revision });
      } else {
        let intent = intents.current.get(s.id);
        if (!intent) {
          intent = { key: crypto.randomUUID(), body: { selection: s.selection, engines: s.engines, profile: s.profile } };
          intents.current.set(s.id, intent);
        }
        setAccepted(await api.launchRun(intent.body, intent.key));
        intents.current.delete(s.id);
      }
      await load();
    } catch (e) { setActionError(e instanceof Error ? e.message : String(e)); }
    finally { acting.current = false; setBusy(null); }
  }

  const web = data?.ops.engines.public_web;
  return <section className="assessment-panel space-y-4" aria-label={L('Quét tự động', 'Automatic scanning')}>
    <div className="flex flex-wrap justify-between items-center gap-3"><h2 className="font-semibold">{L('Quét tự động & quét ngay', 'Automatic scanning & scan now')}</h2><Link className="assessment-link" href="/scans/">{L('Chọn mục tiêu quét', 'Choose scan targets')} →</Link></div>
    {error && <p className="assessment-alert" role="alert">{L('Không tải được hiện trạng; số liệu cũ không xác nhận hệ thống đang chạy.', 'Current state unavailable; cached figures do not confirm the system is running.')} {error}</p>}
    {actionError && <p className="assessment-alert" role="alert">{actionError}</p>}
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
      <div><p className="assessment-muted">{L('Mục tiêu đang cấu hình', 'Configured targets')}</p><p className="text-2xl font-semibold">{data?.eligible ?? '—'}</p><Link className="underline text-xs" href="/assets/?inventory=all">{L('Kiểm kê', 'Inventory')}: {data?.all ?? '—'}</Link></div>
      <div><p className="assessment-muted">{L('Worker đang hoạt động', 'Workers online')}</p><p className="text-2xl font-semibold">{data?.ops.workers_online ?? '—'}</p></div>
      <div><p className="assessment-muted">{L('Bộ chạy lịch', 'Scheduler')}</p><p className="font-semibold">{!data ? '—' : data.ops.scheduler?.online ? L('Đang hoạt động', 'Online') : L('Chưa có tín hiệu mới', 'No fresh heartbeat')}</p></div>
      <div><p className="assessment-muted">{L('Kết quả web mới nhất', 'Latest web result')}</p><p className="font-semibold">{resultLabel(web?.latest_result?.status, vi)}</p>{web?.latest_result && <Link className="underline text-xs" href={`/engine-runs/?execution=${web.latest_result.execution_id}`}>{L('Log & bằng chứng', 'Logs & evidence')} →</Link>}</div>
    </div>
    {data?.ops.capacity.emergency_stop_active && <p role="alert" className="assessment-alert">{L('Dừng khẩn đang bật. Các lượt quét đang tạm dừng.', 'Emergency stop is active. Scanning is paused.')}</p>}
    {data && (!data.ops.workers_online || !data.ops.scheduler?.online) && <p role="alert" className="assessment-alert">{L('Chưa đủ tín hiệu worker và bộ chạy lịch. Lịch đã bật không có nghĩa hệ thống đang thực thi; kiểm tra tiến trình và log vận hành.', 'Worker and scheduler heartbeats are required. An enabled schedule alone does not establish execution; inspect processes and operational logs.')}</p>}
    {data?.ops.schedules.map((s) => <div key={s.id} className="border-t border-[var(--border-subtle)] pt-4 flex flex-wrap items-start justify-between gap-4">
      <ScheduleStatus schedule={s} vi={vi} />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" icon={<Play className="w-4 h-4" />} disabled={!!busy || !!error || data.ops.capacity.emergency_stop_active || s.running || s.backlog > 0} loading={busy === s.id} onClick={() => void act(s, 'run')}>{L('Quét ngay', 'Scan now')}</Button>
        <Button size="sm" variant="outline" icon={s.is_active ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />} disabled={!!busy || !!error} onClick={() => void act(s, 'toggle')}>{s.is_active ? L('Tạm dừng lịch', 'Pause schedule') : L('Bật tự động', 'Enable automatic scanning')}</Button>
      </div>
    </div>)}
    {data?.ops.schedules_visible && !data.ops.schedules.length && <p className="text-sm">{L('Chưa có lịch tự động.', 'No automatic schedule yet.')} <Link className="underline" href="/schedules/">{L('Tạo lịch', 'Create schedule')}</Link></p>}
    {accepted && <p role="status" className="text-sm">{accepted.executions.length ? L('Đã xếp hàng quét.', 'Scan queued.') : L('Không có kiểm tra nào được xếp hàng; xem lý do trong lượt chạy.', 'No checks queued; inspect the run for reasons.')} <Link className="assessment-link" href={`/engine-runs/?run=${accepted.batch_id}`}>{L('Theo dõi tiến độ & log', 'Track progress & logs')} →</Link></p>}
    <p className="assessment-muted">{L('Web công khai: kiểm tra theo chế độ đã cấu hình; duyệt trang cùng origin có ngân sách hoặc HEAD tại URL cụ thể. Lịch web tự xuất báo cáo khi hoàn tất. Máy phải hoạt động để chạy sáng, tối và qua đêm. Phạm vi kiểm thử có đăng nhập và engine còn thiếu được ghi rõ ở Trung tâm đánh giá.', 'Public web follows the configured bounded same-origin traversal or single-URL HEAD mode. Web schedules generate reports on completion. The host must stay on for morning, evening and overnight runs. Authenticated coverage and missing engines are listed in the Assessment Center.')}</p>
    <Link className="assessment-link text-sm" href="/schedules/">{L('Cấu hình lịch & lịch sử thực thi', 'Schedule settings & execution history')} →</Link>
    {data && data.all > data.eligible && <p className="assessment-muted">{L('Các biểu đồ lịch sử bên dưới còn bao gồm bản ghi mẫu / kiểm thử; không phải kết quả đánh giá production. Số mục tiêu đang cấu hình quét được hiển thị riêng ở trên.', 'Historical charts below also include seed / test records; they are not production assessment results. Configured scan targets are counted separately above.')}</p>}
  </section>;
}
