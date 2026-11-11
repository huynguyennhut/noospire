## 2026-11-08T16:17:07Z
You are the Worker implementing Milestone 6: SaaS Command Center Views Overhaul.

MANDATORY FIRST STEP:
Read C:\Users\nguye\desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read C:\Users\nguye\desktop\noospire\PROJECT.md.

Read the technical specifications and drop-in blueprints produced by the M6 Explorers:
- C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m6_1\plan_dashboard.md
- C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m6_2\plan_vulnerabilities.md
- C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m6_3\plan_targets_scans.md

Working directory: C:\Users\nguye\desktop\noospire
Your state folder: C:\Users\nguye\desktop\noospire\.agents\teamwork\worker_m6_1\

FILES YOU OWN EXCLUSIVELY:
- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/app/findings/page.tsx`
- `frontend/src/app/remediation/page.tsx`
- `frontend/src/components/evidence/EvidenceViewer.tsx` (and `frontend/src/components/EvidenceViewer.tsx`)
- `frontend/src/app/assets/page.tsx`
- `frontend/src/app/scans/page.tsx`
- `frontend/src/app/active-assessments/page.tsx`
- `frontend/src/lib/i18n.tsx`

IMPLEMENTATION TASKS:
1. Security Analytics Dashboard Overhaul (`frontend/src/app/dashboard/page.tsx`):
   - Overhaul using the UI primitives (`StatCard`, `Card`, `Badge`, `Button`, `Tabs`) and SVG charts (`InteractiveAreaChart`, `InteractiveBarChart`, `InteractiveDonutChart`, `InteractiveGaugeChart`).
   - 10 KPI summary cards with trend indicators wired to `GET /api/v1/metrics/overview`.
   - Sentinel Risk Score (SRS) hero banner with posture badge.
   - 8 interactive charts with tooltips, legends, and 7D / 14D / 30D time-range filter toggles.
   - Concurrent refresh button and quick navigation to `/scans`.
2. Vulnerability Views & Forensic Drill-Down (`frontend/src/app/findings/page.tsx`, `frontend/src/app/remediation/page.tsx`, `EvidenceViewer.tsx`):
   - Multi-column sortable findings table (Severity, Title, Target, Date) with clear sort indicators.
   - Multi-filter bar (Severity, Module, Status, full-text Search with clear button).
   - Bulk triage checkbox selection with floating action bar (Change status, assign, mark false positive) wired to `POST /api/v1/findings/{id}/triage`.
   - CSV and JSON export buttons.
   - 5-tab forensic evidence viewer modal (Proof Summary, Raw HTTP Request, Raw HTTP Response, Response Headers, Reproducible cURL Command).
   - Live Retest button on finding rows and in evidence viewer calling `POST /api/v1/findings/{id}/retest` with live status update.
   - 5-column Kanban remediation board (`/remediation`) with automated SLA countdowns and quick move actions.
3. Target Management & Live Verification (`frontend/src/app/assets/page.tsx`):
   - Sortable & filterable assets table with status badges and findings count drill-down links.
   - Slide-over Target Detail Profile Drawer with 5 tabs (Overview, DNS & TLS, Endpoints list, Scan history, Vulnerabilities).
   - Add Single Target modal wired to `POST /api/v1/assets`.
   - Bulk Import modal with 2-stage workflow (ingest -> duplicate preview via `POST /api/v1/assets/bulk-preview` -> commit).
   - 8-Step Live Target Verification Pipeline modal wired to `POST /api/v1/assets/{id}/verify` with real-time step status and JSON fingerprint inspector.
4. Scan Dispatch & Live Telemetry (`frontend/src/app/scans/page.tsx` and `frontend/src/app/active-assessments/page.tsx`):
   - Scan Dispatcher (`/scans`): 7 Scan Profile Cards, target selector, engine preferences (Nuclei, ZAP, Empire Engine), description, and dispatch handler calling `POST /api/v1/scans`.
   - Live Scan Tracker (`/active-assessments`): Active scans list, 5-stage visual pipeline stepper, real-time scanning HUD (req/s, elapsed timer, live findings count), and full SSE terminal with live log stream from `GET /api/v1/scans/{id}/logs/stream`, log level filtering, search, and export logs button.
   - Scan Cancel button calling `POST /api/v1/scans/{id}/cancel`.
5. Bilingual Support (`frontend/src/lib/i18n.tsx`):
   - Ensure all new labels, tab titles, headers, and tooltips are translated in both Vietnamese (default) and English.
6. Verification:
   - Run `npm run lint` in `frontend/` — verify 0 errors.
   - Run `npm run build` in `frontend/` — verify all static routes compile cleanly with 0 TypeScript errors.
   - Run `pytest tests/` and `python scripts/verify_empire_e2e.py` — verify 100% pass without regression.
