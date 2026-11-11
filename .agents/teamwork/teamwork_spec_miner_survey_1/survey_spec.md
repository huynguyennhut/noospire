# Enterprise Cybersecurity SaaS Dashboard — Specification & Verification Survey Report

**Document Version**: 1.0.0  
**Author**: Specification Investigator (`teamwork_spec_miner_survey_1`)  
**Workspace**: `C:\Users\nguye\desktop\noospire`  
**Date**: 2026-11-08  

---

## 1. Executive Summary & Specification Scope

This specification survey document provides the authoritative breakdown of requirements, component hierarchies, state flows, error handling, edge cases, and verification criteria for the **Enterprise Cybersecurity SaaS Dashboard** (NOOSFORGE Security Intelligence Platform) for the Empire Education Platform (`https://empire.edu.vn/`).

The project mandate establishes two core requirements:
1. **Requirement R1 (Enterprise Cybersecurity SaaS Dashboard UI)**: Overhaul and enhance frontend views to provide a production-grade, dark UI dashboard responsive across mobile, tablet, and desktop viewports. The UI must integrate real interactive charts for security analytics, sortable and filterable vulnerability management tables with detailed forensic evidence drill-downs, a target management interface wired to backend endpoints, and a live scanning interface with real-time SSE telemetry—strictly built with real functional components, active state management, and no static placeholder mockups.
2. **Requirement R2 (Existing Project and Backend Preservation)**: Fully preserve all existing FastAPI backend routes, SQLAlchemy 2.0 ORM models, Pydantic V2 schemas, SSRF gatekeepers, and scanning engines without regressions. Existing automated test suites (`pytest` with 164 tests and `scripts/verify_empire_e2e.py` with 10 checks) must continue to pass cleanly with 100% pass rates. Frontend build (`npm run build`) and linting (`npm run lint`) must execute cleanly.

---

## 2. Deconstruction of Requirement R1: Enterprise Cybersecurity SaaS Dashboard UI

### 2.1. Professional Dark UI & Black/White/Liquid Glass Design System

#### 2.1.1 Design System Tokens & Styling (`globals.css`)
- **Base Color Palette**:
  - Primary Background: `--bg-primary: #070B14` (Deep obsidian)
  - Surface Background: `--bg-surface: #0E1526` (Liquid glass base)
  - Surface Hover: `--bg-surface-hover: #162038`
  - Subtle Borders: `--border-subtle: #1F2E4D`
  - Strong Borders: `--border-strong: #2D426B`
  - Text Tokens: Primary `#F1F5F9`, Secondary `#94A3B8`, Muted `#64748B`
  - Severity Accent Tokens:
    - Critical: `#EF4444` (`bg-rose-500`, `text-rose-400`, `border-rose-800`)
    - High: `#F97316` (`bg-orange-500`, `text-orange-400`, `border-orange-800`)
    - Medium: `#F59E0B` (`bg-amber-500`, `text-amber-400`, `border-amber-800`)
    - Low: `#10B981` (`bg-emerald-500`, `text-emerald-400`, `border-emerald-800`)
    - Info: `#06B6D4` (`bg-cyan-500`, `text-cyan-400`, `border-cyan-800`)
- **Liquid Glass Elevation Classes**:
  - `.liquid-glass`: Linear gradient `rgba(255, 255, 255, 0.04)` to `0.01` over `rgba(14, 21, 38, 0.7)` with `backdrop-filter: blur(16px)` and specular box-shadow `inset 0 1px 0 0 rgba(255, 255, 255, 0.15)`.
  - `.liquid-glass-card`: Card backdrop blur (16px), subtle border `rgba(255, 255, 255, 0.08)`, smooth hover transition with `translateY(-1px)` and cyan glow elevation.
  - `.liquid-glass-modal`: Opaque blur (24px) background `rgba(20, 29, 51, 0.95)` to `rgba(10, 15, 29, 0.95)`, specular border, elevation shadow `0 24px 64px 0 rgba(0, 0, 0, 0.7)`.
  - `.specular-highlight`: Header specular border with top 1px gradient mask.
  - Tactical Scrollbars: 6px width/height, styled with thumb `#1F2E4D` and track `#070B14`.

#### 2.1.2 Responsive Layout & Viewports (`Shell.tsx`)
- **Desktop (>= 768px)**: Fixed/sticky vertical sidebar `w-64 bg-cyber-900/80 backdrop-blur-xl border-r border-white/10` with brand header, bilingual toggle pill, notification bell with unread badge counter, target environment badge (`Empire Education`), and 14 operational navigation links.
- **Tablet & Mobile (< 768px)**: Sticky top header bar `bg-cyber-900/90 backdrop-blur-md border-b border-white/10` containing brand logo, inline language toggle button (`VI / EN`), and collapsible hamburger menu button (`Menu` / `X`).
- **Main Viewport Area**: Fluid scrollable container `flex-1 overflow-y-auto min-h-screen bg-cyber-950 p-4 md:p-6 lg:p-8`.

#### 2.1.3 Bilingual Internationalization Engine (`i18n.tsx`)
- **Default Locale**: Vietnamese (`vi`) as default on initial load; English (`en`) selectable.
- **Persistence**: Locale selection persisted across page refreshes via `localStorage.getItem('sentinel_locale')` and synchronized to `document.documentElement.lang`.
- **Dictionary Completeness**: Full bidirectional dictionary for brand, common actions, severities, risk postures, and all 14 operational views with automatic fallback chains (`locale dict -> English dict -> fallback parameter -> key`).

---

### 2.2. Security Analytics Dashboard (`/dashboard`)

#### 2.2.1 Header & Operational State
- Context Header: "EMPIRE SECURITY INTELLIGENCE", Live SOC badge, subtitle.
- Quick Actions:
  - "Sync Data" (`RefreshCw`): Triggers concurrent `Promise.all` refresh across all 9 metric APIs with rotating loading state.
  - "Launch Assessment" (`Crosshair`): One-click navigation link to `/scans` scan dispatcher.

#### 2.2.2 10 Core Summary KPI Metric Cards
Backed by database query `GET /api/v1/metrics/overview`:
1. **Total Managed Targets** (`metrics.total_assets`): Total assets registered in inventory.
2. **Targets Assessed Today** (`metrics.targets_assessed_today`): Verified target count assessed within last 24h, showing daily coverage percentage.
3. **Active Assessments** (`metrics.active_assessments`): Running/queued scanner tasks with animated pulsing radio icon.
4. **Failed Assessments** (`metrics.failed_assessments`): Errors or broken targets with degradation indicator.
5. **Critical Findings** (`metrics.critical_findings`): Unremediated severity `CRITICAL` count with rose alert styling.
6. **High Findings** (`metrics.high_findings`): Unremediated severity `HIGH` count with amber alert styling.
7. **Total Open Findings** (`metrics.total_open_findings`): Aggregate unresolved vulnerability backlog.
8. **Fixed Findings** (`metrics.fixed_findings`): Verified remediated vulnerability count.
9. **Indexed CVEs** (`metrics.newly_discovered_cves`): Correlated CVEs from NVD/OSV threat feeds.
10. **CISA KEV Actives** (`metrics.relevant_kev_count`): Confirmed vulnerabilities present on CISA Known Exploited Vulnerabilities catalog.

#### 2.2.3 8 Interactive Data-Backed Metric Charts
All charts bind to live backend endpoints in `backend/app/api/metrics.py`:
1. **Chart 1 — Findings by Severity Tier** (`GET /api/v1/metrics/severity-distribution`):
   - Horizontal comparative progress bars for CRITICAL, HIGH, MEDIUM, LOW, INFO.
   - Dynamic width calculated relative to highest tier count (`Math.round((count / maxVal) * 100)`).
2. **Chart 2 — Vulnerability Lifecycle Trend (14 Days)** (`GET /api/v1/metrics/charts/vulnerability-trend?days=14`):
   - 14-day chronological column chart comparing Newly Detected findings vs Remediated findings.
   - Interactive bar heights with tooltip data and rotated date labels.
3. **Chart 3 — Security Risk by Empire Business Module** (`GET /api/v1/metrics/charts/module-risk`):
   - Domain-level risk metrics across Student Management, Learning Materials, Supporting Tools, API Services, Web App, Server Infrastructure.
   - Displays Critical count, High count, Total findings, and calculated Sentinel Risk Score ($SRS$).
4. **Chart 4 — Target Assessment Coverage** (`GET /api/v1/metrics/charts/coverage`):
   - Radial circular progress indicator rendering `coverage_percentage`.
   - Grid breakdown: Total targets, assessed today, and pending pipeline queue.
5. **Chart 5 — Risk Score Evolution ($SRS$)** (`GET /api/v1/metrics/charts/risk-trend?days=14`):
   - 14-day trajectory tracking overall calculated organizational security risk score.
6. **Chart 6 — Scanner Engine Performance & Completion Rate** (`GET /api/v1/metrics/charts/scanner-performance`):
   - Engine-by-engine breakdown (Nuclei, OWASP ZAP, Empire Custom Engine, Aqua Trivy).
   - Execution duration (seconds), total runs, and completion/success rate percentage badge.
7. **Chart 7 — Threat Intelligence Sync & Feed Ingestion** (`GET /api/v1/metrics/charts/intelligence-activity`):
   - 4-card matrix: Indexed CVEs, Active CISA KEV entries, high EPSS exploitable CVEs, and active YAML detection rules.
8. **Chart 8 — Finding Remediation Lifecycle Breakdown** (`GET /api/v1/metrics/charts/remediation-progress`):
   - State-by-state counter: OPEN, IN_REMEDIATION, FIXED, REOPENED, ACCEPTED_RISK.

---

### 2.3. Vulnerability Management Views (`/findings` & `/remediation`)

#### 2.3.1 Filterable & Sortable Findings Table (`/findings`)
- **Query & Parameter Support**:
  - Search term (`searchTerm`): Live debounced text filter matching Title, Description, Location URL, CVE ID, and Scanner Rule ID.
  - Severity dropdown filter: ALL, CRITICAL, HIGH, MEDIUM, LOW, INFO.
  - Empire Module dropdown filter: ALL, STUDENT_MANAGEMENT, LEARNING_MATERIALS, SUPPORTING_TOOLS, API_SERVICES, WEB_APPLICATION, SERVER_INFRASTRUCTURE.
  - Lifecycle State dropdown filter: ALL, OPEN, IN_REMEDIATION, FIXED, REOPENED, ACCEPTED_RISK, FALSE_POSITIVE.
  - URL query parameter auto-binding: Accepts `?module=...` and `?assetId=...` for seamless drill-down from Target or Module Hub pages.
- **Table Data Grid**:
  - Severity tier badge (custom color-coded border & background).
  - Finding Title with Scanner Rule ID and CVE chip.
  - Empire operational module tag.
  - Target location path (truncated font-mono with tooltip).
  - Lifecycle state badge (e.g. `FIXED`, `REOPENED` with pulsing alert, `IN_REMEDIATION`).

#### 2.3.2 Forensic Detail Drawer & Interactive Evidence Viewer (`EvidenceViewer.tsx`)
When a finding row is clicked, an expandable right drawer displays:
- Finding title, severity tier, scanner rule ID, CVE ID.
- Target scope, component name, Empire business module.
- Exposure Classification chip (`PUBLIC_BY_DESIGN` for approved media, or `STANDARD_RESTRICTED`).
- Plain-English vulnerability description and actionable remediation advice.
- **5-Tabbed Forensic Evidence Viewer**:
  1. **Tab 1: Proof / Matched Content**: Raw matched strings, regex captures, or payload proof validating exploitability without mock data.
  2. **Tab 2: Request**: Verbatim HTTP request line, headers, and request body.
  3. **Tab 3: Response**: Verbatim HTTP response status, headers, and response payload.
  4. **Tab 4: Headers**: Structured key-value table of target HTTP response headers.
  5. **Tab 5: Replay cURL**: Complete, runnable `curl -k -i -s -X ...` command allowing instant manual verification.
  - One-click "Copy" button with visual feedback indicator ("Copied!").
- **Live Retest Engine & Triage Controls**:
  - Lifecycle selector (`triageStatus`): Updates status via `POST /api/v1/findings/{id}/triage`.
  - Assignee input (`triageAssignee`): Assigns responsible engineer email.
  - Remediation comment input (`triageComment`).
  - "Retest Target Live" action button: Dispatches probe via `POST /api/v1/findings/{id}/retest` and renders authentic verdict (`VERIFIED_FIXED` or `STILL_VULNERABLE`).

#### 2.3.3 Kanban Remediation Tracking Board (`/remediation`)
- 5 Lifecycle Columns: Open & Unassigned, In Remediation, Fixed & Verified, Reopened Regressions, Accepted Baseline Risk.
- Cards render severity badges, finding title, target URL, assignee, and Empire module.
- Click-to-transition modal dialog for reassigning engineers, updating notes, and transitioning states.

---

### 2.4. Target Management Interface (`/assets`)

#### 2.4.1 Inventory View & Filtering
- Displays all managed Empire assets wired to `GET /api/v1/assets`.
- Search across Target Name, URL locator, and technology stack.
- Filtering by Empire Business Module and Environment (PRODUCTION, STAGING, DEV).
- Action buttons per row: "8-Step Verify", "Scan Now", "Findings", "Delete Target".

#### 2.4.2 Target Registration Modal
- Direct single target registration via `POST /api/v1/assets`.
- Required inputs: Target Name, Target URL Locator (`https://...`), Empire Module selection, Environment selection, Technology profile, Criticality Tier (LOW, MEDIUM, HIGH, CRITICAL).
- Checkbox toggle: "Activate Approved Public Media Policy (`/media` PUBLIC_BY_DESIGN)".

#### 2.4.3 Bulk Target Ingestion & Deduplication Modal
- Form accepting raw multiline text: domains, full URLs, line-delimited lists, CSV, JSON arrays, or OpenAPI definitions.
- Wired to `POST /api/v1/assets/bulk-import`.
- Displays real-time import summary: `imported_count` vs `skipped_duplicates`.

#### 2.4.4 8-Step Live Target Verification Pipeline Modal (`TargetVerificationModal.tsx`)
Executes an authentic 8-step target verification pipeline against target endpoints:
1. **Step 1: Input Validation & URL Normalization**: Scheme parsing, port extraction, canonical path normalization.
2. **Step 2: DNS Resolution (A/AAAA/CNAME)**: Query IPv4/IPv6 records, nameservers, and TTL.
3. **Step 3: TLS/SSL Certificate Verification**: X.509 certificate chain, SAN matching, cipher suites, expiration days.
4. **Step 4: HTTP Connectivity & Status Code**: Bounded HTTP probe measuring latency (ms) and status code (200 OK).
5. **Step 5: Redirect Inspection & Loop Detection**: Traces HTTP 301/302 hops and verifies canonical endpoint safety.
6. **Step 6: Web Discovery & Content Inspection**: Checks `/robots.txt`, `/sitemap.xml`, and security response headers (HSTS, CSP, X-Frame-Options).
7. **Step 7: Technology Stack Fingerprint**: Detects web server (nginx, Cloudflare), framework, WAF (Cloudflare Turnstile), and media baseline.
8. **Step 8: Policy Verification & Scope Authorization**: Authorizes persistent management policy without repeated manual authorization.
- UI Features: Sequential animated execution, latency measurements per step, expandable JSON forensic viewer per step, and final persistent verification via `POST /api/v1/assets/{id}/verify`.

---

### 2.5. Live Scanning Interface (`/scans` & `/active-assessments`)

#### 2.5.1 Scan Dispatch Center (`/scans`)
- **7 Pre-Configured Scan Profiles**:
  1. `QUICK`: Passive fingerprinting, HTTP headers check (< 30s).
  2. `DAILY_SECURITY`: Continuous daily evaluation, Better-Auth routes, /media policy, KEV correlation.
  3. `STANDARD`: Balanced OWASP Top 10, Nuclei + ZAP + Empire.
  4. `AUTHENTICATED`: Synthetic student credentials, BOLA/IDOR authorization validation.
  5. `API_ASSESSMENT`: OWASP API Security Top 10, JWT validation, rate limiting.
  6. `THOROUGH`: Multi-vector scan combining all available engines.
  7. `INFRASTRUCTURE`: Port checks, TLS ciphers, MinIO buckets, reverse proxy headers.
- **Engine Selection**: Consolidated Suite (`all`), Nuclei (`nuclei`), OWASP ZAP (`zap`), Aqua Trivy (`trivy`).
- **Target Selection**: Dropdown dynamically populated from active asset inventory.
- **Dispatch Action**: Submits `POST /api/v1/scans` and seamlessly routes user to `/active-assessments?scan_id={id}`.
- **Recent Jobs Table**: Displays target locator, engine, profile, progress percentage bar, status badge, and link to Live Logs.

#### 2.5.2 Live Assessment Tracker & Telemetry (`/active-assessments`)
- **Dual-Pane Layout**:
  - Left Column: Assessment Jobs Queue with clickable cards showing target, status, profile, and progress percentage bar.
  - Right Column: Live Telemetry & Log Terminal for the selected scan job.
- **Connection Mode Indicator**:
  - Live SSE Stream (`EventSource` to `/api/v1/scans/{id}/logs/stream`): Renders green pulsing `Wifi` icon.
  - Fallback Polling (`GET /api/v1/scans/{id}/logs` every 2.5s): Renders amber `WifiOff` icon if SSE fails or disconnects.
- **Live Terminal Window (`scanner_worker_output.log`)**:
  - Streams formatted log lines: Timestamp, Source engine (`[nuclei]`, `[zap]`, `[empire]`), Log level (`[INFO]`, `[WARNING]`, `[ERROR]`), and message.
  - Live log search box for filtering messages in real-time.
  - Log level filter dropdown: ALL, INFO, WARNING, ERROR.
  - Auto-scroll toggle with down arrow button.
- **Cooperative Cancellation**:
  - Red "Cancel Assessment" button (`StopCircle`) enabled when scan is RUNNING or INITIALIZING.
  - Invokes `POST /api/v1/scans/{id}/cancel` to safely terminate the subprocess without leaving orphan tasks.

---

### 2.6. Additional Integrated Views in Command Center (`Shell.tsx`)
1. **Empire Business Module Hub (`/empire-modules`)**: 6 operational cards with risk index, target counts, and direct links to filtered findings.
2. **Vulnerability & Threat Intelligence Center (`/threat-intel`)**: CISA KEV catalog table, instant CVE lookup tool, and manual sync action.
3. **Audit-Grade Report Generator (`/reports`)**: Generates vector PDF, interactive HTML, and raw JSON reports across 10 template types with direct download links.
4. **Daily Assessment Scheduler (`/schedules`)**: Manages recurring daily automated scans configured in `Asia/Ho_Chi_Minh` (02:00 AM ICT) with instant "Run Daily Pipeline Now" manual trigger.
5. **Detection Rule Manager (`/detection-rules`)**: Declarative YAML detection rule editor, schema validation engine, review lifecycle state machine (`draft -> in_review -> approved -> active`), and sandbox test runner.
6. **External Integrations & Adapters (`/integrations`)**: Status of scanner binary adapters (Nuclei CLI, ZAP, Trivy), threat feeds, and Telegram/Discord webhook dispatchers.
7. **System Health & Diagnostics (`/health`)**: Diagnostics matrix for FastAPI gateway, SQLAlchemy async persistence, async worker dispatcher pool (4 workers), and subsystem drivers.
8. **Security Settings & Policies (`/settings`)**: Configures Approved Public Media policy exceptions, persistent target policies, dedicated synthetic student identities, and two-tier SSRF CIDR boundaries.

---

## 3. Deconstruction of Requirement R2: Existing Project and Backend Preservation

### 3.1. API Route Contracts & Schemas Preservation
The existing FastAPI backend exposed at `/api/v1` must remain 100% stable without breaking changes to route paths, request payloads, or response schemas:
- **Assets API (`/api/v1/assets`)**:
  - `GET /api/v1/assets`: Returns `{ items: AssetRead[], total: int }`.
  - `POST /api/v1/assets`: Ingests `AssetCreate`, returns `AssetRead`.
  - `GET /api/v1/assets/{id}`: Returns single `AssetRead`.
  - `DELETE /api/v1/assets/{id}`: Deletes asset (status 204 or 200).
  - `POST /api/v1/assets/{id}/verify`: Runs live target verification, updates status.
  - `POST /api/v1/assets/bulk-import`: Parses raw CSV/JSON/multiline, returns `{ imported_count, skipped_duplicates, errors, imported_assets }`.
- **Scans API (`/api/v1/scans`)**:
  - `GET /api/v1/scans`: Returns list of scan jobs.
  - `POST /api/v1/scans`: Dispatches scan job, returns `ScanJobRead`.
  - `GET /api/v1/scans/{id}`: Returns scan job status and progress percentage.
  - `POST /api/v1/scans/{id}/cancel`: Sets cancelled state.
  - `GET /api/v1/scans/{id}/logs`: Returns JSON array of log chunks.
  - `GET /api/v1/scans/{id}/logs/stream`: SSE `text/event-stream` endpoint.
- **Findings API (`/api/v1/findings`)**:
  - `GET /api/v1/findings`: Query with filters (`asset_id`, `empire_module`, `severity`, `status_filter`).
  - `GET /api/v1/findings/{id}`: Returns normalized finding with full `evidence` dictionary.
  - `POST /api/v1/findings/{id}/triage`: Updates finding lifecycle status and assignee.
  - `POST /api/v1/findings/{id}/retest`: Executes live retest, returns `{ status, retest_status, message }`.
- **Metrics API (`/api/v1/metrics`)**:
  - `/overview`, `/severity-distribution`, `/charts/vulnerability-trend`, `/charts/module-risk`, `/charts/coverage`, `/charts/risk-trend`, `/charts/scanner-performance`, `/charts/intelligence-activity`, `/charts/remediation-progress`.
- **Empire Modules API (`/api/v1/empire-modules`)**: Returns 6 module summaries.
- **Baselines API (`/api/v1/baselines`)**: List and create `BaselineException` objects.
- **Schedules API (`/api/v1/schedules`)**: List, create, toggle, and trigger daily schedules.
- **Reports API (`/api/v1/reports`)**: List, generate, download (`/download?format=...`), delete.
- **Detection Rules API (`/api/v1/rules`)**: List, create, validate (`/validate`), lifecycle transition (`/lifecycle`), and test (`/test`).

### 3.2. Database Schema & Models Preservation (`backend/app/models/`)
No alterations or regressions to existing SQLAlchemy 2.0 ORM models:
- `Asset`: UUID primary key, name, asset_type, target_locator, empire_module, environment, technology, approved_media_baseline, assessment_policy, verification_status.
- `Scan`: UUID primary key, asset_id, engine, profile, status, progress_percentage, quality_status.
- `ScanLog`: UUID primary key, scan_id, timestamp, level, message, source.
- `NormalizedFinding`: UUID primary key, scan_id, asset_id, fingerprint (SHA-256), empire_module, exposure_classification, is_approved_baseline, scanner_engine, scanner_rule_id, title, description, severity, cve_id, cvss_score, evidence (JSON), status, assignee.
- `BaselineException`: Scope, classification, reason, owner, approved_by, is_active.
- `DailySchedule`: Name, profile, cron_expression, timezone, is_active, target_ids.
- `DetectionRule`: Name, version, author, severity, status, raw_yaml.

---

## 4. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | UI / Layout | Liquid Glass Command Center | Dark UI layout with specular highlight, frosted glass cards, and mobile sidebar drawer | Viewport width, route changes | Rendered responsive HTML layout | Responsive fallback to collapsible hamburger menu on `< 768px` | `Shell.tsx`, `globals.css` |
| 2 | UI / i18n | Bilingual Internationalization | Vietnamese (default) and English locale switching with localStorage persistence | Language toggle click (`vi` / `en`) | Translated UI labels across all 14 views | Automatic fallback to English, then default key if missing | `i18n.tsx`, `Shell.tsx` |
| 3 | Dashboard | 10 Summary KPI Cards | Live cards displaying total targets, assessed today, active/failed scans, findings by severity, CVEs, KEVs | Database query via `GET /api/v1/metrics/overview` | KPI metric count cards | Defaults to 0 if API unreachable | `dashboard/page.tsx`, `metrics.py` |
| 4 | Dashboard | 8 Data-Backed Charts | Visual metrics for severity tiers, 14-day trend, module risk, coverage gauge, risk score, scanner perf, threat activity, remediation | Database chart endpoints `/api/v1/metrics/charts/*` | Bar, column, radial gauge, and matrix visualizations | Empty dataset fallback containers | `dashboard/page.tsx`, `metrics.py` |
| 5 | Target Mgmt | Target Inventory Grid | Sortable and filterable table displaying targets, modules, tech stacks, and verification badges | `GET /api/v1/assets`, search term, module filter, env filter | Filtered asset table rows | Empty state message if no matching targets | `assets/page.tsx` |
| 6 | Target Mgmt | Single Target Registration | Modal form to register new target with module and environment assignment | Name, URL locator, module, environment, tech stack, media policy | Created `Asset` object in DB | Alert on network/validation error, form validation | `assets/page.tsx`, `assets.py` |
| 7 | Target Mgmt | Bulk Target Ingestion & Deduplication | Ingests multiline URLs, CSV, JSON arrays, or OpenAPI definitions with duplicate detection | Raw text content | Imported count vs skipped duplicates summary | Skips duplicates cleanly, displays errors | `assets/page.tsx`, `assets.py` |
| 8 | Target Mgmt | 8-Step Live Probe Modal | Multi-stage verification pipeline (DNS, TLS, HTTP, redirect, discovery, fingerprint, auth) | Target locator, verification trigger | Sequential step progression, latency (ms), forensic JSON metadata | Step error highlighting, fallback to persistent verified status | `TargetVerificationModal.tsx`, `target_verifier.py` |
| 9 | Findings | Forensic Findings Table | Multi-criteria search and filterable table (search, severity, module, lifecycle status) | Query parameters, search text, dropdown filters | Filtered findings list | Empty table message with reset option | `findings/page.tsx`, `findings.py` |
| 10 | Findings | Tabbed Evidence Viewer | Interactive viewer displaying Proof/Matched Content, Request, Response, Headers, and Replay cURL | Finding evidence dictionary | Formatted forensic text, syntax highlighted tables, copyable cURL | Graceful fallbacks for missing raw request/response | `EvidenceViewer.tsx`, `findings.py` |
| 11 | Findings | Live Triage & Retest Engine | Updates finding lifecycle status, assignee, and executes live target retest | Lifecycle status, assignee, notes, retest trigger | Updated status, verdict (`VERIFIED_FIXED` vs `STILL_VULNERABLE`) | Error alert on network failure | `findings/page.tsx`, `findings.py` |
| 12 | Remediation | Kanban Lifecycle Board | 5-column Kanban board (OPEN, IN REMEDIATION, FIXED, REOPENED, ACCEPTED RISK) | Finding items by lifecycle state | Visual status columns with card dragging/dialog transition | Empty column message | `remediation/page.tsx` |
| 13 | Scan Center | Scan Dispatcher & Profiles | Select from 7 tailored profiles (Quick, Daily, Standard, Authenticated, API, Thorough, Infra) | Selected asset ID, profile, scanner engine | Dispatched `ScanJob` record in DB, redirect to active monitor | Validation alert if target unselected | `scans/page.tsx`, `scans.py` |
| 14 | Scan Center | Live Telemetry & Log Stream | Real-time scan monitoring with SSE log stream, fallback polling, terminal search, and log levels | Scan ID, SSE stream `/api/v1/scans/{id}/logs/stream` | Streaming log lines with engine tags and color-coded levels | Automatic switch to 2.5s fallback polling if SSE disconnects | `active-assessments/page.tsx`, `scans.py` |
| 15 | Scan Center | Cooperative Cancellation | Cooperative stop signal to terminate running scanner processes safely | Cancel button click on active scan | Scan status set to `CANCELLED`, child processes killed | Graceful alert if cancellation fails | `active-assessments/page.tsx`, `scans.py` |
| 16 | Threat Intel | CISA KEV Catalog & CVE Tool | Live KEV catalog list, instant CVE query lookup tool, and manual sync action | CVE ID query, manual sync button | CVSS score, EPSS probability, ransomware campaign association | "CVE not found" error message | `threat-intel/page.tsx`, `intel.py` |
| 17 | Reports | Audit-Grade Report Generator | Compiles vector PDF, standalone HTML, and raw JSON reports across 10 template types | Title, template type, asset scope, format checkboxes | Generated file artifacts on disk with download links | Alert if no formats selected or compilation error | `reports/page.tsx`, `reports.py` |
| 18 | Schedules | Recurring Daily Scheduler | Automated scan pipeline scheduled at 02:00 AM ICT (`Asia/Ho_Chi_Minh`) with manual trigger | Cron expression, timezone, active toggle, manual trigger | Scheduled jobs, dispatched scans list on manual trigger | Alert if schedule creation or trigger fails | `schedules/page.tsx`, `schedules.py` |
| 19 | Detection Rules | YAML Rule Authoring & Sandbox | Declarative YAML detection editor with schema validation, lifecycle gating, and test fixture runner | Raw YAML rule content, lifecycle transitions | Validation verdict, rule records, sandbox execution results | Schema validation error list displayed in red box | `detection-rules/page.tsx`, `rules.py` |
| 20 | Integrations | Scanners & Webhook Dispatcher | Status of Nuclei, ZAP, Trivy, threat feeds, and test alert dispatcher for Telegram / Discord | Bot token, webhook URL, test dispatch button | Operational status badges, test alert payload sent | Alert confirmation or error | `integrations/page.tsx` |
| 21 | Health | System Diagnostics Matrix | Telemetry monitoring FastAPI gateway, SQLAlchemy async persistence, and worker dispatcher pool | `/health` endpoint query | Real-time health badges and diagnostics table | Displays error if gateway unreachable | `health/page.tsx` |
| 22 | Settings | Baseline Policies & SSRF | Configuration for Approved Public Media `/media` policy, persistent target rules, and SSRF CIDRs | Scope pattern, justification, CIDR list | Active baseline exceptions, updated SSRF rules | Alert on registration failure | `settings/page.tsx`, `baselines.py` |

---

## 5. Edge Cases & Observed Behaviors

| # | Feature | Input / Scenario | Observed / Expected Behavior |
|---|---------|------------------|------------------------------|
| 1 | Evidence Viewer | Finding has empty or malformed `evidence` dictionary | Viewer gracefully synthesizes fallback HTTP request and response based on `targetLocation` and `findingTitle`, preventing UI crashes. |
| 2 | Active Assessments | EventSource (SSE) connection drops or proxy blocks streaming | Tracker detects `es.onerror`, flips connection badge to "Fallback Polling" (`WifiOff`), and begins interval polling `/api/v1/scans/{id}/logs` every 2500ms without data loss. |
| 3 | Active Assessments | Scan log entries received from multiple sources with identical timestamps | Composite key `${log.timestamp}-${log.message}` prevents duplicate log entries in terminal state. |
| 4 | Target Verification | Verification runs on a domain that is currently offline or unresolvable | DNS/HTTP probe fails cleanly, records failure step in details, and does not block other target operations. |
| 5 | Bulk Target Import | Input contains duplicate URLs already registered in `noospire.db` | Backend deduplicator matches normalized canonical URLs, increments `skipped_duplicates`, imports only net-new targets, and displays summary. |
| 6 | Findings Filter | Module or severity filter returns zero matching findings | Renders informative empty state: "No targets matching current filter" / "No matching data found" without breaking layout. |
| 7 | Findings Retest | Retesting a finding that still reproduces on the live target | Endpoint returns status `CONFIRMED` and `retest_status: "STILL_VULNERABLE"`. Finding card updates to show red verdict badge. |
| 8 | Findings Retest | Retesting a finding that has been patched on the target | Endpoint returns status `FIXED` and `retest_status: "VERIFIED_FIXED"`. Finding card updates to show green verified badge. |
| 9 | Approved Media Policy | Anonymous access probe hits `https://mh.empire.edu.vn/media/*` | Route matches `BaselineException` scope; access is classified as `PUBLIC_BY_DESIGN` and suppressed from raising false-positive exposure findings. |
| 10 | SSRF Defense | Scanner target input points to internal IP `127.0.0.1` or `169.254.169.254` | SSRF gatekeeper intercepts request, validates against blocked CIDR lists, and rejects probe unless explicitly marked `allow_private_targets: True` in verified lab environment. |
| 11 | Internationalization | Browser locale is set to unsupported language (e.g. `fr` or `de`) | Context defaults to `vi` (Vietnamese default), falls back to English dictionary, and prevents missing text keys. |
| 12 | Frontend Linting | `npm run lint` executed in non-interactive environment without `.eslintrc.json` | Next.js prompts interactive setup wizard (`? How would you like to configure ESLint?`) and exits with code 1. A non-interactive `.eslintrc.json` (e.g. `{"extends": "next/core-web-vitals"}`) is required to pass cleanly. |
| 13 | Responsive Viewport | User opens dashboard on mobile screen (< 480px) | Sidebar collapses automatically into sticky top bar with hamburger menu; KPI cards adapt to `grid-cols-2`; tables scroll horizontally with smooth touch scrolling. |

---

## 6. Verification Commands & Pass/Fail Criteria Definitions

### 6.1. Backend Automated Test Suite (`pytest`)
- **Command**:
  ```powershell
  pytest
  ```
- **Execution Target**: `tests/` directory (includes 8 test suites: `test_challenger_live_empire.py`, `test_empirical_challenger.py`, `test_platform_core_m1.py`, `test_scan_intelligence_m2.py`, `test_tier1_feature_coverage.py`, `test_tier2_boundary_corner.py`, `test_tier3_cross_feature.py`, `test_tier4_real_world.py`).
- **Pass Definition**:
  - Exit code `0`.
  - All 164 tests report `PASSED`.
  - Zero test failures, zero test errors.

### 6.2. Empire End-to-End Vertical Slice Verifier (`verify_empire_e2e.py`)
- **Command**:
  ```powershell
  python scripts/verify_empire_e2e.py
  ```
- **Execution Target**: All 10 vertical subsystem capability tests:
  1. Database Initialization & Empire Seed Verification
  2. Dashboard Overview KPIs & Analytics Verification
  3. Empire Business Architecture Modules Verification
  4. Asset Inventory & Bulk Import Deduplication
  5. Approved Public Media Baseline Verification
  6. Scan Dispatch & Empire Assessment Engine Execution
  7. Vulnerability Triage Lifecycle & Live Retest Verification
  8. Multi-Format Report Generation (Zero Fabrication PDF/HTML/JSON)
  9. Daily Assessment Scheduler & Asia/Ho_Chi_Minh Pipeline Trigger
  10. Security Alerts & In-App Notification System
- **Pass Definition**:
  - Exit code `0`.
  - Output displays: `ALL 10 EMPIRE E2E CAPABILITY TESTS COMPLETED SUCCESSFULLY! XANH MƯỢT 100%`.
  - Zero step failures.

### 6.3. Frontend Build Verification (`npm run build`)
- **Command**:
  ```powershell
  npm --prefix frontend run build
  ```
- **Execution Target**: Next.js 14 App Router production compilation and typecheck.
- **Pass Definition**:
  - Exit code `0`.
  - Output displays `✓ Compiled successfully`, `Linting and checking validity of types ...`, and `✓ Generating static pages (18/18)`.
  - Zero TypeScript compiler errors.

### 6.4. Frontend Lint Verification (`npm run lint`)
- **Command**:
  ```powershell
  npm --prefix frontend run lint
  ```
- **Execution Target**: ESLint static code analysis across `frontend/src`.
- **Known Issue & Resolution Definition**:
  - *Current state*: Exits with code 1 because Next.js CLI encounters an interactive prompt asking how to configure ESLint due to missing `.eslintrc.json`.
  - *Pass Definition*: Once `.eslintrc.json` (containing `{"extends": "next/core-web-vitals"}`) is configured in `frontend/`, `npm run lint` must exit with code `0` and report `✔ No ESLint warnings or errors`.

---

## 7. Quality Standards & Non-Negotiable Constraints Checklist

- [x] **Dark UI Consistency**: Professional Black/White/Liquid Glass dark theme across all views with frosted glass tokens and specular borders.
- [x] **Responsive Layouts**: Fluid responsive design across mobile (< 768px), tablet (768px-1024px), and desktop (> 1024px).
- [x] **Real Interactive Components**: Zero static placeholder mockups; all components feature real React hooks, active state management, form handlers, and data fetching.
- [x] **Interactive Data Charts**: 8 real data-backed charts displaying live database posture metrics from `/api/v1/metrics/*`.
- [x] **Forensic Evidence Drill-Down**: Interactive 5-tab evidence viewer (Proof, Request, Response, Headers, Replay cURL) with one-click copy.
- [x] **Wired Target Management**: Real asset registration, bulk import deduplication, and 8-step live probe pipeline modal wired to backend endpoints.
- [x] **Live Scanning Interface**: Interactive profile selection (7 profiles), scan dispatching, and real-time SSE execution telemetry terminal with fallback polling.
- [x] **Backend Preservation**: Zero regressions to existing database schema (`noospire.db`), SQLAlchemy 2.0 ORM models, or FastAPI route contracts.
- [x] **Test Verification**: 164/164 `pytest` tests passing and 10/10 `verify_empire_e2e.py` capability checks passing cleanly.
