## 2026-11-08T16:07:17Z
You are Explorer 3 for Milestone 6: Target Management & Live Scanning Interface.

MANDATORY FIRST STEP:
Read C:\Users\nguye\desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read C:\Users\nguye\desktop\noospire\PROJECT.md.

Working directory: C:\Users\nguye\desktop\noospire
Your state folder: C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m6_3\

MISSION & SCOPE:
Design the complete technical specification and implementation blueprint for overhauling `frontend/src/app/assets/page.tsx`, `frontend/src/app/scans/page.tsx`, and `frontend/src/app/active-assessments/page.tsx`:
1. Target Management (`/assets`):
   - Sortable & filterable assets table: Target Name, Type (URL, Domain, IP, CIDR), Verification Status (`VERIFIED`, `PENDING`, `FAILED`), Risk Level, Open Findings count badge (clickable link to `/findings?asset_id=X`), Last Assessed timestamp.
   - Target Detail Profile Drawer: Slide-over drawer when clicking a target row showing: Target Overview, Verified DNS & TLS records, Discovered Endpoints list, Scan History on this target, and Vulnerabilities breakdown.
   - Add Single Target modal: Input for Target URL, name, environment, policy, wired to `POST /api/v1/assets`.
   - Bulk Import modal: Ingest OpenAPI, CSV, JSON, TXT, CIDR with duplicate preview wired to `POST /api/v1/assets/bulk-preview` before persistence.
   - 8-Step Live Target Verification Pipeline modal: Interactive probe modal wired to `POST /api/v1/assets/{id}/verify` showing real-time 8 steps progression (Input validation, DNS resolution, TLS verification, HTTP connectivity, Redirect inspection, Web discovery, Target fingerprint, Verification result) with JSON fingerprint viewer.
2. Scan Dispatch Center (`/scans`):
   - 7 Scan Profile Cards (Baseline Discovery, Deep Active Assessment, Empire Business Logic, OWASP Top 10, Network & Port Audit, Stealth Passive Recon, Continuous Compliance) with description, engine icons, and risk rating.
   - Target selector dropdown (wired to `GET /api/v1/assets`), Engine preference toggles (Nuclei, ZAP, Empire Engine), custom description, and dispatch button calling `POST /api/v1/scans`.
3. Live Scan Tracker & Telemetry (`/active-assessments`):
   - Active scans list with live progress indicators.
   - 5-Stage visual pipeline stepper: 1. Pre-flight Checks -> 2. Asset Discovery -> 3. Active Scanning -> 4. Empire Module Audit -> 5. Deduplication & Score Calculation.
   - Real-time Scanning Telemetry HUD: Active requests/sec counter, elapsed timer, live findings discovered count, current target URL.
   - Real-time SSE Telemetry Terminal: EventSource connection to `GET /api/v1/scans/{id}/logs/stream` with auto-scroll toggle, log level filter (ALL, INFO, WARN, ERROR, VULN), search box, clear terminal, and export logs button.
   - Cooperative Scan Cancel button calling `POST /api/v1/scans/{id}/cancel`.
4. Provide full drop-in TypeScript implementation blueprint.

CONSTRAINTS:
- You are read-only. Do NOT write or modify application code.
- Write your comprehensive plan to `C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m6_3\plan_targets_scans.md`.
- Write your final handoff to `C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m6_3\handoff.md`.
- Update `progress.md` in your state folder with timestamps for heartbeat.
- Send a message to parent when completed.
