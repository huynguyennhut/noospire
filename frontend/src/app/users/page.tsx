'use client';

/**
 * Users (Milestone 5): only the sole owner sees and uses this screen. Server enforces it too
 * (every call is owner-only); a non-owner sees the server's refusal, not an empty table.
 * Active/disabled, invite (non-owner roles only), per-asset grants and the audit log
 * "who did what, when" (filter by user / action).
 */

import React, { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { useI18n } from '@/lib/i18n';

const TZ = 'Asia/Ho_Chi_Minh';
const ROLES = ['DEVELOPER', 'VIEWER', 'OPERATOR', 'SECURITY_LEAD'];

function ict(iso: string | null | undefined): string {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('vi-VN', { timeZone: TZ, hour12: false }) + ' ICT';
}

type U = { id: string; username: string; email: string; role: string; is_active: boolean; is_owner: boolean; created_at: string };
type G = { id: string; asset_id: string; permissions: string; granted_by: string; created_at: string };
type A = { id: string; user_id: string; username: string; action: string; details: string; ip_address: string; created_at: string };

export default function UsersPage() {
  const { locale } = useI18n();
  const vi = locale === 'vi';
  const L = (a: string, b: string) => (vi ? a : b);
  const [users, setUsers] = useState<U[] | null>(null);
  const [assets, setAssets] = useState<Array<{ id: string; name: string }>>([]);
  const [sel, setSel] = useState<U | null>(null);
  const [grants, setGrants] = useState<G[]>([]);
  const [audit, setAudit] = useState<A[]>([]);
  const [auditUser, setAuditUser] = useState('');
  const [auditAction, setAuditAction] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [invite, setInvite] = useState({ username: '', email: '', password: '', role: 'DEVELOPER' });
  const [grant, setGrant] = useState({ asset_id: '', permissions: 'READ,SCAN' });

  const fail = (e: any) => setError(e?.kind === 'forbidden'
    ? L('Chỉ chủ hệ thống được quản lý người dùng.', 'Only the system owner manages users.')
    : (e?.message || String(e)));

  const loadAudit = useCallback(async () => {
    const q = new URLSearchParams({ limit: '100' });
    if (auditUser) q.set('user_id', auditUser);
    if (auditAction) q.set('action', auditAction);
    try {
      setAudit(await api.request<A[]>(`/auth/audit?${q.toString()}`));
    } catch (e) {
      fail(e);
    }
  }, [auditUser, auditAction]); // eslint-disable-line react-hooks/exhaustive-deps

  const load = useCallback(async () => {
    try {
      setUsers(await api.request<U[]>('/auth/users'));
      const a: any = await api.listAssets({ size: 200 } as any);
      setAssets((a.items || []).map((x: any) => ({ id: x.id, name: x.name })));
      setError(null);
    } catch (e) {
      fail(e);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void loadAudit(); }, [loadAudit]);

  const openUser = async (u: U) => {
    setSel(u);
    try {
      setGrants(await api.request<G[]>(`/auth/users/${u.id}/grants`));
    } catch (e) {
      fail(e);
    }
  };

  const toggle = async (u: U) => {
    if (!window.confirm(u.is_active
      ? L(`Vô hiệu hóa ${u.username}? Mọi phiên của người này kết thúc ngay.`, `Disable ${u.username}? All their sessions end now.`)
      : L(`Kích hoạt lại ${u.username}?`, `Re-enable ${u.username}?`))) return;
    try {
      await api.request(`/auth/users/${u.id}/status`, { method: 'PATCH', body: JSON.stringify({ is_active: !u.is_active }) });
      setNotice(L('Đã cập nhật trạng thái và ghi audit.', 'Status updated and audited.'));
      void load();
      void loadAudit();
    } catch (e) {
      fail(e);
    }
  };

  const doInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await api.request('/auth/users/invite', { method: 'POST', body: JSON.stringify(invite) });
      setInvite({ username: '', email: '', password: '', role: 'DEVELOPER' });
      setNotice(L('Đã tạo tài khoản. Gửi mật khẩu tạm qua kênh riêng.', 'Account created. Share the temporary password out of band.'));
      void load();
      void loadAudit();
    } catch (err) {
      fail(err);
    }
  };

  const addGrant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!sel) return;
    try {
      await api.request(`/auth/users/${sel.id}/grants`, { method: 'POST', body: JSON.stringify(grant) });
      void openUser(sel);
      void loadAudit();
    } catch (err) {
      fail(err);
    }
  };

  const revoke = async (g: G) => {
    if (!sel || !window.confirm(L('Thu hồi quyền này?', 'Revoke this grant?'))) return;
    try {
      await api.request(`/auth/users/${sel.id}/grants/${g.id}`, { method: 'DELETE' });
      void openUser(sel);
      void loadAudit();
    } catch (err) {
      fail(err);
    }
  };

  const assetName = (id: string) => assets.find((a) => a.id === id)?.name || id;

  return (
    <div className="space-y-6 text-sm text-slate-200">
      <h1 className="text-xl font-semibold">{L('Người dùng và quyền', 'Users and access')}</h1>
      {error && <div role="alert" className="p-3 rounded border border-rose-700 bg-rose-950 text-rose-200">{error}</div>}
      {notice && <div role="status" className="p-3 rounded border border-emerald-700 bg-emerald-950 text-emerald-200">{notice}</div>}

      {users && (
        <section className="p-4 rounded-xl border border-white/10 bg-black/30 space-y-3">
          <table className="w-full text-xs">
            <thead className="text-left text-slate-400"><tr><th>{L('Tên', 'Username')}</th><th>Email</th><th>{L('Vai trò', 'Role')}</th><th>{L('Trạng thái', 'Status')}</th><th>{L('Tạo lúc', 'Created')}</th><th /></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className={`border-t border-white/5 ${sel?.id === u.id ? 'bg-white/5' : ''}`}>
                  <td><button className="underline" onClick={() => void openUser(u)}>{u.username}</button>{u.is_owner ? ' (owner)' : ''}</td>
                  <td>{u.email}</td>
                  <td>{u.role}</td>
                  <td className={u.is_active ? 'text-emerald-300' : 'text-rose-300'}>{u.is_active ? 'active' : 'disabled'}</td>
                  <td>{ict(u.created_at)}</td>
                  <td>{!u.is_owner && <button onClick={() => void toggle(u)} className="px-2 py-0.5 rounded border border-slate-600">{u.is_active ? L('Vô hiệu hóa', 'Disable') : L('Kích hoạt', 'Enable')}</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <form onSubmit={doInvite} className="flex flex-wrap gap-2 items-end text-xs">
            <input required placeholder="username" value={invite.username} onChange={(e) => setInvite({ ...invite, username: e.target.value })} className="bg-slate-800 border border-slate-600 rounded px-2 py-1" />
            <input required type="email" placeholder="email" value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} className="bg-slate-800 border border-slate-600 rounded px-2 py-1" />
            <input required type="password" minLength={12} autoComplete="new-password" placeholder={L('mật khẩu tạm (≥12)', 'temporary password (≥12)')} value={invite.password} onChange={(e) => setInvite({ ...invite, password: e.target.value })} className="bg-slate-800 border border-slate-600 rounded px-2 py-1" />
            <select value={invite.role} onChange={(e) => setInvite({ ...invite, role: e.target.value })} className="bg-slate-800 border border-slate-600 rounded px-2 py-1">
              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button className="px-3 py-1.5 rounded bg-cyan-700 text-white">{L('Mời', 'Invite')}</button>
          </form>
        </section>
      )}

      {sel && (
        <section className="p-4 rounded-xl border border-white/10 bg-black/30 space-y-2 text-xs">
          <h2 className="text-sm font-semibold">{L('Quyền theo asset của', 'Asset grants for')} {sel.username}</h2>
          {sel.is_owner ? <p className="text-slate-400">{L('Chủ hệ thống có toàn quyền.', 'The owner has estate-wide access.')}</p> : (
            <>
              <ul className="space-y-1">
                {grants.length === 0 && <li className="text-slate-400">{L('Chưa có quyền nào: người này không thấy asset nào.', 'No grants: this user sees no asset.')}</li>}
                {grants.map((g) => (
                  <li key={g.id}>{assetName(g.asset_id)} · {g.permissions} · {ict(g.created_at)} <button onClick={() => void revoke(g)} className="ml-2 underline text-rose-300">{L('thu hồi', 'revoke')}</button></li>
                ))}
              </ul>
              <form onSubmit={addGrant} className="flex flex-wrap gap-2 items-end">
                <select required value={grant.asset_id} onChange={(e) => setGrant({ ...grant, asset_id: e.target.value })} className="bg-slate-800 border border-slate-600 rounded px-2 py-1">
                  <option value="">{L('— chọn asset —', '— asset —')}</option>
                  {assets.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
                <input value={grant.permissions} onChange={(e) => setGrant({ ...grant, permissions: e.target.value })} className="bg-slate-800 border border-slate-600 rounded px-2 py-1 w-48" aria-label="permissions (READ,SCAN,TRIAGE,REPORT)" />
                <button className="px-3 py-1.5 rounded bg-cyan-700 text-white">{L('Cấp quyền', 'Grant')}</button>
              </form>
            </>
          )}
        </section>
      )}

      <section className="p-4 rounded-xl border border-white/10 bg-black/30 space-y-2 text-xs">
        <h2 className="text-sm font-semibold">{L('Audit: ai thực hiện gì, khi nào', 'Audit: who did what, when')}</h2>
        <div className="flex flex-wrap gap-2">
          <select value={auditUser} onChange={(e) => setAuditUser(e.target.value)} className="bg-slate-800 border border-slate-600 rounded px-2 py-1">
            <option value="">{L('mọi người', 'everyone')}</option>
            {(users || []).map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
          </select>
          <input placeholder="action (e.g. GRANT_CREATE)" value={auditAction} onChange={(e) => setAuditAction(e.target.value)} className="bg-slate-800 border border-slate-600 rounded px-2 py-1" />
        </div>
        <table className="w-full">
          <thead className="text-left text-slate-400"><tr><th>{L('Thời điểm', 'When')}</th><th>{L('Ai', 'Who')}</th><th>{L('Hành động', 'Action')}</th><th>{L('Chi tiết', 'Details')}</th><th>IP</th></tr></thead>
          <tbody>
            {audit.map((a) => (
              <tr key={a.id} className="border-t border-white/5 align-top">
                <td>{ict(a.created_at)}</td><td>{a.username}</td><td className="font-mono">{a.action}</td><td className="break-all">{a.details}</td><td>{a.ip_address}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
