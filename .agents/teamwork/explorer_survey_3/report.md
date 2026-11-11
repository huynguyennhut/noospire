# NOOSFORGE Security Intelligence — Frontend & UI/UX Architecture Survey Report

**Explorer**: `explorer_survey_3`  
**Target Codebase**: `c:\Users\nguye\Desktop\noospire\frontend` & `c:\Users\nguye\Desktop\noospire\backend`  
**Date**: 2026-11-08  
**Scope**: Frontend architecture, 14 navigation views (R4), Liquid Glass design system, bilingual i18n, and backend API integration points.

---

## 1. Executive Summary

A comprehensive, read-only architectural investigation was conducted across the NOOSFORGE frontend codebase (`frontend/`) and its integration boundaries with the FastAPI backend (`backend/`).

### Key Findings Summary:
1. **Frontend Architecture**: Built on **Next.js 14.2.35 (App Router)**, **React 18.3.1**, **TypeScript 5.6.3**, and **Tailwind CSS 3.4.14**. Both `tsc --noEmit` and `next build` compile cleanly (18/18 static pages generated).
2. **14 Navigation Views**: All 14 distinct route directories exist under `frontend/src/app/`, but `components/layout/Shell.tsx` only lists **13 navigation items** in its sidebar—`/detection-rules` is missing from `NAVIGATION_ITEMS`.
3. **Design System**: Currently styled in a dark "Cyber-Slate" theme (`cyber-950` #070B14, `cyber-900` #0E1526, Cyan accents). It does **not** yet adhere to the required **Black/White/Liquid Glass** styling (translucent frosted glass cards, white specular borders, `backdrop-blur` elevation, and liquid glass reflections).
4. **Bilingual Internationalization (i18n)**: **0% implemented**. There is currently no dictionary file, no i18n context/hook, `<html lang="en">` is hardcoded, no language switcher exists in `Shell.tsx`, and all 14 views contain 100% hardcoded English text.
5. **Backend API Integrations**: `api.ts` connects to FastAPI via Next.js rewrites (`/api/v1/:path*` -> `http://127.0.0.1:8000/api/v1/:path*`). Three critical integration gaps exist:
   - **8-Step Live Target Verification Pipeline**: Missing in the Targets UI (`/assets`).
   - **Live Scan Telemetry**: The UI polls `GET /scans/{id}/logs` every 2s rather than connecting to the backend's real-time Server-Sent Events (SSE) stream (`/scans/{id}/logs/stream`).
   - **Evidence Viewer**: Displays raw unstructured JSON in a `<pre>` tag rather than an interactive, tabbed HTTP Request / Response / Payload / Proof forensic viewer.

---

## 2. Frontend Architecture & Next.js 14 App Router Structure

### 2.1. Directory Structure

```text
frontend/
├── package.json                   # Next 14.2.24/14.2.35, React 18.3.1, Tailwind 3.4.14, Lucide-React
├── tsconfig.json                  # Target ES2017, path alias "@/*" -> "./src/*"
├── next.config.js                 # API rewrites proxying /api/v1 to http://127.0.0.1:8000
├── tailwind.config.js             # Theme definitions (cyber-* slate colors, severity colors)
├── postcss.config.js              # Tailwind + Autoprefixer
└── src/
    ├── app/                       # Next.js 14 App Router
    │   ├── layout.tsx             # Root layout (Server Component), html lang="en", dark class
    │   ├── page.tsx               # Root redirect -> /dashboard (Server Component)
    │   ├── dashboard/page.tsx     # Overview Dashboard (Client Component)
    │   ├── assets/page.tsx        # Targets Management (Client Component)
    │   ├── scans/page.tsx         # Scan Center (Client Component)
    │   ├── active-assessments/page.tsx # Live Scan Detail & Tracker (Client Component)
    │   ├── findings/page.tsx      # Findings & Evidence (Client Component)
    │   ├── threat-intel/page.tsx  # Vulnerability Intelligence (Client Component)
    │   ├── reports/page.tsx       # Reports Center (Client Component)
    │   ├── empire-modules/page.tsx# Empire Business Modules (Client Component)
    │   ├── remediation/page.tsx   # Remediation Board (Client Component)
    │   ├── schedules/page.tsx     # Daily Assessment Scheduler (Client Component)
    │   ├── detection-rules/page.tsx # Detection Rules Library & YAML Editor (Client Component)
    │   ├── integrations/page.tsx  # Scanner Engines & Webhooks (Client Component)
    │   ├── health/page.tsx        # System Health & Telemetry (Client Component)
    │   └── settings/page.tsx      # Security Settings & Baseline Policy (Client Component)
    ├── components/
    │   └── layout/
    │       └── Shell.tsx          # Unified SOC layout shell with Sidebar, Header, Alerts badge
    ├── lib/
    │   ├── api.ts                 # ApiClient class interfacing with /api/v1 REST endpoints
    │   └── types.ts               # Complete TypeScript types matching backend schemas
    └── styles/
        └── globals.css            # Base Tailwind imports, dark CSS variables, scrollbars
```

### 2.2. Component Architecture (Client vs. Server Components)

- **Server Components**:
  - `src/app/layout.tsx`: Renders top-level HTML, metadata, and mounts `<Shell>{children}</Shell>`.
  - `src/app/page.tsx`: Simple redirect component calling `redirect('/dashboard')`.
- **Client Components (`'use client'`)**:
  - `src/components/layout/Shell.tsx`: Manages navigation state, mobile drawer toggle, active route highlighting, and alert counts.
  - **All 14 page files** (`src/app/*/page.tsx`) are marked `'use client'` because they manage interactive forms, client-side fetches (`api.*`), polling intervals, modals, tabs, or search filters.
  - Pages that read search params (`/active-assessments` and `/findings`) use `<React.Suspense>` boundaries to prevent Next.js static prerender bailouts.
- **Component Modularity Assessment**:
  - **Zero shared UI primitives**: Currently, `src/components/` only contains `layout/Shell.tsx`. Modals, forms, status badges, KPI stat blocks, and tables are directly implemented inline inside each of the 14 `page.tsx` files.
  - Refactoring opportunity: Creating modular shared components (e.g., `LiquidGlassCard`, `EvidenceViewerModal`, `LanguageSwitcher`, `VerificationStepPipeline`, `SeverityBadge`, `MetricStatCard`) will significantly improve maintainability and i18n consistency.

---

## 3. Analysis of the 14 Navigation Views (Requirement R4)

The platform provides 14 operational views matching the Empire security lifecycle. The table below catalogs each view, its file location, current status, operational capabilities, and identified discrepancies:

| # | Route | View Name | File Location | Key Capabilities | Discrepancies & Findings |
|---|---|---|---|---|---|
| 1 | `/dashboard` | **Security Overview** | `src/app/dashboard/page.tsx` | 10 KPI summary cards; 8 DB-backed chart datasets (Severity, Lifecycle Trend, Module Risk, Coverage, Risk Trend, Engine Perf, Intel Activity, Remediation). | Hardcoded English; uses opaque Cyber-Slate cards instead of Liquid Glass. |
| 2 | `/assets` | **Targets Management** | `src/app/assets/page.tsx` | Target inventory table, search, module/environment filters, target registration modal, bulk importer (CSV, JSON, OpenAPI). | **Missing 8-step live target verification pipeline UI** (`api.verifyAsset` not connected). Auto-registration of `https://empire.edu.vn/` must be ensured. |
| 3 | `/scans` | **Scan Center** | `src/app/scans/page.tsx` | 7 assessment profiles (Quick, Daily Security, Standard, Authenticated, API, Thorough, Infra); dispatch form; execution history table. | Profile descriptions hardcoded in English; no real-time status indicator on history rows. |
| 4 | `/active-assessments` | **Live Scan Detail** | `src/app/active-assessments/page.tsx` | Assessment job queue, target locator, engine badge, progress bar, live terminal output, cooperative scan cancel button. | **Uses 2s polling interval** (`getScanLogs`) instead of Server-Sent Events stream (`/scans/{id}/logs/stream`). |
| 5 | `/findings` | **Findings Center** | `src/app/findings/page.tsx` | Filterable findings inventory table (severity, module, lifecycle state); slide-in detail drawer; 1-click live retest; lifecycle state triage updater. | **Evidence viewer is raw JSON text** (`<pre>{JSON.stringify(...)}</pre>`); needs structured Request/Response/Payload tabs. |
| 6 | `/threat-intel` | **Vulnerability Intelligence** | `src/app/threat-intel/page.tsx` | CVE lookup form; CISA KEV catalog table with ransomware flags & EPSS scores; feed synchronization trigger; status cards. | Fully functional; needs bilingual translations for feed labels and descriptions. |
| 7 | `/reports` | **Report Center** | `src/app/reports/page.tsx` | 10 audit report templates; multi-format generation modal (PDF, HTML, JSON); report inventory table with instant download links. | Fully integrated with ReportLab backend; template descriptions require i18n dictionary mapping. |
| 8 | `/empire-modules` | **Empire Business Modules** | `src/app/empire-modules/page.tsx` | 6 functional unit cards (Student Mgmt, Learning Materials, Supporting Tools, APIs, Web App, Infra) with risk scoring and finding counts. | Navigation link to filtered findings works; needs Liquid Glass card styling. |
| 9 | `/remediation` | **Remediation Board** | `src/app/remediation/page.tsx` | 5-column Kanban board (OPEN, IN_REMEDIATION, FIXED, REOPENED, ACCEPTED_RISK); triage modal to update assignee, notes, and lifecycle state. | Functional lifecycle transitions; needs drag-and-drop or streamlined quick-action buttons. |
| 10 | `/schedules` | **Daily Scheduler** | `src/app/schedules/page.tsx` | Asia/Ho_Chi_Minh (02:00 AM ICT) assessment pipeline configuration; one-click manual dispatch; schedule creation modal; active toggle. | Fully integrated with backend scheduler; cron text needs localized Vietnamese tooltips. |
| 11 | `/detection-rules` | **Detection Rules** | `src/app/detection-rules/page.tsx` | Declarative YAML rules library; syntax validator; rule editor modal; lifecycle gating transitions (draft → active); rule test runner. | **CRITICAL: Omitted from `Shell.tsx` navigation sidebar!** Only 13 items currently listed in `Shell.tsx`. |
| 12 | `/integrations` | **Integrations & Scanners** | `src/app/integrations/page.tsx` | Status cards for integrated scanners (Nuclei, Empire Engine, ZAP, Trivy); threat feed sync; notification webhook test dispatcher. | Webhook simulation functional; scanner engines listed statically. |
| 13 | `/health` | **System Health & Telemetry** | `src/app/health/page.tsx` | Real-time health telemetry: FastAPI Gateway, SQLAlchemy DB connection, Dispatcher Worker pool depth, Operating Timezone. | Directly fetches `/health`; status badges need Liquid Glass glow styling. |
| 14 | `/settings` | **Security Settings & Policies** | `src/app/settings/page.tsx` | 4 tabbed panels: Approved Public Media Policy (`/media` `BaselineException` manager), Synthetic Student Identities, Target Assessment Policies, SSRF Defense boundaries. | Fully functional CRUD for baseline exceptions; needs i18n support. |

---

## 4. Design System: Black/White/Liquid Glass Styling Analysis

### 4.1. Current Styling State
- Current styles in `tailwind.config.js` and `styles/globals.css`:
  - Heavy dependence on opaque slate dark backgrounds: `bg-cyber-950` (`#070B14`), `bg-cyber-900` (`#0E1526`), `bg-cyber-850` (`#141D33`).
  - Borders use low-contrast blue/slate: `border-cyber-800` (`#1F2E4D`).
  - Accents are predominantly cyan (`#06B6D4` / `#22D3EE`).
- **Deficiencies against R4 Black/White/Liquid Glass**:
  - Missing frosted glass translucent cards (`bg-white/[0.02]` or `bg-white/[0.04]`).
  - Missing backdrop blur utilities (`backdrop-blur-md` / `backdrop-blur-xl`).
  - Missing pure white specular border highlights (`border-white/10`, `border-white/15`, `hover:border-white/30`).
  - Missing subtle gradient glass sheen and reflection overlay (`before:bg-gradient-to-b before:from-white/10 before:to-transparent`).
  - Missing deep pitch-black contrast base (`#000000` / `#05070E`).

### 4.2. Recommended Liquid Glass Design System Specifications

To achieve the modern Black/White/Liquid Glass aesthetic without breaking existing layout mechanics:

1. **CSS Variables & Utility Classes (`globals.css`)**:
   ```css
   :root {
     --glass-bg: rgba(255, 255, 255, 0.03);
     --glass-bg-elevated: rgba(255, 255, 255, 0.06);
     --glass-border: rgba(255, 255, 255, 0.08);
     --glass-border-strong: rgba(255, 255, 255, 0.18);
     --glass-highlight: rgba(255, 255, 255, 0.12);
     --bg-pitch-black: #05070E;
   }

   .liquid-glass-card {
     background: rgba(14, 21, 38, 0.55);
     backdrop-filter: blur(16px);
     -webkit-backdrop-filter: blur(16px);
     border: 1px solid rgba(255, 255, 255, 0.08);
     box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
     position: relative;
   }

   .liquid-glass-card::before {
     content: '';
     position: absolute;
     inset: 0;
     border-radius: inherit;
     padding: 1px;
     background: linear-gradient(180deg, rgba(255, 255, 255, 0.15) 0%, rgba(255, 255, 255, 0.02) 100%);
     -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
     mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
     -webkit-mask-composite: xor;
     mask-composite: exclude;
     pointer-events: none;
   }

   .liquid-glass-elevated {
     background: rgba(20, 29, 51, 0.7);
     backdrop-filter: blur(24px);
     -webkit-backdrop-filter: blur(24px);
     border: 1px solid rgba(255, 255, 255, 0.14);
     box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.45);
   }
   ```

2. **Tailwind Extension (`tailwind.config.js`)**:
   - Add backdrop blur scale (`backdropBlur: { 'xs': '2px', 'glass': '16px', 'deep': '24px' }`).
   - Add glass border colors (`border: { 'glass-subtle': 'rgba(255,255,255,0.08)', 'glass-strong': 'rgba(255,255,255,0.2)' }`).
   - Add pitch-black base color palette (`deep-black: '#030509'`).

---

## 5. Bilingual Internationalization (i18n) Architecture & Strategy

### 5.1. Current Gap Analysis
- Currently, **0% of strings are internationalized**.
- All navigation items, table column headers, status labels, modal text, button actions, and notifications are hardcoded in English.
- Requirement R4 demands:
  > "Deliver a Next.js 14 App Router frontend featuring 14 navigation views... Provide complete bilingual internationalization (Vietnamese and English) with Vietnamese as the default locale."

### 5.2. Recommended i18n Architecture

Since all 14 pages are Client Components, an ultra-fast, zero-overhead, reactive React Context provider approach is optimal:

1. **Dictionary Storage**:
   - `frontend/src/lib/i18n/vi.json` (Default Locale)
   - `frontend/src/lib/i18n/en.json` (Selectable Locale)
   - Structured by domain:
     - `nav`: Navigation titles and badges
     - `common`: Action buttons (Save, Cancel, Refresh, Delete, Filter, Search, Download)
     - `dashboard`: KPI cards and chart titles
     - `targets`: Target management and 8-step verification labels
     - `scans`: Scan profiles, dispatch options, stage progress
     - `active`: Live terminal labels and telemetry
     - `findings`: Vulnerability triage, severity tiers, lifecycle states, evidence viewer
     - `intel`: Threat intelligence, CISA KEV, EPSS
     - `reports`: 10 report template names and descriptions
     - `empire_modules`: 6 business units and risk tiers
     - `remediation`: Kanban columns and SLA status
     - `schedules`: Scheduler configuration and timezones
     - `rules`: Detection rule editor and validator
     - `integrations`: Scanner engine and webhook labels
     - `health`: Telemetry indicators
     - `settings`: Approved baseline policy and identity configurations
2. **I18n Context & Custom Hook (`src/lib/i18n/context.tsx`)**:
   ```typescript
   export type Locale = 'vi' | 'en';
   interface I18nContextType {
     locale: Locale;
     setLocale: (loc: Locale) => void;
     t: (path: string, fallback?: string) => string;
   }
   ```
   - Persists user selection in `localStorage` (`sentinel_locale`).
   - Defaults to `'vi'` on initial load.
   - Synchronizes `document.documentElement.lang = locale`.
3. **Language Switcher Control in `Shell.tsx`**:
   - Added to the top header / sidebar footer of `Shell.tsx`.
   - Compact toggle: `[VI | EN]` with visual badge and flag icon.

---

## 6. Backend API Integration Points & Discrepancy Analysis

The frontend connects to the backend via `ApiClient` (`frontend/src/lib/api.ts`). The table below outlines key integration points, backend endpoints, and specific gaps:

| Subsystem | Backend Endpoint | Frontend Method | Integration Status | Required Actions |
|---|---|---|---|---|
| **Overview Metrics** | `GET /api/v1/metrics/overview` | `api.getOverviewMetrics()` | Integrated | Connect i18n to KPI card titles and risk posture badges. |
| **Chart Datasets** | `GET /api/v1/metrics/charts/*` | `api.getSeverityDist()`, `api.getVulnerabilityTrend()`, etc. | Integrated (8 charts) | Upgrade bar and donut charts to Liquid Glass styling with glow accents. |
| **Targets (List/CRUD)** | `GET /api/v1/assets`, `POST /api/v1/assets`, `DELETE /api/v1/assets/{id}` | `api.listAssets()`, `api.createAsset()`, `api.deleteAsset()` | Integrated | Ensure primary target `https://empire.edu.vn/` is prominent and verified. |
| **Targets Bulk Import** | `POST /api/v1/assets/bulk-import` | `api.bulkImportAssets()` | Integrated | Supports CSV, JSON, OpenAPI raw input with server-side deduplication. |
| **Target Verification** | `POST /api/v1/assets/{id}/verify` | `api.verifyAsset(id)` | **UI Missing** | **Build 8-step live verification UI** displaying: 1. Input validation, 2. DNS resolution, 3. TLS verification, 4. HTTP connectivity, 5. Redirect inspection, 6. Web discovery, 7. Fingerprint, 8. Verification result. |
| **Scan Dispatch** | `POST /api/v1/scans` | `api.dispatchScan()` | Integrated | Form supports 7 profiles and maps directly to backend engines. |
| **Scan Log Streaming** | `GET /api/v1/scans/{id}/logs/stream` (SSE) vs `GET /api/v1/scans/{id}/logs` | `api.getScanLogs(id)` | **Sub-optimal (Polling)** | **Upgrade to real-time `EventSource` SSE stream** (`/scans/{id}/logs/stream`) with automatic fallback to polling. |
| **Findings Explorer** | `GET /api/v1/findings` | `api.listFindings()` | Integrated | Filterable by module, severity, and lifecycle status. |
| **Live Retest Engine** | `POST /api/v1/findings/{id}/retest` | `api.retestFinding(id)` | Integrated | One-click live retest executes live against target and updates verdict. |
| **Evidence Viewer** | `GET /api/v1/findings/{id}` | `api.getFinding(id)` | **UI Primitive** | Replace raw JSON pre-tag with **tabbed Evidence Viewer**: Request Headers/Body, Response Headers/Body, Extracted Proof, Replay cURL command. |
| **Report Generation** | `POST /api/v1/reports/generate` | `api.generateReport()` | Integrated | Generates Vector PDF (ReportLab), HTML, and JSON with real DB data. |
| **Report Downloads** | `GET /api/v1/reports/{id}/download?format=...` | `api.getDownloadUrl()` | Integrated | Direct browser download triggers for PDF, HTML, and JSON artifacts. |
| **Detection Rules** | `GET /api/v1/rules`, `POST /api/v1/rules`, `POST /api/v1/rules/validate` | `api.listRules()`, `api.createRule()`, `api.validateRule()` | Functional | **Add `/detection-rules` to `Shell.tsx` navigation sidebar!** |

---

## 7. Actionable Implementation Roadmap for AGENT 3 (UI & Product Experience)

1. **Step 1: Fix Navigation Sidebar in `Shell.tsx`**:
   - Add `{ name: 'Detection Rules', href: '/detection-rules', icon: Code2 }` to `NAVIGATION_ITEMS` so all 14 views are accessible from the navigation menu.
2. **Step 2: Implement Bilingual i18n Subsystem**:
   - Create `src/lib/i18n/vi.json` (Vietnamese default) and `src/lib/i18n/en.json` (English).
   - Create `src/lib/i18n/context.tsx` with `I18nProvider` and `useI18n()` hook.
   - Embed language switcher component in `Shell.tsx`.
   - Wrap root layout and translate all 14 views.
3. **Step 3: Implement Black/White/Liquid Glass Styling**:
   - Update `globals.css` with `.liquid-glass-card`, `.liquid-glass-elevated`, frosted borders, and backdrop-blur tokens.
   - Refactor cards and headers across the 14 views to use translucent frosted glass styling with specular white borders.
4. **Step 4: Build Interactive 8-Step Target Verification Pipeline**:
   - Create `TargetVerificationModal` component on `/assets` allowing users to trigger and view the 8-step live verification pipeline against `https://empire.edu.vn/` and other targets.
5. **Step 5: Upgrade Live Scan Telemetry to Server-Sent Events (SSE)**:
   - In `/active-assessments`, implement `EventSource` connection to `/api/v1/scans/{scan_id}/logs/stream` for zero-latency terminal log streaming, with automatic fallback to polling.
6. **Step 6: Build Interactive Evidence Viewer**:
   - In `/findings`, replace the raw `<pre>` JSON display with a rich tabbed Evidence Viewer component providing Request, Response, Proof, and cURL command tabs.
