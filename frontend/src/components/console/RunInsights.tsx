'use client';

/**
 * Scan Center tracker pieces (Milestone 5):
 * - RunTree: module -> asset -> engine -> attempt -> evidence for one run, plus its diff
 *   (new / unchanged / fixed / reopened / unavailable / changed scope).
 * - TodayResults: "Kết quả hôm nay" — every run of the current ICT day with diff and skip/fail reasons.
 */

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { api, RunDiffItem, RunsOfDay } from '@/lib/api';
import { useI18n } from '@/lib/i18n';

const TZ = 'Asia/Ho_Chi_Minh';
const OUTCOMES = ['new', 'reopened', 'fixed', 'unchanged', 'unavailable', 'changed_scope'];
const OUTCOME_VI: Record<string, string> = {
  new: 'mới', reopened: 'mở lại', fixed: 'đã sửa', unchanged: 'không đổi', unavailable: 'không kiểm được', changed_scope: 'đổi phạm vi',
};

function ict(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', { timeZone: TZ, hour12: false }) + ' ICT';
}

export function RunTree({ batchId, finished }: { batchId: string; finished: boolean }) {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const [tree, setTree] = useState<any | null>(null);
  const [diff, setDiff] = useState<{ counts: Record<string, number>; items: RunDiffItem[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stop = false;
    Promise.all([api.getRunTree(batchId), api.getRunDiff(batchId)])
      .then(([t, d]) => { if (!stop) { setTree(t); setDiff(d); setError(null); } })
      .catch((e) => { if (!stop) setError(e?.message || String(e)); });
    return () => { stop = true; };
  }, [batchId, finished]);

  if (error) return <p role="alert" className="text-rose-300 text-xs">{error}</p>;
  if (!tree) return null;
  return (
    <div className="space-y-3 text-xs">
      {diff && (
        <div>
          <h3 className="font-semibold text-slate-200 mb-1">{vi ? 'Thay đổi so với trước' : 'Changes'}</h3>
          <p className="flex flex-wrap gap-3">
            {OUTCOMES.map((o) => (
              <span key={o}>{vi ? OUTCOME_VI[o] : o.replace('_', ' ')}: <b>{diff.counts[o] || 0}</b></span>
            ))}
          </p>
          {diff.items.length > 0 && (
            <table className="w-full mt-1">
              <thead className="text-left text-slate-400"><tr><th>{vi ? 'Kết quả' : 'Outcome'}</th><th>Finding</th><th>{vi ? 'Mức' : 'Severity'}</th><th>{vi ? 'Trạng thái' : 'Status'}</th><th>{vi ? 'Lý do' : 'Reason'}</th></tr></thead>
              <tbody>
                {diff.items.map((x, i) => (
                  <tr key={i} className="border-t border-white/5">
                    <td>{vi ? OUTCOME_VI[x.outcome] || x.outcome : x.outcome}</td>
                    <td><Link className="underline" href={`/findings/?finding=${x.finding_id}`}>{x.title}</Link></td>
                    <td>{x.severity}</td>
                    <td>{x.status_before ?? '∅'} → {x.status_after ?? '∅'}</td>
                    <td className="text-slate-400">{x.reason || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      <div>
        <h3 className="font-semibold text-slate-200 mb-1">{vi ? 'Cây lượt chạy' : 'Run tree'}</h3>
        <ul className="space-y-1">
          {tree.modules.map((m: any) => (
            <li key={m.module}>
              <details open>
                <summary className="cursor-pointer font-mono">{m.module}</summary>
                <ul className="ml-4 space-y-1">
                  {m.assets.map((a: any) => (
                    <li key={a.asset_id}>
                      <details open>
                        <summary className="cursor-pointer">{a.name}</summary>
                        <ul className="ml-4 space-y-1">
                          {a.engines.map((e: any) => (
                            <li key={e.execution_id}>
                              <details>
                                <summary className="cursor-pointer">
                                  <span className="font-mono">{e.engine_id}</span> · {e.status} · {e.lane}
                                  {e.reason ? <span className="text-slate-400"> · {e.reason}</span> : null}
                                </summary>
                                <ul className="ml-4">
                                  {e.attempts.map((t: any) => (
                                    <li key={t.attempt_no}>
                                      attempt {t.attempt_no} · {t.status} · {t.worker_id} · {t.phase}
                                      {t.duration_ms != null ? ` · ${t.duration_ms} ms` : ''}{t.error_class ? ` · ${t.error_class}` : ''}
                                    </li>
                                  ))}
                                  <li className="text-slate-400">
                                    evidence: in {e.evidence.input_sha256?.slice(0, 12) || '—'} · out {e.evidence.output_sha256?.slice(0, 12) || '—'} ·
                                    rules {e.evidence.rule_digest?.slice(0, 12) || '—'} · {ict(e.evidence.observed_at)}
                                    {e.evidence.output_url ? <> · <a className="underline" href={e.evidence.output_url}>output</a></> : null}
                                    {' '}· {e.evidence.findings.length} finding
                                  </li>
                                </ul>
                              </details>
                            </li>
                          ))}
                        </ul>
                      </details>
                    </li>
                  ))}
                </ul>
              </details>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function TodayResults() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const [data, setData] = useState<RunsOfDay | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listRunsForDay().then(setData).catch((e) => setError(e?.message || String(e)));
  }, []);

  return (
    <section className="p-4 rounded-xl border border-white/10 bg-black/30 text-xs text-slate-200 space-y-2">
      <h2 className="text-sm font-semibold">{vi ? 'Kết quả hôm nay' : "Today's results"} {data ? `(${data.day_ict} ICT)` : ''}</h2>
      {error && <p role="alert" className="text-rose-300">{error}</p>}
      {data && data.runs.length === 0 && <p className="text-slate-400">{vi ? 'Chưa có lượt chạy nào hôm nay.' : 'No runs today yet.'}</p>}
      {data && data.runs.length > 0 && (
        <>
          <p>{OUTCOMES.map((o) => `${vi ? OUTCOME_VI[o] : o}: ${data.totals[o] || 0}`).join(' · ')}</p>
          <ul className="space-y-1">
            {data.runs.map((r) => (
              <li key={r.batch_id} className="border-t border-white/5 pt-1">
                <Link className="underline text-cyan-300" href={`/engine-runs/?run=${r.batch_id}`}>{r.name || r.batch_id}</Link>{' '}
                · {ict(r.accepted_at)} · {r.trigger} · {r.finished ? (vi ? 'đã xong' : 'finished') : (vi ? 'đang chạy' : 'running')}
                · {Object.entries(r.by_status).map(([k, v]) => `${k} ${v}`).join(', ')}
                {r.skip_or_fail.length > 0 && (
                  <ul className="ml-4 text-amber-300">
                    {r.skip_or_fail.map((x) => <li key={x.execution_id}>{x.engine_id} {x.status}: {x.reason || '—'}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
