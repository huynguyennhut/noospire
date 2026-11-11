'use client';

import React, { useState, useEffect } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import {
  Lock,
  Mail,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  KeyRound,
} from 'lucide-react';
import { useI18n } from '@/lib/i18n';
import { api } from '@/lib/api';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export default function LoginPage() {
  const router = useRouter();
  const { t, locale, setLocale } = useI18n();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  // Already signed in (server-side session)? Go straight to the dashboard.
  useEffect(() => {
    api.me().then(() => router.push('/dashboard/')).catch(() => {});
  }, [router]);

  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setError(null);
    setLoading(true);

    const cleanEmail = email.trim();

    try {
      // Call backend API /api/v1/auth/login
      // Server sets the HttpOnly session cookie; nothing is written to browser storage.
      await api.login(cleanEmail, password);

      setSuccess(true);
      setTimeout(() => {
        router.push('/dashboard');
      }, 500);
    } catch (err: any) {
      const outage = ['network', 'upstream_unreachable', 'upstream_timeout', 'misrouted'].includes(err?.kind);
      const errorMsg =
        (outage
          ? (locale === 'vi'
              ? `Không kết nối được máy chủ API (${err.kind}${err.requestId ? ' · ' + err.requestId : ''}).`
              : `API is unreachable (${err.kind}${err.requestId ? ' · ' + err.requestId : ''}).`)
          : null) ||
        err?.detail ||
        err?.message ||
        (locale === 'vi'
          ? 'Tên đăng nhập hoặc mật khẩu không chính xác.'
          : 'Invalid credentials. Please verify your username and password.');
      setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
      setLoading(false);
    }
  };


  return (
    <div className="min-h-screen bg-nf-950 text-nf-100 flex flex-col justify-between relative overflow-hidden selection:bg-white/20 selection:text-white">
      {/* Background Subtle Gradient Glow */}
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-gradient-to-tr from-white/[0.03] via-cyan-500/[0.04] to-transparent rounded-full blur-3xl pointer-events-none" />

      {/* Top Header */}
      <header className="p-6 flex items-center justify-between border-b border-white/[0.06] backdrop-blur-md relative z-10">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-b from-white/[0.09] via-white/[0.04] to-white/[0.01] border border-white/15 p-1 flex items-center justify-center shadow-[inset_0_1px_2px_rgba(255,255,255,0.2),0_4px_12px_rgba(0,0,0,0.5)] backdrop-blur-xl">
            <Image
              src="/brand/logo-white-emblem.png"
              alt="NOOSFORGE Emblem"
              width={28}
              height={28}
              className="w-full h-full object-contain filter drop-shadow-[0_2px_4px_rgba(255,255,255,0.2)]"
              priority
            />
          </div>
          <div>
            <div className="text-sm font-black font-mono tracking-tight text-white leading-none">NOOSFORGE</div>
            <div className="text-[10px] font-bold text-slate-400 tracking-wider uppercase mt-0.5">SECURITY INTELLIGENCE</div>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs">
          <button
            onClick={() => setLocale(locale === 'vi' ? 'en' : 'vi')}
            className="px-2.5 py-1 rounded-lg border border-white/10 hover:border-white/20 bg-white/[0.03] text-slate-300 hover:text-white transition"
          >
            {locale === 'vi' ? 'EN' : 'VI'}
          </button>
          <Badge severity="info" size="sm" dot>
            AIR-GAPPED READY
          </Badge>
        </div>
      </header>

      {/* Main Login Box */}
      <main className="flex-1 flex items-center justify-center p-4 relative z-10 my-8">
        <div className="w-full max-w-md space-y-6">
          <Card className="p-6 md:p-8 backdrop-blur-2xl bg-black/75 border border-white/10 shadow-[0_16px_48px_rgba(0,0,0,0.8)] relative overflow-hidden">
            {/* Top Border Specular Shine */}
            <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-white/40 to-transparent pointer-events-none" />

            {/* Header */}
            <div className="text-center space-y-2 mb-6">
              <div className="inline-flex p-2.5 rounded-2xl bg-white/[0.05] border border-white/10 text-white shadow-[0_0_20px_rgba(255,255,255,0.1)] mb-1">
                <KeyRound className="w-5 h-5 text-cyan-400" />
              </div>
              <h1 className="text-xl md:text-2xl font-black tracking-tight text-white font-mono uppercase">
                {locale === 'vi' ? 'Cổng Xác Thực Quản Trị' : 'Enterprise Admin Portal'}
              </h1>
              <p className="text-xs text-slate-400">
                {locale === 'vi'
                  ? 'NOOSFORGE Security Command Center — Empire Ecosystem'
                  : 'Continuous Security Platform Authentication'}
              </p>
            </div>

            {/* Control Plane Authentication Banner */}
            <div className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-xs mb-4">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-cyan-400" />
                <span className="font-mono text-[11px] text-slate-300">
                  {locale === 'vi' ? 'Trạng Thái Kiểm Soát Truy Cập:' : 'Control Plane Access:'}{' '}
                  <strong className="text-cyan-400">RBAC PROTECTED</strong>
                </span>
              </div>
              <Badge severity="info" size="sm">
                AUTHENTICATION
              </Badge>
            </div>

            {/* Error Message */}
            {error && (
              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2 animate-fadeIn mb-4">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {/* Success Message */}
            {success && (
              <div className="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs flex items-center gap-2 animate-fadeIn mb-4">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>{locale === 'vi' ? 'Xác thực thành công! Đang chuyển hướng...' : 'Authenticated! Redirecting...'}</span>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleLogin} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <Mail className="w-3.5 h-3.5 text-slate-400" />
                  <span>{locale === 'vi' ? 'Tài Khoản / Email Quản Trị' : 'Username / Email'}</span>
                </label>
                <input
                  type="text"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="dangnhutnguyen0910@gmail.com"
                  required
                  className="w-full px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 focus:border-white/30 focus:outline-none text-xs text-white placeholder-slate-600 font-mono transition"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <Lock className="w-3.5 h-3.5 text-slate-400" />
                  <span>{locale === 'vi' ? 'Mật Khẩu' : 'Password'}</span>
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  required
                  className="w-full px-3.5 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 focus:border-white/30 focus:outline-none text-xs text-white placeholder-slate-600 font-mono transition"
                />
              </div>

              <Button
                type="submit"
                variant="primary"
                size="md"
                loading={loading}
                className="w-full mt-4"
                icon={<ArrowRight className="w-4 h-4" />}
              >
                <span>{locale === 'vi' ? 'Đăng Nhập Vào Hệ Thống' : 'Authenticate Session'}</span>
              </Button>
            </form>
          </Card>
        </div>
      </main>

      {/* Footer */}
      <footer className="p-4 border-t border-white/[0.06] text-center text-[11px] text-slate-500">
        NOOSFORGE Security Intelligence &copy; 2026. Self-Hosted Sovereign Deployment. All rights reserved.
      </footer>
    </div>
  );
}
