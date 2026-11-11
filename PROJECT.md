# Project: NOOSFORGE Security Intelligence — Enterprise Cybersecurity SaaS Dashboard

## Architecture
NOOSFORGE Security Intelligence is a production-grade, enterprise cybersecurity SaaS platform and command center for the Empire Education Platform (`https://empire.edu.vn/`).

The architecture comprises:
- **Backend Core**: FastAPI (Python 3.12/3.14) with asynchronous SQLAlchemy 2.0 ORM (`aiosqlite`/`asyncpg`) backed by `noospire.db`. Features SSRF protection gatekeeper, multi-tenant asset registry, 8-step target verification engine, bounded crawling, real scanner process executor, and multi-factor Sentinel Risk Score ($SRS$). 13 mounted API routers under `/api/v1` provide stable REST contracts.
- **Scan & Evidence Engine**: Process-safe scanner runner (Nuclei CLI v3.11.1, OWASP ZAP adapter, Empire custom business module engine) with raw HTTP request/response evidence capture, SSE log streaming (`ScanLogBuffer`), deterministic finding deduplication (SHA-256 fingerprint), and explicit 5-state quality machine (`SCANNED_SUCCESSFULLY`, `PARTIAL_COVERAGE`, `AUTH_REQUIRED`, `SCANNER_FAILED`, `TARGET_UNAVAILABLE`).
- **Frontend Command Center**: Next.js 14 App Router, TypeScript, Tailwind CSS, featuring the Black/White/Liquid Glass design system, full bilingual internationalization (Vietnamese default, English toggle), 14 operational navigation views, responsive layouts across mobile/tablet/desktop viewports, reusable UI component primitives (`components/ui/`), dedicated zero-dependency interactive SVG charting engine (`components/charts/`), live SSE scan monitoring with 5-stage stepper and telemetry HUD, and interactive tabbed forensic evidence viewer.
- **Verification Harness**: `scripts/verify_empire_e2e.py` (10 automated capability tests), `pytest` test suite (244 tests across 14 modules in `tests/`), non-interactive Next.js ESLint (`npm run lint`), TypeScript compile check (`tsc --noEmit`), Next.js static build check (`npm run build`), and automated dual-track test suite.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Primary Target Registration | Register `https://empire.edu.vn/` in `noospire.db` with same-origin scope & production-safe policy | M1 | Survey (R1) |
| 2 | 8-Step Live Target Verification Engine | Input validation, DNS resolution, TLS verification, HTTP connectivity, Redirect inspection, Web discovery, Target fingerprint, Verification result | M1 | Survey (R1) |
| 3 | Bulk Target Ingestion & Deduplication | CSV/JSON/TXT import with URL normalization, duplicate detection, and preview | M1 | Survey (R1) |
| 4 | Scanner Quality State Machine | Explicit quality states (`SCANNED_SUCCESSFULLY`, `PARTIAL_COVERAGE`, `AUTH_REQUIRED`, `SCANNER_FAILED`, `TARGET_UNAVAILABLE`) | M2 | Survey (R2) |
| 5 | Real Scanner Orchestration & Process Safety | Process registration in `ProcessSafetyManager`, Nuclei CLI / ZAP / Empire engine runner, bounded BFS crawler | M2 | Survey (R2) |
| 6 | Raw Evidence Capture & SSE Streaming | Full HTTP request/response evidence storage, audit trails, and SSE log streaming | M2 | Survey (R2) |
| 7 | Empire Module Security Taxonomy & Finding Intel | Coverage across 7 Empire modules, SHA-256 finding deduplication, SRS risk scoring, retesting lifecycle | M2 | Survey (R3) |
| 8 | 14 Navigation Views & Sidebar Completeness | All 14 views active and wired in `Shell.tsx` navigation sidebar including `/detection-rules` | M3 | Survey (R4) |
| 9 | Black/White/Liquid Glass Design System | Frosted glass cards, white specular borders, backdrop-blur elevation tokens | M3 | Survey (R4) |
| 10 | Bilingual Internationalization (VI/EN) | Vietnamese as default locale, English selectable, comprehensive dictionary across all 14 views | M3 | Survey (R4) |
| 11 | Interactive Evidence Viewer & SSE Tracker | Tabbed evidence modal (Request/Response/Headers/cURL) and real-time SSE scan tracking | M3 | Survey (R4) |
| 12 | Comprehensive E2E Verification & Live Assessment | Automated verification suite (10/10 tests in `scripts/verify_empire_e2e.py`) + live baseline against `https://empire.edu.vn/` | M4 | Survey (R5) |
| 13 | UI Component Primitives Library | Standardized reusable UI primitives in `src/components/ui/` (Card, Button, Badge, Table, Modal, Tooltip, Tabs, StatCard, Input, Dropdown) | M5 | Survey (R1) |
| 14 | Responsive Viewport Navigation Layout | Fully responsive layout in `Shell.tsx` with mobile topbar, collapsible drawer, tablet breakpoint, and desktop sticky sidebar | M5 | Survey (R1) |
| 15 | Reusable Interactive SVG Charting Engine | Zero-dependency SVG charts in `src/components/charts/` (AreaChart, DonutChart, BarChart, GaugeChart) with tooltips, legends, and animations | M5 | Survey (R1) |
| 16 | Non-Interactive ESLint Configuration | `.eslintrc.json` extending `next/core-web-vitals` to ensure `npm run lint` passes 100% cleanly | M5 | Survey (R2) |
| 17 | Security Analytics Overview Dashboard | Overhaul `/dashboard` with 10 KPI summary cards, 8 interactive SVG charts, time-range filters, and live API data hydration | M6 | Survey (R1) |
| 18 | Interactive Vulnerability Management Table | Overhaul `/findings` with multi-column sorting (Severity, Title, Target, Date), severity/module/status filters, search, and bulk triage | M6 | Survey (R1) |
| 19 | Forensic Vulnerability Drill-Down & Live Retest | 5-tab forensic evidence viewer modal (Proof, Request, Response, Headers, cURL), 10-state triage selector, and live retest trigger | M6 | Survey (R1) |
| 20 | Target Management & Profile Drawer | Overhaul `/assets` with sortable target table, target detail profile drawer, findings count drill-down, and single target registration | M6 | Survey (R1) |
| 21 | 8-Step Live Target Verification Pipeline Modal | Interactive probe pipeline modal wired to `POST /api/v1/assets/{id}/verify` with real-time step results and fingerprint inspect | M6 | Survey (R1) |
| 22 | Live Scanning Interface & Real-Time Telemetry HUD | Overhaul `/scans` and `/active-assessments` with 7 scan profiles, 5-stage pipeline stepper, real-time metrics HUD, and SSE log terminal | M6 | Survey (R1) |
| 23 | Dual-Track E2E Test Suite & Full Verification | Comprehensive E2E verification (`TEST_INFRA.md`, `TEST_READY.md`, `pytest`, `scripts/verify_empire_e2e.py`, `npm run build`, `npm run lint`) | M7 | Survey (R2) |
| 24 | Batch Domain Model & Migration | `ScanBatch` model (`scan_batches` table), SQLite WAL mode, foreign keys, busy timeout | M8 | Orchestrator (M8) |
| 25 | Batch Orchestration & Resource Throttling | `POST /api/v1/scans/batch`, `psutil` CPU/RAM throttling, concurrency bounds (1-4), cooperative cancel & emergency stop | M8 | Orchestrator (M8) |
| 26 | Live Telemetry & "trackcurrent" Feed | `GET /api/v1/scans/trackcurrent`, active worker thread matrix, lifecycle alerts in `security_alerts` | M8 | Orchestrator (M8) |
| 27 | Brand Asset & Liquid Glass Shell Header | Official brand logo integration in `Shell.tsx` across desktop, tablet, and mobile | M9 | Orchestrator (M9) |
| 28 | Liquid Glass Toast Notification System | `toast.tsx` (`ToastProvider`, `useToast()`) with backdrop-blur, specular highlight, auto-dismiss | M9 | Orchestrator (M9) |
| 29 | "Scan All" Batch Dispatch UI Hero Card | In `/scans`, Hero Card & Modal for "Scan All" across all targets/engines/profiles with concurrency slider | M9 | Orchestrator (M9) |
| 30 | Multi-Worker Thread Tracking ("trackcurrent") HUD | In `/active-assessments`, active worker matrix, focus switcher, batch progress bar, cooperative cancel | M9 | Orchestrator (M9) |
| 31 | Dual-Track Test Suite & Full Regression Pass | Automated tests `tests/test_scan_all_batch_orchestration.py` (BAT-01..BAT-13), `pytest`, `verify_empire_e2e.py`, `npm run build`, `npm run lint` | M10 | Orchestrator (M10) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Platform Core (AGENT 1) | Target management, primary root asset seeding (`https://empire.edu.vn/`), 8-step live verification engine, bulk import preview API | none | DONE |
| M2 | Scanning & Intelligence (AGENT 2) | Quality state machine, process safety, bounded BFS crawler, raw evidence logging, Empire finding taxonomy & retesting | M1 | DONE |
| M3 | UI & Product Experience (AGENT 3) | 14 views in Shell sidebar, Black/White/Liquid Glass styling, Vietnamese/English i18n, 8-step verification modal, tabbed evidence viewer, SSE live stream | M1 | DONE |
| M4 | Integration, E2E Verification & Live Assessment | Dual-track E2E verification test suite, 10/10 automated tests passing, real baseline scan execution on `https://empire.edu.vn/` | M1, M2, M3 | DONE |
| M5 | UI Foundation, Primitives, Responsive Shell & Chart Engine | Create `components/ui/` primitives, zero-dependency interactive SVG chart library (`components/charts/`), `.eslintrc.json`, and responsive `Shell.tsx` | M4 | DONE |
| M6 | SaaS Command Center Views Overhaul | Overhaul `/dashboard`, `/findings`, `/remediation`, `/assets`, `/scans`, and `/active-assessments` with real interactive components, sorting, filtering, modals, and SSE telemetry. Achieved unanimous approval across 2 Reviewers, 2 Challengers, and Forensic Auditor (CLEAN). | M5 | DONE |
| M7 | Dual-Track E2E Test Suite, Full Regression & Quality Verification | Publish `TEST_INFRA.md` & `TEST_READY.md`, execute `npm run build`, `npm run lint`, `pytest tests/`, and `python scripts/verify_empire_e2e.py` (182 pytest items passing, 10/10 E2E checks passing, 0 lint/typecheck errors, 18/18 static pages). | M6 | DONE |
| M8 | Batch Scan & Resource Optimization | `ScanBatch` model, WAL mode, batch scan API, `psutil` CPU/RAM throttling, worker tracking telemetry | M7 | DONE |
| M9 | Liquid Glass UI, Brand Logo & HUD | Brand logo in `Shell.tsx`, toast notification system, "Scan All" Hero Card, worker matrix ("trackcurrent") HUD | M8 | DONE |
| M10 | Dual-Track Acceptance & Final Sign-Off | Backend pytest (244/244), live E2E (10/10), Next.js build (18/18), ESLint (0 errors/warnings) | M8, M9 | DONE |

## Interface Contracts
### UI Primitives & Charting Components (M5 ↔ M6)
- `Card`, `CardHeader`, `CardTitle`, `CardDescription`, `CardContent`, `CardFooter`, `StatCard` (`src/components/ui/`)
- `Button` (`src/components/ui/button.tsx`) supporting variants (`primary`, `secondary`, `destructive`, `outline`, `ghost`, `glass`) and sizes (`sm`, `md`, `lg`, `icon`).
- `Badge` (`src/components/ui/badge.tsx`) supporting severity colors (`critical`, `high`, `medium`, `low`, `info`, `status`, `neutral`).
- `Table`, `TableHeader`, `TableBody`, `TableRow`, `TableHead`, `TableCell` (`src/components/ui/table.tsx`).
- `Modal` / `Dialog` (`src/components/ui/modal.tsx`) with backdrop blur, keyboard escape, and body scroll lock.
- `InteractiveAreaChart`, `InteractiveBarChart`, `InteractiveDonutChart`, `InteractiveGaugeChart` (`src/components/charts/`) accepting structured datasets with tooltip callbacks and dimension props.

### Target Management ↔ Frontend (M6 ↔ Backend)
- `POST /api/v1/assets`: Ingest target, returns `AssetRead`.
- `POST /api/v1/assets/bulk-preview`: Previews incoming targets, detects duplicates, returns `{ "total": int, "new": [...], "duplicate": [...] }`.
- `POST /api/v1/assets/{id}/verify`: Executes the 8-step live probe pipeline, returns `{ "status": "VERIFIED" | "FAILED", "steps": [ { "step": int, "name": str, "status": "PASS" | "FAIL", "detail": str, "metadata": dict } ], "fingerprint": dict }`.

### Scanner Engine & Live Telemetry ↔ Frontend (M6 ↔ Backend)
- `POST /api/v1/scans`: Creates scan in `QUEUED` state with profile payload `{ "asset_id": int, "profile": str, "engine_preferences": list, "description": str }`.
- `GET /api/v1/scans/{id}/logs/stream`: SSE `text/event-stream` yielding JSON log chunks `{ "id": int, "scan_id": int, "timestamp": str, "level": str, "message": str, "source": str }`.
- `POST /api/v1/scans/{id}/cancel`: Cooperatively aborts scan execution.

### Vulnerability Management ↔ Frontend (M6 ↔ Backend)
- `GET /api/v1/findings`: Query parameters for pagination and filtering (`severity`, `status`, `module`, `asset_id`, `search`).
- `POST /api/v1/findings/{id}/triage`: Updates finding state (`status`, `triage_note`, `assignee`).
- `POST /api/v1/findings/{id}/retest`: Dispatches immediate HTTP probe to re-verify finding remediation.

### Analytics Telemetry ↔ Frontend (M6 ↔ Backend)
- `GET /api/v1/metrics/overview`: Returns 10 core KPIs.
- `GET /api/v1/metrics/charts/*`: 8 dedicated endpoints providing structured telemetry for severity distribution, vulnerability trends, module risk, assessment coverage, risk trajectory, scanner performance, intelligence feeds, and remediation progress.

## Code Layout
- `backend/app/api/`: FastAPI REST routers (`assets.py`, `scans.py`, `findings.py`, `metrics.py`, `empire_modules.py`, etc.).
- `backend/app/core/`: Configuration, database session, SSRF gatekeeper, `empire_seeder.py`, process dispatcher, `target_verifier.py`.
- `backend/app/models/`: SQLAlchemy 2.0 ORM models (`asset.py`, `scan.py`, `finding.py`, `base.py`).
- `backend/app/schemas/`: Pydantic V2 schemas (`asset.py`, `scan.py`, `finding.py`, `common.py`).
- `backend/app/scanners/`: Real scanner adapters (`nuclei.py`, `zap.py`, `empire_engine.py`, `crawler.py`).
- `frontend/src/app/`: Next.js 14 App Router views (`dashboard`, `assets`, `scans`, `active-assessments`, `findings`, `remediation`, etc.).
- `frontend/src/components/ui/`: Reusable UI primitives (Card, Button, Badge, Table, Modal, Tooltip, Input, Tabs, StatCard).
- `frontend/src/components/charts/`: Reusable interactive SVG chart components (AreaChart, BarChart, DonutChart, GaugeChart).
- `frontend/src/components/`: Layout (`Shell.tsx`), cards, tables, evidence viewer, verification modal.
- `frontend/src/lib/`: Utilities, API client (`api.ts`), `i18n.tsx` (Vietnamese default + English dictionary).
- `frontend/src/styles/`: `globals.css` with Black/White/Liquid Glass design tokens.
- `frontend/.eslintrc.json`: ESLint configuration extending `next/core-web-vitals`.
- `scripts/`: Verification scripts (`verify_empire_e2e.py`).
- `tests/`: Pytest automated test suites.
