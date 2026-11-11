# Scope: Milestone M10 Dual-Track Regression & Final Acceptance Verification

## Architecture
NOOSFORGE Security Intelligence is a production-grade enterprise cybersecurity SaaS platform and command center designed for the Empire Education Platform (`https://empire.edu.vn/`).
The platform features:
- **Backend Core**: FastAPI (Python 3.12/3.14) with asynchronous SQLAlchemy 2.0 ORM (`aiosqlite`) backed by `noospire.db`. Real-time scanner runner with SSRF prevention gatekeeper, 8-step target verification, bounded BFS crawler, SQLite WAL mode, and batch scan orchestration (`ScanBatch`) with `psutil` CPU/RAM throttling.
- **Frontend Command Center**: Next.js 14 App Router, TypeScript, Tailwind CSS, Black/White Modern Liquid Glass design language, official brand logo integration, 18 compiled routes, 14 operational views, live worker thread matrix HUD ("trackcurrent"), SSE log stream, and interactive forensic evidence modal.
- **Verification Harness**: Full backend pytest test suite (244 items across 14 modules), live E2E capability script (`python scripts/verify_empire_e2e.py`), Next.js static production build (`npm run build`), and ESLint static check (`npm run lint`).

## Feature Inventory
| # | Feature | Description | Milestone | Status |
|---|---------|-------------|-----------|:------:|
| 1-7 | Platform Core & Scanner Engine | Targets, 8-step verification, bulk ingestion, quality states, process runner, raw evidence, findings taxonomy | M1, M2 | DONE |
| 8-16 | UI Foundation & Design System | 14 views in Shell, Liquid Glass design, VI/EN i18n, evidence viewer, primitives, responsive shell, charts, ESLint | M3, M5 | DONE |
| 17-23 | SaaS Command Center & Analytics | Dashboard KPIs, findings table, forensic drilldown, target profile, live scanner HUD, M7 E2E suite | M6, M7 | DONE |
| 24 | Batch Domain Model & Migration | `ScanBatch` model (`scan_batches` table), SQLite WAL mode, foreign keys, busy timeout | M8 | DONE |
| 25 | Batch Orchestration & Resource Throttling | `POST /api/v1/scans/batch`, `psutil` CPU/RAM throttling, concurrency bounds (1-4), cooperative cancel & emergency stop | M8 | DONE |
| 26 | Live Telemetry & "trackcurrent" Feed | `GET /api/v1/scans/trackcurrent`, active worker thread matrix, lifecycle alerts in `security_alerts` | M8 | DONE |
| 27 | Brand Asset & Liquid Glass Shell Header | Official brand logo integration in `Shell.tsx` across desktop, tablet, and mobile | M9 | DONE |
| 28 | Liquid Glass Toast Notification System | `toast.tsx` (`ToastProvider`, `useToast()`) with backdrop-blur, specular highlight, auto-dismiss | M9 | DONE |
| 29 | "Scan All" Batch Dispatch UI Hero Card | In `/scans`, Hero Card & Modal for "Scan All" across all targets/engines/profiles with concurrency slider | M9 | DONE |
| 30 | Multi-Worker Thread Tracking ("trackcurrent") HUD | In `/active-assessments`, active worker matrix, focus switcher, batch progress bar, cooperative cancel | M9 | DONE |
| 31 | Dual-Track Test Suite & Full Regression Pass | Automated tests `tests/test_scan_all_batch_orchestration.py` (BAT-01..BAT-13), `pytest`, `verify_empire_e2e.py`, `npm run build`, `npm run lint` | M10 | DONE |

## Milestones Summary
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|:------:|
| M1 | Platform Core | Target management, root asset seeding, 8-step verification, bulk import preview | none | DONE |
| M2 | Scanning & Intelligence | Quality state machine, process safety, crawler, evidence logging, finding taxonomy | M1 | DONE |
| M3 | UI & Product Experience | 14 views in Shell, Liquid Glass styling, i18n, evidence modal, SSE live stream | M1 | DONE |
| M4 | Integration & Live Baseline | Dual-track E2E verification (10/10 tests), live baseline on `https://empire.edu.vn/` | M1-M3 | DONE |
| M5 | UI Foundation & Chart Engine | UI primitives, SVG chart library, ESLint, responsive Shell | M4 | DONE |
| M6 | SaaS Command Center Overhaul | Overhaul dashboard, findings, assets, scans, active assessments | M5 | DONE |
| M7 | Dual-Track E2E Test Suite | Test infrastructure (`TEST_INFRA.md`, `TEST_READY.md`), full test suite pass | M6 | DONE |
| M8 | Batch Scan & Resource Optimization | `ScanBatch` model, WAL, batch scan API, `psutil` CPU/RAM throttling, telemetry | M7 | DONE |
| M9 | Liquid Glass UI, Brand Logo & HUD | Brand logo in `Shell.tsx`, toast system, "Scan All" Hero Card, worker matrix HUD | M8 | DONE |
| M10 | Dual-Track Acceptance & Final Sign-Off | Backend pytest (244/244), live E2E (10/10), Next.js build (18/18), ESLint (0 errors/warnings) | M8, M9 | IN_PROGRESS |
