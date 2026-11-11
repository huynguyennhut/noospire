'use client';

import React, { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { FileCode, Lock, RefreshCw, Upload, XCircle, Download, ExternalLink, ShieldAlert } from 'lucide-react';
import { api, AdvisorySnapshotInfo, ApiError, ExecutionDetail, RunStatus } from '@/lib/api';
import { useI18n } from '@/lib/i18n';
import { RunTree, TodayResults } from '@/components/console/RunInsights';

const TZ = 'Asia/Ho_Chi_Minh';
const TERMINAL = new Set(['succeeded', 'failed', 'timed_out', 'cancelled', 'skipped', 'unavailable']);

function ict(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', { timeZone: TZ, hour12: false }) + ' ICT';
}

const STATUS_STYLE: Record<string, string> = {
  queued: 'bg-slate-800 text-slate-200 border-slate-600',
  running: 'bg-cyan-950 text-cyan-300 border-cyan-700',
  succeeded: 'bg-emerald-950 text-emerald-300 border-emerald-700',
  skipped: 'bg-amber-950 text-amber-300 border-amber-700',
  unavailable: 'bg-amber-950 text-amber-300 border-amber-700',
  failed: 'bg-rose-950 text-rose-300 border-rose-700',
  timed_out: 'bg-rose-950 text-rose-300 border-rose-700',
  cancelled: 'bg-slate-800 text-slate-400 border-slate-600',
};

function errText(e: any, vi: boolean): string {
  if (e instanceof ApiError || e?.kind) {
    const rid = e.requestId ? ` · request ${e.requestId}` : '';
    if (e.kind === 'forbidden') return (vi ? 'Không đủ quyền: ' : 'Not permitted: ') + e.message + rid;
    if (e.kind === 'not_found') return (vi ? 'Không tìm thấy hoặc ngoài phạm vi của bạn.' : 'Not found or outside your scope.') + rid;
    if (['network', 'upstream_unreachable', 'upstream_timeout', 'misrouted'].includes(e.kind))
      return (vi ? 'Không kết nối được API (' : 'API unreachable (') + e.kind + ')' + rid;
    return e.message + rid;
  }
  return String(e?.message || e);
}

function EngineRunsInner() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const router = useRouter();
  const params = useSearchParams();
  const selectedExecution = params.get('execution');
  const selectedRun = params.get('run');
  const assetParam = params.get('asset') || '';

  const [assets, setAssets] = useState<Array<{ id: string; name: string }>>([]);
  const [assetId, setAssetId] = useState(assetParam);
  const [engine, setEngine] = useState<'sbom' | 'tls_health'>('sbom');
  const [file, setFile] = useState<File | null>(null);
  const [snapshots, setSnapshots] = useState<AdvisorySnapshotInfo[] | null>(null);
  const [runs, setRuns] = useState<ExecutionDetail[]>([]);
  const [detail, setDetail] = useState<ExecutionDetail | null>(null);
  const [runFindings, setRunFindings] = useState<any[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const idemKey = useRef<string | null>(null);

  const setQuery = useCallback((next: Record<string, string | null>) => {
    const q = new URLSearchParams(params.toString());
    Object.entries(next).forEach(([k, v]) => (v ? q.set(k, v) : q.delete(k)));
    router.push(`/engine-runs/?${q.toString()}`);
  }, [params, router]);

  useEffect(() => {
    api.listAssets({ size: 200 } as any)
      .then((r: any) => setAssets((r.items || []).map((a: any) => ({ id: a.id, name: a.name }))))
      .catch((e) => setError(errText(e, vi)));
    api.listAdvisorySnapshots().then(setSnapshots).catch(() => setSnapshots(null));
  }, [vi]);

  const loadRuns = useCallback(async () => {
    try {
      const r = await api.listExecutions({ assetId: assetId || undefined, size: 20 });
      setRuns(r.items);
    } catch (e) {
      setError(errText(e, vi));
    }
  }, [assetId, vi]);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  // Detail polling: bounded (3 s) and only while the execution is not terminal.
  useEffect(() => {
    if (!selectedExecution) { setDetail(null); return; }
    let stop = false;
    let timer: any;
    const tick = async () => {
      try {
        const d = await api.getExecution(selectedExecution);
        if (stop) return;
        setDetail(d);
        setError(null);
        if (!TERMINAL.has(d.status)) timer = setTimeout(tick, 3000);
        else {
          loadRuns();
          if (d.status === 'succeeded') {
            api.request(`/findings?scan_id=${d.scan_id}&size=200`).then((r: any) => !stop && setRunFindings(r.items || []))
              .catch((e) => !stop && setError(errText(e, vi)));
          } else setRunFindings(null);
        }
      } catch (e) {
        if (!stop) { setError(errText(e, vi)); timer = setTimeout(tick, 6000); }
      }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [selectedExecution, vi, loadRuns]);

  // ?run=<batch_id>: one run accepted by POST /runs or launched by the schedule (polls until finished).
  const [run, setRun] = useState<RunStatus | null>(null);
  useEffect(() => {
    if (!selectedRun) { setRun(null); return; }
    let stop = false;
    let timer: any;
    const tick = async () => {
      try {
        const r = await api.getRun(selectedRun);
        if (stop) return;
        setRun(r);
        if (!r.finished) timer = setTimeout(tick, 3000);
      } catch (e) {
        if (!stop) setError(errText(e, vi));
      }
    };
    tick();
    return () => { stop = true; clearTimeout(timer); };
  }, [selectedRun, vi]);

  const activeSnapshot = snapshots?.find((s) => s.is_active) || null;

  const submit = async () => {
    if (!assetId || busy) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    // One key per user intent: retries of the same click reuse it, so the server returns the same execution.
    idemKey.current = idemKey.current || (typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : String(Date.now()));
    try {
      let artifactId: string | undefined;
      if (engine === 'sbom') {
        if (!file) throw new Error(vi ? 'Chọn tệp SBOM (CycloneDX/SPDX JSON).' : 'Choose an SBOM file (CycloneDX/SPDX JSON).');
        const art = await api.uploadArtifact(assetId, file);
        artifactId = art.id;
      }
      const res = await api.launchExecution({ asset_id: assetId, engine, artifact_id: artifactId }, idemKey.current);
      idemKey.current = null;
      setNotice(
        (vi ? 'Đã nhận: ' : 'Accepted: ') + `execution ${res.execution_id} · batch ${res.batch_id} · ${ict(res.queued_at)}` +
        (res.worker.ready ? '' : (vi ? ' · Chưa có worker hoạt động: job chờ trong hàng đợi.' : ' · No live worker: job waits in queue.')),
      );
      setQuery({ execution: res.execution_id, asset: assetId });
    } catch (e) {
      setError(errText(e, vi));
    } finally {
      setBusy(false);
    }
  };

  const importSnapshot = async (f: File) => {
    try {
      const label = f.name.replace(/\.json$/i, '');
      const s = await api.importAdvisorySnapshot(f, 'OSV export', label);
      setNotice((vi ? 'Đã nhập advisory snapshot ' : 'Imported advisory snapshot ') + `${s.version_label} (${s.record_count} records, ${s.digest.slice(0, 12)}…)`);
      setSnapshots(await api.listAdvisorySnapshots());
    } catch (e) {
      setError(errText(e, vi));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-4 border-b border-white/10">
        <div>
          <h1 className="text-2xl font-black tracking-tight text-white flex items-center gap-2">
            <FileCode className="w-6 h-6 text-cyan-400" /> {vi ? 'Lượt chạy engine phòng thủ' : 'Defensive engine runs'}
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            {vi ? 'SBOM đối chiếu advisory có phiên bản · đo TLS/health chỉ đọc. Giờ hiển thị theo ICT, lưu theo UTC.'
                : 'SBOM vs versioned advisories · read-only TLS/health. Times shown in ICT, stored in UTC.'}
          </p>
        </div>
        <button onClick={loadRuns} className="px-3 py-1.5 rounded-lg border border-white/10 text-xs text-slate-200 hover:bg-white/5 flex items-center gap-1">
          <RefreshCw className="w-3.5 h-3.5" /> {vi ? 'Làm mới' : 'Refresh'}
        </button>
      </div>

      {error && <div role="alert" className="p-3 rounded-lg border border-rose-700 bg-rose-950/60 text-rose-200 text-xs">{error}</div>}
      {notice && <div role="status" className="p-3 rounded-lg border border-emerald-700 bg-emerald-950/50 text-emerald-200 text-xs break-all">{notice}</div>}

      {run && (
        <section className="p-4 rounded-xl border border-cyan-800 bg-black/30 text-xs text-slate-200 space-y-2">
          <div className="flex flex-wrap gap-3 items-center">
            <b className="text-sm text-white">{run.name}</b>
            <span>batch <code>{run.batch_id}</code></span>
            <span>{vi ? 'nhận lúc' : 'accepted'} {ict(run.accepted_at)}</span>
            <span>{run.trigger}</span>
            {run.correlation_id && <span className="text-slate-400">corr {run.correlation_id}</span>}
            <span className={run.finished ? 'text-emerald-300' : 'text-cyan-300'}>
              {run.finished ? (vi ? 'đã kết thúc' : 'finished') : (vi ? 'đang xử lý' : 'in progress')}
            </span>
          </div>
          <p>{Object.entries(run.by_status).map(([k, v]) => `${k}: ${v}`).join(' · ') || (vi ? 'Không có execution nào trong phạm vi của bạn.' : 'No executions in your scope.')}</p>
          {run.plan_summary && Object.keys(run.plan_summary.reasons || {}).length > 0 && (
            <p className="text-slate-400">{vi ? 'Lý do bỏ qua/dời' : 'Skip/defer reasons'}: {Object.entries(run.plan_summary.reasons).map(([k, v]) => `${k} × ${v}`).join(' · ')}</p>
          )}
          <ul className="space-y-0.5">
            {run.executions.map((x) => (
              <li key={x.execution_id}>
                <button className="underline text-cyan-300" onClick={() => setQuery({ execution: x.execution_id })}>{x.engine_id}</button>{' '}
                <span className="font-mono">{x.status}</span> · {x.lane}
                {x.plan_note ? <span className="text-amber-300"> · {x.plan_note}</span> : null}
                {x.status_reason ? <span className="text-slate-400"> · {x.status_reason}</span> : null}
              </li>
            ))}
          </ul>
          <RunTree batchId={run.batch_id} finished={run.finished} />
        </section>
      )}

      {!selectedExecution && <TodayResults />}

      <section className="p-4 rounded-2xl border border-white/10 liquid-glass-card grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <label className="block text-xs text-slate-300">
            {vi ? 'Asset' : 'Asset'}
            <select value={assetId} onChange={(e) => { setAssetId(e.target.value); setQuery({ asset: e.target.value || null }); }}
              className="mt-1 w-full bg-black/40 border border-white/10 rounded-lg px-2 py-2 text-sm text-white">
              <option value="">{vi ? '— chọn asset trong phạm vi của bạn —' : '— choose an asset in your scope —'}</option>
              {assets.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </label>
          <fieldset className="flex gap-4 text-xs text-slate-300">
            <label className="flex items-center gap-1"><input type="radio" checked={engine === 'sbom'} onChange={() => setEngine('sbom')} /> SBOM</label>
            <label className="flex items-center gap-1"><input type="radio" checked={engine === 'tls_health'} onChange={() => setEngine('tls_health')} /> TLS / health</label>
          </fieldset>
          {engine === 'sbom' ? (
            <label className="block text-xs text-slate-300">
              {vi ? 'Tệp SBOM (CycloneDX hoặc SPDX JSON)' : 'SBOM file (CycloneDX or SPDX JSON)'}
              <input type="file" accept=".json,application/json" onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="mt-1 block w-full text-xs text-slate-300" />
            </label>
          ) : (
            <p className="text-xs text-slate-400">
              {vi ? 'Chỉ đo endpoint health mà owner đã duyệt trên asset này (một GET, không theo redirect, không gửi credential).'
                  : 'Measures only the owner-approved health endpoint of this asset (one GET, no redirects, no credentials).'}
            </p>
          )}
          <button onClick={submit} disabled={!assetId || busy || (engine === 'sbom' && !file)}
            className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white text-sm font-bold flex items-center gap-2">
            <Upload className="w-4 h-4" /> {busy ? (vi ? 'Đang gửi…' : 'Submitting…') : (vi ? 'Chạy phân tích' : 'Run analysis')}
          </button>
          <p className="text-[11px] text-slate-500">{vi ? 'Dự kiến: 1 lượt engine trên 1 asset.' : 'Planned: 1 engine execution on 1 asset.'}</p>
        </div>

        <div className="space-y-2 text-xs text-slate-300">
          <div className="font-bold text-slate-200">{vi ? 'Advisory đang dùng' : 'Active advisory snapshot'}</div>
          {snapshots === null ? (
            <div className="text-amber-300">{vi ? 'Không tải được danh sách snapshot.' : 'Could not load snapshots.'}</div>
          ) : activeSnapshot ? (
            <div className="font-mono text-[11px] space-y-0.5">
              <div>{activeSnapshot.source} · {activeSnapshot.version_label}</div>
              <div>digest {activeSnapshot.digest.slice(0, 16)}… · {activeSnapshot.record_count} records</div>
              <div>{vi ? 'nhập lúc' : 'imported'} {ict(activeSnapshot.imported_at)} · {vi ? 'tuổi' : 'age'} {activeSnapshot.age_hours} h</div>
              <div>{vi ? 'dữ liệu gốc mới nhất' : 'newest record'} {activeSnapshot.data_modified_max || '—'}</div>
            </div>
          ) : (
            <div className="text-amber-300">{vi ? 'Chưa có snapshot: lượt SBOM sẽ ở trạng thái unavailable.' : 'No snapshot: SBOM runs will be unavailable.'}</div>
          )}
          <label className="block mt-2">
            <span className="flex items-center gap-1"><Lock className="w-3 h-3" /> {vi ? 'Nhập OSV snapshot (chỉ owner)' : 'Import OSV snapshot (owner only)'}</span>
            <input type="file" accept=".json" onChange={(e) => e.target.files?.[0] && importSnapshot(e.target.files[0])} className="mt-1 block text-xs" />
          </label>
        </div>
      </section>

      {detail && (
        <section className="p-4 rounded-2xl border border-white/10 liquid-glass-card space-y-3" aria-live="polite">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`px-2 py-0.5 rounded border text-xs font-mono font-bold ${STATUS_STYLE[detail.status] || ''}`}>{detail.status}</span>
            <span className="text-xs font-mono text-slate-300 break-all">execution {detail.execution_id}</span>
            {!TERMINAL.has(detail.status) && (
              <button onClick={async () => { try { setDetail(await api.cancelExecution(detail.execution_id)); } catch (e) { setError(errText(e, vi)); } }}
                className="ml-auto px-2 py-1 rounded border border-rose-700 text-rose-300 text-xs flex items-center gap-1">
                <XCircle className="w-3.5 h-3.5" /> {vi ? 'Hủy' : 'Cancel'}
              </button>
            )}
          </div>
          {detail.status_reason && (
            <div className="text-xs text-amber-200 flex items-start gap-1"><ShieldAlert className="w-3.5 h-3.5 mt-0.5" /> {detail.error_class}: {detail.status_reason}</div>
          )}
          {detail.worker && !detail.worker.ready && (
            <div className="text-xs text-amber-300">{vi ? 'Worker: ' : 'Worker: '}{detail.worker.reason}</div>
          )}
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-[11px] font-mono text-slate-300">
            <div><dt className="inline text-slate-500">engine </dt><dd className="inline">{detail.engine_id} · {detail.driver || '—'} {detail.driver_version || ''} · {detail.execution_mode}</dd></div>
            <div><dt className="inline text-slate-500">rules </dt><dd className="inline break-all">{detail.rules.source || '—'} {detail.rules.version || ''} · {detail.rules.digest ? detail.rules.digest.slice(0, 16) + '…' : '—'}</dd></div>
            <div><dt className="inline text-slate-500">input </dt><dd className="inline break-all">{detail.input.filename || detail.input.url || '—'} · {detail.input.sha256 ? detail.input.sha256.slice(0, 16) + '…' : '—'}</dd></div>
            <div><dt className="inline text-slate-500">findings </dt><dd className="inline">{detail.finding_count ?? '—'}</dd></div>
            <div><dt className="inline text-slate-500">queued </dt><dd className="inline">{ict(detail.timestamps_utc.queued_at)}</dd></div>
            <div><dt className="inline text-slate-500">finished </dt><dd className="inline">{ict(detail.timestamps_utc.finished_at)} · {detail.duration_ms ?? '—'} ms</dd></div>
          </dl>
          {Object.keys(detail.summary || {}).length > 0 && (
            <pre className="text-[11px] bg-black/40 rounded-lg p-2 overflow-x-auto text-slate-300">{JSON.stringify(detail.summary, null, 2)}</pre>
          )}
          <div className="overflow-x-auto">
            <table className="w-full text-[11px] font-mono text-slate-300">
              <thead><tr className="text-slate-500 text-left"><th className="pr-3">#</th><th className="pr-3">status</th><th className="pr-3">phase</th><th className="pr-3">worker</th><th className="pr-3">token</th><th className="pr-3">started</th><th>error</th></tr></thead>
              <tbody>
                {(detail.attempts || []).map((a) => (
                  <tr key={a.attempt_id} className="border-t border-white/5">
                    <td className="pr-3">{a.attempt_no}</td><td className="pr-3">{a.status}</td><td className="pr-3">{a.phase}</td>
                    <td className="pr-3 break-all">{a.worker_id}</td><td className="pr-3">{a.fencing_token}</td>
                    <td className="pr-3">{ict(a.started_at)}</td><td className="break-all">{a.error_class || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap gap-3 text-xs">
            {detail.output.available && (
              <a href={api.executionOutputUrl(detail.execution_id)} className="text-cyan-300 hover:underline flex items-center gap-1">
                <Download className="w-3.5 h-3.5" /> {vi ? 'Tải kết quả chuẩn hóa' : 'Download normalized output'} (sha256 {detail.output.sha256?.slice(0, 12)}…)
              </a>
            )}
          </div>
          {detail.status === 'succeeded' && runFindings && (
            <div className="overflow-x-auto">
              <div className="text-xs font-bold text-slate-200 mb-1 flex items-center gap-1">
                <ExternalLink className="w-3.5 h-3.5" /> {vi ? 'Finding của lượt này' : 'Findings of this run'} ({runFindings.length})
              </div>
              {runFindings.length === 0 ? (
                <div className="text-xs text-emerald-300">{vi ? 'Đã đánh giá, không có finding (kết quả hợp lệ).' : 'Evaluated with zero findings (valid result).'}</div>
              ) : (
                <table className="w-full text-[11px] text-slate-300">
                  <thead className="text-slate-500 text-left"><tr><th className="pr-3">rule</th><th className="pr-3">severity</th><th className="pr-3">status</th><th className="pr-3">component</th><th>remediation</th></tr></thead>
                  <tbody>
                    {runFindings.map((f) => (
                      <tr key={f.id} className="border-t border-white/5">
                        <td className="pr-3 font-mono">{f.scanner_rule_id}</td><td className="pr-3">{f.severity}{f.evidence?.severity_basis === 'unrated_default' ? ' (unrated)' : ''}</td>
                        <td className="pr-3">{f.status}</td><td className="pr-3 font-mono break-all">{f.target_component}@{f.affected_version}</td>
                        <td>{f.remediation}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </section>
      )}

      <section className="rounded-2xl border border-white/10 liquid-glass-card overflow-x-auto">
        <table className="w-full text-xs text-slate-300">
          <thead className="text-slate-500 text-left"><tr><th className="p-2">{vi ? 'Trạng thái' : 'Status'}</th><th className="p-2">Engine</th><th className="p-2">{vi ? 'Xếp hàng' : 'Queued'}</th><th className="p-2">Findings</th><th className="p-2">{vi ? 'Lý do' : 'Reason'}</th></tr></thead>
          <tbody>
            {runs.length === 0 && <tr><td className="p-3 text-slate-500" colSpan={5}>{vi ? 'Chưa có lượt chạy trong phạm vi của bạn.' : 'No runs in your scope yet.'}</td></tr>}
            {runs.map((r) => (
              <tr key={r.execution_id} className={`border-t border-white/5 cursor-pointer hover:bg-white/5 ${r.execution_id === selectedExecution ? 'bg-white/5' : ''}`}
                onClick={() => setQuery({ execution: r.execution_id })} tabIndex={0}
                onKeyDown={(e) => { if (e.key === 'Enter') setQuery({ execution: r.execution_id }); }}>
                <td className="p-2"><span className={`px-1.5 py-0.5 rounded border font-mono ${STATUS_STYLE[r.status] || ''}`}>{r.status}</span></td>
                <td className="p-2 font-mono">{r.engine_id}</td>
                <td className="p-2">{ict(r.timestamps_utc.queued_at)}</td>
                <td className="p-2">{r.finding_count ?? '—'}</td>
                <td className="p-2 text-slate-400">{r.error_class || ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

export default function EngineRunsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-center text-slate-400">Loading…</div>}>
      <EngineRunsInner />
    </Suspense>
  );
}
