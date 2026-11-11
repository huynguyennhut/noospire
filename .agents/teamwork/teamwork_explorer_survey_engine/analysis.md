# Engine Authenticity & Execution Verification Survey Report

**Platform**: NOOSFORGE Security Intelligence — Enterprise Cybersecurity SaaS Platform  
**Target Architecture**: Empire Educational Platform (`https://empire.edu.vn/`)  
**Auditor Role**: Principal Systems Architect, Lead Security Researcher, and Engine Verification Explorer  
**Date**: 2026-11-09T23:55:00Z  
**Repository Working Directory**: `c:\Users\nguye\Desktop\noospire\`  

---

## 1. Executive Summary

This investigation conducted a rigorous, evidence-driven audit of all execution engines, scanners, processors, background workers, and telemetry pipelines in the NOOSFORGE Security Intelligence platform. Every engine was tested against the non-negotiable audit principles: **Evidence over assumptions**, **No fake success**, and **Real execution verification**.

### Key Findings at a Glance:
1. **Real Core Execution Engines**:
   - **Nuclei**: Native CLI binary genuinely installed at `C:\Users\nguye\go\bin\nuclei.exe` (Engine Version: `v3.11.1`). Subprocess execution, JSONL streaming, template filtering, and raw evidence capture are fully verified. Embedded `NucleiLabRunner` provides verified real-HTTP template evaluation as a fallback.
   - **Empire Specialized Security Engine**: In-process asynchronous assessment engine (`backend/app/scanners/empire_engine.py`) covering all 7 Empire educational business modules (A through G). Issues genuine HTTP requests using `httpx.AsyncClient` with non-destructive payloads, measuring latency, status codes, and rate-limiting headers.
   - **Async BFS Crawler**: Genuine Breadth-First Search web crawler (`backend/app/scanners/crawler.py`) with strict same-origin filtering, HTML link extraction, static asset bypass, bounded depth (max 3), bounded pages (max 50), and cooperative cancellation.
   - **8-Step Live Target Verification Engine**: Production probe pipeline (`backend/app/core/target_verifier.py`) executing genuine network operations: DNS `getaddrinfo` resolution (A/AAAA), TLS SSL socket handshake with certificate chain validation, HTTP round-trip latency probe, hop-by-hop redirect tracing, standard web discovery (`/robots.txt`, `/sitemap.xml`, `/.well-known/security.txt`), and header/body fingerprinting (Envoy, Next.js, Cloudflare).
   - **Background Dispatcher & Resource Throttler**: Local async worker pool (`AsyncWorkerDispatcher`) with `psutil` CPU/RAM throttling (delays dequeuing when CPU > 90% or RAM > 95%), `ProcessSafetyManager` recursive process-tree termination, per-asset locking, and active worker thread tracking (`/trackcurrent`).
   - **Deduplication & Quality State Machine**: Deterministic SHA-256 finding fingerprints (`asset_id:engine:rule:location:component`), regression reopening (`REOPENED`), and explicit 5-state quality machine (`SCANNED_SUCCESSFULLY`, `PARTIAL_COVERAGE`, `AUTH_REQUIRED`, `SCANNER_FAILED`, `TARGET_UNAVAILABLE`).
2. **Partially Implemented Adapters**:
   - **OWASP ZAP & Aqua Trivy**: Their native binaries (`zap.bat` and `trivy.exe`) are not installed on the Windows host PATH. However, both adapters cleanly detect the absence of CLI binaries and route execution to their respective embedded high-fidelity lab runners (`ZAPLabRunner` and `TrivyLabRunner`). These lab runners execute genuine operations (real HTTP passive/active probes for ZAP; real `package.json`/`requirements.txt` parsing and secret scanning on disk for Trivy), rather than returning fabricated canned results.
3. **Simulated / Discrepant Elements**:
   - **Nmap Scanner**: Displayed in the frontend client-side fallback (`scan-engine.ts`, `fallback-data.ts`, and `api.ts`), but **DOES NOT EXIST** in the backend scanner inventory (`backend/app/scanners/`).
   - **CeleryDispatcher**: Stated in `dispatcher.py` lines 966-999 as a placeholder/stub logging messages without actual Celery/Redis message passing. However, it is inactive by default since `DISPATCHER_MODE=async_worker`.
   - **Client-Side Standalone Simulation Layer**: `frontend/src/lib/scan-engine.ts` and `fallback-data.json` provide a complete client-side mock/storage engine for static hosting on Cloudflare Pages (`noosforge-soc.pages.dev`). When the frontend is connected to the real backend, `fetchJson` queries `/api/v1/*` directly.

---

## 2. Engine Authenticity Matrix

| Engine / Component | Implementation Location | Invoked In Flow | Real Execution | Output Validated | Data Persisted | Classification | Notes / Evidence |
|---|---|---|---|---|---|---|---|
| **Nuclei Vulnerability Scanner** | `backend/app/scanners/nuclei.py` | Yes | Yes (Native CLI) | Yes (JSONL parsed) | Yes (noospire.db) | **REAL IMPLEMENTATION** | CLI binary verified at `C:\Users\nguye\go\bin\nuclei.exe` (v3.11.1). Subprocess execution, PID registration, and JSONL parser verified. |
| **Nuclei Lab Runner (Fallback)** | `backend/app/scanners/lab_runners.py` (lines 15-165) | Yes (Fallback) | Yes (Real HTTP via `httpx`) | Yes (Regex matchers) | Yes (noospire.db) | **REAL IMPLEMENTATION** | Evaluates 5 templates (.git/config, .env, CORS, /static/, Spring actuator) using genuine HTTP requests. Zero findings if target doesn't match. |
| **OWASP ZAP Adapter** | `backend/app/scanners/zap.py` | Yes | Partial (Lab runner invoked) | Yes | Yes (noospire.db) | **PARTIALLY IMPLEMENTED** | CLI command defined, but `zap.bat` absent on host; automatically routes to `ZAPLabRunner`. |
| **OWASP ZAP Lab Runner** | `backend/app/scanners/lab_runners.py` (lines 167-396) | Yes | Yes (Real HTTP via `httpx`) | Yes (Header audit & active probes) | Yes (noospire.db) | **REAL IMPLEMENTATION** | Live HTTP inspection of XFO, CSP, XCTO, Server headers. In `DEEP_ACTIVE`, runs real SQLi syntax & XSS canary reflection probes. |
| **Aqua Trivy Adapter** | `backend/app/scanners/trivy.py` | Yes (Archive/Image) | Partial (Lab runner invoked) | Yes | Yes (noospire.db) | **PARTIALLY IMPLEMENTED** | CLI command defined, but `trivy.exe` absent on host; routes to `TrivyLabRunner`. |
| **Aqua Trivy Lab Runner** | `backend/app/scanners/lab_runners.py` (lines 398-656) | Yes | Yes (Filesystem & manifest inspection) | Yes (Semantic version match & secrets) | Yes (noospire.db) | **REAL IMPLEMENTATION** | Real manifest parsing (`package.json`, `requirements.txt`), version comparison against CVEs, and regex secret scanning on source files. |
| **Empire Specialized Security Engine** | `backend/app/scanners/empire_engine.py` | Yes | Yes (Real HTTP via `httpx`) | Yes (Payload & header validation) | Yes (noospire.db) | **REAL IMPLEMENTATION** | Covers Modules A-G. Probes Better-Auth routes, BOLA endpoints, `/media` policies, news aggregator SSRF, BFLA, and bounded negative auth (5 probes). |
| **Async BFS Crawler** | `backend/app/scanners/crawler.py` | Yes (Web/Domain/API) | Yes (Real HTTP via `httpx`) | Yes (Same-origin link extraction) | Yes (Logged & indexed) | **REAL IMPLEMENTATION** | Bounded BFS queue, max depth 3, max pages 50, rate-limiting sleep, same-origin domain & port enforcement, cancellation token support. |
| **8-Step Live Target Verifier** | `backend/app/core/target_verifier.py` | Yes (`/assets/{id}/verify`) | Yes (Live socket, TLS, HTTP) | Yes (Step-by-step verdicts) | Yes (`assets` table updated) | **REAL IMPLEMENTATION** | All 8 steps verified live against `https://empire.edu.vn/`: DNS resolution, TLS handshake, HTTP latency, redirect trace, web discovery, fingerprint. |
| **Async Worker Dispatcher** | `backend/app/core/dispatcher.py` | Yes | Yes (AsyncIO worker pool) | Yes | Yes (SQLite WAL transactions) | **REAL IMPLEMENTATION** | Manages queue, concurrency semaphore (`min(MAX, CPU)`), per-asset locks, lifecycle transitions, and telemetry. |
| **Process Safety Manager** | `backend/app/core/dispatcher.py` (lines 160-199) | Yes | Yes (psutil process trees) | Yes | N/A (OS Process Table) | **REAL IMPLEMENTATION** | Tracks child PIDs, terminates recursive process trees on cancel/stop, kills remaining alive processes after 3s grace. |
| **System Resource Throttler** | `backend/app/core/dispatcher.py` (lines 46-74) | Yes | Yes (psutil CPU/RAM sampling) | Yes | N/A | **REAL IMPLEMENTATION** | Samples CPU% and RAM%. Delays dequeuing by 1.0s when host CPU > 90% or RAM > 95%. Verified active under empirical stress. |
| **ScanLogBuffer & SSE Streamer** | `backend/app/core/dispatcher.py` (lines 76-158) | Yes (`/scans/{id}/logs/stream`) | Yes (In-memory ring buffer & async pub/sub) | Yes | Yes (`scan_logs` table) | **REAL IMPLEMENTATION** | Ring buffer `deque(maxlen=1000)` with async queue pub/sub for SSE clients. Concurrently persists to `ScanLog` in SQLite with retry logic. |
| **Batch Scan Orchestrator** | `backend/app/api/scans.py` (`POST /scans/batch`) | Yes | Yes | Yes (Matrix expansion) | Yes (`scan_batches` & `scans`) | **REAL IMPLEMENTATION** | Dispatches synchronized scans across targets x profiles, enforces `DEEP_ACTIVE` ownership gate, updates batch progress. |
| **Loop Test Stability Engine** | `backend/app/api/scans.py` (`POST /scans/loop-test`) | Yes | Yes | Yes (Drift detection) | Yes (`scans`, `alerts`) | **REAL IMPLEMENTATION** | Executes sequential assessment passes (1-5), measures duration, tracks new finding drift, and creates lifecycle alerts per pass. |
| **Continuous Scheduler Engine** | `backend/app/core/scheduler.py` | Yes (Background task) | Yes (30s cron tick loop) | Yes | Yes (`schedules`, `scans`, `alerts`) | **REAL IMPLEMENTATION** | Evaluates active cron schedules in `Asia/Ho_Chi_Minh` timezone, dispatches queued scans to worker, updates `next_run_at`. |
| **SSRF Gatekeeper (SSRFProtector)** | `backend/app/core/ssrf.py` | Yes (Pre-flight on all scans) | Yes (DNS IP check & CIDR validation) | Yes | N/A (Security Gate) | **REAL IMPLEMENTATION** | Validates target URLs, resolves IPs, blocks loopback (`127.0.0.0/8`), private RFC1918, link-local, and cloud metadata (`169.254.169.254`). |
| **System Reset & Purge Engine** | `backend/app/api/system.py` & `logs.py` | Yes (`POST /system/reset`, `/logs/purge`) | Yes | Yes | Yes (Full DB purge & re-seed) | **REAL IMPLEMENTATION** | Stops active scans, clears log buffer, purges operational tables, re-seeds Empire ecosystem baseline, re-seeds Ultra Admin. |
| **Celery Dispatcher** | `backend/app/core/dispatcher.py` (lines 966-999) | No (Inactive by default) | No (Stub only) | No | No | **PLACEHOLDER / STUB** | Minimal logging stub; only selected if `DISPATCHER_MODE=celery`. Default is `async_worker`. |
| **Nmap Scanner** | `frontend/src/lib/api.ts` / `scan-engine.ts` | Frontend fallback only | No | No | No | **MOCK / SIMULATED** | Appears only in client-side fallback/mock telemetry. No backend adapter exists in `backend/app/scanners/`. |
| **Client-Side Simulation Layer** | `frontend/src/lib/scan-engine.ts` | Cloudflare Pages fallback only | Client simulation | LocalStorage | Browser LocalStorage | **SIMULATED / OFFLINE FALLBACK** | Designed for standalone offline hosting on Cloudflare Pages without backend. Bypassed when backend `/api/v1` is reachable. |

---

## 3. Deep Dive Technical Analysis

### 3.1. Nuclei Scanner CLI & NucleiLabRunner Fallback
- **Source Code**: `backend/app/scanners/nuclei.py`, `backend/app/scanners/lab_runners.py`
- **Native Binary Detection**: `shutil.which("nuclei")` or `shutil.which("nuclei.exe")`.
  - **Empirical Host Check**: Verified at `C:\Users\nguye\go\bin\nuclei.exe`.
  - **Command Executed**: `nuclei -version`
  - **Output**: `[INF] Nuclei Engine Version: v3.11.1` (ProjectDiscovery).
- **Execution Mechanism**:
  ```python
  cmd = [
      shutil.which("nuclei") or "nuclei",
      "-target", request.target_locator,
      "-jsonl",
      "-silent",
      "-nc",
      "-timeout", "5",
      "-tags", "cve,exposure",
      "-c", "10",
  ]
  proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
  await process_safety.register_pid(request.scan_id, proc.pid)
  stdout_data, stderr_data = await asyncio.wait_for(proc.communicate(), timeout=timeout_limit)
  ```
- **Process Safety**: The spawned PID is immediately recorded in `ProcessSafetyManager`. If the user cancels the scan or the platform triggers emergency stop, `proc.pid` and all child processes are killed.
- **Evidence Capture**: Each JSONL finding line is parsed; `matched-at`, `extracted-results`, `curl-command`, `request`, and `response` are structured into `NormalizedFindingCreate.evidence`.
- **Lab Runner Fallback**: If the native CLI encounters an error or is absent, `NucleiLabRunner` executes real HTTP GET requests against `/.git/config`, `/.env`, `/`, `/static/`, and `/actuator/env`. Regex patterns (`r"\[core\]"`, `r"(DB_PASSWORD|SECRET_KEY)"`, etc.) are evaluated against the actual response body. If the endpoint does not leak information, no finding is generated.

---

### 3.2. OWASP ZAP & Aqua Trivy Adapters
- **Source Code**: `backend/app/scanners/zap.py`, `backend/app/scanners/trivy.py`
- **Native Binary Status on Host**:
  - `Get-Command zap*, trivy*`: Returned 0 results. Neither `zap.bat` nor `trivy.exe` is installed on PATH.
- **Fallback Verification**:
  - **ZAP**: Automatically falls back to `ZAPLabRunner` (`execution_mode="lab_engine"`).
    - Real HTTP requests via `httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True)`.
    - Passive checks inspect actual target headers: Clickjacking (`X-Frame-Options` & CSP `frame-ancestors`), `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, and `Server` / `X-Powered-By` banner disclosures.
    - Active checks: Strictly gated to `DEEP_ACTIVE` profile and verified target assets. Sends SQL injection error-based probes (`' OR '1'='1`) and Reflected XSS canary probes (`<s3nt1n3l_xss_probe>`).
  - **Trivy**: Automatically falls back to `TrivyLabRunner`.
    - Real filesystem inspection: Traverses `target_path`, parses `package.json` and `requirements.txt`.
    - Compares installed package versions against known vulnerable thresholds (`max_vulnerable`) for CVE-2021-23337 (lodash), CVE-2020-28168 (axios), CVE-2023-32681 (requests), CVE-2023-45803 (urllib3), CVE-2023-49083 (cryptography).
    - Scans source code files for secret regexes (AWS keys, GitHub PATs, private keys, Slack webhooks), masking tokens in evidence.

---

### 3.3. Empire Specialized Security Engine
- **Source Code**: `backend/app/scanners/empire_engine.py`
- **Designation**: Tailored security assessment engine specifically designed for the Empire Educational Ecosystem (`https://empire.edu.vn/`).
- **Module Coverage (Modules A through G)**:
  1. **Module A (Student Management & Auth)**: Probes `/api/auth/sign-in/email`, `/api/users/profile`, `/social/v2/groups` for unauthenticated PII leakage. Evaluates horizontal privilege escalation (IDOR/BOLA) on `/api/users/{id}/learning-records`.
  2. **Module B (Educational Materials & /media Policy)**: Validates approved anonymous access on `/media/public-course.pdf` (`PUBLIC_BY_DESIGN`, zero false positives). Probes unintended sensitive files (`/media/student-records.csv`, `/media/.env`, `/media/passwords.txt`) and MinIO directory indexing.
  3. **Module C (Supporting Tools & News Aggregation)**: Probes `/news/api/fetch-feed` for SSRF vectors (sending AWS metadata IP `169.254.169.254`). Probes `/news/search` for reflected XSS.
  4. **Module D (API Security OWASP Top 10)**: Probes unauthenticated administrative endpoints (`/api/admin/system-status`, `/api/admin/users/export`, `/api/v1/internal/config`). Checks for presence of `RateLimit-*` response headers on `/api/courses/list`.
  5. **Module E (Web Application Security)**: Verifies CSP headers, Clickjacking defenses, and cookie security flags (`Secure`, `HttpOnly`, `SameSite`).
  6. **Module F (Controlled Negative-Auth Defense Audit)**: Executes exactly 5 controlled negative-authentication attempts with synthetic non-existent credentials (`audit_synthetic_probe@empire.local`) against `/api/auth/sign-in/email`. Measures response codes, elapsed request durations, and presence of `429 Too Many Requests` or `Retry-After` headers.
  7. **Module G (Server & Cloud Infrastructure)**: Checks server banner disclosure, HTTP Strict Transport Security (HSTS), and public exposure of `/server-status`.

---

### 3.4. 8-Step Live Target Verification Engine
- **Source Code**: `backend/app/core/target_verifier.py`
- **API Endpoint**: `POST /api/v1/assets/{id}/verify`
- **Live Verification Evidence** (Executed against `https://empire.edu.vn/` in `test_platform_core_m1.py` and passed in 19.51s):
  1. **Step 1: Input Validation**: Validates URL scheme (`https`), hostname (`empire.edu.vn`), port (443), and invokes `SSRFProtector.validate_target()`. Verdict: `PASS`.
  2. **Step 2: DNS Resolution**: Invokes `asyncio.get_running_loop().getaddrinfo("empire.edu.vn", 443)`. Resolves real public IP addresses (`103.20.144.12` / IPv6). Verdict: `PASS`.
  3. **Step 3: TLS Verification**: Establishes raw TCP socket connection, wraps with `ssl.create_default_context()`, performs SNI TLS handshake with `server_hostname="empire.edu.vn"`. Inspects certificate subject, issuer, SAN list, TLS version (`TLSv1.3`), cipher (`TLS_AES_256_GCM_SHA384`), and calculates remaining validity days. Verdict: `PASS`.
  4. **Step 4: HTTP Connectivity**: Executes `httpx.get()` with `follow_redirects=False`. Measures round-trip latency in milliseconds, status code (200 OK or 301/308 redirect), HTTP version (`HTTP/2` or `HTTP/1.1`), and server headers. Verdict: `PASS`.
  5. **Step 5: Redirect Inspection**: Follows hop-by-hop redirects with `max_redirects=10`. Inspects landing URL. Detects insecure protocol downgrade (HTTPS redirected to plain HTTP). Verdict: `PASS`.
  6. **Step 6: Web Discovery**: Concurrently probes standard files (`/robots.txt`, `/sitemap.xml`, `/.well-known/security.txt`) using `asyncio.gather()`. Reports accessibility and status codes. Verdict: `PASS`.
  7. **Step 7: Target Fingerprint**: Analyzes response headers and HTML body. Detects reverse proxy/WAF (`Envoy Reverse Proxy`), frontend framework (`Next.js (React Framework)`), and counts active baseline security headers (HSTS, CSP, XFO, XCTO, Referrer-Policy). Verdict: `PASS`.
  8. **Step 8: Verification Result**: Requires critical passes across Steps 1-5. Computes total elapsed duration. Sets overall status to `VERIFIED`. Updates `Asset.verification_status="VERIFIED"`, `Asset.technology="Envoy / Next.js / React"`, and persists timestamp in database. Verdict: `PASS`.

---

### 3.5. Batch Scan Orchestrator & Device Resource Throttling
- **Source Code**: `backend/app/api/scans.py` (`POST /scans/batch`, `POST /scans/scan-all`)
- **Matrix Expansion**:
  - Accepts targets: `"ALL"` or list of asset UUIDs.
  - Accepts profiles: list of profiles (default: `BASELINE`, `DAILY_SECURITY`, `STANDARD`).
  - Accepts engines: list of engines (default: `["all"]`).
  - Creates `ScanBatch` in `ScanStatus.QUEUED`.
  - Expands target x profile combinations into individual `Scan` rows.
  - Security Gate: If a scan specifies `DEEP_ACTIVE` and the target is not verified, it is immediately marked `FAILED` with quality status `AUTH_REQUIRED`, preventing unauthorized active testing.
- **Resource Throttling (`psutil`)**:
  - In `backend/app/core/dispatcher.py`, `check_system_resources()` samples:
    ```python
    cpu_pct = float(psutil.cpu_percent(interval=None))
    mem = psutil.virtual_memory()
    is_throttled = bool(cpu_pct > 90.0 or mem.percent > 95.0)
    ```
  - In `_worker_loop()`:
    ```python
    if res_info.get("is_throttled", False):
        logger.warning(f"Resource throttling active: CPU {cpu_pct}%, RAM {mem.percent}%. Delaying next scan dequeuing by 1.0s...")
        await asyncio.sleep(1.0)
    ```
  - **Empirical Observation**: During our execution of `scripts/verify_empire_e2e.py` and adversarial stress tests, the live console logged:
    `Resource throttling active: CPU 98.8%, RAM 93.0%. Delaying next scan dequeuing by 1.0s...`
    Proving that host resource monitoring and throttling is genuinely active and enforced at runtime.
- **Cooperative Cancellation & Emergency Stop**:
  - `POST /api/v1/scans/{id}/cancel`: Sets `CancellationToken.cancel()`, invokes `process_safety.terminate_process_tree(scan_id)`, transitions scan status to `CANCELLED`.
  - `POST /api/v1/scans/batch/{id}/cancel`: Cancels all scans in the batch, terminates process trees, instantly purges cancelled scan IDs from in-memory queue to prevent backlog execution.
  - `POST /api/v1/scans/stop-all`: Emergency platform-wide kill switch halting all active worker threads and queued scans.
- **Active Worker Thread Matrix ("trackcurrent")**:
  - `GET /api/v1/scans/trackcurrent`: Returns real-time telemetry:
    ```json
    {
      "active_workers": 2,
      "max_concurrency": 4,
      "queued_count": 0,
      "completed_count": 14,
      "is_throttled": false,
      "system_resources": { "cpu_percent": 18.2, "memory_percent": 42.1 },
      "active_threads": [
        {
          "thread_id": 1,
          "scan_id": "...",
          "target_locator": "https://id.empire.edu.vn",
          "profile": "DAILY_SECURITY",
          "stage": "active",
          "progress_percentage": 50,
          "elapsed_seconds": 12,
          "last_log": "Dispatching execution to adapter: nuclei"
        }
      ],
      "trackcurrent": { ... }
    }
    ```

---

### 3.6. Finding Deduplication & Quality State Machine
- **SHA-256 Finding Fingerprint**:
  - Location: `backend/app/scanners/base.py` line 48:
    ```python
    def compute_finding_fingerprint(asset_id, scanner_engine, scanner_rule_id, target_location, target_component):
        raw_key = f"{asset_id}:{norm_engine}:{norm_rule}:{norm_location}:{norm_component}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    ```
  - **Collision Resistance**: Two findings on the same asset with identical engine, rule ID, location, and component produce the exact same SHA-256 hash.
  - **Lifecycle Updates**:
    - If finding exists: updates `occurrence_count += 1`, updates `last_seen_at`.
    - Regression detection: If existing finding was `FIXED` or `RESOLVED`, status transitions to `REOPENED` and emits a warning log and in-app `SecurityAlert`.
    - If new finding: inserts `NormalizedFinding`. If `CRITICAL` or `HIGH`, creates a `SecurityAlert` (category: `"VULN"`).
- **Scanner Quality State Machine (5 Explicit States)**:
  1. `SCANNED_SUCCESSFULLY`: All configured scanner adapters executed to completion with zero runtime errors.
  2. `PARTIAL_COVERAGE`: At least one scanner adapter succeeded, but one or more encountered non-fatal errors, timeouts, or unverified active scan gates.
  3. `AUTH_REQUIRED`: Zero scanners succeeded because asset ownership or authentication credentials were required.
  4. `TARGET_UNAVAILABLE`: Target was unreachable due to DNS resolution failure, network timeout, or connection refusal.
  5. `SCANNER_FAILED`: All scanner adapters returned non-zero exit codes or unhandled execution exceptions.
  - Evaluated in `backend/app/core/dispatcher.py` lines 898-928; updates `Scan.quality_status` in the database and emits a lifecycle `SecurityAlert` (category: `"SCAN"`).

---

### 3.7. Operational Logs, Maintenance & System Reset
- **Logs Management (`/api/v1/logs`)**:
  - `GET /api/v1/logs`: Real-time querying of `ScanLog` with filters for `days` (past N days), `from_date`, `to_date`, `level`, `source`, and `search`.
  - `GET /api/v1/logs/export`: Exports operational logs directly in JSON or CSV format.
  - `POST /api/v1/logs/purge`: Purges logs older than N days, or for specific scan ID, or entirely (`purge_all=True`), and clears in-memory buffer.
- **System State Reset (`POST /api/v1/system/reset`)**:
  - Halts all background workers and scans (`dispatcher.stop_all()`).
  - Clears in-memory log buffer (`log_buffer.clear_all()`).
  - Deletes all rows from `ScanLog`, `Scan`, `ScanBatch`, `NormalizedFinding`, `SecurityAlert`, `AdminAuditLog`, `BaselineException`, `DailySchedule`, `SyntheticIdentity`, `Asset`.
  - Re-seeds Empire ecosystem primary target (`https://empire.edu.vn/`) and 6 functional modules via `seed_empire_ecosystem()`.
  - Re-seeds Ultra Admin (`dangnhutnguyen0910@gmail.com` with `REDACTED-ROTATE-ME`).
  - Adds audit trail entry and baseline alert.
  - Fully fulfills user directive: "xóa logs- kiểm tra kỹ, đdầyddur, hoàn toàn - lưu logs, xóa logs, quay về trạng thái ban đầu, track by days...".

---

## 4. End-to-End Execution Trace

```
[User Action on Frontend]
   │
   ├─► Click "Scan All" / "Launch Scan" in /scans or /active-assessments
   │
[API Layer]
   │
   ├─► POST /api/v1/scans/batch (or POST /api/v1/scans)
   │     ├─► Validates target assets against Asset inventory
   │     ├─► Enforces DEEP_ACTIVE security gate (blocks unverified assets)
   │     ├─► Inserts ScanBatch & Scan rows into SQLite (noospire.db)
   │     └─► Calls get_dispatcher().dispatch_scan(scan_id)
   │
[Dispatcher Layer]
   │
   ├─► AsyncWorkerDispatcher.dispatch_scan()
   │     ├─► Puts scan_id into asyncio.Queue
   │     └─► Appends log to ScanLogBuffer ring buffer
   │
[Worker Loop & Resource Gate]
   │
   ├─► check_system_resources() (psutil)
   │     ├─► If CPU > 90% or RAM > 95%: Delays dequeue by 1.0s
   │     └─► Semaphore bounds active threads to min(MAX_CONCURRENT, CPU_COUNT)
   │
[Per-Asset Mutual Exclusion]
   │
   ├─► Acquires asset_locks[asset_id] (prevents race conditions on same target)
   │
[Execution Engine Pipeline]
   │
   ├─► Stage 1 (Pre-flight): SSRFProtector.validate_target() -> IP resolution & CIDR check
   ├─► Stage 2 (Discovery): AsyncBFSCrawler.crawl() -> Bounded same-origin BFS crawl
   ├─► Stage 3 (Active Scanning):
   │     ├─► NucleiAdapter: Executes native nuclei.exe v3.11.1 (or NucleiLabRunner)
   │     ├─► ZAPAdapter: Executes ZAPLabRunner (real passive/active HTTP probes)
   │     └─► TrivyAdapter: Executes TrivyLabRunner (real package/secret scans)
   ├─► Stage 4 (Empire Specialized): EmpireAssessmentEngine.execute_empire_assessment()
   │     └─► Real HTTP probes across Modules A, B, C, D, E, F, G
   │
[Result Processing & Deduplication]
   │
   ├─► For each finding: compute_finding_fingerprint() (SHA-256)
   ├─► If exists in DB: increments occurrence_count, detects REOPENED regression
   ├─► If new in DB: inserts NormalizedFinding; if Critical/High, adds SecurityAlert
   │
[Quality State Determination]
   │
   ├─► Evaluates adapter success/error list
   ├─► Sets quality_status: SCANNED_SUCCESSFULLY, PARTIAL_COVERAGE, AUTH_REQUIRED, etc.
   ├─► Emits lifecycle SecurityAlert (category="SCAN")
   ├─► Updates ScanBatch progress percentage
   │
[Persistence Layer]
   │
   └─► Commits all changes to noospire.db (SQLite with WAL mode)
   │
[Real-Time Streaming & Frontend Hydration]
   │
   ├─► SSE Stream: GET /api/v1/scans/{id}/logs/stream via EventSource
   ├─► Telemetry HUD: GET /api/v1/scans/trackcurrent (polls active worker matrix)
   ├─► Findings View: GET /api/v1/findings displays new findings in table
   └─► Dashboard View: GET /api/v1/metrics/overview updates KPI cards and charts
```

---

## 5. Exposing Simulated & Disconnected Modules

In strict accordance with the audit guidelines (**Section 2.2: No fake success** and **Section 14: Ultimate Acceptance Criterion**), the following discrepancies and simulations are explicitly cataloged:

### 1. Nmap Network Scanner (SIMULATED in Frontend Fallback)
- **Claimed in UI / Fallback**: `frontend/src/lib/api.ts` line 388, 723-731; `frontend/src/lib/scan-engine.ts` lines 278-280 claim `Nmap Network & Port Recon` (driver: `NmapSubprocessAdapter`, version: 7.94).
- **Backend Reality**: **DOES NOT EXIST**. There is no `nmap.py` or Nmap subprocess adapter in `backend/app/scanners/`. The backend uses standard Python `socket.getaddrinfo()` in `target_verifier.py` for port/socket checks.
- **Classification**: **MOCK / SIMULATED IN FRONTEND FALLBACK**.
- **Impact**: When the backend is operational, Nmap is not listed or executed. It only appears in the static offline demo mode.

### 2. Celery Distributed Dispatcher (STUB / PLACEHOLDER)
- **Claimed in Code**: `backend/app/core/dispatcher.py` lines 966-999 (`CeleryDispatcher`).
- **Backend Reality**: Minimal stub methods (`dispatch_scan`, `cancel_scan`, `get_telemetry`) containing only `logger.info()` and returning hardcoded 0 counts.
- **Classification**: **PLACEHOLDER**.
- **Impact**: Non-blocking because `settings.DISPATCHER_MODE` defaults to `async_worker`, which routes all tasks to the fully functional `AsyncWorkerDispatcher`.

### 3. Client-Side Standalone Simulation Layer (SIMULATED FOR CLOUDFLARE PAGES)
- **Location**: `frontend/src/lib/scan-engine.ts`, `frontend/src/lib/fallback-data.json`.
- **Purpose**: Cloudflare Pages (`noosforge-soc.pages.dev`) is a static asset host without an active Python server. The developers implemented `scan-engine.ts` to allow frontend demonstration without backend connection errors.
- **Backend Reality**: In full-stack production, `api.ts` invokes real HTTP `fetch` to `/api/v1/*`. Only if `fetch` throws a network error does `api.ts` drop into `handleFallback`.
- **Classification**: **OFFLINE DEMO FALLBACK**.

---

## 6. Empirical Verification Command Log

All test commands were executed directly on the workspace:

1. **Empire End-to-End Capability Test Suite**:
   - Command: `python scripts/verify_empire_e2e.py`
   - Exit Code: `0`
   - Result: **10/10 PASS (100% Xanh Mượt)**
   - Resource throttling verified active during test: `Resource throttling active: CPU 98.8%, RAM 93.0%. Delaying next scan dequeuing by 1.0s...`
   - Verified real artifact generation: PDF (5.99 KB), HTML (12.23 KB), JSON (2.53 KB).

2. **Milestone M2 & M8 Scanning & Batch Test Suites**:
   - Command: `pytest tests/test_scan_intelligence_m2.py tests/test_scan_all_batch_orchestration.py -v`
   - Exit Code: `0`
   - Result: **25/25 PASS (100%)**

3. **Platform Core & 8-Step Target Verifier Live Probes**:
   - Command: `pytest tests/test_platform_core_m1.py -v`
   - Exit Code: `0`
   - Result: **9/9 PASS (100%)**
   - Verified live 8-step probe against `https://empire.edu.vn/`: DNS resolution, TLS certificate handshake, HTTP latency measurement, redirect tracing, web discovery, and Envoy/Next.js fingerprinting.

4. **Empirical Adversarial Stress & Process Safety Suite**:
   - Command: `pytest tests/test_m8_empirical_adversarial_stress.py -v`
   - Exit Code: `0`
   - Result: **6/6 PASS (100%)**
   - Verified real OS subprocess tree termination without zombies, SQLite WAL concurrent read/write stress, emergency stop-all, and rapid batch cancellation.

5. **Total Automated Pytest Collection**:
   - Command: `pytest --collect-only -q`
   - Result: **260 tests collected** across all modules.

6. **Frontend Static Checks**:
   - Command: `npm --prefix frontend run typecheck`
     - Result: `tsc --noEmit` exited `0` (Zero TypeScript compilation errors).
   - Command: `npm --prefix frontend run lint`
     - Result: `next lint` exited `0` (`✔ No ESLint warnings or errors`).

---

## 7. Final Assessment & Recommendations

1. **Overall Engine Maturity**: **PRODUCTION READY (for Local Async / Nuclei / Empire Engine / Target Verifier / Crawler)**.
   - The primary engines (Nuclei CLI v3.11.1, Empire Assessment Engine, Async BFS Crawler, 8-Step Live Target Verifier, AsyncWorkerDispatcher, ScanLogBuffer SSE stream) are authentic, non-fabricated, and production-operational.
2. **Native ZAP & Trivy Recommendation**:
   - If full native CLI execution is desired for ZAP and Trivy in addition to Nuclei, install `zap.bat` (OWASP ZAP) and `trivy.exe` (Aqua Security Trivy) and ensure their directories are added to system `PATH`. The adapters are already fully coded to execute them automatically once detected.
3. **Nmap Clarification**:
   - Remove or label Nmap references in `frontend/src/lib/api.ts` and `scan-engine.ts` to prevent user expectation of an Nmap daemon when running connected to the FastAPI backend.
