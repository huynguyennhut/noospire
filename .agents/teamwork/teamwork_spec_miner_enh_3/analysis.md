# NOOSFORGE Security Intelligence — Specification Mining & Verification Harness Analysis

**Document Version**: 1.0.0  
**Author**: Specification Investigator (`teamwork_spec_miner_enh_3`)  
**Target Platform**: NOOSFORGE Security Intelligence (`https://noosforge-soc.pages.dev`)  
**Primary Target**: Empire Educational Ecosystem (`https://empire.edu.vn/`)  
**Workspace**: `c:\Users\nguye\Desktop\noospire`  
**Date**: 2026-11-09T19:24:00Z  

---

## 1. Executive Summary & Specification Scope

This specification mining report probes, discovers, and documents the authoritative behavioral and technical specifications of the NOOSFORGE Security Intelligence platform. The investigation focuses on four core strategic pillars:
1. **Primary Target (`https://empire.edu.vn/`)**: Target onboarding, 8-step live probe pipeline, and scanner execution interfaces.
2. **Multi-Engine Real Execution**: Authentic network probe execution across Nuclei CLI, OWASP ZAP adapter, Empire custom assessment engine, and bounded BFS Crawler, with raw HTTP evidence capture and zero fabrication.
3. **Loop Testing & Notification Tracking**: Sequential, batch, and recurring scan automation architecture, resource throttling, and end-to-end alert notification lifecycle tracking.
4. **Verification Harness & Coverage Gap Analysis**: Complete audit of `scripts/verify_empire_e2e.py` and `tests/`, identifying existing capabilities and exact test requirements for scan schedules, auto-scroll disable controls, complete log lifecycle, Ultra Admin authentication & dev tracking, engine health/update endpoints, and loop testing.

---

## 2. Primary Target (`https://empire.edu.vn/`) Specification

### 2.1. Target Onboarding & Policy Baseline
- **Seeded Definition (`backend/app/core/empire_seeder.py`)**:
  - `name`: "Empire Educational Platform (Primary Root)"
  - `target_locator`: `https://empire.edu.vn/`
  - `asset_type`: `WEB_APP`
  - `empire_module`: `WEB_APPLICATION`
  - `technology`: "Next.js / Envoy / React"
  - `criticality`: `CRITICAL`
  - `exposure`: `INTERNET`
  - `approved_media_baseline`: `False`
  - `assessment_policy`:
    ```json
    {
      "daily_scan": true,
      "intensity": "PRODUCTION_SAFE",
      "baseline_policy": "PRODUCTION_SAFE",
      "allow_active": true,
      "scope": "*.empire.edu.vn",
      "same_origin_scope": "*.empire.edu.vn",
      "same_origin_only": true,
      "rate_limit_rps": 5,
      "safe_mode": true
    }
    ```
  - `tags`: `["empire", "root", "primary", "production", "web_application"]`
  - Initial `verification_status`: `VERIFIED` via `VerificationType.ADMIN_OVERRIDE`.

- **Dynamic Onboarding APIs (`backend/app/api/assets.py`)**:
  - `POST /api/v1/assets`: Registers a single target with SSRF validation.
  - `POST /api/v1/assets/bulk-import`: Parses CSV, JSON, or line-delimited URLs, automatically classifies Empire module based on URL tokens (`id.` -> STUDENT_MANAGEMENT, `voh.`/`media` -> LEARNING_MATERIALS, `gw.`/`api` -> API_SERVICES, `news` -> SUPPORTING_TOOLS), and deduplicates against existing inventory.
  - `POST /api/v1/assets/bulk-preview`: Previews candidate targets from OpenAPI specs, JSON arrays, CSV data, or CIDR blocks, detecting duplicates against `noospire.db` and within the incoming batch.

### 2.2. The 8-Step Live Probe Pipeline (`backend/app/core/target_verifier.py`)
Executed via `POST /api/v1/assets/{id}/verify` using `TargetVerifier`:
1. **Step 1: Input Validation**:
   - Syntax validation, scheme whitelisting (`http`, `https`), port bounds check.
   - SSRF Gatekeeper (`SSRFProtector.validate_target`): Blocks loopback (`127.0.0.0/8`, `::1`), RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local (`169.254.0.0/16`), cloud metadata (`169.254.169.254`), CGNAT (`100.64.0.0/10`), decimal IP obfuscations, and octal IP encodings unless `allow_private=True`.
2. **Step 2: DNS Resolution**:
   - Resolves A and AAAA records via `asyncio.getaddrinfo(hostname, port)`. Returns list of resolved IPv4 and IPv6 addresses.
3. **Step 3: TLS Verification**:
   - Opens direct TLS socket handshake using `ssl.create_default_context()`.
   - Inspects certificate subject CN, issuer organization, Subject Alternative Names (SANs), expiration date (`notAfter`), remaining validity days, TLS protocol version (e.g. TLSv1.3), and negotiated cipher suite.
   - Fails if expired or certificate verification fails; returns `INFO` if scheme is plain HTTP.
4. **Step 4: HTTP Connectivity**:
   - Sends real non-destructive HTTP GET probe via `httpx.AsyncClient(verify=False, timeout=10.0, follow_redirects=False)`.
   - Measures round-trip latency in milliseconds, captures HTTP status code, HTTP version, and response headers count.
5. **Step 5: Redirect Inspection**:
   - Traces hop-by-hop redirects with `max_redirects=10`.
   - Protocol Downgrade Detection: Fails if an HTTPS initial locator redirects to an insecure plain HTTP landing URL.
6. **Step 6: Web Discovery**:
   - Concurrently probes standard discovery endpoints: `/robots.txt`, `/sitemap.xml`, and `/.well-known/security.txt`.
   - Records status code, accessibility boolean, content-type, and body preview snippets.
7. **Step 7: Target Fingerprint**:
   - Reverse Proxy & WAF identification: Envoy (`server: envoy` or `x-envoy-upstream-service-time`), Cloudflare (`cf-ray` or `server: cloudflare`), Nginx, AWS CloudFront.
   - Framework identification: Next.js (`x-powered-by: Next.js`, `x-nextjs-cache`, `/_next/` assets), Vite, Express.js, FastAPI.
   - Security headers audit: HSTS, Content-Security-Policy, X-Frame-Options, X-Content-Type-Options, Referrer-Policy.
8. **Step 8: Verification Result**:
   - Computes final verdict: `VERIFIED` if Step 1, Step 2, and Step 4 pass and Step 3 is PASS/INFO.
   - Updates target asset verification status, verification timestamp, and detected technology stack in database.

### 2.3. APIs and Scripts to Launch and Track Scans
- **Dispatch APIs**:
  - `POST /api/v1/scans`: Creates single scan in `QUEUED` state; enforces SSRF checks and verification requirement for `DEEP_ACTIVE`.
  - `POST /api/v1/scans/batch` & `POST /api/v1/scans/scan-all`: Dispatches synchronized matrix sweeps across targets, engines, and profiles with concurrency control.
  - `POST /api/v1/schedules/{id}/trigger`: Triggers scheduled scans across assigned targets.
- **Tracking & Telemetry APIs**:
  - `GET /api/v1/scans/{id}`: Returns scan metadata, status, quality status, progress percentage, error messages.
  - `GET /api/v1/scans/{id}/logs`: Returns paginated execution logs.
  - `GET /api/v1/scans/{id}/logs/stream`: Live Server-Sent Events (`text/event-stream`) streaming logs in real time.
  - `GET /api/v1/scans/trackcurrent`: Multi-worker thread matrix HUD telemetry (`active_workers`, `max_concurrency`, `queued_count`, `active_threads`, `is_throttled`, CPU/RAM stats).
  - `POST /api/v1/scans/{id}/cancel`: Cooperatively aborts scan and halts process tree.
  - `POST /api/v1/scans/stop-all`: Platform-wide master emergency stop halting all running jobs.

---

## 3. Multi-Engine Real Execution Architecture & Integrity Standards

### 3.1. Engine Adapters & Dispatch Mechanics
The platform orchestrates scans via `AsyncWorkerDispatcher` (`backend/app/core/dispatcher.py`):
1. **Nuclei CLI Adapter (`NucleiAdapter` in `backend/app/scanners/nuclei.py`)**:
   - Native Execution: Checks `shutil.which("nuclei")`. Spawns `nuclei -target <url> -jsonl -silent -nc -timeout 5`. Subprocess PID registered in `ProcessSafetyManager`. Parses JSONL lines for finding details, CVE, CWE, and raw evidence.
   - Embedded Lab Runner Fallback (`NucleiLabRunner` in `backend/app/scanners/lab_runners.py`): When CLI binary is absent, performs genuine HTTP network requests using `httpx.AsyncClient` against approved vulnerability templates:
     - `git-config-exposure` (`/.git/config`)
     - `env-file-exposure` (`/.env`)
     - `cors-misconfiguration` (Origin header reflection)
     - `directory-listing-enabled` (`/static/`)
     - `cve-2023-38606-spring-actuator` (`/actuator/env`)
   - Captures raw request string, raw response headers and body snippet, matched string, and reproduction cURL command.
2. **OWASP ZAP Adapter (`ZAPAdapter` in `backend/app/scanners/zap.py`)**:
   - Native Execution: Checks `shutil.which("zap.bat"|"zap.sh"|"zap")`. Spawns ZAP in command-line mode and parses generated report JSON.
   - Embedded Lab Runner Fallback (`ZAPLabRunner` in `backend/app/scanners/lab_runners.py`):
     - Passive Web Audit: Inspects HTTP response headers for missing anti-clickjacking (`X-Frame-Options` / `frame-ancestors`), missing Content-Security-Policy, missing `X-Content-Type-Options: nosniff`, and server banner disclosure (`Server`, `X-Powered-By`).
     - Gated Active Probing (`DEEP_ACTIVE` profile only): Executes bounded SQL injection probe (`' OR '1'='1`) and reflected XSS probe (`<s3nt1n3l_xss_probe>`) against discovery endpoints. Captures injected parameter, payload, and raw HTTP response evidence.
3. **Empire Custom Security Engine (`EmpireAssessmentEngine` in `backend/app/scanners/empire_engine.py`)**:
   - Deep business logic security assessment specialized for the Empire Platform:
     - Module A (Student Management & Authentication): Better-Auth unauthenticated user disclosure and BOLA/IDOR cross-student authorization testing.
     - Module B (Educational Material Management): Verifies `/media` Approved Public Exposure Policy; audits for unintended sensitive leaks (`/media/student-records.csv`, `/media/.env`, `/media/passwords.txt`) and directory/MinIO bucket listing.
     - Module C (Supporting Educational Tools): Tests news feed aggregator for SSRF against cloud metadata (`169.254.169.254`) and news search for reflected XSS.
     - Module D (API Security): Audits administrative routes for Broken Function-Level Authorization (BFLA) and checks rate-limiting headers.
     - Module E (Web Application Security): Evaluates CSP, XFO, and cookie security flags (`Secure`, `HttpOnly`, `SameSite`).
     - Module F (Controlled Brute-Force & Negative Auth Defense): Executes exactly 5 bounded probes with synthetic credentials (`audit_synthetic_probe@empire.local`) against `/api/auth/sign-in/email` to verify progressive delays, lockouts, or HTTP 429 rate limiting without touching real user accounts.
     - Module G (Server & Cloud Infrastructure): Audits version disclosures, HSTS enforcement, and public `/server-status` exposures.
4. **Bounded BFS Crawler (`AsyncBFSCrawler` in `backend/app/scanners/crawler.py`)**:
   - Asynchronous same-origin Breadth-First Search web crawler.
   - Enforces strict same-origin hostname matching.
   - Bounds maximum crawl depth (default: 3, quick: 2) and maximum visited pages (default: 50, quick: 10).
   - Rate-limited delay per request (0.02s - 0.05s).
   - Automatically skips non-HTML static file extensions (`.png`, `.jpg`, `.css`, `.js`, `.pdf`, `.zip`, `.mp4`).
   - Extracts `href`, `action`, and `src` links from HTML and indexes discovered endpoints.

### 3.2. Zero-Fabrication Integrity Standard
- **"Test thật, kết quả thật - không fake kết quả, trực quan, trực tuyến, khả quan"**:
  - All scanner adapters and lab runners execute authentic HTTP/HTTPS network connections.
  - Every finding persists raw, verifiable forensic evidence:
    - `request`: Full HTTP method, URL, and headers sent.
    - `response`: Exact HTTP status code, response headers, and response body sample received.
    - `matched_content`: Verbatim text or regular expression match proving the vulnerability.
    - `curl_command`: Standalone command allowing security engineers to manually reproduce the finding outside the platform.
  - Finding Deduplication: Uses deterministic SHA-256 fingerprint:
    $$\text{Fingerprint} = \text{SHA256}(\text{asset\_id} : \text{engine} : \text{rule\_id} : \text{location} : \text{component})$$
    Identical findings from recurring scans increment `occurrence_count` and update `last_seen_at` without duplicating database records. If a previously `FIXED` finding is detected again, its status automatically transitions to `REOPENED` and generates a regression security alert.
  - Scanner Quality State Machine:
    - `SCANNED_SUCCESSFULLY`: All engines executed without errors.
    - `PARTIAL_COVERAGE`: Non-fatal errors occurred in a subset of engines, but partial results were obtained.
    - `AUTH_REQUIRED`: Active scans blocked due to lack of verified asset ownership or missing credentials.
    - `SCANNER_FAILED`: Adapter subprocess crashed or returned non-zero exit code with no findings.
    - `TARGET_UNAVAILABLE`: Network connect timeout, DNS failure, or connection refused.

---

## 4. Loop Testing & Notification Tracking Architecture

### 4.1. Loop Testing & Sequential Execution
- **Recurring Schedules (`DailySchedule` in `backend/app/models/schedule.py`)**:
  - Cron syntax representation (e.g. `0 2 * * *` for daily 02:00 AM ICT, `*/30 * * * *` for 30-minute intervals).
  - Timezone-aware execution (`Asia/Ho_Chi_Minh`).
  - Target binding: `target_ids = ["ALL"]` or array of target UUIDs.
  - Trigger API (`POST /api/v1/schedules/{id}/trigger`): Sequentially dispatches assessment scans across targets.
  - Toggle API (`PUT /api/v1/schedules/{id}/toggle`): Enables or pauses schedule without deleting configuration.
- **Batch Orchestration (`ScanBatch` in `backend/app/models/scan.py`)**:
  - Expands target matrix across chosen profiles and engines.
  - Resource Throttling: `psutil` monitors system CPU% and RAM%. If CPU > 90% or RAM > 95%, dequeuing delays by 1.0s to prevent system freeze.
  - Per-Asset Mutual Exclusion: An `asyncio.Lock` per asset prevents race conditions and resource contention on the same target.
  - Cooperative Cancellation: Cancelling a batch purges queued scans, halts running worker tasks, and invokes `ProcessSafetyManager.terminate_process_tree()` to terminate subprocess trees.

### 4.2. Notification Tracking System
- **In-App Security Alerts (`SecurityAlert` in `backend/app/models/alert.py`)**:
  - Severity: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`.
  - Categories:
    - `VULN`: Generated when CRITICAL or HIGH findings are uncovered. Contains finding ID and asset locator.
    - `SCAN`: Emitted at scan lifecycle milestones (`Scan Completed`, `Scan Warning: PARTIAL_COVERAGE`, `Scan Failed`).
    - `BASELINE`: Emitted on baseline policy activation or exceptions.
  - REST Endpoints (`/api/v1/alerts`):
    - `GET /api/v1/alerts`: Paginated query with `is_read` filtering.
    - `POST /api/v1/alerts/{id}/read`: Acknowledges an alert.
    - `POST /api/v1/alerts/read-all`: Bulk acknowledges all unread alerts.
- **Real-Time SSE Streaming (`/api/v1/scans/{id}/logs/stream`)**:
  - Streams structured JSON event chunks over SSE: `{ id, scan_id, timestamp, level, message, source }`.
  - Backed by thread-safe in-memory ring buffer `ScanLogBuffer` with database persistence fallback.
- **Frontend Liquid Glass Toast Notifications (`components/ui/toast.tsx`)**:
  - Reactive notifications on scan dispatch, emergency stop, batch cancellation, and schedule triggers with auto-dismiss timers.

---

## 5. Existing Verification Harness & Coverage Gap Analysis

### 5.1. Existing Verification Scripts & Test Suites
- **`scripts/verify_empire_e2e.py`**:
  - 10 comprehensive vertical slice tests:
    1. Database Initialization & Seeding (Assets >= 6, Findings >= 6, Baselines >= 1, Schedules >= 1)
    2. Dashboard Overview KPIs & Module Risk Chart
    3. Empire 6-Module Hub Taxonomy
    4. Asset Inventory & Bulk Import Deduplication
    5. Approved Public Media Baseline Verification
    6. Scan Dispatch & Empire Assessment Engine Execution
    7. Vulnerability Triage Lifecycle & Live Retest
    8. Multi-Format Report Generation (PDF, HTML, JSON on disk)
    9. Daily Assessment Scheduler & Pipeline Trigger
    10. Security Alerts & Notification System
  - Verified Status: **10/10 PASS (100% Green)**.
- **`tests/test_scan_all_batch_orchestration.py`**:
  - Tests BAT-01 through BAT-13 covering batch dispatch, matrix expansion, active scan gates, concurrency throttling, per-asset locks, cooperative cancel, and live telemetry.
- **`tests/test_challenger_live_empire.py`**:
  - Live empirical tests against `https://empire.edu.vn/`.
- **`tests/test_empirical_challenger.py`**:
  - 700+ lines testing SSRF edge cases, bulk preview deduplication, and quality state transitions.

### 5.2. Coverage Gaps & Additional Test Specifications Needed
Based on the original requirements in `ORIGINAL_REQUEST.md`, the following 6 areas require explicit verification tests or feature augmentations:

| # | Requested Area | Current Codebase State | Gap / Specification Needed |
|---|----------------|------------------------|----------------------------|
| 1 | **Scan Schedules** | Basic list, create, trigger, toggle endpoints exist in `backend/app/api/schedules.py` and UI in `frontend/src/app/schedules/page.tsx`. | Add test suite verifying: (a) cron expression validation, (b) schedule toggle persistence, (c) schedule-triggered batch scan expansion, (d) scheduled scan completion tracking. |
| 2 | **Disabling Auto-Scroll** | In `frontend/src/app/active-assessments/page.tsx`, `autoScroll` state exists and defaults to `false` (`useState(false)`). When `autoScroll` is false, new logs append without jumping the viewport. | Add explicit UI component test asserting that `autoScroll` is initially `false`, toggles cleanly on user interaction, and suppresses `scrollIntoView` calls when disabled. |
| 3 | **Complete Log Lifecycle** | (a) Export logs: implemented in UI (`handleExportLogs` download blob).<br>(b) Clear logs: UI calls `api.clearLogs(id)` which clears client storage, while backend has `DELETE /api/v1/scans/{id}` (cascading).<br>(c) Reset to clean baseline: UI calls `api.resetBaseline()` in `scan-engine.ts`.<br>(d) Track by days: UI has `timeFilter` ('1D', '7D', '14D', '30D', 'ALL'). | Add backend endpoints and test cases for:<br>- `DELETE /api/v1/scans/{id}/logs` or clear logs API.<br>- `POST /api/v1/settings/reset-baseline` to reset DB to initial seeded state via REST.<br>- `days` / date-range filtering query parameter on `GET /api/v1/scans`. |
| 4 | **Ultra Admin Authentication & Dev Tracking** | Frontend `login/page.tsx` defines `ULTRA_ADMIN_CREDENTIALS` (`dangnhutnguyen0910@gmail.com` / `Hahanguyen09@`). Backend `backend/app/api/auth.py` checks `ADMIN_USERNAME` / `ADMIN_PASSWORD` (defaults `admin` / `admin123`) or `settings.is_development`. | Add explicit backend support for Ultra Admin credentials (`dangnhutnguyen0910@gmail.com` / `Hahanguyen09@`) in `auth.py` regardless of dev flags, and verify dev session tracking in `localStorage` (`sentinel_user`). |
| 5 | **Engine Health & Update Endpoints** | Backend has `GET /health` and `GET /api/v1/settings`, but lacks granular per-engine status and update trigger endpoints. | Add endpoints and tests for:<br>- `GET /api/v1/settings/engines`: Returns availability status, execution mode (CLI vs Lab), and versions for Nuclei, ZAP, Empire Engine, Crawler, and Trivy.<br>- `POST /api/v1/settings/engines/update`: Triggers vulnerability template and database updates. |
| 6 | **Loop Testing & Notification Tracking** | Batch scans and scheduler trigger multiple scans, and `SecurityAlert` records notifications. | Implement a dedicated automated loop test script (`scripts/verify_loop_and_notifications.py` or pytest) that executes sequential recurring scan loops (3 passes), verifies deduplication stability (zero duplicate findings), tracks alert emissions per pass, and tests read/read-all alert lifecycle. |

---

## 6. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Target Management | Seeded Empire Targets | Seeds 7 core targets including `https://empire.edu.vn/` with same-origin scope and safe policy | Async database session | Seeded `assets` records in `noospire.db` | Duplicate check prevents re-insertion | `empire_seeder.py:53-173` |
| 2 | Target Management | Bulk Target Preview | Previews imported targets from OpenAPI, CSV, JSON, CIDR with duplicate detection | `AssetBulkPreviewRequest` (raw_content or items) | `AssetBulkPreviewResponse` (`new`, `duplicate`, `total`) | Invalid formats gracefully handled with fallback parsing | `assets.py:256-563` |
| 3 | Verification Pipeline | 8-Step Live Probe Engine | Comprehensive network probe: validation, DNS, TLS, HTTP, redirects, web discovery, fingerprinting, verdict | Target locator, `allow_private` boolean | Verification dict with 8 step results and fingerprint | Returns `FAILED` on SSRF, DNS error, or HTTP unreachable | `target_verifier.py:38-166` |
| 4 | Verification Pipeline | Verify Target API | Executes 8-step probe against target asset and updates database status | `POST /api/v1/assets/{id}/verify` with verify options | `AssetVerifyResponse` with step details | HTTP 404 if asset not found; FAILED status if probe fails | `assets.py:654-704` |
| 5 | Scanning Engine | Scan Dispatch Gate | Dispatches scan with SSRF pre-flight validation and DEEP_ACTIVE ownership check | `POST /api/v1/scans` (`asset_id`, `profile`, `engine`) | `ScanResponse` in QUEUED state | HTTP 400 on SSRF violation; HTTP 403 if unverified active scan | `scans.py:71-122` |
| 6 | Scanning Engine | Multi-Worker Dispatcher | Manages async queue, dynamic CPU/RAM throttling, per-asset mutual exclusion | Scan UUID | Background execution task | Retries log persistence on lock; sets FAILED on fatal error | `dispatcher.py:212-436` |
| 7 | Scanning Engine | Process Safety Manager | Tracks spawned subprocess PIDs and ensures recursive process tree kill on cancel | Scan UUID, process PID | Process termination | Gracefully ignores already terminated processes | `dispatcher.py:151-190` |
| 8 | Scanning Engine | Batch "Scan All" Orchestration | Dispatches synchronized assessment matrix across targets and profiles | `POST /api/v1/scans/batch` (`targets`, `profiles`, `engines`) | `BatchScanResponse` with created scans | HTTP 404 if no targets found; skips unverified on DEEP_ACTIVE | `scans.py:128-261` |
| 9 | Scanning Engine | Cooperative Batch Cancel | Cancels all running and queued scans in a batch and purges queue | `POST /api/v1/scans/batch/{id}/cancel` | JSON with `cancelled_count` | HTTP 404 if batch not found | `scans.py:300-320` |
| 10 | Scanning Engine | Platform Emergency Stop | Instantly halts all active, running, and queued scan jobs across platform | `POST /api/v1/scans/stop-all` | JSON with `halted_count` | Purges worker queue and marks records CANCELLED | `scans.py:322-334` |
| 11 | Scanning Engine | Live Telemetry ("trackcurrent") | Provides real-time active worker matrix, CPU/RAM stats, and queue depth | `GET /api/v1/scans/trackcurrent` | `TrackCurrentResponse` with active threads and resource stats | Returns fallback zero values if sampling fails | `scans.py:336-342` |
| 12 | Scanning Engine | Real-Time SSE Log Streaming | Streams real-time scanner logs via Server-Sent Events | `GET /api/v1/scans/{id}/logs/stream` | `text/event-stream` SSE chunks | Stream closes cleanly on client disconnect | `scans.py:421-450` |
| 13 | Scanner Adapter | Nuclei CLI & Lab Runner | Runs native Nuclei binary or falls back to authentic HTTP request lab runner | `ScanExecutionRequest` | `ScannerExecutionResult` with normalized findings | Falls back to lab runner if CLI fails or is absent | `nuclei.py:111-180` |
| 14 | Scanner Adapter | OWASP ZAP & Lab Runner | Runs native ZAP or embedded lab runner for passive headers & gated active SQLi/XSS | `ScanExecutionRequest` | `ScannerExecutionResult` with normalized findings | Raises PermissionError if active probe on unverified asset | `zap.py:96-169` |
| 15 | Scanner Adapter | Empire Assessment Engine | Tailored business module checks (Better-Auth, /media policy, BOLA, SSRF, negative auth) | Target locator, module, profile | List of `NormalizedFindingCreate` with raw evidence | Skips or logs warning on connection timeouts | `empire_engine.py:38-123` |
| 16 | Scanner Adapter | Bounded BFS Crawler | Same-origin breadth-first search crawler bounded by depth, pages, and rate limits | Root URL, depth bound, max pages | `CrawlResult` with discovered endpoints | Halts when queue empty, max pages reached, or cancelled | `crawler.py:120-251` |
| 17 | Intelligence & Quality | Quality State Machine | Explicit 5-state scan outcome classification based on adapter results | Adapter successes, auth errors, connection errors | Quality state (`SCANNED_SUCCESSFULLY`, `PARTIAL_COVERAGE`, etc.) | Recorded on scan record | `dispatcher.py:888-919` |
| 18 | Intelligence & Quality | Deterministic Deduplication | SHA-256 fingerprinting deduplicates findings and triggers regression on reopened bugs | Asset ID, engine, rule ID, location, component | SHA-256 hash string; updates existing finding count | Flags previously fixed findings as REOPENED | `dispatcher.py:808-875` |
| 19 | Policy & Governance | Approved Public Media Baseline | Policy exception declaring `/media` public by design, suppressing false-positive alerts | Baseline scope pattern, owner, reason | `BaselineException` record | Checks for unintended sensitive content regardless of baseline | `empire_seeder.py:368-398` |
| 20 | Automation & Schedules | Continuous Daily Scheduler | Cron-based daily security assessment execution in Asia/Ho_Chi_Minh | Daily schedule definition, trigger request | Dispatched scan jobs across target perimeter | Preserves last run time and execution status | `schedules.py:42-128` |
| 21 | Alerts & Notifications | In-App Alert System | Emits notifications for critical findings, scan completions, and policy drift | Alert category, severity, message, metadata | Stored `SecurityAlert` records | API allows filtering by read state and marking read | `alerts.py:26-59` |
| 22 | User Experience | Auto-Scroll Disable Control | Terminal logs viewer has auto-scroll toggle defaulting to disabled (false) | User click on auto-scroll toggle | Toggles `autoScroll` boolean in state | Viewport does not jump on new incoming logs when disabled | `active-assessments/page.tsx:84,317-321` |
| 23 | User Experience | Terminal Logs Clear & Export | Clears active log terminal and exports logs to downloadable `.log` text file | User click on Clear or Export button | Client blob download or log array purge | Displays toast confirmation to user | `active-assessments/page.tsx:351-399` |
| 24 | User Experience | Track by Days Filter | Filters displayed scan history queue by time elapsed (1D, 7D, 14D, 30D, ALL) | User selects time range filter pill | Filtered scan job list | Computes millisecond delta from scan timestamp | `active-assessments/page.tsx:85,463-471` |
| 25 | Authentication | Ultra Admin Authentication | Dedicated login portal supporting Ultra Admin credentials & one-click quick login | Email & password or quick login trigger | JWT session token & user profile in localStorage | Displays invalid credentials error on mismatch | `login/page.tsx:23-123` |

---

## 7. Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | SSRF Gatekeeper | Loopback `http://127.0.0.1:8000` or `http://localhost` | Rejected immediately with `SSRFValidationError` ("Blocked network address") unless `allow_private=True`. |
| 2 | SSRF Gatekeeper | Cloud metadata `http://169.254.169.254/latest/meta-data/` | Rejected immediately by SSRF validator; protects cloud hosting environment from token exfiltration. |
| 3 | SSRF Gatekeeper | Decimal IP obfuscation `http://2130706433` (127.0.0.1) | Resolved to loopback and strictly rejected by socket address analysis. |
| 4 | SSRF Gatekeeper | IPv6 loopback `http://[::1]` or link-local `http://[fe80::1]` | Blocked by IPv6 range match against blocked network list. |
| 5 | Target Verification | Scheme downgrade (HTTPS initial redirects to HTTP landing) | Step 5 (Redirect Inspection) flags protocol downgrade and marks step FAILED. |
| 6 | Target Verification | Domain without A/AAAA DNS records | Step 2 (DNS Resolution) fails with `gaierror`; Step 8 verdict is FAILED. |
| 7 | Target Verification | Expired TLS certificate | Step 3 (TLS Verification) detects negative `days_until_expiry` and marks step FAILED. |
| 8 | Scan Dispatch | Active profile `DEEP_ACTIVE` on unverified target asset | Rejected with HTTP 403 Forbidden: "Active scanning is prohibited: asset ownership is not verified." |
| 9 | Scan Dispatch | Batch dispatch with mixed verified and unverified targets | Unverified targets for `DEEP_ACTIVE` fail immediately with `AUTH_REQUIRED`; verified targets proceed to execution. |
| 10 | Scanner Dispatcher | Host CPU exceeds 90% or RAM exceeds 95% | Throttling activates: worker loop delays scan dequeuing by 1.0s until resources drop below thresholds. |
| 11 | Scanner Dispatcher | Multiple concurrent scans dispatched against same asset ID | Per-asset `asyncio.Lock` serializes execution to prevent resource exhaustion and race conditions on the target. |
| 12 | Scanner Dispatcher | Cooperative cancellation of running batch | Process safety terminates all active child process trees; queue is purged; status set to CANCELLED. |
| 13 | Findings Deduplication | Same vulnerability found across multiple sequential scan runs | Matching SHA-256 fingerprint increments `occurrence_count` and updates `last_seen_at`; zero duplicate rows created. |
| 14 | Findings Lifecycle | Previously fixed finding detected in subsequent scan pass | Finding status automatically transitions from `FIXED` to `REOPENED`; regression warning alert generated. |
| 15 | Media Baseline | Request to `/media/public-course.pdf` | Returns HTTP 200/404; classified as `PUBLIC_BY_DESIGN`; zero false-positive vulnerability alerts generated. |
| 16 | Media Baseline | Sensitive file `/media/student-records.csv` or `/media/.env` | Generates CRITICAL vulnerability `EMPIRE-MEDIA-LEAK-01` despite `/media` baseline exception. |
| 17 | Negative Auth Defense | 5 sequential failed login attempts to `/api/auth/sign-in/email` | If response does not emit rate-limit headers or delays, flags `EMPIRE-AUTH-BRUTEFORCE-01` (High). |
| 18 | Crawler | External off-domain links (e.g. `https://google.com` or `https://cdn.external.com`) | Filtered out by `is_same_origin`; crawler strictly remains on target domain. |
| 19 | Crawler | Static asset links (`.png`, `.pdf`, `.mp4`, `.zip`, `.js`, `.css`) | Skipped from FIFO queue expansion to prevent wasted requests on non-navigational content. |
| 20 | Terminal Logs | Rapid incoming stream of SSE logs while user is inspecting earlier log line | If `autoScroll` is false (default), terminal maintains scroll offset without scrolling to bottom. |
| 21 | Scan History Queue | Target scans started > 7 days ago with "1D" filter selected | Filter suppresses older jobs and displays only scans started within the last 24 hours. |
| 22 | Authentication | Login with Ultra Admin credentials `dangnhutnguyen0910@gmail.com` | Authenticates with `SUPER_ADMIN` role and full system permissions; stores session in `localStorage`. |
| 23 | Authentication | Non-existent user with invalid password in production mode | Returns HTTP 401 Unauthorized with `WWW-Authenticate: Bearer` header. |
| 24 | Emergency Stop | 20 active and queued scan jobs running when stop-all is invoked | All 20 scans halted, subprocesses killed, queue drained, and system returns to idle state. |

---

## 8. Concrete Verification Plan & Enhancement Roadmap

To fully fulfill all user requirements from `ORIGINAL_REQUEST.md`, downstream workers should execute the following test and feature enhancements:

1. **Test Suite `tests/test_enhancement_spec_coverage.py`**:
   - **Test 1 (Schedules)**: Test `POST /api/v1/schedules`, `GET /api/v1/schedules`, `PUT /api/v1/schedules/{id}/toggle`, and `POST /api/v1/schedules/{id}/trigger` verifying cron validation, status toggle, and batch scan generation.
   - **Test 2 (Disabling Auto-Scroll)**: UI test asserting `autoScroll` defaults to `false` and viewport does not shift on log arrival.
   - **Test 3 (Complete Log Lifecycle)**: Test log retrieval (`GET /api/v1/scans/{id}/logs`), log export, log clearing, and day tracking filter.
   - **Test 4 (Ultra Admin Auth & Dev Tracking)**: Test `POST /api/v1/auth/login` with `dangnhutnguyen0910@gmail.com` / `Hahanguyen09@`, verifying JWT token generation, `is_superuser: true`, and dev tracking.
   - **Test 5 (Engine Health & Update Endpoints)**: Test engine health discovery endpoint and update simulation endpoint.
   - **Test 6 (Loop Testing & Notification Tracking)**: Automated test running 3 sequential scan iterations on `https://empire.edu.vn/`, proving zero duplicate findings (deduplication SHA-256 stability) and verifying emitted alerts in `security_alerts`.

2. **Automated Verification Harness Script (`scripts/verify_enhancements_complete.py`)**:
   - End-to-end script executing the complete pipeline against `https://empire.edu.vn/` with all engines, verifying no fake results, real evidence capture, schedule triggering, log clearing, and alert acknowledgments.

---
*End of Specification Analysis Report.*
