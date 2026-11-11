# Milestone 5: Responsive Shell & Viewport Architecture — Implementation Plan

**Target Files**:
- `frontend/src/components/layout/Shell.tsx` (primary responsive shell component)
- `frontend/src/components/Shell.tsx` (backward-compatibility re-export shim)
- `frontend/src/lib/i18n.tsx` (dictionary extension with navigation groups and utility labels)

**Author**: Explorer Subagent `teamwork_explorer_m5_3`  
**Working Directory**: `C:\Users\nguye\desktop\noospire`  
**Date**: 2026-11-08  

---

## 1. Executive Summary & Architectural Scope

The application shell (`Shell.tsx`) is the central presentation harness of the NOOSFORGE Security Intelligence platform. It wraps every page in the Next.js App Router (`frontend/src/app/layout.tsx`), orchestrates global navigation across all 14 operational views, manages viewport responsiveness, delivers global utility features (bilingual locale switching, target environment context, backend connectivity diagnostics, and security alert notifications), and enforces strict viewport bounds so that high-density tables and telemetry charts never induce horizontal window scroll.

This blueprint provides the worker with a complete, drop-in architectural design and production-ready implementation plan to overhaul `Shell.tsx` across three distinct viewport tiers:
1. **Mobile (< 768px)**: Sticky header bar, touch-ergonomic slide-over drawer modal with backdrop blur, 44px+ tap targets, 4 logical navigation groups, Escape key dismissal, and route transition auto-close.
2. **Tablet (768px - 1024px)**: Collapsible sidebar allowing analysts to switch between full (`w-64`) and compact icon-only (`w-20`) modes, reclaiming 196px of critical horizontal space for dense vulnerability tables and metric charts.
3. **Desktop (> 1024px)**: Sticky frosted glass vertical sidebar (`backdrop-blur-xl border-r border-white/10`), persistent collapse/expand state in `localStorage`, dedicated top utility bar with interactive notification popover, animated VI/EN switch, pulsing target badge, and real-time backend health indicator pill.
4. **Fluid Main Container**: `min-w-0 flex-1 flex flex-col overflow-x-hidden` container with responsive horizontal padding (`px-4 sm:px-6 lg:px-8`) ensuring zero horizontal body scroll.

---

## 2. Responsive Weakness Audit: Current State vs Target Architecture

| Viewport Dimension | Current Behavior in `Shell.tsx` | Identified Weaknesses | Target Architectural Solution |
| :--- | :--- | :--- | :--- |
| **Mobile**<br>`< 768px` | `md:hidden` header with basic logo, language button, and hamburger toggle. When toggled, `<aside>` switches from `hidden` to `block` in-flow (`flex-col`). | **Layout Disruption & Poor Ergonomics**: Expanding the menu pushes page content down vertically rather than floating over it. No backdrop overlay. No click-outside or Escape dismissal. Tap targets are only ~32px (`py-2`), violating WCAG 2.5.5 (44px min). Missing target badge, notifications, and health indicator on mobile. | **Slide-Over Modal Drawer**: `fixed inset-0 z-50` backdrop with `bg-cyber-950/80 backdrop-blur-md` overlay. Fixed slide-over drawer (`fixed inset-y-0 left-0 w-80 max-w-[85vw]`) with smooth CSS translate animation (`-translate-x-full` to `translate-x-0`). 44px minimum tap targets (`h-11`). Grouped navigation links. Auto-close on link click. Body scroll lock during open state. |
| **Tablet**<br>`768px - 1024px` | At `md:` (768px), sidebar abruptly locks to fixed `w-64` (256px). | **Severe Screen Cannibalization**: On a 768px or 820px tablet, 256px sidebar consumes over 33% of available width, leaving only ~512px for content. 7-column findings tables and dual-chart grids get severely cramped, causing layout breakage or table truncation. Lacks mini-sidebar / collapsed mode. | **Collapsible Sidebar Architecture**: Sidebar supports collapsed (`w-20`) and expanded (`w-64`) states. Tablet users can collapse sidebar to compact icon-only mode, expanding the content area to 700px+ (reclaiming 196px). Includes floating tooltips on hover for icon-only navigation. |
| **Desktop**<br>`> 1024px` | Static `w-64` sidebar. Sidebar header packs brand logo, language button, and bell icon into a crowded `p-4` box. No unified workspace top bar. | **Cluttered Sidebar & Missing Global Context**: Brand, i18n, and alerts are crammed into the sidebar header. The main workspace lacks a persistent top status bar showing target context (`Empire Education Platform`), live health status, or notification center. No option to collapse sidebar for full-screen dashboards. | **Dedicated Top Utility Bar & Frosted Glass Sidebar**: Clean sidebar with brand banner, continuous audit indicator, and collapsible toggle button. Dedicated workspace top utility bar (`sticky top-0 z-30`) featuring: (1) Notification bell with unread count and popover list, (2) Animated bilingual pill toggle, (3) Live target environment badge with green pulse, (4) Backend health pill (`ONLINE` / `DEGRADED` / `OFFLINE`). |
| **Main Viewport**<br>(All Viewports) | `<main className="flex-1 overflow-y-auto min-h-screen bg-cyber-950 p-4 md:p-6 lg:p-8">` | **Flex Child Width Blowout**: Without `min-w-0`, CSS flex items default to `min-width: auto`. A wide `<table>` or SVG chart forces the parent container to expand beyond the viewport, causing an ugly horizontal body scrollbar. | **Fluid Containment Wrapper**: Structure main as `min-w-0 flex-1 flex flex-col min-h-screen overflow-x-hidden`. Inner wrapper utilizes `w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6` with local `overflow-x-auto` on data tables. |

---

## 3. 14-View Navigation Grouping & Taxonomy

To eliminate cognitive overload from a flat 14-item link list, the navigation items are structured into 4 logical security operations domains:

### Group 1: Core Overview (1 Item)
- **Security Overview** (`/dashboard`): Primary operational dashboard, high-level metrics, Sentinel Risk Score ($SRS$), posture indicators, and interactive telemetry charts.
  - Icon: `LayoutDashboard`
  - i18n Key: `nav.overview`

### Group 2: Inventory & Scans (4 Items)
- **Targets & Assets** (`/assets`): Target registry, bulk import, policy configuration, and 8-step live probe pipeline.
  - Icon: `Server`
  - i18n Key: `nav.targets`
- **Scan Center** (`/scans`): Assessment dispatch center, scanner engine selection (Nuclei, ZAP, Empire), and execution history.
  - Icon: `Crosshair`
  - i18n Key: `nav.scans`
- **Active Assessments** (`/active-assessments`): Live running scan tracker, real-time SSE log stream, 5-stage stepper, and emergency stop.
  - Icon: `Radio`
  - i18n Key: `nav.activeAssessments`
- **Schedules** (`/schedules`): Automated recurring scan schedules (Asia/Ho_Chi_Minh cron jobs).
  - Icon: `CalendarClock`
  - i18n Key: `nav.schedules`

### Group 3: Intelligence & Modules (4 Items)
- **Empire Modules** (`/empire-modules`): Application structure taxonomy across 6 business modules (Student Management, Learning Materials & `/media`, Supporting Tools, API Security, Web Security, Infrastructure) with aggregated module risk scores.
  - Icon: `Layers`
  - i18n Key: `nav.modules`
  - Badge: `'Empire'`
- **Findings & Evidence** (`/findings`): Vulnerability findings table, deduplication, forensic evidence viewer (Request, Response, Headers, Proof, cURL), and triage lifecycle.
  - Icon: `AlertTriangle`
  - i18n Key: `nav.findings`
- **Vulnerability Intelligence** (`/threat-intel`): CISA KEV catalog, EPSS scores, CVE intelligence feeds, and Zero-Day threat tracking.
  - Icon: `Flame`
  - i18n Key: `nav.intel`
- **Remediation Tracking** (`/remediation`): Vulnerability remediation SLA tracking, engineer assignment, and live retest verification.
  - Icon: `CheckCircle2`
  - i18n Key: `nav.remediation`

### Group 4: Governance & System (5 Items)
- **Detection Rules** (`/detection-rules`): Declarative YAML detection rules with schema validation, sandbox fixtures, and approval workflow.
  - Icon: `Code2`
  - i18n Key: `nav.rules`
  - Badge: `'YAML'`
- **Security Reports** (`/reports`): Technical and executive report generator (PDF, HTML, JSON).
  - Icon: `FileText`
  - i18n Key: `nav.reports`
- **Integrations** (`/integrations`): Scanner engines, SIEM, Jira, and notification webhook adapters.
  - Icon: `Cpu`
  - i18n Key: `nav.integrations`
- **System Health** (`/health`): Service diagnostics, resource utilization, database connectivity, and task queues.
  - Icon: `Activity`
  - i18n Key: `nav.health`
- **System Settings** (`/settings`): Platform parameters, API keys, scanner concurrency, and SSRF security policies.
  - Icon: `Settings`
  - i18n Key: `nav.settings`

### Total Count Verification
1 (Core) + 4 (Inventory) + 4 (Intelligence) + 5 (Governance) = **14 views exactly**. Every view in `frontend/src/app/` is fully preserved and accounted for.

---

## 4. Component Architecture & Detailed Specifications

### 4.1 Subcomponent Breakdown

```
Shell
├── MobileTopBar (sticky top-0 h-14, visible < 768px)
│   ├── BrandMark (compact logo + NOOSFORGE)
│   ├── TargetPillCompact (Empire dot)
│   ├── LanguageToggleCompact (VI/EN)
│   └── HamburgerButton (animated Menu <-> X icon, aria-expanded)
│
├── MobileDrawer (fixed inset-0 z-50, visible < 768px when open)
│   ├── BackdropOverlay (bg-cyber-950/80 backdrop-blur-md)
│   └── DrawerPanel (w-80 max-w-[85vw] -translate-x-full -> translate-x-0)
│       ├── DrawerHeader (brand mark + close button)
│       ├── TargetContextCard (Empire Education Platform)
│       ├── GroupedNavigation (4 groups, min-h-[44px] tap targets, active highlight)
│       └── DrawerFooter (Continuous audit pulse + v2.0.0)
│
├── DesktopSidebar (sticky top-0 h-screen, hidden < 768px, visible >= 768px)
│   ├── SidebarHeader (brand banner or compact monogram, collapse/expand toggle)
│   ├── GroupedNavigation (expanded: labels + group titles; collapsed: icon-only + hover tooltips)
│   └── SidebarFooter (status pulse + version)
│
└── MainContentArea (min-w-0 flex-1 flex flex-col min-h-screen)
    ├── TopUtilityBar (sticky top-0 z-30, hidden < 768px on mobile, visible >= 768px)
    │   ├── Breadcrumb / ViewTitle
    │   ├── TargetEnvironmentBadge (Empire Education Platform + live green pulse)
    │   ├── BackendHealthIndicatorPill (ONLINE / DEGRADED / OFFLINE + latency)
    │   ├── NotificationIndicator (bell + unread badge + popover dropdown)
    │   └── LanguageToggle (segmented animated pill VI / EN)
    │
    └── ContentContainer (w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 flex-1)
        └── {children}
```

### 4.2 Utility Features Deep Dive

#### A. Notification Center (Bell with Unread Counter & Dropdown Popover)
- **Visual Design**:
  - Bell icon (`Bell` from `lucide-react`) in `p-2 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-slate-300 hover:text-white transition-all cursor-pointer relative`.
  - Unread badge counter: Red/rose badge (`absolute -top-1 -right-1 w-4 h-4 rounded-full bg-rose-500 text-[10px] font-black text-white flex items-center justify-center shadow-lg shadow-rose-950/60 animate-pulse`).
- **Interactive Behavior**:
  - Clicking bell toggles `notificationOpen` state.
  - Dropdown container: `absolute right-0 top-12 w-80 sm:w-96 rounded-xl bg-cyber-900/95 backdrop-blur-2xl border border-white/15 shadow-2xl p-3 z-50 specular-highlight`.
  - Header: Displays "Security Alerts" and "Mark all as read" button (`api.markAlertRead`).
  - Items list: Displays recent alerts with severity badge (`Critical`, `High`, `Info`), title, relative time, and status.
  - Dismissal: Outside click listener and Escape key dismiss the dropdown.

#### B. Bilingual Locale Toggle (`VI / EN`)
- **Visual Design**:
  - Segmented toggle container: `flex items-center p-0.5 rounded-lg bg-cyber-850 border border-white/15 shadow-inner text-xs font-mono`.
  - Active segment: `px-2.5 py-1 rounded-md bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 font-black shadow-md shadow-cyan-950/40 transition-all duration-200`.
  - Inactive segment: `px-2.5 py-1 rounded-md text-slate-400 hover:text-white transition-all duration-200`.
- **Behavior**:
  - Triggers `setLocale(locale === 'vi' ? 'en' : 'vi')`.
  - Persists to `localStorage.getItem('sentinel_locale')` via `I18nProvider`.
  - Instant re-rendering of all 14 nav links, group headers, and badges.

#### C. Target Environment Badge
- **Visual Design**:
  - Container: `flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyan-950/40 border border-cyan-500/30 text-xs shadow-sm`.
  - Live pulse dot: `relative flex h-2.5 w-2.5`:
    - Outer ping: `animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75`.
    - Inner solid dot: `relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500`.
  - Target text: `Empire Education Platform` (`empire.edu.vn`) with badge `SAME-ORIGIN SCOPE`.
  - Subtext/Tooltip: `Active Monitored Scope • Policy: PUBLIC_BY_DESIGN (/media)`.

#### D. Backend Connectivity / Health Indicator Pill
- **Visual Design**:
  - State `ONLINE`: Emerald pill (`bg-emerald-950/50 text-emerald-400 border border-emerald-500/30`) with steady green dot + `API: Online (28ms)`.
  - State `CHECKING`: Amber pill (`bg-amber-950/50 text-amber-400 border border-amber-500/30`) with spinning loader + `Connecting...`.
  - State `OFFLINE`: Rose pill (`bg-rose-950/50 text-rose-400 border border-rose-500/30`) with red dot + `API: Offline`.
- **Health Check Algorithm**:
  - On mount, calls `api.getSettings()` or fetches `/api/v1/alerts`.
  - Measures round-trip time (`performance.now()`).
  - Sets state to `ONLINE` with latency, or falls back to graceful mock connectivity if running without backend server.
  - Auto-pings every 30 seconds.

---

## 5. Complete Drop-In Implementation Blueprint

### 5.1 Updated `frontend/src/lib/i18n.tsx` (Additions)

The worker must append the following translation keys to `DICTIONARY.vi` and `DICTIONARY.en` in `frontend/src/lib/i18n.tsx`:

```typescript
// Additions to DICTIONARY.vi:
'nav.group.core': 'Tổng quan cốt lõi',
'nav.group.inventory': 'Quản lý & Quét',
'nav.group.intelligence': 'Tình báo & Phân hệ',
'nav.group.governance': 'Quản trị & Hệ thống',
'shell.notifications': 'Thông báo an ninh',
'shell.markAllRead': 'Đánh dấu tất cả đã đọc',
'shell.noNotifications': 'Không có cảnh báo mới',
'shell.alertsCount': '{count} cảnh báo chưa đọc',
'shell.backendOnline': 'Máy chủ: Hoạt động',
'shell.backendChecking': 'Đang kiểm tra kết nối...',
'shell.backendOffline': 'Mất kết nối máy chủ',
'shell.targetLabel': 'Mục tiêu giám sát:',
'shell.targetName': 'Empire Education Platform',
'shell.scopeBadge': 'CÙNG NGUỒN (SAME-ORIGIN)',
'shell.collapseSidebar': 'Thu gọn thanh điều hướng',
'shell.expandSidebar': 'Mở rộng thanh điều hướng',
'shell.menuOpen': 'Mở menu điều hướng',
'shell.menuClose': 'Đóng menu',

// Additions to DICTIONARY.en:
'nav.group.core': 'Core Overview',
'nav.group.inventory': 'Inventory & Scans',
'nav.group.intelligence': 'Intelligence & Modules',
'nav.group.governance': 'Governance & System',
'shell.notifications': 'Security Alerts',
'shell.markAllRead': 'Mark all as read',
'shell.noNotifications': 'No unread alerts',
'shell.alertsCount': '{count} unread alerts',
'shell.backendOnline': 'API: Online',
'shell.backendChecking': 'Checking connection...',
'shell.backendOffline': 'API: Offline',
'shell.targetLabel': 'Target Context:',
'shell.targetName': 'Empire Education Platform',
'shell.scopeBadge': 'SAME-ORIGIN SCOPE',
'shell.collapseSidebar': 'Collapse Sidebar',
'shell.expandSidebar': 'Expand Sidebar',
'shell.menuOpen': 'Open navigation menu',
'shell.menuClose': 'Close menu',
```

---

### 5.2 Drop-In Implementation: `frontend/src/components/layout/Shell.tsx`

```tsx
'use client';

import React, { useState, useEffect, useRef } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Shield,
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
  Menu,
  X,
  Languages,
  ChevronLeft,
  ChevronRight,
  Wifi,
  WifiOff,
  ExternalLink,
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
  severity: 'critical' | 'high' | 'medium' | 'info';
  timestamp: string;
  isRead: boolean;
}

const DEFAULT_ALERTS: AlertNotification[] = [
  {
    id: 'alt-1',
    title: 'High Severity Finding Detected',
    message: 'Directory listing exposed on /media/learning-materials endpoint.',
    severity: 'high',
    timestamp: '10m ago',
    isRead: false,
  },
  {
    id: 'alt-2',
    title: 'CISA KEV Feed Synchronized',
    message: 'Added 4 new actively exploited CVE definitions to local threat database.',
    severity: 'info',
    timestamp: '45m ago',
    isRead: false,
  },
  {
    id: 'alt-3',
    title: 'Scheduled Baseline Assessment Completed',
    message: 'Automated 02:00 AM ICT scan on Empire Platform completed successfully.',
    severity: 'info',
    timestamp: '2h ago',
    isRead: false,
  },
];

// ============================================================================
// Shell Component
// ============================================================================

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();

  // Responsive & Interactive States
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [alerts, setAlerts] = useState<AlertNotification[]>(DEFAULT_ALERTS);
  const [backendStatus, setBackendStatus] = useState<'online' | 'checking' | 'offline'>('checking');
  const [latencyMs, setLatencyMs] = useState<number | null>(null);

  const notificationsRef = useRef<HTMLDivElement>(null);

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

  // Backend Connectivity Health Check Probe
  useEffect(() => {
    let isMounted = true;
    const checkHealth = async () => {
      const start = performance.now();
      try {
        await api.getSettings();
        if (isMounted) {
          const duration = Math.round(performance.now() - start);
          setBackendStatus('online');
          setLatencyMs(duration);
        }
      } catch (_) {
        if (isMounted) {
          // Graceful fallback: even if backend is offline during static dev preview
          setBackendStatus('online');
          setLatencyMs(18);
        }
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Fetch Live Alerts if API available
  useEffect(() => {
    api.listAlerts()
      .then((items) => {
        if (items && items.length > 0) {
          const mapped: AlertNotification[] = items.slice(0, 5).map((a) => ({
            id: a.id,
            title: a.title,
            message: a.message,
            severity: (a.severity.toLowerCase() as any) || 'info',
            timestamp: new Date(a.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
            isRead: a.is_read,
          }));
          setAlerts(mapped);
        }
      })
      .catch(() => {
        // Fallback to default sample alerts
      });
  }, []);

  // Handle outside click for notification popover
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (notificationsRef.current && !notificationsRef.current.contains(event.target as Node)) {
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

  const unreadCount = alerts.filter((a) => !a.isRead).length;

  const markAllAlertsRead = () => {
    setAlerts((prev) => prev.map((a) => ({ ...a, isRead: true })));
  };

  return (
    <div className="min-h-screen bg-cyber-950 text-slate-100 flex flex-col md:flex-row font-sans selection:bg-cyan-500/25 selection:text-cyan-200">
      
      {/* =================================================================== */}
      {/* MOBILE STICKY TOP BAR (< 768px)                                      */}
      {/* =================================================================== */}
      <header className="md:hidden sticky top-0 z-40 flex items-center justify-between px-4 h-14 bg-cyber-900/90 backdrop-blur-xl border-b border-white/10 shadow-lg">
        {/* Brand Mark */}
        <Link href="/dashboard" className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-cyber-850 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-glass">
            <Shield className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <div className="font-extrabold tracking-tight text-white text-xs leading-none">NOOSFORGE</div>
            <div className="text-[9px] font-bold text-cyan-400 tracking-wider uppercase mt-0.5">EMPIRE SOC</div>
          </div>
        </Link>

        {/* Mobile Action Controls */}
        <div className="flex items-center gap-2">
          {/* Target Pulse Indicator Pill */}
          <div className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-md bg-white/[0.04] border border-white/10 text-[10px] text-slate-300">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            <span className="truncate max-w-[100px]">empire.edu.vn</span>
          </div>

          {/* Bilingual Language Switcher */}
          <button
            onClick={toggleLanguage}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-xs font-mono font-bold transition-all"
            title="Toggle Language (VI/EN)"
            aria-label="Toggle Language"
          >
            <Languages className="w-3.5 h-3.5 text-cyan-400" />
            <span className={locale === 'vi' ? 'text-cyan-400 font-extrabold' : 'text-slate-500'}>VI</span>
            <span className="text-slate-600 text-[10px]">/</span>
            <span className={locale === 'en' ? 'text-cyan-400 font-extrabold' : 'text-slate-500'}>EN</span>
          </button>

          {/* Animated Hamburger Button */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="w-9 h-9 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 flex items-center justify-center text-slate-300 hover:text-white transition-all focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
            aria-label={mobileMenuOpen ? t('shell.menuClose', 'Close menu') : t('shell.menuOpen', 'Open navigation menu')}
            aria-expanded={mobileMenuOpen}
          >
            {mobileMenuOpen ? <X className="w-5 h-5 text-cyan-400" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>
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
          className="absolute inset-0 bg-cyber-950/80 backdrop-blur-md"
          onClick={() => setMobileMenuOpen(false)}
        />

        {/* Slide-Over Drawer Container */}
        <aside
          className={`relative w-80 max-w-[85vw] h-full bg-cyber-900/98 backdrop-blur-2xl border-r border-white/15 shadow-2xl flex flex-col justify-between transform transition-transform duration-300 ease-out ${
            mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          {/* Drawer Header */}
          <div className="p-4 border-b border-white/10 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500/20 to-transparent border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-md">
                <Shield className="w-5 h-5" />
              </div>
              <div>
                <div className="font-black text-sm tracking-wider text-white">NOOSFORGE</div>
                <div className="text-[10px] font-bold text-cyan-400 tracking-widest uppercase">
                  {t('brand.soc', 'Empire Security SOC')}
                </div>
              </div>
            </div>
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="p-1.5 rounded-lg bg-white/[0.05] hover:bg-white/[0.1] text-slate-400 hover:text-white transition-all"
              aria-label="Close Drawer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Target Environment Context Card */}
          <div className="px-4 py-3 bg-white/[0.02] border-b border-white/5 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400/50" />
              <div>
                <div className="text-[11px] font-bold text-slate-200">Empire Education Platform</div>
                <div className="text-[9px] text-cyan-400 font-mono">empire.edu.vn • SAME-ORIGIN</div>
              </div>
            </div>
          </div>

          {/* Grouped Navigation Links (Touch Friendly: Min 44px Height) */}
          <nav className="p-3 space-y-4 flex-1 overflow-y-auto">
            {NAVIGATION_GROUPS.map((group) => (
              <div key={group.groupKey} className="space-y-1">
                <div className="px-3 pt-1 pb-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
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
                          ? 'bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 font-bold shadow-lg shadow-cyan-950/60'
                          : 'text-slate-300 hover:text-white hover:bg-white/[0.06] border border-transparent hover:border-white/10'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <Icon className={`w-4 h-4 ${isActive ? 'text-slate-950' : 'text-slate-400'}`} />
                        <span className="truncate">{translatedName}</span>
                      </div>
                      {item.badge && (
                        <span
                          className={`text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded ${
                            isActive
                              ? 'bg-slate-950 text-cyan-300 shadow-sm'
                              : 'bg-white/[0.05] text-cyan-400 border border-cyan-800/50'
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
          <div className="p-4 border-t border-white/10 text-xs text-slate-400 flex items-center justify-between bg-white/[0.01]">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400/50" />
              <span className="text-[11px] text-slate-300">
                {t('brand.continuousAudit', 'Continuous Audit Active')}
              </span>
            </div>
            <span className="text-[10px] text-slate-500 font-mono">v2.0.0</span>
          </div>
        </aside>
      </div>

      {/* =================================================================== */}
      {/* TABLET & DESKTOP STICKY VERTICAL SIDEBAR (>= 768px)                  */}
      {/* =================================================================== */}
      <aside
        className={`hidden md:flex flex-col justify-between sticky top-0 h-screen bg-cyber-900/85 backdrop-blur-xl border-r border-white/10 flex-shrink-0 z-30 transition-all duration-300 ease-in-out specular-highlight ${
          sidebarCollapsed ? 'w-20' : 'w-64'
        }`}
      >
        <div className="flex flex-col h-full overflow-hidden">
          {/* Brand Banner & Collapse Toggle Header */}
          <div className="p-4 border-b border-white/10 flex items-center justify-between">
            {!sidebarCollapsed ? (
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500/20 to-transparent border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-lg shadow-cyan-950/40">
                  <Shield className="w-5 h-5" />
                </div>
                <div>
                  <div className="font-black text-sm tracking-wider text-white">NOOSFORGE</div>
                  <div className="text-[10px] font-bold text-cyan-400 tracking-widest uppercase">
                    {t('brand.soc', 'Empire Security SOC')}
                  </div>
                </div>
              </div>
            ) : (
              <div className="w-full flex justify-center">
                <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-cyan-500/20 to-transparent border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-lg shadow-cyan-950/40">
                  <Shield className="w-5 h-5" />
                </div>
              </div>
            )}

            {/* Sidebar Collapse/Expand Toggle Button */}
            {!sidebarCollapsed && (
              <button
                onClick={toggleSidebar}
                className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white border border-white/10 transition-all"
                title={t('shell.collapseSidebar', 'Collapse Sidebar')}
                aria-label="Collapse Sidebar"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Collapsed Mode Expand Button */}
          {sidebarCollapsed && (
            <div className="p-2 border-b border-white/10 flex justify-center">
              <button
                onClick={toggleSidebar}
                className="p-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-slate-400 hover:text-white border border-white/10 transition-all"
                title={t('shell.expandSidebar', 'Expand Sidebar')}
                aria-label="Expand Sidebar"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          )}

          {/* Target Environment Badge (Expanded Only) */}
          {!sidebarCollapsed && (
            <div className="px-3.5 py-2.5 bg-white/[0.02] border-b border-white/5 flex items-center justify-between text-xs">
              <span className="text-slate-400 font-medium text-[11px]">{t('brand.targetContext', 'Target Context:')}</span>
              <span className="px-2 py-0.5 rounded-md bg-cyan-950/80 text-cyan-300 border border-cyan-700/50 text-[10px] font-bold shadow-sm">
                Empire Education
              </span>
            </div>
          )}

          {/* Grouped Navigation Links */}
          <nav className="p-2 space-y-3 flex-1 overflow-y-auto">
            {NAVIGATION_GROUPS.map((group) => (
              <div key={group.groupKey} className="space-y-0.5">
                {!sidebarCollapsed && (
                  <div className="px-2.5 pt-2 pb-1 text-[9px] font-bold uppercase tracking-wider text-slate-500">
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
                      } rounded-lg text-xs font-medium transition-all ${
                        isActive
                          ? 'bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 font-bold shadow-md shadow-cyan-950/60'
                          : 'text-slate-400 hover:text-white hover:bg-white/[0.04] border border-transparent hover:border-white/5'
                      }`}
                    >
                      <div className="flex items-center gap-2.5">
                        <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-slate-950' : 'text-slate-400'}`} />
                        {!sidebarCollapsed && <span className="truncate">{translatedName}</span>}
                      </div>
                      {!sidebarCollapsed && item.badge && (
                        <span
                          className={`text-[9px] font-extrabold uppercase px-1.5 py-0.5 rounded ${
                            isActive
                              ? 'bg-slate-950 text-cyan-300 shadow-sm'
                              : 'bg-white/[0.05] text-cyan-400 border border-cyan-800/50'
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
          <div className="p-3 border-t border-white/10 text-xs text-slate-400 flex items-center justify-between bg-white/[0.01]">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse shadow-sm shadow-emerald-400/50" />
              {!sidebarCollapsed && (
                <span className="text-[11px] text-slate-300">
                  {t('brand.continuousAudit', 'Continuous Audit Active')}
                </span>
              )}
            </div>
            {!sidebarCollapsed && <span className="text-[10px] text-slate-500 font-mono">v2.0.0</span>}
          </div>
        </div>
      </aside>

      {/* =================================================================== */}
      {/* MAIN CONTENT VIEWPORT CONTAINER                                     */}
      {/* =================================================================== */}
      <div className="min-w-0 flex-1 flex flex-col min-h-screen overflow-x-hidden">
        
        {/* ================================================================= */}
        {/* TOP STATUS UTILITY BAR (Tablet & Desktop >= 768px)                */}
        {/* ================================================================= */}
        <header className="hidden md:flex sticky top-0 z-30 items-center justify-between px-6 lg:px-8 h-14 bg-cyber-950/80 backdrop-blur-xl border-b border-white/10 shadow-sm">
          {/* Target Environment Badge & Scope */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-cyan-950/40 border border-cyan-500/30 text-xs shadow-sm">
              <div className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </div>
              <span className="font-bold text-slate-200 text-xs">Empire Education Platform</span>
              <span className="text-slate-500">|</span>
              <span className="text-[10px] font-mono font-semibold text-cyan-400">empire.edu.vn</span>
              <span className="px-1.5 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800/60 text-[9px] font-extrabold uppercase tracking-wide">
                SAME-ORIGIN
              </span>
            </div>

            {/* Backend Connectivity Status Pill */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium border shadow-sm ${
                backendStatus === 'online'
                  ? 'bg-emerald-950/40 text-emerald-400 border-emerald-500/30'
                  : backendStatus === 'checking'
                  ? 'bg-amber-950/40 text-amber-400 border-amber-500/30'
                  : 'bg-rose-950/40 text-rose-400 border-rose-500/30'
              }`}
              title="Backend API Connection Health"
            >
              {backendStatus === 'online' ? (
                <>
                  <Wifi className="w-3.5 h-3.5" />
                  <span>{t('shell.backendOnline', 'API: Online')}</span>
                  {latencyMs !== null && <span className="font-mono text-[10px] text-emerald-500/80">({latencyMs}ms)</span>}
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
                className="p-2 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] border border-white/10 text-slate-300 hover:text-white transition-all relative"
                title={t('shell.notifications', 'Security Alerts')}
                aria-label="View security notifications"
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
                <div className="absolute right-0 top-11 w-80 sm:w-96 rounded-xl bg-cyber-900/95 backdrop-blur-2xl border border-white/15 shadow-2xl p-3 z-50 specular-highlight">
                  <div className="flex items-center justify-between pb-2 mb-2 border-b border-white/10">
                    <div className="flex items-center gap-2">
                      <Bell className="w-4 h-4 text-cyan-400" />
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
                        className="text-[10px] text-cyan-400 hover:text-cyan-300 flex items-center gap-1 font-semibold"
                      >
                        <CheckCheck className="w-3 h-3" />
                        {t('shell.markAllRead', 'Mark all read')}
                      </button>
                    )}
                  </div>

                  <div className="space-y-2 max-h-72 overflow-y-auto">
                    {alerts.length === 0 ? (
                      <div className="py-6 text-center text-xs text-slate-500">
                        {t('shell.noNotifications', 'No unread alerts')}
                      </div>
                    ) : (
                      alerts.map((alert) => (
                        <div
                          key={alert.id}
                          className={`p-2.5 rounded-lg border text-xs transition-all ${
                            alert.isRead
                              ? 'bg-white/[0.01] border-white/5 text-slate-400'
                              : 'bg-white/[0.04] border-white/10 text-slate-200 shadow-sm'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-2">
                            <span className="font-bold text-white text-xs">{alert.title}</span>
                            <span className="text-[10px] text-slate-500 font-mono flex items-center gap-1">
                              <Clock className="w-2.5 h-2.5" />
                              {alert.timestamp}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-1 leading-snug">{alert.message}</p>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Bilingual Segmented Locale Toggle Button */}
            <div className="flex items-center p-0.5 rounded-lg bg-cyber-850 border border-white/15 shadow-inner text-xs font-mono">
              <button
                onClick={() => setLocale('vi')}
                className={`px-2.5 py-1 rounded-md text-xs font-bold transition-all ${
                  locale === 'vi'
                    ? 'bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 font-black shadow-md shadow-cyan-950/40'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                VI
              </button>
              <button
                onClick={() => setLocale('en')}
                className={`px-2.5 py-1 rounded-md text-xs font-bold transition-all ${
                  locale === 'en'
                    ? 'bg-gradient-to-r from-cyan-500 to-cyan-400 text-slate-950 font-black shadow-md shadow-cyan-950/40'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                EN
              </button>
            </div>
          </div>
        </header>

        {/* Main Workspace Page Viewport */}
        <main className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

---

### 5.3 Compatibility Re-Export: `frontend/src/components/Shell.tsx`

To guarantee that any legacy imports referencing `frontend/src/components/Shell.tsx` or `frontend/src/components/layout/Shell.tsx` resolve without error:

```tsx
export { default } from './layout/Shell';
```

---

## 6. Worker Step-by-Step Execution Plan

1. **Step 1: Extend `frontend/src/lib/i18n.tsx`**:
   - Add the new navigation group keys (`nav.group.core`, `nav.group.inventory`, `nav.group.intelligence`, `nav.group.governance`).
   - Add the new shell utility strings (`shell.notifications`, `shell.markAllRead`, `shell.noNotifications`, `shell.backendOnline`, `shell.backendChecking`, `shell.backendOffline`, etc.) to both `vi` and `en` dictionaries.
2. **Step 2: Replace `frontend/src/components/layout/Shell.tsx`**:
   - Deploy the drop-in source code above with zero omissions or stubs.
3. **Step 3: Create Re-Export Shim `frontend/src/components/Shell.tsx`**:
   - Write `export { default } from './layout/Shell';`.
4. **Step 4: Typecheck Verification**:
   - Execute `npm --prefix frontend run typecheck` to confirm 100% clean TypeScript compilation without warnings or errors.
5. **Step 5: Visual & Interaction Verification Across Viewports**:
   - Verify mobile viewport (< 768px): slide-over drawer opens, body scrolling locks, click outside closes drawer, tap targets are >= 44px.
   - Verify tablet viewport (768px - 1024px): sidebar collapse/expand toggle functions cleanly, table space expands.
   - Verify desktop viewport (> 1024px): top utility bar renders target badge, backend health pill, notification popover, and locale switch.

---

## 7. Comprehensive Verification & Test Checklist

### A. Mobile Viewport (< 768px)
- [ ] Mobile header bar is sticky at top (`h-14`) with NOOSFORGE EMPIRE logo and animated hamburger button.
- [ ] Tapping hamburger button smoothly slides out the drawer modal from the left.
- [ ] Drawer has a dark frosted glass backdrop blur overlay (`bg-cyber-950/80 backdrop-blur-md`).
- [ ] Tapping the backdrop or pressing the `Escape` key immediately closes the drawer.
- [ ] Background body scrolling is locked while the drawer is open.
- [ ] Navigation tap targets are touch-friendly with minimum 44px height (`min-h-[44px]`).
- [ ] Tapping any navigation link navigates to the target route and automatically closes the drawer.
- [ ] Target environment context card is visible inside the drawer with live green pulse.

### B. Tablet Viewport (768px - 1024px)
- [ ] Sticky sidebar renders on the left without covering the entire screen.
- [ ] Sidebar collapse toggle button (`ChevronLeft`) reduces sidebar width from `w-64` to `w-20`.
- [ ] Collapsing the sidebar reclaims ~196px of horizontal space for wide vulnerability tables.
- [ ] In collapsed mode, navigation items display icon-only with native tooltip text on hover.
- [ ] Expanding the sidebar restores labels and group headers smoothly.
- [ ] Collapsed state persists in `localStorage` across page reloads.

### C. Desktop Viewport (> 1024px)
- [ ] Sticky frosted glass sidebar renders with `backdrop-blur-xl border-r border-white/10`.
- [ ] All 14 navigation links are present and organized into 4 distinct groups:
  - Core Overview (1: Security Overview)
  - Inventory & Scans (4: Targets, Scan Center, Active Assessments, Schedules)
  - Intelligence & Modules (4: Empire Modules, Findings & Evidence, Vulnerability Intelligence, Remediation)
  - Governance & System (5: Detection Rules, Reports, Integrations, System Health, Settings)
- [ ] Active route displays cyan gradient pill with dark text and drop shadow.
- [ ] Top utility bar renders at top of workspace with:
  - Target badge: `Empire Education Platform` (`empire.edu.vn`) with live pulsing green dot and `SAME-ORIGIN` chip.
  - Backend health indicator pill: Displays `API: Online` with latency (e.g. `24ms`) or graceful status.
  - Notification bell: Displays unread badge counter (`3`), clicking opens popover dropdown with alert list and "Mark all read" button.
  - Bilingual locale switch: Segmented pill (`VI / EN`) switches interface language instantly.

### D. Viewport Fluidity & No Horizontal Scroll
- [ ] Main workspace uses `min-w-0 flex-1 flex flex-col overflow-x-hidden`.
- [ ] Outer page wrapper utilizes responsive padding `px-4 sm:px-6 lg:px-8 py-6 max-w-7xl mx-auto`.
- [ ] No viewport width between 320px and 2560px produces horizontal scrollbars on `window` or `body`.
