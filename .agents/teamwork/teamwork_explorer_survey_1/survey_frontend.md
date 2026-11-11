# FRONTEND ARCHITECTURE & SAAS OVERHAUL SURVEY
**NOOSFORGE Security Intelligence Platform**
**Author**: Teamwork Explorer (Survey Agent 1)
**Timestamp**: 2026-11-08T15:12:00Z
**Target Codebase**: `frontend/` (Next.js 14 App Router, TypeScript, Tailwind CSS)
**Working Directory**: `C:\Users\nguye\desktop\noospire`

---

## 1. Executive Summary & Purpose

This survey investigates the frontend architecture of the NOOSFORGE Security Intelligence platform located in `frontend/`. The investigation assesses the existing codebase against the requirements of **R1: Enterprise Cybersecurity SaaS Dashboard UI** and **R2: Existing Project and Backend Preservation**.

The primary objective is to evaluate what components, routes, styling tokens, data bindings, and UI mechanisms currently exist, diagnose gaps preventing it from reaching a production-grade enterprise cybersecurity SaaS dashboard standard, and provide a concrete, actionable roadmap for overhauling the frontend views without disrupting existing backend contracts or test suites.

### Key High-Level Findings
1. **Next.js 14 App Router Baseline is Solid**:
   - Clean Next.js 14.2 App Router setup with 18 prerendered static routes that compile with 0 TypeScript errors (`tsc --noEmit` PASS, `next build` PASS).
   - Rich "Black/White/Liquid Glass" dark design tokens configured in `tailwind.config.js` and `src/styles/globals.css`.
   - Comprehensive bilingual internationalization (`src/lib/i18n.tsx`) defaulting to Vietnamese (`vi`) with English (`en`) selectable across all 14 navigation views.
   - Complete REST API client (`src/lib/api.ts`) with 35+ typed methods connecting seamlessly to FastAPI `/api/v1/*` via Next.js proxy rewrites.
   - Real-time Server-Sent Events (SSE) telemetry connection for live scan streaming in `/active-assessments`.

2. **Core Architectural Gaps Against R1 Requirements**:
   - **No Dedicated Charting Library / Primitive**: Currently, zero charting libraries (`recharts`, `chart.js`, `visx`) are installed in `frontend/package.json`. In `/dashboard`, all 8 charts are currently built with raw, static CSS `<div>` progress bars and plain text boxes without interactive tooltips, SVG curves, hover crosshairs, responsive scaling, legends, or click-to-filter capabilities.
   - **Lack of Reusable UI Component Primitives**: All components (cards, tables, buttons, badges, inputs, dropdowns, modals) are styled ad-hoc and duplicated inline within individual route `page.tsx` files. There is no `src/components/ui/` library (Card, Button, Badge, Table, Modal, Tooltip, Tabs, StatCard).
   - **Vulnerability Management Table Lacks Interactive Sorting & Bulk Operations**: The table in `/findings` has basic filters (Severity, Module, Status) and search, but columns are not clickable/sortable (asc/desc), there is no multi-select bulk triage, no CSV/JSON export, and no pagination for large datasets.
   - **Target Management Lacks In-Depth Target Profiling**: `/assets` has target creation, bulk import, and 8-step verification, but lacks an expandable target drill-down profile drawer (endpoints list, TLS certificate details, DNS history, findings breakdown).
   - **Live Scanning Telemetry Needs Stage Progression Stepper & HUD**: `/active-assessments` streams SSE logs effectively, but lacks a visual multi-stage pipeline stepper (Pre-flight -> Discovery -> Active Scan -> Module Audit -> Deduplication) and real-time scanning HUD metrics (requests/sec, live findings count, elapsed time).

---

## 2. Dependency & Tooling Analysis (`frontend/package.json`)

### 2.1 Installed Dependencies
```json
{
  "dependencies": {
    "clsx": "^2.1.1",
    "lucide-react": "^0.460.0",
    "next": "^14.2.24",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "tailwind-merge": "^2.5.4"
  },
  "devDependencies": {
    "@types/node": "^20.17.0",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.47",
    "tailwindcss": "^3.4.14",
    "typescript": "^5.6.3"
  }
}
```

### 2.2 Critical Dependency Gaps & Observations
1. **Charting Library**:
   - No charting package (`recharts`, `chart.js`, `nivo`) is present in `package.json`.
   - **Strategic Decision**:
     - *Option A*: Install `recharts` (`npm install recharts --prefix frontend`). Recharts is declarative and React-native, but can sometimes have React 18 peer dependency warnings.
     - *Option B*: Build custom, lightweight, enterprise-grade SVG interactive charting components in `src/components/charts/` (AreaChart, DonutChart, BarChart, GaugeChart, RadarChart).
     - *Recommendation*: Building specialized, zero-dependency interactive SVG chart components with React state (custom tooltips, animated paths, hover crosshairs, glowing gradients, time-window filters) guarantees 100% build compatibility, zero bundle bloat, zero dependency conflicts, and complete visual alignment with the "Black/White/Liquid Glass" theme. If `recharts` is preferred, it can also be evaluated.
2. **UI Component Primitives**:
   - `clsx` and `tailwind-merge` are installed. This provides the exact foundation needed to build standard Shadcn-style lightweight UI primitives (`src/components/ui/`).
3. **Build & Lint Health**:
   - `npm run typecheck` (`tsc --noEmit`): **Passes with 0 errors**.
   - `npm run build` (`next build`): **Passes cleanly, producing 18 static routes**.
   - `npm run lint` (`next lint`): Currently prompts for ESLint initialization because `.eslintrc.json` is not present in `frontend/`. Adding a minimal `.eslintrc.json` (`{"extends": "next/core-web-vitals"}`) ensures `npm run lint` runs non-interactively and passes cleanly in CI.

---

## 3. Route & Navigation Architecture (`src/app/`)

The application implements a comprehensive 14-view Command Center mapped to Next.js 14 App Router routes:

| Route Path | View Name | Current Implementation | Backend Contract | Gaps / Required Enhancements |
|---|---|---|---|---|
| `/` | Root Landing | Redirects to `/dashboard` | None | Optimal. |
| `/dashboard` | Security Overview | 10 KPI summary cards, 8 chart widgets | `GET /api/v1/metrics/overview`, `/api/v1/metrics/charts/*` | Static CSS bars need upgrade to interactive SVG charts with tooltips, time-range toggles, and drill-down links. |
| `/assets` | Target Management | Target list table, Add Target modal, Bulk Import modal, 8-Step Verification modal | `GET/POST /api/v1/assets`, `POST /api/v1/assets/bulk-import`, `POST /api/v1/assets/{id}/verify` | Add sortable table columns, target detail drawer, findings count badge with drill-down link, batch actions. |
| `/scans` | Scan Dispatch Center | 7 Scan Profiles selector, target picker, engine picker, dispatch button | `POST /api/v1/scans`, `GET /api/v1/scans`, `GET /api/v1/assets` | Enhance profile configuration with advanced toggles (crawling depth, rate limit, excluded paths, auth profile). |
| `/active-assessments` | Live Scan Tracker | Scan queue list, SSE stream terminal, log level filter, keyword search, cancel button | `GET /api/v1/scans/{id}/logs/stream` (SSE), `GET /api/v1/scans/{id}`, `POST /api/v1/scans/{id}/cancel` | Add 5-stage visual pipeline stepper, real-time metrics HUD (req/s, findings discovered, elapsed time), log export. |
| `/findings` | Findings & Evidence | Findings table, severity/module/status filters, forensic detail drawer, tabbed EvidenceViewer | `GET /api/v1/findings`, `GET /api/v1/findings/{id}`, `POST /api/v1/findings/{id}/triage`, `POST /api/v1/findings/{id}/retest` | Add sortable columns (Severity, Title, Location, Date), multi-select bulk triage, CSV/JSON export, CVSS v3.1 calculator. |
| `/empire-modules` | Empire Business Modules | 6 module summary cards (Student, Materials, Tools, APIs, Web, Infra), risk scores | `GET /api/v1/empire-modules` | Add module attack surface breakdown, sub-component health meters, and quick scan trigger per module. |
| `/threat-intel` | Threat Intelligence | CISA KEV catalog table, CVE search box, sync intel trigger | `GET /api/v1/intel/kev`, `GET /api/v1/intel/cve/{id}`, `POST /api/v1/intel/sync` | Add EPSS score percentile distribution chart, KEV exploitation timeline, and affected asset correlation. |
| `/remediation` | Remediation Board | 5 lifecycle columns (Open, In Remediation, Fixed, Reopened, Accepted Risk) | `GET /api/v1/findings`, `POST /api/v1/findings/{id}/triage` | Add drag-and-drop or quick move action, SLA countdown indicators, assignee avatars, retest status. |
| `/reports` | Reports Center | 10 report template cards, generation modal (PDF, HTML, JSON), download list | `GET /api/v1/reports`, `POST /api/v1/reports/generate`, `GET /api/v1/reports/{id}/download` | Add report preview modal, custom date range filter, executive summary preview. |
| `/schedules` | Automated Schedules | Scheduled scan jobs list, trigger now button, toggle active switch, create modal | `GET/POST /api/v1/schedules`, `POST /api/v1/schedules/{id}/trigger`, `PUT /api/v1/schedules/{id}/toggle` | Add next run countdown timer, execution history modal, cron expression helper. |
| `/detection-rules` | Detection Rules | YAML rule editor, validation button, test rule execution, rule lifecycle | `GET/POST /api/v1/rules`, `POST /api/v1/rules/validate`, `POST /api/v1/rules/{id}/lifecycle` | Add syntax highlighted editor, rule testing results drawer, template library. |
| `/integrations` | Integrations Hub | External integration status (Better-Auth, MinIO, CISA KEV, Webhooks) | `GET /api/v1/settings` | Add connection test ping button, webhook payload tester, secret masking toggle. |
| `/health` | System Health | Service health cards, worker pool status, database ping latency | `GET /health` | Add real-time latency sparklines, worker queue depth gauge, scanner process monitor. |
| `/settings` | System Settings | System configurations, API keys, scanner safety policies | `GET /api/v1/settings` | Add policy presets, export/import configuration, audit log viewer. |

---

## 4. Component Architecture & Design System

### 4.1 Existing Components
1. `src/components/layout/Shell.tsx`:
   - Top-level persistent responsive layout container.
   - Fixed desktop sidebar (width: `16rem` / `w-64`) with smooth backdrop blur (`backdrop-blur-xl`).
   - Sticky mobile topbar with hamburger toggle (`Menu`/`X` from Lucide) and responsive mobile drawer.
   - Bilingual language pill (`VI` / `EN`) with instantaneous locale switching.
   - Visual status footer: Continuous Audit Active indicator with pulsing green dot.
2. `src/components/evidence/EvidenceViewer.tsx`:
   - Tabbed forensic modal/component: Proof/Matched Content, Request, Response, Headers, Replay cURL.
   - Syntax-formatted code containers with dark monospace styling and one-click clipboard copy (`navigator.clipboard.writeText`) with "Copied!" feedback.
3. `src/components/verification/TargetVerificationModal.tsx`:
   - 8-Step verification stepper executing the live target validation pipeline against backend endpoint `POST /api/v1/assets/{id}/verify`.
   - Visual step indicators: Input validation, DNS resolution, TLS verification, HTTP connectivity, Redirect inspection, Web discovery, Target fingerprint, Verification result.
   - Shows latency (ms), HTTP status codes, DNS A/AAAA/CNAME records, and TLS certificate details.

### 4.2 Design System Tokens (`globals.css` and `tailwind.config.js`)
- **Theme Name**: *Black / White / Liquid Glass Design System*
- **Color Palette**:
  - Background Base: `#070B14` (`cyber-950`) — Deep midnight tactical background.
  - Card Surface: `#0E1526` (`cyber-900`) — Frosted translucent container.
  - Surface Elevated: `#141D33` (`cyber-850`) — Elevated modals and dropdowns.
  - Subtle Border: `#1F2E4D` (`cyber-800`), Strong Border: `#2D426B` (`cyber-700`).
  - Primary Accent: `#06B6D4` (`cyber-500` / Cyan), `#22D3EE` (`cyber-400`).
  - Severity Matrix:
    * `CRITICAL`: `#EF4444` (Rose-500)
    * `HIGH`: `#F97316` (Orange-500)
    * `MEDIUM`: `#F59E0B` (Amber-500)
    * `LOW`: `#10B981` (Emerald-500)
    * `INFO`: `#06B6D4` (Cyan-500)
- **Glassmorphism Tokens**:
  - `.liquid-glass`: Linear gradient `rgba(255, 255, 255, 0.04)` to `0.01`, blur 16px, specular border.
  - `.liquid-glass-card`: Translucent surface with hover elevation `translateY(-1px)` and cyan glow.
  - `.liquid-glass-modal`: Backdrop blur 24px, deep shadow `rgba(0, 0, 0, 0.7)`.
  - `.specular-highlight`: Top border gradient reflection simulating polished liquid glass edge.

### 4.3 Missing Shared UI Primitives (`src/components/ui/`)
Currently, common UI patterns are repeatedly implemented inline across the 14 views. We recommend creating clean, reusable components in `src/components/ui/`:
- `Card.tsx` / `GlassCard.tsx`: Standardized liquid-glass container with header, content, and footer.
- `Badge.tsx`: Severity badge (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`), status badge, and module badge with consistent borders and glow.
- `Button.tsx`: Variants for `primary` (cyan gradient), `secondary` (glass), `danger` (rose), `ghost`, and `icon`.
- `Input.tsx` / `Select.tsx`: Form controls with cyber dark backgrounds and cyan focus rings.
- `DataTable.tsx`: Generic sortable, filterable table component with column headers, empty state, and loading skeleton.
- `Modal.tsx`: Accessible dialog wrapper with backdrop blur, ESC key dismiss, and focus lock.
- `Tabs.tsx`: Animated tab switcher for multi-view interfaces.
- `Tooltip.tsx`: Cyber-styled hover tooltips for charts and table icons.
- `StatCard.tsx`: Unified KPI metric card with icon, title, value, subtext, and trend sparkline indicator.

---

## 5. Data Layer & API Architecture (`src/lib/`)

### 5.1 API Client (`src/lib/api.ts`)
The API layer is cleanly abstracted into an `ApiClient` class exposing typed async methods:
- **Authentication**: `login(username, password)` with JWT storage in `localStorage`.
- **Metrics**: `getOverviewMetrics()`, `getSeverityDist()`, `getVulnerabilityTrend()`, `getModuleRiskChart()`, `getCoverageChart()`, `getRiskTrendChart()`, `getScannerPerformance()`, `getIntelligenceActivity()`, `getRemediationProgress()`.
- **Assets / Targets**: `listAssets()`, `createAsset()`, `bulkImportAssets()`, `getAsset()`, `verifyAsset()`, `deleteAsset()`.
- **Scans**: `listScans()`, `dispatchScan()`, `getScan()`, `cancelScan()`, `getScanLogs()`.
- **Findings**: `listFindings()`, `getFinding()`, `triageFinding()`, `retestFinding()`.
- **Baselines / Modules**: `listBaselines()`, `createBaseline()`, `getEmpireModules()`.
- **Schedules**: `listSchedules()`, `createSchedule()`, `triggerSchedule()`, `toggleSchedule()`.
- **Threat Intel & Rules**: `getIntelStatus()`, `syncIntel()`, `lookupCve()`, `getKevCatalog()`, `listRules()`, `validateRule()`, `createRule()`, `transitionRule()`, `testRule()`.
- **Reports & Settings**: `listReports()`, `generateReport()`, `deleteReport()`, `getDownloadUrl()`, `getSettings()`.

### 5.2 Server-Sent Events (SSE) Telemetry
In `src/app/active-assessments/page.tsx`, the application establishes a live stream:
- `const es = new EventSource('/api/v1/scans/{id}/logs/stream');`
- Parses chunked JSON log payloads: `{ timestamp, level, message, source }`.
- Integrates fallback polling (`api.getScanLogs`) if SSE is interrupted or unsupported.
- Implements autoscroll to the latest log line with smooth scrolling and pause-on-scroll user control.

### 5.3 Internationalization Engine (`src/lib/i18n.tsx`)
- Provides `useI18n()` hook with `locale` state (`vi` default, `en` toggle) and `t(key, fallback)` translation helper.
- Dictionary includes over 250 translated keys across all 14 functional views.
- Persists locale choice across browser sessions using `localStorage.setItem('sentinel_locale', locale)`.

---

## 6. Gap Analysis Against Requirement R1

| Requirement Item | Current Status | Identified Gap | Required Enhancement |
|---|---|---|---|
| **R1.1 Security analytics dashboard with interactive charts** | Partial | 8 charts exist but use static HTML/CSS divs and text boxes. No tooltips, no hover curves, no time-range selectors, no drill-down links. | Implement custom interactive SVG charts (Donut, Multi-Series Area/Line, Stacked Bar, Circular Gauge, Radar) with hover tooltips, crosshairs, time-range toggles (7D/14D/30D), and click-to-filter navigation. |
| **R1.2 Vulnerability management views with sortable, filterable tables & drill-down views** | Partial | Table exists with basic dropdown filters and search, but columns are not sortable. Missing multi-select bulk triage, CSV/JSON export, and advanced filter tags. | Add interactive column sorting (Severity, Title, Location, Module, CVSS, Date), multi-select checkboxes for batch triage, export to CSV/JSON, and full-screen expandable detail view with CVSS v3.1 calculator. |
| **R1.3 Target management interface supporting adding, viewing, and managing targets** | Mostly Complete | Full creation modal, bulk import modal, 8-step verification modal, scan trigger, and delete. Missing deep target profiling drawer and direct finding link. | Add target detail profile drawer (DNS history, TLS certificate validity, open findings breakdown, past scans), column sorting, and "View Findings" button. |
| **R1.4 Live scanning interface with interactive scan controls & real-time status/log displays** | Mostly Complete | Live SSE stream, scan selection queue, log search, level filter, cancel button. Missing visual phase stepper and scanner HUD metrics. | Add 5-stage visual execution pipeline stepper, real-time metrics HUD (requests/sec, findings counter, elapsed time), and log export. |
| **R1.5 Professional dark UI and responsive layouts across viewports** | Good | Rich color tokens, glassmorphism, responsive sidebar. Needs polished UI primitives, smoother micro-interactions, and mobile card fallbacks. | Create standardized `src/components/ui/` primitives and ensure high-density table views degrade gracefully on mobile (<768px). |
| **R1.6 Real, functional UI components rather than static mockups** | Met | All forms, buttons, and modals are wired to backend API endpoints. No mock/dummy arrays. | Maintain 100% functional data wiring during the overhaul. |

---

## 7. Strategic Recommendations for the Frontend Overhaul

### Strategy 1: Create a Dedicated Interactive SVG Chart Library (`src/components/charts/`)
To deliver a high-performance, dependency-safe charting system that adheres to the Black/White/Liquid Glass theme, implement dedicated interactive SVG chart components:
1. `InteractiveDonutChart.tsx`:
   - Interactive donut chart with animated SVG stroke-dasharray.
   - Hover on slices shows interactive tooltip with percentage and count.
   - Click on slice filters findings or navigates directly to `/findings?severity=CRITICAL`.
2. `InteractiveAreaTrendChart.tsx`:
   - SVG cubic bezier curves (`M... C...`) with linear gradients.
   - Dual series: Detected vulnerabilities vs Remediated vulnerabilities.
   - Hover crosshair showing precise date and counts for both series.
   - Time-range selector: 7 Days / 14 Days / 30 Days.
3. `InteractiveBarChart.tsx`:
   - Horizontal and vertical SVG bar charts with hover value tooltips, glowing gradients, and category labels.
4. `InteractiveCircularGauge.tsx`:
   - Circular SVG gauge with animated sweep angle displaying assessment coverage ($%$) with color thresholds (Emerald for >80%, Amber for 50-80%, Rose for <50%).
5. `RiskScoreGauge.tsx`:
   - Tactical circular speedometer displaying the overall Sentinel Risk Score ($SRS$) with posture level badge.

### Strategy 2: Modularize Common UI Primitives (`src/components/ui/`)
Build reusable components to unify the design language and eliminate duplicate code:
- `Badge.tsx`: Severity and status badges with standardized specular borders.
- `StatCard.tsx`: KPI summary cards with trend indicator and icon.
- `DataTable.tsx`: Reusable table with built-in sorting (asc/desc), search, pagination, and empty/loading states.
- `Modal.tsx`: Liquid glass modal with smooth fade-in and backdrop blur.
- `Tabs.tsx`: Cyber-styled tab bar with active indicator.

### Strategy 3: Overhaul Dashboard Page (`src/app/dashboard/page.tsx`)
- Replace the 8 basic CSS widgets with the new interactive SVG chart components.
- Wire time-range selector (`7d`, `14d`, `30d`) to `api.getVulnerabilityTrend(days)` and `api.getRiskTrendChart(days)`.
- Make chart elements clickable to navigate to filtered views (e.g., clicking on Critical in the Donut Chart navigates to `/findings?severity=CRITICAL`).

### Strategy 4: Overhaul Findings View (`src/app/findings/page.tsx`)
- Add clickable sort headers for all columns: Severity, Title, Module, Location, Lifecycle Status.
- Add multi-select checkboxes for batch triage (e.g., select 5 findings -> mark as "IN_REMEDIATION" or "ACCEPTED_RISK").
- Add CSV and JSON export buttons.
- Enhance the forensic detail drawer with a CVSS v3.1 calculator, finding timeline, and direct links to the target locator.

### Strategy 5: Overhaul Target Management (`src/app/assets/page.tsx`)
- Add sortable table columns (Name, Module, Status, Findings, Last Assessed).
- Add an expandable Target Profile Drawer showing DNS resolution details, TLS certificate expiration dates, discovered endpoints, and associated findings.
- Add direct navigation links to view findings for each specific target (`/findings?assetId=${asset.id}`).

### Strategy 6: Overhaul Live Assessment Tracker (`src/app/active-assessments/page.tsx`)
- Add a 5-stage visual execution pipeline stepper:
  1. *Target Pre-flight & Verification*
  2. *Bounded Web Crawler & Surface Discovery*
  3. *Nuclei / ZAP Security Assessment*
  4. *Empire Business Module Auditing*
  5. *Evidence Normalization & SRS Scoring*
- Add a live telemetry HUD showing:
  - Total requests dispatched
  - Requests per second
  - Discovered findings counter
  - Elapsed scan duration clock
- Add a "Copy All Logs" and "Download Logs (.txt)" button.

---

## 8. Verification & Compatibility Plan

The overhaul must satisfy the following verification criteria:
1. **Frontend Compilation**:
   - `npm run typecheck` (`tsc --noEmit`) must exit with code 0.
   - `npm run build` (`next build`) must successfully generate all static and dynamic pages with 0 errors.
2. **Backend Preservation & Test Suite**:
   - `pytest tests/` must pass cleanly with 0 regressions.
   - `scripts/verify_empire_e2e.py` (all 10 automated end-to-end tests) must pass with 10/10 PASS.
3. **Responsive Visual Verification**:
   - Verify desktop (1920x1080), tablet (768px), and mobile (375px) viewports for layout integrity, navigation accessibility, and chart responsiveness.
4. **Bilingual Verification**:
   - Toggle between Vietnamese (`vi`) and English (`en`) to confirm all new strings and chart labels render correctly.
