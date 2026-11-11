'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  Server,
  Layers,
  Crosshair,
  Radio,
  AlertTriangle,
  Flame,
  CheckCircle2,
  FileText,
  CalendarClock,
  Code2,
  Cpu,
  Activity,
  Settings,
  Bell,
  Users,
  Menu,
  X,
  Languages,
  ChevronLeft,
  ChevronRight,
  Wifi,
  WifiOff,
  CheckCheck,
  Clock,
} from 'lucide-react';
import { useI18n, Locale } from '@/lib/i18n';
import { api } from '@/lib/api';

// ============================================================================
// Types & Navigation Taxonomy (14 Views Grouped into 4 Logical Categories)
// ============================================================================

interface NavItem {
  name: string;
  i18nKey: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
}

interface NavGroup {
  groupKey: string;
  defaultTitle: string;
  items: NavItem[];
}

const NAVIGATION_GROUPS: NavGroup[] = [
  {
    groupKey: 'nav.group.core',
    defaultTitle: 'Core Overview',
    items: [
      { name: 'Security Overview', i18nKey: 'nav.overview', href: '/dashboard', icon: LayoutDashboard },
    ],
  },
  {
    groupKey: 'nav.group.inventory',
    defaultTitle: 'Inventory & Scans',
    items: [
      { name: 'Targets', i18nKey: 'nav.targets', href: '/assets', icon: Server },
      { name: 'Scan Center', i18nKey: 'nav.scans', href: '/scans', icon: Crosshair },
      { name: 'Active Assessments', i18nKey: 'nav.activeAssessments', href: '/active-assessments', icon: Radio },
      { name: 'Engine Runs', i18nKey: 'nav.engineRuns', href: '/engine-runs', icon: Code2 },
      { name: 'Schedules', i18nKey: 'nav.schedules', href: '/schedules', icon: CalendarClock },
    ],
  },
  {
    groupKey: 'nav.group.intelligence',
    defaultTitle: 'Intelligence & Modules',
    items: [
      { name: 'Empire Modules', i18nKey: 'nav.modules', href: '/empire-modules', icon: Layers, badge: 'Empire' },
      { name: 'Findings & Evidence', i18nKey: 'nav.findings', href: '/findings', icon: AlertTriangle },
      { name: 'Vulnerability Intelligence', i18nKey: 'nav.intel', href: '/threat-intel', icon: Flame },
      { name: 'Remediation Tracking', i18nKey: 'nav.remediation', href: '/remediation', icon: CheckCircle2 },
    ],
  },
  {
    groupKey: 'nav.group.governance',
    defaultTitle: 'Governance & System',
    items: [
      { name: 'Detection Rules', i18nKey: 'nav.rules', href: '/detection-rules', icon: Code2, badge: 'YAML' },
      { name: 'Reports', i18nKey: 'nav.reports', href: '/reports', icon: FileText },
      { name: 'Users', i18nKey: 'nav.users', href: '/users', icon: Users },
      { name: 'Integrations', i18nKey: 'nav.integrations', href: '/integrations', icon: Cpu },
      { name: 'System Health', i18nKey: 'nav.health', href: '/health', icon: Activity },
      { name: 'Settings', i18nKey: 'nav.settings', href: '/settings', icon: Settings },
    ],
  },
];

interface AlertNotification {
  id: string;
  title: string;
  message: string;
  severity: string;
  timestamp: string;
  isRead: boolean;
  link: string;
}

const SEV_DOT: Record<string, string> = {
  CRITICAL: 'bg-rose-500', HIGH: 'bg-orange-500', MEDIUM: 'bg-amber-400', LOW: 'bg-sky-400', INFO: 'bg-slate-400',
};

/** Per-user inbox list shared by the mobile and desktop popovers. */
function NotificationList({ items, error, vi, onOpen, onDelete }: {
  items: AlertNotification[];
  error: string | null;
  vi: boolean;
  onOpen: (n: AlertNotification) => void;
  onDelete: (n: AlertNotification) => void;
}) {
  if (error) {
    return <div className="py-6 text-center text-xs text-amber-300" role="status">{error}</div>;
  }
  if (items.length === 0) {
    return <div className="py-6 text-center text-xs text-nf-500">{vi ? 'Không có thông báo' : 'No notifications'}</div>;
  }
  return (
    <ul className="space-y-2 max-h-72 overflow-y-auto" aria-label={vi ? 'Thông báo' : 'Notifications'}>
      {items.map((n) => (
        <li key={n.id} className={`p-2.5 rounded-xl border text-xs ${n.isRead ? 'bg-white/[0.01] border-white/5 text-nf-500' : 'bg-white/[0.04] border-white/10 text-nf-200'}`}>
          <div className="flex items-start justify-between gap-2">
            <button onClick={() => onOpen(n)} className="text-left font-bold text-white text-xs hover:underline focus:outline-none focus:ring-1 focus:ring-white/40 rounded flex items-center gap-1.5">
              <span className={`inline-block w-1.5 h-1.5 rounded-full ${SEV_DOT[n.severity] || SEV_DOT.INFO}`} aria-hidden />
              {!n.isRead && <span className="sr-only">{vi ? 'Chưa đọc: ' : 'Unread: '}</span>}
              {n.title}
            </button>
            <button onClick={() => onDelete(n)} aria-label={vi ? 'Xóa thông báo' : 'Delete notification'} className="text-nf-500 hover:text-rose-300 px-1">×</button>
          </div>
          <p className="text-[11px] text-nf-400 mt-1 leading-snug">{n.message}</p>
          <span className="text-[10px] text-nf-500 font-mono flex items-center gap-1 mt-1"><Clock className="w-2.5 h-2.5" />{n.timestamp}</span>
        </li>
      ))}
    </ul>
  );
}


// ============================================================================
// Shell Component
// ============================================================================

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { locale, setLocale, t } = useI18n();

  // Responsive & Interactive States
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [alerts, setAlerts] = useState<AlertNotification[]>([]);
  const [backendStatus, setBackendStatus] = useState<'online' | 'checking' | 'offline'>('checking');
  const [backendReason, setBackendReason] = useState<string | null>(null);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [unreadCount, setUnreadCount] = useState(0);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [currentUser, setCurrentUser] = useState<{ email: string; name: string; role: string; is_ultra_admin?: boolean } | null>(null);

  const notificationsRef = useRef<HTMLDivElement>(null);
  const mobileNotificationsRef = useRef<HTMLDivElement>(null);
  const mobilePopoverRef = useRef<HTMLDivElement>(null);

  // Session comes from the server (HttpOnly cookie). Nothing identity-related is kept in storage.
  useEffect(() => {
    let cancelled = false;
    if (pathname.startsWith('/login')) return;
    api.me()
      .then((u) => {
        if (!cancelled) setCurrentUser({ email: u.email || u.username, name: u.username, role: u.is_owner ? 'OWNER' : u.role });
      })
      .catch((err: any) => {
        if (cancelled) return;
        if (err?.kind === 'unauthenticated' || err?.kind === 'forbidden') {
          setCurrentUser(null);
          router.push('/login/');
        }
        // Gateway/API outage: keep the page, the status pill shows offline with the reason.
      });
    const onUnauth = () => router.push('/login/');
    window.addEventListener('noospire:unauthenticated', onUnauth);
    return () => {
      cancelled = true;
      window.removeEventListener('noospire:unauthenticated', onUnauth);
    };
  }, [pathname, router]);

  const handleLogout = async () => {
    try {
      await api.logout();
    } catch (_) {
      // Even if the server is unreachable, leave the console; the cookie expires server-side.
    }
    setCurrentUser(null);
    window.location.href = '/login/';
  };


  // Restore collapsed state from localStorage
  useEffect(() => {
    try {
      const savedCollapsed = localStorage.getItem('sentinel_sidebar_collapsed');
      if (savedCollapsed !== null) {
        setSidebarCollapsed(savedCollapsed === 'true');
      }
    } catch (_) {}
  }, []);

  const toggleSidebar = () => {
    const nextState = !sidebarCollapsed;
    setSidebarCollapsed(nextState);
    try {
      localStorage.setItem('sentinel_sidebar_collapsed', String(nextState));
    } catch (_) {}
  };

  const toggleLanguage = () => {
    const nextLocale: Locale = locale === 'vi' ? 'en' : 'vi';
    setLocale(nextLocale);
  };

  // API readiness via the gateway. Never reports online when the probe fails.
  useEffect(() => {
    let isMounted = true;
    const checkHealth = async () => {
      const t0 = performance.now();
      try {
        await api.ready();
        if (!isMounted) return;
        setBackendStatus('online');
        setBackendReason(null);
        setLatencyMs(Math.round(performance.now() - t0));
      } catch (err: any) {
        if (!isMounted) return;
        setBackendStatus('offline');
        setLatencyMs(null);
        const reasons: Record<string, string> = {
          network: 'gateway unreachable',
          upstream_unreachable: 'API unreachable (502)',
          upstream_timeout: 'API timeout (503)',
          misrouted: 'misrouted (HTML on API path)',
        };
        const rid = err?.requestId ? ` · ${err.requestId}` : '';
        setBackendReason((reasons[err?.kind] || err?.message || 'unknown') + rid);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Per-user notifications (server data only). Errors are shown, not replaced by samples.
  const loadNotifications = React.useCallback(() => {
    if (pathname.startsWith('/login')) return;
    api.listNotifications(20)
      .then((res) => {
        setAlertsError(null);
        setUnreadCount(res.unread);
        setAlerts(res.items.map((a) => ({
          id: a.id,
          title: a.title,
          message: a.message,
          severity: (a.severity || 'INFO').toUpperCase(),
          timestamp: new Date(a.created_at).toLocaleString('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' }) + ' ICT',
          isRead: a.read,
          link: a.link,
        })));
      })
      .catch((err: any) => {
        setAlertsError((locale === 'vi' ? 'Không tải được thông báo: ' : 'Could not load notifications: ') + (err?.message || err?.kind || 'error'));
      });
  }, [pathname, locale]);

  useEffect(() => {
    loadNotifications();
    const id = setInterval(loadNotifications, 60_000);
    return () => clearInterval(id);
  }, [loadNotifications]);

  useEffect(() => {
    if (notificationsOpen) loadNotifications();
  }, [notificationsOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  const openNotification = async (n: AlertNotification) => {
    try {
      if (!n.isRead) await api.readNotification(n.id);
    } catch (err: any) {
      setAlertsError((locale === 'vi' ? 'Máy chủ từ chối: ' : 'Server refused: ') + (err?.message || 'error'));
      loadNotifications();
      return;
    }
    setNotificationsOpen(false);
    loadNotifications();
    router.push(n.link);
  };

  const deleteNotification = async (n: AlertNotification) => {
    try {
      await api.deleteNotification(n.id);
      setAlerts((prev) => prev.filter((x) => x.id !== n.id));
      if (!n.isRead) setUnreadCount((c) => Math.max(0, c - 1));
    } catch (err: any) {
      setAlertsError((locale === 'vi' ? 'Máy chủ từ chối: ' : 'Server refused: ') + (err?.message || 'error'));
      loadNotifications();
    }
  };

  // Handle outside click for notification popover
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const t = event.target as Node;
      const inside = (notificationsRef.current && notificationsRef.current.contains(t)) ||
        (mobileNotificationsRef.current && mobileNotificationsRef.current.contains(t)) ||
        (mobilePopoverRef.current && mobilePopoverRef.current.contains(t));
      if (!inside) {
        setNotificationsOpen(false);
      }
    };
    if (notificationsOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [notificationsOpen]);

  // Handle ESC key to dismiss mobile drawer & notification popover
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMobileMenuOpen(false);
        setNotificationsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Body scroll lock on mobile drawer open
  useEffect(() => {
    if (mobileMenuOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileMenuOpen]);

  const markAllAlertsRead = async () => {
    try {
      await api.readAllNotifications();
      setAlerts((prev) => prev.map((a) => ({ ...a, isRead: true })));
      setUnreadCount(0);
    } catch (err: any) {
      setAlertsError((locale === 'vi' ? 'Máy chủ từ chối: ' : 'Server refused: ') + (err?.message || 'error'));
    }
  };

  const isLoginPage = pathname === '/login' || pathname.startsWith('/login');
  if (isLoginPage) {
    return <main className="min-h-screen bg-nf-950 text-nf-100">{children}</main>;
  }

  return (
    <div className="min-h-screen bg-nf-950 text-nf-100 flex flex-col md:flex-row font-sans selection:bg-white/20 selection:text-white">
      
      {/* =================================================================== */}
      {/* MOBILE STICKY TOP BAR (< 768px)                                      */}
      {/* =================================================================== */}
      <header className="md:hidden sticky top-0 z-40 flex items-center justify-between px-4 h-14 bg-nf-950/85 backdrop-blur-2xl border-b border-white/[0.08] shadow-sm">
        {/* Brand Mark */}
        <Link href="/dashboard" className="flex items-center gap-2.5 group/brand">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-b from-white/[0.09] via-white/[0.04] to-white/[0.01] border border-white/15 p-1 flex items-center justify-center shadow-[inset_0_1px_2px_rgba(255,255,255,0.2),0_4px_12px_rgba(0,0,0,0.5)] backdrop-blur-xl overflow-hidden transition-all duration-300 group-hover/brand:border-white/30">
            <Image
              src="/brand/logo-white-emblem.png"
              alt="NOOSFORGE Logo"
              width={26}
              height={26}
              className="w-full h-full object-contain filter drop-shadow-[0_2px_4px_rgba(255,255,255,0.15)] transition-transform duration-300 group-hover/brand:scale-105"
              priority
            />
          </div>
          <div>
            <div className="font-extrabold tracking-tight text-white text-xs leading-none">NOOSFORGE</div>
            <div className="text-[9px] font-bold text-nf-400 tracking-wider uppercase mt-0.5">SECURITY SOC</div>
          </div>
        </Link>

        {/* Mobile Action Controls */}
        <div className="flex items-center gap-2">
          {/* Target Pulse Indicator Pill */}
          <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/[0.04] border border-white/[0.08] text-[10px] text-nf-300 backdrop-blur-md">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="truncate max-w-[100px] font-mono">empire.edu.vn</span>
          </div>

          {/* Mobile Notification Bell */}
          <div className="relative" ref={mobileNotificationsRef}>
            <button
              onClick={() => setNotificationsOpen(!notificationsOpen)}
              className="p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-nf-300 hover:text-white transition-all relative cursor-pointer"
              title={t('shell.notifications', 'Security Alerts')}
              aria-label="View notifications"
              aria-expanded={notificationsOpen}
              aria-haspopup="dialog"
            >
              <Bell className="w-3.5 h-3.5" />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-rose-500 text-[9px] font-extrabold text-white flex items-center justify-center shadow-md shadow-rose-950/60 animate-pulse">
                  {unreadCount}
                </span>
              )}
            </button>
          </div>

          {/* Bilingual Language Switcher */}
          <button
            onClick={toggleLanguage}
            className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-mono font-bold transition-all cursor-pointer"
            title="Toggle Language (VI/EN)"
            aria-label="Toggle Language"
          >
            <Languages className="w-3.5 h-3.5 text-nf-400" />
            <span className={locale === 'vi' ? 'text-white font-extrabold' : 'text-nf-500'}>VI</span>
            <span className="text-nf-600 text-[10px]">/</span>
            <span className={locale === 'en' ? 'text-white font-extrabold' : 'text-nf-500'}>EN</span>
          </button>

          {/* Animated Hamburger Button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="w-9 h-9 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 flex items-center justify-center text-nf-300 hover:text-white transition-all focus:outline-none focus:ring-2 focus:ring-white/20 cursor-pointer"
            aria-label={mobileMenuOpen ? t('shell.menuClose', 'Close menu') : t('shell.menuOpen', 'Open navigation menu')}
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X className="w-5 h-5 text-white" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* Mobile Notification Center Dropdown */}
        {notificationsOpen && (
          <div ref={mobilePopoverRef} role="dialog" aria-label="Notifications" className="md:hidden absolute top-14 left-2 right-2 rounded-2xl bg-nf-900/98 backdrop-blur-3xl border border-white/15 shadow-2xl p-3.5 z-50 specular-highlight animate-fadeIn">
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/10">
              <div className="flex items-center gap-2">
                <Bell className="w-4 h-4 text-white" />
                <span className="font-bold text-xs text-white">
                  {t('shell.notifications', 'Security Alerts')}
                </span>
                {unreadCount > 0 && (
                  <span className="px-1.5 py-0.2 rounded-full bg-rose-950 text-rose-400 border border-rose-800 text-[10px] font-bold">
                    {unreadCount}
                  </span>
                )}
              </div>
              {unreadCount > 0 && (
                <button
                  onClick={markAllAlertsRead}
                  className="text-[10px] text-nf-300 hover:text-white flex items-center gap-1 font-semibold cursor-pointer"
                >
                  <CheckCheck className="w-3 h-3" />
                  {t('shell.markAllRead', 'Mark all read')}
                </button>
              )}
            </div>

            <NotificationList items={alerts} error={alertsError} vi={locale === 'vi'} onOpen={openNotification} onDelete={deleteNotification} />
          </div>
        )}
      </header>


      {/* =================================================================== */}
      {/* MOBILE SLIDE-OVER DRAWER MODAL OVERLAY (< 768px)                    */}
      {/* =================================================================== */}
      <div
        className={`md:hidden fixed inset-0 z-50 transition-opacity duration-300 ${
          mobileMenuOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        role="dialog"
        aria-modal="true"
      >
        {/* Backdrop Blur Overlay */}
        <div
          className="absolute inset-0 bg-nf-950/80 backdrop-blur-xl"
          onClick={() => setMobileMenuOpen(false)}
        />

        {/* Slide-Over Drawer Container */}
        <aside
          className={`relative w-80 max-w-[85vw] h-full bg-nf-950/98 backdrop-blur-3xl border-r border-white/10 shadow-2xl flex flex-col justify-between transform transition-transform duration-300 ease-out ${
            mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          {/* Drawer Header */}
          <div className="p-4 border-b border-white/[0.08] flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-b from-white/[0.09] via-white/[0.04] to-white/[0.01] border border-white/15 p-1.5 flex items-center justify-center shadow-[inset_0_1px_2px_rgba(255,255,255,0.2),0_4px_12px_rgba(0,0,0,0.5)] backdrop-blur-xl overflow-hidden">
                <Image
                  src="/brand/logo-white-emblem.png"
                  alt="NOOSFORGE Logo"
                  width={30}
                  height={30}
                  className="w-full h-full object-contain filter drop-shadow-[0_2px_4px_rgba(255,255,255,0.15)]"
                />
              </div>
              <div>
                <div className="font-black text-sm tracking-wider text-white">NOOSFORGE</div>
                <div className="text-[10px] font-bold text-nf-400 tracking-widest uppercase">
                  {t('brand.soc', 'Empire Security SOC')}
                </div>
              </div>
            </div>
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="p-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-nf-400 hover:text-white transition-all cursor-pointer"
              aria-label="Close Drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Target Environment Context Card */}
          <div className="px-4 py-3 bg-white/[0.02] border-b border-white/[0.05] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400/50" />
              <div>
                <div className="text-[11px] font-bold text-white">Empire Education Platform</div>
                <div className="text-[9px] text-nf-400 font-mono">empire.edu.vn • SAME-ORIGIN</div>
              </div>
            </div>
          </div>

          {/* Grouped Navigation Links (Touch Friendly: Min 44px Height) */}
          <nav className="p-3 space-y-4 flex-1 overflow-y-auto">
            {NAVIGATION_GROUPS.map((group) => (
              <div key={group.groupKey} className="space-y-1">
                <div className="px-3 pt-1 pb-1 text-[10px] font-bold uppercase tracking-wider text-nf-500">
                  {t(group.groupKey, group.defaultTitle)}
                </div>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href));
                  const translatedName = t(item.i18nKey, item.name);

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setMobileMenuOpen(false)}
                      className={`flex items-center justify-between px-3.5 min-h-[44px] rounded-xl text-xs font-semibold transition-all ${
                        isActive
                          ? 'bg-white text-nf-950 font-bold shadow-md shadow-white/10'
                          : 'text-nf-300 hover:text-white hover:bg-white/[0.05] border border-transparent hover:border-white/[0.06]'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <Icon className={`w-4 h-4 ${isActive ? 'text-nf-950' : 'text-nf-400'}`} />
                        <span className="truncate">{translatedName}</span>
                      </div>
                      {item.badge && (
                        <span
                          className={`text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded ${
                            isActive
                              ? 'bg-nf-950 text-white shadow-sm'
                              : 'bg-white/[0.06] text-nf-300 border border-white/10'
                          }`}
                        >
                          {item.badge}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            ))}
          </nav>

          {/* Drawer Footer Status */}
          <div className="p-4 border-t border-white/[0.08] text-xs text-nf-400 flex items-center justify-between bg-white/[0.01]">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400/50" />
              <span className="text-[11px] text-nf-300">
                {t('brand.continuousAudit', 'Continuous Audit Active')}
              </span>
            </div>
            <span className="text-[10px] text-nf-500 font-mono">v2.0.0</span>
          </div>
        </aside>
      </div>

      {/* =================================================================== */}
      {/* TABLET & DESKTOP STICKY VERTICAL SIDEBAR (>= 768px)                  */}
      {/* =================================================================== */}
      <aside
        className={`hidden md:flex flex-col justify-between sticky top-0 h-screen bg-nf-950/80 backdrop-blur-2xl border-r border-white/[0.07] flex-shrink-0 z-30 transition-all duration-300 ease-in-out specular-highlight ${
          sidebarCollapsed ? 'w-20' : 'w-64'
        }`}
      >
        <div className="flex flex-col h-full overflow-hidden">
          {/* Brand Banner & Collapse Toggle Header */}
          <div className="p-4 border-b border-white/[0.08] flex items-center justify-between">
            {!sidebarCollapsed ? (
              <div className="flex items-center gap-3 group/brand">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-b from-white/[0.09] via-white/[0.04] to-white/[0.01] border border-white/15 p-1.5 flex items-center justify-center shadow-[inset_0_1px_2px_rgba(255,255,255,0.2),0_4px_14px_rgba(0,0,0,0.6)] backdrop-blur-xl overflow-hidden transition-all duration-300 group-hover/brand:border-white/30 group-hover/brand:shadow-[inset_0_1px_2px_rgba(255,255,255,0.3),0_6px_20px_rgba(0,0,0,0.7)]">
                  <Image
                    src="/brand/logo-white-emblem.png"
                    alt="NOOSFORGE Logo"
                    width={32}
                    height={32}
                    className="w-full h-full object-contain filter drop-shadow-[0_2px_4px_rgba(255,255,255,0.18)] transition-transform duration-300 group-hover/brand:scale-105"
                    priority
                  />
                </div>
                <div>
                  <div className="font-black text-sm tracking-wider text-white">NOOSFORGE</div>
                  <div className="text-[10px] font-bold text-nf-400 tracking-widest uppercase">
                    {t('brand.soc', 'Empire Security SOC')}
                  </div>
                </div>
              </div>
            ) : (
              <div className="w-full flex justify-center">
                <div className="w-10 h-10 rounded-xl bg-gradient-to-b from-white/[0.09] via-white/[0.04] to-white/[0.01] border border-white/15 p-1.5 flex items-center justify-center shadow-[inset_0_1px_2px_rgba(255,255,255,0.2),0_4px_14px_rgba(0,0,0,0.6)] backdrop-blur-xl overflow-hidden transition-all hover:border-white/30" title="NOOSFORGE Security">
                  <Image
                    src="/brand/logo-white-emblem.png"
                    alt="NOOSFORGE Logo"
                    width={32}
                    height={32}
                    className="w-full h-full object-contain filter drop-shadow-[0_2px_4px_rgba(255,255,255,0.18)]"
                  />
                </div>
              </div>
            )}

            {/* Sidebar Collapse/Expand Toggle Button */}
            {!sidebarCollapsed && (
              <button
                onClick={toggleSidebar}
                className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-nf-400 hover:text-white border border-white/[0.08] transition-all cursor-pointer"
                title={t('shell.collapseSidebar', 'Collapse Sidebar')}
                aria-label="Collapse Sidebar"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Collapsed Mode Expand Button */}
          {sidebarCollapsed && (
            <div className="p-2 border-b border-white/[0.08] flex justify-center">
              <button
                onClick={toggleSidebar}
                className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-nf-400 hover:text-white border border-white/[0.08] transition-all cursor-pointer"
                title={t('shell.expandSidebar', 'Expand Sidebar')}
                aria-label="Expand Sidebar"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Target Environment Badge (Expanded Only) */}
          {!sidebarCollapsed && (
            <div className="px-3.5 py-2.5 bg-white/[0.02] border-b border-white/[0.05] flex items-center justify-between text-xs">
              <span className="text-nf-400 font-medium text-[11px]">{t('brand.targetContext', 'Target Context:')}</span>
              <span className="px-2 py-0.5 rounded-md bg-white/[0.06] text-white border border-white/10 text-[10px] font-bold shadow-sm backdrop-blur-md">
                Empire Education
              </span>
            </div>
          )}

          {/* Grouped Navigation Links */}
          <nav className="p-2 space-y-3 flex-1 overflow-y-auto">
            {NAVIGATION_GROUPS.map((group) => (
              <div key={group.groupKey} className="space-y-0.5">
                {!sidebarCollapsed && (
                  <div className="px-2.5 pt-2 pb-1 text-[9px] font-bold uppercase tracking-wider text-nf-500">
                    {t(group.groupKey, group.defaultTitle)}
                  </div>
                )}
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const isActive = pathname === item.href || (item.href !== '/dashboard' && pathname.startsWith(item.href));
                  const translatedName = t(item.i18nKey, item.name);

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={sidebarCollapsed ? translatedName : undefined}
                      className={`flex items-center ${
                        sidebarCollapsed ? 'justify-center px-0 py-2.5' : 'justify-between px-3 py-2'
                      } rounded-xl text-xs font-medium transition-all ${
                        isActive
                          ? 'bg-white text-nf-950 font-bold shadow-md shadow-white/10'
                          : 'text-nf-400 hover:text-white hover:bg-white/[0.04] border border-transparent hover:border-white/[0.06]'
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-nf-950' : 'text-nf-400'}`} />
                        {!sidebarCollapsed && <span className="truncate">{translatedName}</span>}
                      </div>
                      {!sidebarCollapsed && item.badge && (
                        <span
                          className={`text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded ${
                            isActive
                              ? 'bg-nf-950 text-white shadow-sm'
                              : 'bg-white/[0.06] text-nf-300 border border-white/10'
                          }`}
                        >
                          {item.badge}
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            ))}
          </nav>

          {/* Sidebar Footer Status */}
          <div className="p-3 border-t border-white/[0.08] text-xs text-nf-400 flex items-center justify-between bg-white/[0.01]">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400/50" />
              {!sidebarCollapsed && (
                <span className="text-[11px] text-nf-300">
                  {t('brand.continuousAudit', 'Continuous Audit Active')}
                </span>
              )}
            </div>
            {!sidebarCollapsed && <span className="text-[10px] text-nf-500 font-mono">v2.0.0</span>}
          </div>
        </div>
      </aside>

      {/* =================================================================== */}
      {/* MAIN CONTENT VIEWPORT CONTAINER                                     */}
      {/* =================================================================== */}
      <div className="min-w-0 flex-1 flex flex-col min-h-screen overflow-x-hidden relative">
        
        {/* Subtle Ambient Watermark (Chìm, ấn tượng, sâu lắng) */}
        <div
          aria-hidden="true"
          className="fixed pointer-events-none select-none right-0 bottom-0 md:right-12 md:bottom-8 w-[380px] h-[320px] md:w-[640px] md:h-[540px] z-0 overflow-hidden"
        >
          <div
            className="w-full h-full opacity-[0.035] contrast-125 filter blur-[0.2px]"
            style={{
              backgroundImage: 'url(/brand/logo-white.png)',
              backgroundPosition: 'center bottom',
              backgroundRepeat: 'no-repeat',
              backgroundSize: 'contain',
              maskImage: 'radial-gradient(ellipse at center, rgba(0,0,0,1) 30%, rgba(0,0,0,0) 75%)',
              WebkitMaskImage: 'radial-gradient(ellipse at center, rgba(0,0,0,1) 30%, rgba(0,0,0,0) 75%)',
            }}
          />
        </div>
        
        {/* ================================================================= */}
        {/* TOP STATUS UTILITY BAR (Tablet & Desktop >= 768px)                */}
        {/* ================================================================= */}
        <header className="hidden md:flex sticky top-0 z-30 items-center justify-between px-6 lg:px-8 h-14 bg-nf-950/80 backdrop-blur-2xl border-b border-white/[0.07] shadow-sm">
          {/* Target Environment Badge & Scope */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.08] text-xs shadow-sm backdrop-blur-md">
              <div className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </div>
              <span className="font-bold text-white text-xs">Empire Education Platform</span>
              <span className="text-nf-600">|</span>
              <span className="text-[10px] font-mono font-semibold text-nf-300">empire.edu.vn</span>
              <span className="px-1.5 py-0.5 rounded-md bg-white/[0.06] text-white border border-white/10 text-[9px] font-extrabold uppercase tracking-wide">
                SAME-ORIGIN
              </span>
            </div>

            {/* Backend Connectivity Status Pill */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border shadow-sm backdrop-blur-md ${
                backendStatus === 'online'
                  ? 'bg-emerald-950/20 text-emerald-400 border-emerald-500/20'
                  : backendStatus === 'checking'
                  ? 'bg-amber-950/20 text-amber-400 border-amber-500/20'
                  : 'bg-rose-950/20 text-rose-400 border-rose-500/20'
              }`}
              title="Backend API Connection Health"
            >
              {backendStatus === 'online' ? (
                <>
                  <Wifi className="w-3.5 h-3.5" />
                  <span>{t('shell.backendOnline', 'API: Online')}</span>
                  {latencyMs !== null && <span className="font-mono text-[10px] text-emerald-400/80">({latencyMs}ms)</span>}
                </>
              ) : backendStatus === 'checking' ? (
                <>
                  <Activity className="w-3.5 h-3.5 animate-spin" />
                  <span>{t('shell.backendChecking', 'Checking...')}</span>
                </>
              ) : (
                <>
                  <WifiOff className="w-3.5 h-3.5" />
                  <span>{t('shell.backendOffline', 'API: Offline')}</span>
                  {backendReason && <span className="font-mono text-[10px] text-rose-300/80" title={backendReason}>({backendReason})</span>}
                </>
              )}
            </div>
          </div>

          {/* Right Utility Controls: Notifications & Bilingual Switch */}
          <div className="flex items-center gap-3">
            {/* Interactive Notification Indicator Bell */}
            <div className="relative" ref={notificationsRef}>
              <button
                onClick={() => setNotificationsOpen(!notificationsOpen)}
                className="p-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-nf-300 hover:text-white transition-all relative cursor-pointer"
                title={t('shell.notifications', 'Security Alerts')}
                aria-label="View security notifications"
                aria-expanded={notificationsOpen}
                aria-haspopup="dialog"
              >
                <Bell className="w-4 h-4" />
                {unreadCount > 0 && (
                  <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-rose-500 text-[10px] font-extrabold text-white flex items-center justify-center shadow-md shadow-rose-950/60 animate-pulse">
                    {unreadCount}
                  </span>
                )}
              </button>

              {/* Notification Center Popover */}
              {notificationsOpen && (
                <div role="dialog" aria-label="Notifications" className="absolute right-0 top-11 w-80 sm:w-96 rounded-2xl bg-nf-900/98 backdrop-blur-3xl border border-white/15 shadow-2xl p-3.5 z-50 specular-highlight">
                  <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/10">
                    <div className="flex items-center gap-2">
                      <Bell className="w-4 h-4 text-white" />
                      <span className="font-bold text-xs text-white">
                        {t('shell.notifications', 'Security Alerts')}
                      </span>
                      {unreadCount > 0 && (
                        <span className="px-1.5 py-0.2 rounded-full bg-rose-950 text-rose-400 border border-rose-800 text-[10px] font-bold">
                          {unreadCount}
                        </span>
                      )}
                    </div>
                    {unreadCount > 0 && (
                      <button
                        onClick={markAllAlertsRead}
                        className="text-[10px] text-nf-300 hover:text-white flex items-center gap-1 font-semibold cursor-pointer"
                      >
                        <CheckCheck className="w-3 h-3" />
                        {t('shell.markAllRead', 'Mark all read')}
                      </button>
                    )}
                  </div>

                  <NotificationList items={alerts} error={alertsError} vi={locale === 'vi'} onOpen={openNotification} onDelete={deleteNotification} />
                </div>
              )}
            </div>

            {/* Bilingual Segmented Locale Toggle Button */}
            <div className="flex items-center p-0.5 rounded-xl bg-nf-900/90 border border-white/10 shadow-inner text-xs font-mono backdrop-blur-md">
              <button
                onClick={() => setLocale('vi')}
                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  locale === 'vi'
                    ? 'bg-white text-nf-950 font-black shadow-sm'
                    : 'text-nf-400 hover:text-white'
                }`}
              >
                VI
              </button>
              <button
                onClick={() => setLocale('en')}
                className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                  locale === 'en'
                    ? 'bg-white text-nf-950 font-black shadow-sm'
                    : 'text-nf-400 hover:text-white'
                }`}
              >
                EN
              </button>
            </div>

            {/* User Session / Ultra Admin Indicator */}
            {currentUser ? (
              <div className="flex items-center gap-2 pl-2 border-l border-white/10">
                <Link
                  href="/settings"
                  className="flex items-center gap-2 px-2.5 py-1 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs text-slate-300 hover:text-white transition"
                  title={currentUser.email}
                >
                  <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]" />
                  <span className="font-bold truncate max-w-[120px]">{currentUser.name || 'Ultra Admin'}</span>
                  <span className="px-1.5 py-0.2 rounded bg-white/10 text-[9px] font-mono font-bold text-cyan-300 uppercase">
                    {currentUser.role === 'SUPER_ADMIN' ? 'ULTRA' : currentUser.role}
                  </span>
                </Link>
                <button
                  onClick={handleLogout}
                  className="text-[10px] text-slate-400 hover:text-rose-400 px-1.5 py-1 transition cursor-pointer font-medium"
                  title="Logout / Đăng xuất"
                >
                  {locale === 'vi' ? 'Thoát' : 'Exit'}
                </button>
              </div>
            ) : (
              <Link
                href="/login"
                className="px-2.5 py-1 rounded-xl bg-white text-black font-bold text-xs hover:bg-slate-200 transition"
              >
                {locale === 'vi' ? 'Đăng Nhập' : 'Login'}
              </Link>
            )}
          </div>
        </header>

        {/* Main Workspace Page Viewport */}
        <main className="relative z-10 flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
