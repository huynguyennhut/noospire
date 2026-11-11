'use client';

/**
 * Finding lifecycle (Milestone 5): first/last seen, last verified, source, confidence, owner,
 * assignee, every change (who/when/from/to) and every observation. Recheck reruns the same
 * approved defensive control; Rescan asset creates a new run for the asset within the user's scope.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { api, FindingHistory } from '@/lib/api';
import { useI18n } from '@/lib/i18n';

const TZ = 'Asia/Ho_Chi_Minh';

function ict(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', { timeZone: TZ, hour12: false }) + ' ICT';
}

const OUTCOME_STYLE: Record<string, string> = {
  new: 'text-rose-300', reopened: 'text-rose-300', unchanged: 'text-slate-300', fixed: 'text-emerald-300',
  unavailable: 'text-amber-300', changed_scope: 'text-amber-300',
};

function key(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

export default function FindingLifecyclePanel({ findingId, assetId }: { findingId: string; assetId: string }) {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => (vi ? a : b);
  const [h, setH] = useState<FindingHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<React.ReactNode>(null);
  const [busy, setBusy] = useState(false);
  const recheckKey = useRef<string>(key());

  const load = useCallback(async () => {
    try {
      setH(await api.getFindingHistory(findingId));
      setError(null);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  }, [findingId]);

  useEffect(() => {
    recheckKey.current = key();
    void load();
  }, [load]);

  async function recheck() {
    setBusy(true);
    try {
      const r = await api.recheckFinding(findingId, recheckKey.current);
      setNotice(
        <span>
          {r.note || L('Đã xếp hàng kiểm tra lại', 'Recheck queued')} ·{' '}
          {r.execution_id && <Link className="underline" href={`/engine-runs/?execution=${r.execution_id}`}>{L('theo dõi', 'track')}</Link>}
        </span>,
      );
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function rescan() {
    setBusy(true);
    try {
      const r = await api.launchRun({ selection: { kind: 'assets', asset_ids: [assetId] } }, key());
      setNotice(
        <span>
          {L('Đã tạo lượt quét asset', 'Asset rescan accepted')} · batch <code>{r.batch_id}</code> ·{' '}
          <Link className="underline" href={`/engine-runs/?run=${r.batch_id}`}>{L('theo dõi', 'track')}</Link>
        </span>,
      );
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mb-4 p-3 rounded-xl border border-white/10 bg-black/30 text-xs text-slate-200 space-y-3" aria-label={L('Vòng đời finding', 'Finding lifecycle')}>
      {error && <div role="alert" className="text-rose-300">{error}</div>}
      {notice && <div role="status" className="text-emerald-300">{notice}</div>}
      <div className="flex flex-wrap gap-2">
        <button disabled={busy} onClick={() => void recheck()} className="px-3 py-1.5 rounded-lg bg-cyan-700 text-white disabled:opacity-50">
          {L('Kiểm tra lại (Recheck)', 'Recheck')}
        </button>
        <button disabled={busy} onClick={() => void rescan()} className="px-3 py-1.5 rounded-lg border border-white/15 text-slate-200 disabled:opacity-50">
          {L('Quét lại asset', 'Rescan asset')}
        </button>
        <span className="text-slate-400 self-center">
          {L('Recheck chạy lại đúng control đã duyệt; chỉ engine mới đổi trạng thái khi có bằng chứng tương đương.',
             'Recheck reruns the same approved control; only the engine changes status, with equivalent evidence.')}
        </span>
      </div>
      {h && (
        <>
          <dl className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div><dt className="text-slate-400">{L('Thấy lần đầu', 'First seen')}</dt><dd>{ict(h.first_seen_at)}</dd></div>
            <div><dt className="text-slate-400">{L('Thấy lần cuối', 'Last seen')}</dt><dd>{ict(h.last_seen_at)}</dd></div>
            <div><dt className="text-slate-400">{L('Xác minh gần nhất', 'Last verified')}</dt><dd>{ict(h.last_verified_at)}</dd></div>
            <div><dt className="text-slate-400">{L('Nguồn / độ tin cậy', 'Source / confidence')}</dt><dd>{h.source.engine}{h.source.driver_version ? ` ${h.source.driver_version}` : ''} · {h.confidence}</dd></div>
            <div><dt className="text-slate-400">{L('Chủ sở hữu', 'Owner')}</dt><dd>{h.owner || '—'}</dd></div>
            <div><dt className="text-slate-400">{L('Người xử lý', 'Assignee')}</dt><dd>{h.assignee || '—'}</dd></div>
            <div><dt className="text-slate-400">{L('Trạng thái', 'Status')}</dt><dd>{h.status}</dd></div>
            <div><dt className="text-slate-400">Asset</dt><dd>{h.asset.name || h.asset.id} · {h.asset.module || '—'}</dd></div>
          </dl>
          <div>
            <h3 className="font-semibold mb-1">{L('Lịch sử thay đổi', 'Change history')}</h3>
            <ol className="space-y-0.5">
              {h.changes.map((c, i) => (
                <li key={i}>
                  {ict(c.at)} · <b>{c.actor}</b> · {c.field}: {c.old ?? '∅'} → {c.new ?? '∅'}
                  {c.reason ? <span className="text-slate-400"> · {c.reason}</span> : null}
                  {c.execution_id ? <> · <Link className="underline" href={`/engine-runs/?execution=${c.execution_id}`}>execution</Link></> : null}
                </li>
              ))}
            </ol>
          </div>
          <div>
            <h3 className="font-semibold mb-1">{L('Mọi lần quan sát', 'All observations')}</h3>
            <table className="w-full">
              <thead className="text-slate-400 text-left"><tr><th>{L('Thời điểm', 'When')}</th><th>{L('Kết quả', 'Outcome')}</th><th>{L('Trạng thái', 'Status')}</th><th>{L('Bằng chứng', 'Evidence')}</th></tr></thead>
              <tbody>
                {h.observations.map((o, i) => (
                  <tr key={i} className="border-t border-white/5 align-top">
                    <td>{ict(o.observed_at)}</td>
                    <td className={OUTCOME_STYLE[o.outcome] || ''}>{o.outcome}{o.reason ? <div className="text-slate-500">{o.reason}</div> : null}</td>
                    <td>{o.status_before ?? '∅'} → {o.status_after ?? '∅'}</td>
                    <td className="font-mono">
                      <Link className="underline" href={`/engine-runs/?execution=${o.execution_id}`}>{o.execution_id.slice(0, 8)}</Link>
                      {o.output_sha256 ? ` · out ${o.output_sha256.slice(0, 10)}` : ''}{o.rule_digest ? ` · rules ${o.rule_digest.slice(0, 10)}` : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
