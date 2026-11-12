'use client';

/**
 * Integrations (Milestone 6 contract clean-up).
 * Shows only server-measured state:
 *  - defensive engines and worker heartbeats (/operations/overview, /engines/workers)
 *  - threat-intel feeds (/threat-intel/summary, /threat-intel/sync) with the real per-source result
 * Webhook delivery is NOT implemented in the pilot; the page says so instead of simulating a send.
 */

import React, { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { api, OperationsOverview } from '@/lib/api';
import { useI18n } from '@/lib/i18n';

const TZ = 'Asia/Ho_Chi_Minh';

function ict(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', { timeZone: TZ, hour12: false }) + ' ICT';
}

export default function IntegrationsPage() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => (vi ? a : b);
  const [ov, setOv] = useState<OperationsOverview | null>(null);
  const [intel, setIntel] = useState<any | null>(null);
  const [sync, setSync] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const errs: string[] = [];
    await Promise.all([
      api.getOperationsOverview().then(setOv).catch((e) => errs.push(`operations: ${e?.message || e}`)),
      api.getIntelStatus().then(setIntel).catch((e) => errs.push(`threat-intel: ${e?.message || e}`)),
    ]);
    setError(errs.length ? errs.join(' · ') : null);
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function doSync() {
    setBusy(true);
    try {
      setSync(await api.syncIntel());
      await load();
    } catch (e: any) {
      setError(`sync: ${e?.message || e}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6 text-sm text-slate-200">
      <div className="flex items-end justify-between">
        <h1 className="text-xl font-semibold">{L('Tích hợp', 'Integrations')}</h1>
        <button onClick={() => void load()} className="px-3 py-1.5 rounded border border-slate-600 flex items-center gap-1"><RefreshCw className="w-4 h-4" />{L('Tải lại', 'Reload')}</button>
      </div>
      {error && <div role="alert" className="p-3 rounded border border-rose-700 bg-rose-950 text-rose-200">{error}</div>}

      <section className="p-4 rounded-xl border border-white/10 bg-black/30 space-y-2">
        <h2 className="font-semibold">{L('Engine phòng thủ và worker', 'Defensive engines and workers')}</h2>
        {ov ? (
          <>
            <ul className="text-xs space-y-1">
              {Object.entries(ov.engines).map(([name, e]) => (
                <li key={name}>
                  <span className="font-mono">{name}</span> · {L('thành công cuối', 'last success')} {ict(e.last_success_at)}
                  {e.stale ? <span className="text-amber-300"> · {L('dữ liệu cũ', 'stale')}</span> : null} · {e.queued} {L('chờ', 'queued')} · {e.running} {L('chạy', 'running')}
                </li>
              ))}
            </ul>
            <p className="text-xs">Worker online: {ov.workers_online}/{ov.workers.length}</p>
            {ov.workers.map((w) => (
              <p key={w.worker_id} className="text-xs text-slate-400"><code>{w.worker_id}</code> · {w.state} · {ict(w.last_seen_at)}{w.throttle_reason ? ` · ${w.throttle_reason}` : ''}</p>
            ))}
            <p className="text-xs text-slate-500">
              {L('Các engine tích hợp cũ (nuclei, ZAP, trivy) chưa được nối vào luồng execution có fencing nên không hiển thị trạng thái ở đây.',
                 'Legacy integrated engines (nuclei, ZAP, trivy) are not wired into the fenced execution flow, so no status is shown for them.')}
            </p>
          </>
        ) : <p className="text-xs text-slate-400">{L('Chưa có dữ liệu.', 'No data.')}</p>}
      </section>

      <section className="p-4 rounded-xl border border-white/10 bg-black/30 space-y-2">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold">{L('Nguồn threat intelligence', 'Threat-intelligence feeds')}</h2>
          <button disabled={busy} onClick={() => void doSync()} className="ml-auto px-3 py-1.5 rounded bg-cyan-700 text-white disabled:opacity-50">
            {busy ? L('Đang đồng bộ…', 'Syncing…') : L('Đồng bộ ngay', 'Sync now')}
          </button>
        </div>
        {intel && (
          <>
            <p className="text-xs">CVE: {intel.total_cves} · KEV: {intel.total_kev_exploited} · {L('đồng bộ toàn cục cuối', 'last global sync')} {ict(intel.last_global_sync)}</p>
            <table className="w-full text-xs">
              <thead className="text-left text-slate-400"><tr><th>{L('Nguồn', 'Source')}</th><th>{L('Trạng thái', 'Status')}</th><th>{L('Lần cuối', 'Last sync')}</th><th>Records</th><th>{L('Lỗi', 'Error')}</th></tr></thead>
              <tbody>
                {Object.values(intel.sources || {}).map((s: any) => (
                  <tr key={s.source_name} className="border-t border-white/5">
                    <td className="font-mono">{s.source_name}</td><td>{s.status}</td><td>{ict(s.last_sync_at)}</td><td>{s.records_synced}</td><td className="text-rose-300">{s.error_message || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
        {sync && (
          <p role="status" className={sync.status === 'completed' ? 'text-emerald-300 text-xs' : 'text-amber-300 text-xs'}>
            {L('Kết quả đồng bộ', 'Sync result')}: {sync.status} · {(sync.results || []).map((r: any) => `${r.source}: ${r.success ? 'ok' : 'failed'}`).join(' · ')}
          </p>
        )}
        <p className="text-xs text-slate-500">
          {L('Snapshot advisory dùng cho engine SBOM được nhập riêng ở trang Engine runs và có digest/phiên bản.',
             'The advisory snapshot used by the SBOM engine is imported separately on Engine runs, with digest and version.')}
        </p>
      </section>

      <section className="p-4 rounded-xl border border-white/10 bg-black/30 space-y-1">
        <h2 className="font-semibold">Webhook (Discord / Telegram)</h2>
        <p className="text-xs text-amber-300">
          {L('Chưa có trong pilot: chưa có kênh gửi và biên nhận thật nên không có nút gửi thử. Thông báo hiện ở hộp thư trong console.',
             'Not in the pilot yet: no real delivery channel or receipts, so there is no test-send button. Notifications are in the console inbox.')}
        </p>
      </section>
    </div>
  );
}
