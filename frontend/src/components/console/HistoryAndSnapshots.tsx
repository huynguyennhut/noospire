'use client';

/**
 * History & Reports (Milestone 5).
 * - HistoryPanel: filter executions by ICT day range / run / asset / engine / module / actor / status.
 *   Filters and page live in the URL, so Back restores them. Selective hide: preview shows how many
 *   executions are affected, the owner confirms with a reason; the server re-checks the count and
 *   writes the audit log. Evidence, findings and audit stay.
 * - SnapshotsPanel: generate a frozen report (assets / run / estate), view it inline, download
 *   PDF/HTML/JSON with the authenticated session; checksum, template version and snapshot shown.
 */

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { api, ReportSnapshotInfo } from '@/lib/api';
import { useI18n } from '@/lib/i18n';

const TZ = 'Asia/Ho_Chi_Minh';
const FILTERS = ['day_from', 'day_to', 'batch_id', 'asset_id', 'engine', 'module', 'actor_id', 'status'] as const;

function ict(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', { timeZone: TZ, hour12: false }) + ' ICT';
}

export function HistoryPanel() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => (vi ? a : b);
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const current: Record<string, string> = {};
  FILTERS.forEach((k) => { const v = params.get(k); if (v) current[k] = v; });
  const page = Number(params.get('page') || '1');
  const filterKey = JSON.stringify(current);

  const [data, setData] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>(current);
  useEffect(() => { setDraft(JSON.parse(filterKey)); }, [filterKey]); // Back/forward restores the form
  const [preview, setPreview] = useState<{ would_hide: number; excluded_active: number; note: string } | null>(null);
  const [reason, setReason] = useState('');
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.listHistory({ ...JSON.parse(filterKey), page, size: 50 }));
      setError(null);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }, [filterKey, page]);

  useEffect(() => { void load(); }, [load]);

  const apply = (next: Record<string, string>, nextPage = 1) => {
    const q = new URLSearchParams();
    Object.entries(next).forEach(([k, v]) => { if (v) q.set(k, v); });
    if (nextPage > 1) q.set('page', String(nextPage));
    router.push(`${pathname}?${q.toString()}`); // push: Back restores the previous filter
  };

  const filterBody = () => {
    const b: Record<string, string> = {};
    Object.entries(current).forEach(([k, v]) => { b[k] = v; });
    return b;
  };

  async function doPreview() {
    setNotice(null);
    try {
      setPreview(await api.previewHide(filterBody()));
    } catch (e: any) {
      setError(e?.kind === 'forbidden' ? L('Chỉ chủ hệ thống được xóa khỏi giao diện.', 'Only the system owner can hide history.') : (e?.message || String(e)));
    }
  }

  async function doHide() {
    if (!preview) return;
    try {
      const r = await api.hideHistory(filterBody(), reason, preview.would_hide);
      setNotice(`${L('Đã ẩn', 'Hidden')} ${r.hidden} execution · ${L('đã ghi audit', 'audit recorded')}`);
      setPreview(null);
      setReason('');
      void load();
    } catch (e: any) {
      setError(e?.message || String(e));
      setPreview(null);
    }
  }

  return (
    <section className="p-4 rounded-xl border border-white/10 bg-black/30 text-xs text-slate-200 space-y-3">
      <h2 className="text-sm font-semibold">{L('Lịch sử lượt chạy', 'Run history')}</h2>
      <form
        className="flex flex-wrap gap-2 items-end"
        onSubmit={(e) => { e.preventDefault(); apply(draft); }}
      >
        {FILTERS.map((k) => (
          <label key={k} className="flex flex-col">
            <span className="text-slate-400">{k}</span>
            <input
              type={k.startsWith('day_') ? 'date' : 'text'}
              value={draft[k] || ''}
              onChange={(e) => setDraft({ ...draft, [k]: e.target.value })}
              className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-36"
            />
          </label>
        ))}
        <button className="px-3 py-1.5 rounded bg-cyan-700 text-white">{L('Lọc', 'Filter')}</button>
        <button type="button" onClick={() => { setDraft({}); apply({}); }} className="px-3 py-1.5 rounded border border-slate-600">{L('Xóa lọc', 'Clear')}</button>
        <button type="button" onClick={() => void doPreview()} className="px-3 py-1.5 rounded border border-rose-700 text-rose-300">
          {L('Ẩn các mục đang lọc…', 'Hide filtered…')}
        </button>
      </form>
      {error && <p role="alert" className="text-rose-300">{error}</p>}
      {notice && <p role="status" className="text-emerald-300">{notice}</p>}
      {preview && (
        <div role="dialog" aria-modal="true" aria-label={L('Xác nhận ẩn', 'Confirm hide')} className="p-3 rounded border border-rose-700 bg-rose-950/60 space-y-2">
          <p>
            {L('Sẽ ẩn', 'Will hide')} <b>{preview.would_hide}</b> execution{preview.excluded_active ? ` (${preview.excluded_active} ${L('đang chạy được giữ lại', 'active kept')})` : ''}. {preview.note}
          </p>
          <input autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder={L('Lý do (bắt buộc)', 'Reason (required)')}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-full" onKeyDown={(e) => { if (e.key === 'Escape') setPreview(null); }} />
          <div className="flex gap-2">
            <button disabled={reason.trim().length < 3 || preview.would_hide === 0} onClick={() => void doHide()} className="px-3 py-1.5 rounded bg-rose-700 text-white disabled:opacity-50">
              {L(`Xác nhận ẩn ${preview.would_hide} mục`, `Hide ${preview.would_hide} item(s)`)}
            </button>
            <button onClick={() => setPreview(null)} className="px-3 py-1.5 rounded border border-slate-600">{L('Hủy', 'Cancel')}</button>
          </div>
        </div>
      )}
      {data && (
        <>
          <p className="text-slate-400">{data.total} execution · {L('trang', 'page')} {data.page}/{data.pages}</p>
          <table className="w-full">
            <thead className="text-left text-slate-400"><tr><th>{L('Nhận lúc', 'Queued')}</th><th>Engine</th><th>{L('Trạng thái', 'Status')}</th><th>Trigger</th><th>{L('Lượt chạy', 'Run')}</th><th>Finding</th><th>{L('Lý do', 'Reason')}</th></tr></thead>
            <tbody>
              {data.items.map((x: any) => (
                <tr key={x.execution_id} className="border-t border-white/5">
                  <td><Link className="underline" href={`/engine-runs/?execution=${x.execution_id}`}>{ict(x.queued_at)}</Link></td>
                  <td>{x.engine_id}</td>
                  <td>{x.status}</td>
                  <td>{x.trigger}</td>
                  <td>{x.batch_id ? <Link className="underline" href={`/engine-runs/?run=${x.batch_id}`}>{x.batch_id.slice(0, 8)}</Link> : '—'}</td>
                  <td>{x.finding_count ?? '—'}</td>
                  <td className="text-slate-400">{x.status_reason || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => apply(current, page - 1)} className="px-2 py-1 rounded border border-slate-600 disabled:opacity-40">‹</button>
            <button disabled={page >= data.pages} onClick={() => apply(current, page + 1)} className="px-2 py-1 rounded border border-slate-600 disabled:opacity-40">›</button>
          </div>
        </>
      )}
    </section>
  );
}

export function SnapshotsPanel() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => (vi ? a : b);
  const [items, setItems] = useState<ReportSnapshotInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [batchId, setBatchId] = useState('');
  const [assetIds, setAssetIds] = useState('');
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await api.listReportSnapshots());
      setError(null);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const ids = assetIds.split(/[\s,]+/).filter(Boolean);
      const r = await api.createReportSnapshot({
        title: title || L('Báo cáo bảo mật Empire', 'Empire security report'),
        ...(batchId ? { batch_id: batchId } : ids.length ? { asset_ids: ids } : {}),
      });
      setView(r.id);
      void load();
    } catch (err: any) {
      setError(err?.kind === 'forbidden' ? L('Không đủ quyền REPORT cho phạm vi này.', 'Missing REPORT permission for this scope.') : (err?.message || String(err)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="p-4 rounded-xl border border-white/10 bg-black/30 text-xs text-slate-200 space-y-3">
      <h2 className="text-sm font-semibold">{L('Báo cáo có snapshot', 'Snapshot reports')}</h2>
      <form onSubmit={create} className="flex flex-wrap gap-2 items-end">
        <label className="flex flex-col"><span className="text-slate-400">{L('Tiêu đề', 'Title')}</span>
          <input value={title} onChange={(e) => setTitle(e.target.value)} className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-56" /></label>
        <label className="flex flex-col"><span className="text-slate-400">{L('Lượt chạy (batch id)', 'Run (batch id)')}</span>
          <input value={batchId} onChange={(e) => setBatchId(e.target.value)} className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-64" /></label>
        <label className="flex flex-col"><span className="text-slate-400">{L('hoặc asset id (cách nhau dấu phẩy)', 'or asset ids (comma separated)')}</span>
          <input value={assetIds} onChange={(e) => setAssetIds(e.target.value)} className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-64" /></label>
        <button disabled={busy} className="px-3 py-1.5 rounded bg-cyan-700 text-white disabled:opacity-50">{L('Tạo báo cáo', 'Generate')}</button>
        <span className="text-slate-500">{L('Để trống cả hai = toàn hệ thống (chỉ owner)', 'Both empty = whole estate (owner only)')}</span>
      </form>
      {error && <p role="alert" className="text-rose-300">{error}</p>}
      <table className="w-full">
        <thead className="text-left text-slate-400"><tr><th>{L('Tạo lúc', 'Generated')}</th><th>{L('Tiêu đề', 'Title')}</th><th>{L('Phạm vi', 'Scope')}</th><th>Finding</th><th>Template</th><th>Snapshot sha256</th><th>{L('Tải', 'Files')}</th></tr></thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id} className="border-t border-white/5 align-top">
              <td>{ict(r.generated_at)}</td>
              <td><button className="underline" onClick={() => setView(view === r.id ? null : r.id)}>{r.title}</button></td>
              <td>{r.scope.kind}{r.scope.batch_id ? ` · ${r.scope.batch_id.slice(0, 8)}` : ''} · {r.scope.asset_ids.length} asset</td>
              <td>{r.finding_count}</td>
              <td className="font-mono">{r.template_version}</td>
              <td className="font-mono">{r.snapshot_sha256.slice(0, 16)}…</td>
              <td className="space-x-2">
                {(['pdf', 'html', 'json'] as const).map((f) => (
                  <a key={f} className="underline" href={api.reportSnapshotUrl(r.id, f)} title={`sha256 ${r.files[f]?.sha256}`}>{f.toUpperCase()}</a>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {view && (
        <iframe
          title={L('Xem báo cáo', 'Report preview')}
          src={api.reportSnapshotUrl(view, 'html', true)}
          sandbox=""
          className="w-full h-[600px] bg-white rounded"
        />
      )}
    </section>
  );
}
