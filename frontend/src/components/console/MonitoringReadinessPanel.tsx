'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { api, OperationsOverview } from '@/lib/api';
import { useI18n } from '@/lib/i18n';

/** Inventory admission and live worker telemetry are separate from historical chart totals. */
export default function MonitoringReadinessPanel() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => vi ? a : b;
  const [data, setData] = useState<{ ops: OperationsOverview; eligible: number; all: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      const [ops, eligible, all] = await Promise.all([
        api.getOperationsOverview(), api.listAssets({ assessment_eligible: true, size: 1 }), api.listAssets({ size: 1 }),
      ]);
      setData({ ops, eligible: eligible.total, all: all.total }); setError(null);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, []);
  useEffect(() => { void load(); const timer = setInterval(() => void load(), 15000); return () => clearInterval(timer); }, [load]);
  const web = data?.ops.engines.public_web;
  return <section className="assessment-panel space-y-3" aria-label={L('Giám sát thực tế', 'Actual monitoring')}>
    <div className="flex flex-wrap justify-between items-center gap-3"><h2 className="font-semibold">{L('Giám sát thực tế & phạm vi đã đối chiếu', 'Actual monitoring & reconciled scope')}</h2><Link className="assessment-link" href="/schedules/">{L('Lịch & vận hành', 'Schedules & operations')} →</Link></div>
    {error && <p className="assessment-alert" role="alert">{L('Không tải được hiện trạng; số liệu cũ không xác nhận hệ thống đang chạy.', 'Current state unavailable; cached figures do not confirm the system is running.')} {error}</p>}
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
      <div><p className="assessment-muted">{L('Mục tiêu đủ điều kiện', 'Eligible targets')}</p><p className="text-2xl font-semibold">{data?.eligible ?? '—'}</p></div>
      <div><p className="assessment-muted">{L('Mẫu / cần đối chiếu', 'Test / reconciliation required')}</p><p className="text-2xl font-semibold">{data ? data.all - data.eligible : '—'}</p><Link className="underline text-xs" href="/assets/?inventory=all">{L('Xem kiểm kê', 'Inspect inventory')}</Link></div>
      <div><p className="assessment-muted">{L('Worker online', 'Workers online')}</p><p className="text-2xl font-semibold">{data?.ops.workers_online ?? '—'}</p><p className="assessment-muted">{data?.ops.capacity.emergency_stop_active ? L('Đang dừng khẩn', 'Emergency stop active') : data?.ops.workers_online ? L('Có heartbeat mới', 'Fresh heartbeat received') : L('Chưa xác nhận worker hoạt động', 'No active worker confirmed')}</p></div>
      <div><p className="assessment-muted">public_web · {L('kết quả mới nhất', 'latest result')}</p><p className="font-semibold">{web?.latest_result?.status || L('Chưa có lượt chạy', 'No execution yet')}</p>{web?.latest_result && <Link className="underline text-xs" href={`/engine-runs/?execution=${web.latest_result.execution_id}`}>{L('Log & bằng chứng', 'Logs & evidence')} →</Link>}</div>
    </div>
    {data?.ops.schedules_visible && <p className="text-sm">{L('Lịch đang bật', 'Active schedules')}: {data.ops.schedules.filter((s) => s.is_active).map((s) => `${s.name} · ${s.interval_minutes} ${L('phút', 'min')}`).join(' / ') || L('Chưa có', 'None')}</p>}
    <p className="assessment-muted">{L('Các biểu đồ và tổng số lịch sử bên dưới bao gồm dữ liệu mẫu / kiểm thử trong cơ sở dữ liệu; không phải tỷ lệ bao phủ production. Hoàn thành quan sát web không xác nhận sức khỏe ứng dụng hoặc đánh giá toàn diện. Kiểm tra có đăng nhập vẫn cần hồ sơ được duyệt.', 'Historical charts and totals below include database seed / test records; they are not production coverage. Completed public web observations do not establish application health or comprehensive assessment. Authenticated checks still require approved profiles.')}</p>
  </section>;
}
