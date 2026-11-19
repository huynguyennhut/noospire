'use client';

import React, { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Activity, CalendarClock, CheckCircle, Crosshair, Eye, Play, RefreshCw, ShieldAlert } from 'lucide-react';
import { api, ExecutionDetail, OperationsOverview, RunPlan, RunRequestBody, RunStatus } from '@/lib/api';
import { Asset } from '@/lib/types';
import { assessmentEligible, assessmentLabel, eligibleAssetIds } from '@/lib/assessment';
import { useI18n } from '@/lib/i18n';
import { Button } from '@/components/ui/button';

function ScanCenter() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => vi ? a : b;
  const params = useSearchParams();
  const [assets, setAssets] = useState<Asset[]>([]);
  const [runs, setRuns] = useState<ExecutionDetail[]>([]);
  const [ops, setOps] = useState<OperationsOverview | null>(null);
  const [selection, setSelection] = useState(params.get('asset') || 'eligible');
  const [plan, setPlan] = useState<RunPlan | null>(null);
  const [accepted, setAccepted] = useState<RunStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const request = useRef<RunRequestBody | null>(null);
  const intentKey = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [inventory, executions, operations] = await Promise.all([
        api.listAllAssets(), api.listExecutions({ size: 10 }), api.getOperationsOverview(),
      ]);
      setAssets(inventory);
      setRuns(executions.items);
      setOps(operations);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void load(); const timer = setInterval(() => void load(), 15000); return () => clearInterval(timer); }, [load]);
  const eligible = assets.filter(assessmentEligible);
  const selected = assets.find((a) => a.id === selection);
  const targetIds = selection === 'eligible' ? eligibleAssetIds(assets) : selected && assessmentEligible(selected) ? [selected.id] : [];

  async function preview() {
    if (busy || targetIds.length === 0) return;
    setBusy(true); setError(null); setAccepted(null); setPlan(null);
    request.current = { selection: { kind: 'assets', asset_ids: targetIds }, engines: ['public_web'], profile: 'light' };
    intentKey.current = crypto.randomUUID();
    try { setPlan(await api.previewPlan(request.current)); }
    catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function launch() {
    if (submitting.current || targetIds.length === 0) return;
    submitting.current = true;
    // Preview is optional. The API always validates the current scope itself.
    request.current ??= { selection: { kind: 'assets', asset_ids: targetIds }, engines: ['public_web'], profile: 'light' };
    intentKey.current ??= crypto.randomUUID();
    setBusy(true); setError(null);
    try {
      const result = await api.launchRun(request.current, intentKey.current);
      setAccepted(result); setPlan(null); intentKey.current = null; request.current = null;
      void load();
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { submitting.current = false; setBusy(false); }
  }

  return (
    <div className="space-y-6 text-[var(--text-primary)]">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--border-subtle)] pb-5">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Crosshair className="w-6 h-6" />{L('Trung tâm đánh giá', 'Assessment center')}</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">{L('Phạm vi đã đối chiếu · hàng đợi bền vững · kết quả và giới hạn có bằng chứng.', 'Reconciled scope · durable queue · evidence-backed results and coverage limits.')}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link href="/engine-runs/" className="assessment-link"><Activity className="w-4 h-4" />{L('Lượt chạy & nhật ký', 'Runs & logs')}</Link>
          <Link href="/schedules/" className="assessment-link"><CalendarClock className="w-4 h-4" />{L('Lịch 2 giờ & vận hành', '2-hour schedules & operations')}</Link>
        </div>
      </header>

      {error && <div role="alert" className="assessment-alert">{error}</div>}
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="assessment-panel"><div className="assessment-muted">{L('Mục tiêu đủ điều kiện', 'Eligible targets')}</div><div className="text-3xl font-semibold mt-2">{loading ? '—' : eligible.length}</div></div>
        <div className="assessment-panel"><div className="assessment-muted">{L('Bản ghi cần đối chiếu / kiểm thử', 'Reconciliation / test records')}</div><div className="text-3xl font-semibold mt-2">{loading ? '—' : assets.length - eligible.length}</div><Link href="/assets/?inventory=all" className="text-xs underline">{L('Xem toàn bộ kho tài sản', 'Inspect full inventory')}</Link></div>
        <div className="assessment-panel"><div className="assessment-muted">{L('Worker đang hoạt động', 'Workers online')}</div><div className="text-3xl font-semibold mt-2">{ops?.workers_online ?? '—'}</div><div className="text-xs text-[var(--text-secondary)]">{ops?.workers_online ? L('Theo heartbeat mới nhất', 'From fresh heartbeats') : L('Job sẽ chờ đến khi worker hoạt động', 'Jobs wait until a worker is online')}</div></div>
      </div>

      <section className="assessment-panel space-y-4">
        <div className="flex items-center gap-2"><Eye className="w-5 h-5" /><h2 className="font-semibold">{L('Quan sát web công khai', 'Public web observation')}</h2><code className="text-xs text-[var(--text-secondary)]">public_web</code></div>
        <p className="text-sm text-[var(--text-secondary)]">{L('Chạy chế độ đã cấu hình trên từng mục tiêu: HEAD tại URL cụ thể hoặc duyệt tối đa 12 trang công khai cùng origin, 1 request/giây và 1 MB/lượt. Kiểm tra TLS, header, cookie và chính sách HTML; Nuclei thụ động phân tích header trong sandbox khi có sẵn. Không gửi credential, không theo redirect hoặc submit form.', 'Uses each target’s configured mode: single-URL HEAD or up to 12 same-origin public pages, 1 request/second and 1 MB/run. Checks TLS, headers, cookies and HTML policies; passive Nuclei analyzes headers in a sandbox when available. No credentials, redirects or form submissions.')}</p>
        <label className="block text-sm font-medium" htmlFor="scan-target">{L('Phạm vi đánh giá', 'Assessment scope')}</label>
        <select id="scan-target" value={selection} disabled={busy || loading} onChange={(e) => { setSelection(e.target.value); setPlan(null); request.current = null; intentKey.current = null; }} className="assessment-input w-full">
          <option value="eligible">{L('Tất cả mục tiêu đủ điều kiện', 'All eligible targets')} ({eligible.length})</option>
          {assets.map((a) => <option key={a.id} value={a.id} disabled={!assessmentEligible(a)}>{a.name} · {assessmentLabel(a, vi)}</option>)}
        </select>
        {selected && <p className="text-xs text-[var(--text-secondary)] break-all">{selected.target_locator} · {assessmentLabel(selected, vi)}</p>}
        <p className="text-xs text-[var(--text-secondary)]">{L('Các bản ghi mẫu không được đưa vào đánh giá khách hàng. VERIFIED cũ không thay thế nguồn kiểm kê và phạm vi được duyệt.', 'Seeded records are excluded from customer assessments. A historical VERIFIED flag does not replace inventory provenance and approved scope.')}</p>
        <div className="flex flex-wrap gap-2"><Button onClick={() => void launch()} loading={busy} disabled={loading || targetIds.length === 0 || !!ops?.capacity.emergency_stop_active} icon={<Play className="w-4 h-4" />}>{L('Quét ngay', 'Scan now')}</Button><Button variant="outline" onClick={() => void preview()} disabled={busy || loading || targetIds.length === 0} icon={<Eye className="w-4 h-4" />}>{L('Chi tiết kế hoạch', 'Plan details')}</Button></div>
      </section>

      {plan && <section className="assessment-panel space-y-4" aria-live="polite">
        <h2 className="font-semibold">{L('Kế hoạch từ máy chủ', 'Server execution plan')}</h2>
        <p className="text-sm">{plan.summary.queue} {L('xếp hàng', 'queued')} · {plan.summary.defer} {L('dời lịch', 'deferred')} · {plan.summary.skip} {L('bỏ qua', 'skipped')}</p>
        <div className="overflow-x-auto"><table className="assessment-table"><thead><tr><th>{L('Mục tiêu', 'Target')}</th><th>{L('Quyết định', 'Decision')}</th><th>{L('Lý do', 'Reason')}</th></tr></thead><tbody>{plan.items.map((item) => <tr key={`${item.asset_id}-${item.engine}`}><td>{item.asset_name}</td><td>{item.decision}</td><td>{item.reason || item.reason_code || '—'}</td></tr>)}</tbody></table></div>
        <div className="flex gap-2"><Button onClick={() => void launch()} loading={busy} disabled={plan.summary.queue + plan.summary.defer === 0} icon={<Play className="w-4 h-4" />}>{L('Chạy kế hoạch này', 'Run this plan')}</Button><Button onClick={() => setPlan(null)} disabled={busy}>{L('Đóng', 'Close')}</Button></div>
      </section>}

      {accepted && <section className="assessment-panel space-y-2" role="status"><div className="flex gap-2 items-center"><CheckCircle className="w-4 h-4" /><strong>{accepted.executions.length ? L('Đã nhận vào hàng đợi', 'Accepted into queue') : L('Không có kiểm tra nào được xếp hàng', 'No checks queued')}</strong></div><p className="text-sm">{accepted.executions.length ? L('Theo dõi tiến độ, kết quả và log ở lượt chạy bên dưới.', 'Follow progress, results and logs in the run below.') : L('Xem lý do cụ thể trong lượt chạy; chưa có kiểm tra nào được thực hiện.', 'Inspect the specific reasons in the run; no checks were performed.')}</p><Link href={`/engine-runs/?run=${accepted.batch_id}`} className="assessment-link">{L('Theo dõi lượt chạy', 'Track run')} →</Link></section>}

      <section className="assessment-panel space-y-3"><h2 className="font-semibold flex gap-2 items-center"><ShieldAlert className="w-4 h-4" />{L('Phạm vi chưa được đánh giá', 'Coverage not yet assessed')}</h2><p className="text-sm text-[var(--text-secondary)]">{L('Phân quyền, tài khoản, logic nghiệp vụ và kiểm thử có đăng nhập cần hồ sơ xác thực và dữ liệu kiểm thử được chỉ định. SBOM cần artifact và advisory; health cần endpoint được duyệt. Các engine ngoài chỉ được dùng sau khi tích hợp và kiểm chứng khả năng thực tế.', 'Authorization, account, business-logic and authenticated checks need designated identities and test records. SBOM needs an artifact and advisory snapshot; health needs an approved endpoint. External engines require validated integrations and capabilities.')}</p><Link href="/engine-runs/" className="text-sm underline">{L('Xem engine, bằng chứng và cấu hình bổ sung', 'Inspect engines, evidence and additional configuration')}</Link></section>

      <section className="assessment-panel space-y-3"><div className="flex justify-between items-center"><h2 className="font-semibold">{L('Lượt chạy gần đây', 'Recent executions')}</h2><Button size="sm" onClick={() => void load()} icon={<RefreshCw className="w-3 h-3" />}>{L('Làm mới', 'Refresh')}</Button></div><div className="overflow-x-auto"><table className="assessment-table"><thead><tr><th>Engine</th><th>{L('Trạng thái', 'Status')}</th><th>{L('Kết quả / lý do', 'Result / reason')}</th><th>{L('Chi tiết', 'Details')}</th></tr></thead><tbody>{runs.map((run) => <tr key={run.execution_id}><td><code>{run.engine_id}</code></td><td>{run.status}</td><td>{run.status_reason || (run.finding_count !== null ? `${run.finding_count} findings` : '—')}</td><td><Link className="underline" href={`/engine-runs/?execution=${run.execution_id}&asset=${run.asset_id}`}>{L('Nhật ký & bằng chứng', 'Logs & evidence')}</Link></td></tr>)}{!loading && !runs.length && <tr><td colSpan={4}>{L('Chưa có lượt chạy.', 'No executions yet.')}</td></tr>}</tbody></table></div></section>
    </div>
  );
}

export default function ScansPage() {
  return <Suspense fallback={<div className="p-6">Loading…</div>}><ScanCenter /></Suspense>;
}
