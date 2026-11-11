# TECHNICAL INVESTIGATION REPORT — EXPLORER SURVEY 2
**Platform**: NOOSFORGE Security Intelligence (`noospire`)  
**Target Environment**: Empire Educational Platform (`https://empire.edu.vn/`)  
**Investigator**: `explorer_survey_2`  
**Timestamp**: 2026-11-08T12:45:00Z  

---

## 1. Executive Summary

This investigation analyzed the codebase at `c:\Users\nguye\Desktop\noospire` with deep focus on:
1. **Scan Center & Real Scanner Orchestration** (integrations, ProjectDiscovery tools, OWASP ZAP, process safety, bounded crawling).
2. **Raw HTTP Evidence Storage, Scanner Audit Trails, and Execution Records**.
3. **Scanner Quality State Machines** (explicit coverage/failure states vs. generic completed/failed).
4. **Empire Business Module Security Taxonomy** across all business areas starting from root target `https://empire.edu.vn/`.
5. **Finding Deduplication, Evidence Viewer Schemas, Risk Prioritization, and Remediation Tracking Lifecycle**.

### Key Baseline Findings:
- **E2E Test Suite Status**: Automated suite `scripts/verify_empire_e2e.py` passes **10/10 tests (100% PASS)** against live FastAPI backend and SQLite database `noospire.db`.
- **Live Target Accessibility**: `https://empire.edu.vn/` is **live and reachable** (HTTP 200, `server: envoy`, `x-powered-by: Next.js`, HSTS, frame-ancestors CSP). Subdomains `https://id.empire.edu.vn` (HTTP 404 Better-Auth gateway), `https://gw.empire.edu.vn` (HTTP 404 API gateway), `https://mh.empire.edu.vn/media` (HTTP 403 MinIO object storage), and `https://voh.empire.edu.vn` (HTTP 400 MinIO S3 API) are all live, operational services.
- **Scanner Execution Fidelity**: The platform uses real HTTP requests via `httpx.AsyncClient` and native CLI processes. Zero mock/synthetic data generators were found in scan runners.
- **ProjectDiscovery & Native Tooling**: `nuclei.exe` v3.11.1 is installed on host (`C:\Users\nguye\go\bin\nuclei.exe`). Native OWASP ZAP binary is absent, and the ZAP adapter currently uses a high-fidelity embedded lab runner. ProjectDiscovery `httpx` and bounded web crawling tools are not yet integrated.
- **Quality State Machine Gap**: The current system only supports linear task lifecycle states (`PENDING` -> `QUEUED` -> `INITIALIZING` -> `RUNNING` -> `COMPLETED`/`FAILED`). It lacks the explicit quality states required by R2 (`scanned successfully`, `partial coverage`, `auth required`, `scanner failed`, `target unavailable`).
- **Primary Target Gap**: Root portal `https://empire.edu.vn/` is not yet seeded in `empire_seeder.py` as an asset; only subdomains were seeded.
- **Frontend & Internationalization Gap**: All 14 views exist in Next.js 14 App Router, but the UI is strictly English-only with no bilingual dictionary or locale switcher (violating R4).

---

## 2. Focus Area 1: Scan Center & Real Scanner Orchestration

### 2.1 Existing Scanner Integrations
Located in `backend/app/scanners/`:
- **`NucleiAdapter` (`nuclei.py`)**:
  - Implements `BaseScannerAdapter`.
  - Supports `AssetType.DOMAIN`, `AssetType.WEB_APP`, `AssetType.API_ENDPOINT`.
  - Native binary detection via `shutil.which("nuclei")` or `shutil.which("nuclei.exe")`.
  - CLI invocation command: `[nuclei, -target <url>, -jsonl, -silent, -nc, -timeout 5]`.
  - Parses JSON lines from stdout (`tmpl_id`, `info.severity`, `classification.cve-id`, `matched-at`, `extracted-results`, `request`, `response`, `curl-command`).
  - Fallback: When binary execution fails or binary is absent, calls `NucleiLabRunner().run(...)`.
- **`ZAPAdapter` (`zap.py`)**:
  - Implements `BaseScannerAdapter`.
  - Checks for native ZAP binary via `shutil.which("zap.bat")`, `zap.sh`, `zap`.
  - Active scan authorization gate: If `profile == "DEEP_ACTIVE"`, checks `request.custom_config.get("is_verified", False)`. Raises `PermissionError` if unverified.
  - Native execution block at line 116 currently contains a placeholder `pass` and delegates to `ZAPLabRunner().run(...)`.
- **`TrivyAdapter` (`trivy.py`)**:
  - Implements `BaseScannerAdapter`.
  - Supports `AssetType.PROJECT_ARCHIVE`, `AssetType.CONTAINER_IMAGE`.
  - Checks for `trivy` or `trivy.exe`. Command: `[trivy fs --format json --security-checks vuln,secret <path>]`.
  - Parses `Vulnerabilities` (SCA dependencies) and `Secrets` (hardcoded keys).
  - Fallback: Delegates to `TrivyLabRunner().run(...)` which inspects `package.json`, `requirements.txt`, and secret patterns.
- **`EmpireAssessmentEngine` (`empire_engine.py`)**:
  - Specialized 577-line engine dedicated to Empire platform business logic.
  - Divided into 5 sub-auditors:
    - Module A: Student Management & Authentication (Better-Auth routes, BOLA/IDOR on learning records).
    - Module B: Educational Material & `/media` Approved Policy (`PUBLIC_BY_DESIGN` validation vs sensitive leaks).
    - Module C: Supporting Educational Tools (News RSS feed SSRF, search XSS).
    - Module D: OWASP API Security Top 10 (Administrative BFLA, rate limiting).
    - Module F: Controlled Brute-Force & Negative-Auth Defense (5 bounded probes).

### 2.2 Process Safety & Execution Mechanics
Located in `backend/app/core/dispatcher.py`:
- **Dispatcher Architecture**:
  - Default: `AsyncWorkerDispatcher` using `asyncio.Queue[uuid.UUID]`, `asyncio.Semaphore(max_concurrent=4)`, and per-asset locks (`asset_locks: Dict[uuid.UUID, asyncio.Lock]`) to prevent concurrent overlapping scans on the same target.
  - Alternative: `CeleryDispatcher` interface for enterprise message broker configurations.
- **Process Termination**:
  - `ProcessSafetyManager` tracks scan PIDs.
  - `terminate_process_tree(scan_id)` uses `psutil.Process(pid)` to recursively terminate and kill child processes with `psutil.wait_procs(..., timeout=3)`.
  - **Implementation Bug Identified**: In `nuclei.py:131` and `trivy.py:163`, `proc = await asyncio.create_subprocess_exec(...)` is invoked, but `proc.pid` is **never registered** with `process_safety.register_pid(request.scan_id, proc.pid)`. As a result, cancelling a scan via `cancel_scan` does not kill external `nuclei.exe` or `trivy.exe` subprocesses.
- **Cancellation**:
  - `CancellationToken` cooperative flag passed through execution chain. Checked between scanner adapters and sub-modules.

### 2.3 Scope Matching, SSRF Defense, and Bounded Crawling
- **SSRF Validation**:
  - `SSRFProtector.validate_target` (`backend/app/core/ssrf.py`):
    - Parses URL scheme (`http`, `https`).
    - Resolves host DNS to IPv4/IPv6.
    - Validates against blocked CIDRs (loopback `127.0.0.0/8`, private `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, AWS/cloud metadata `169.254.169.254/32`, carrier-grade NAT `100.64.0.0/10`, IPv6 loopback/unique-local).
    - Supports `allow_private=True` flag for local development and test harness targets.
- **Bounded Crawling Analysis**:
  - **Critical Gap**: There is **no web crawler** currently implemented in the codebase.
  - All scanner adapters probe fixed, hardcoded endpoints (e.g. `/`, `/api/auth/sign-in/email`, `/.git/config`, `/.env`, `/media/public-course.pdf`, etc.).
  - To meet Requirement R2 ("bounded HTTP/crawling"), an asynchronous same-origin BFS crawler is required (bounded by `max_depth` e.g. 3, `max_pages` e.g. 50, same-domain origin check, and exclusion of logout/destructive endpoints).

---

## 3. Focus Area 2: Raw HTTP Evidence Storage & Scanner Audit Trails

### 3.1 Raw Request/Response Evidence Schema
- **Database Model**: `NormalizedFinding` (`backend/app/models/finding.py`):
  - `evidence`: `Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)`
  - `raw_payload`: `Mapped[Optional[str]] = mapped_column(Text, nullable=True)`
- **Pydantic Schema**: `FindingEvidence` (`backend/app/schemas/finding.py`):
  ```python
  class FindingEvidence(BaseModel):
      request: Optional[str] = None          # Full raw HTTP request line and headers
      response: Optional[str] = None         # Raw HTTP response status, headers, and body snippet
      matched_content: Optional[str] = None  # Exact matched regex substring or signature
      curl_command: Optional[str] = None     # Reproducible curl CLI string
      file_path: Optional[str] = None        # Source file or target URI path
      line_number: Optional[int] = None      # Source code or manifest line number
      parameter: Optional[str] = None        # Exploited query param, header, or body field
      raw_payload: Optional[str] = None      # Exact attack probe payload
  ```
- **Evidence Construction Fidelity**:
  - In `NucleiLabRunner` (`lab_runners.py:124-130`), authentic raw HTTP requests and responses are assembled directly from the `httpx.Response` object:
    ```python
    req_str = f"{tmpl['method']} {tmpl['path']} HTTP/1.1\r\nHost: {urlparse(url).netloc}\r\n..."
    resp_headers_str = "\r\n".join(f"{k}: {v}" for k, v in resp.headers.items())
    resp_str = f"HTTP/1.1 {resp.status_code} {resp.reason_phrase}\r\n{resp_headers_str}\r\n\r\n{body_text[:1024]}"
    ```
  - In `ZAPLabRunner` (`lab_runners.py:212-216`), HTTP response status and complete headers are captured verbatim.
  - In `EmpireAssessmentEngine` (`empire_engine.py:561-568`), exact status codes, response snippets, probe counts, and latency arrays are stored.

### 3.2 Scanner Audit Trails
- **Persistent Database Audit Logs**:
  - `ScanLog` model (`backend/app/models/scan.py:60-75`):
    - `id`: GUID primary key.
    - `scan_id`: Foreign key to `scans.id` (CASCADE delete).
    - `timestamp`: UTC datetime.
    - `level`: `INFO`, `WARNING`, `ERROR`, `DEBUG`.
    - `message`: Text log description.
    - `source`: Source engine or subsystem (`system`, `nuclei`, `zap`, `empire_engine`, `lifecycle`).
- **Low-Latency Streaming Buffer**:
  - `ScanLogBuffer` (`backend/app/core/dispatcher.py:42-102`):
    - Async thread-safe in-memory ring buffer using `collections.deque(maxlen=1000)`.
    - Broadcasts to SSE subscriber queues (`asyncio.Queue[ScanLogEntry]`).
    - API Endpoint `/api/v1/scans/{scan_id}/logs/stream` streams live logs using `fastapi.responses.StreamingResponse` (`text/event-stream`).
    - REST Endpoint `/api/v1/scans/{scan_id}/logs` provides paginated query access.

### 3.3 Execution Records & Telemetry
- `Scan` model (`backend/app/models/scan.py`):
  - Tracks `id`, `asset_id`, `engine`, `profile`, `status`, `progress_percentage` (0-100), `target_locator`, `started_at`, `completed_at`, `timeout_seconds`, and `error_message`.
  - Active scan details are monitored by `ActiveAssessmentsPage` (`frontend/src/app/active-assessments/page.tsx`), providing live progress bars and real-time terminal output.

---

## 4. Focus Area 3: Scanner Quality State Machines

### 4.1 Current Scan State Model
The current `ScanStatus` enum (`backend/app/schemas/common.py:53-63`) represents task execution status rather than assessment coverage quality:
```python
class ScanStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
```

### 4.2 Quality State Machine Gap Analysis
Requirement R2 and Acceptance Criteria demand an explicit quality state machine:
1. `scanned successfully` (FULL_COVERAGE): All selected scanner adapters and assessment modules executed completely without critical probe failures.
2. `partial coverage` (PARTIAL_COVERAGE): Scanner executed, but some sub-modules timed out, crawler reached bounded limit, or secondary adapter threw an error.
3. `auth required` (AUTH_REQUIRED): Target returned HTTP 401/403 across core endpoints, blocking authenticated inspection because credentials were not supplied or expired.
4. `scanner failed` (SCANNER_FAILED): Underlying scanner binary crashed, exited with unhandled non-zero code, or unhandled internal adapter exception.
5. `target unavailable` (TARGET_UNAVAILABLE): Target host could not be reached (DNS NXDOMAIN, connection refused, connection timeout, SSL handshake failure).

**Defects in Current Codebase**:
- In `dispatcher.py:353`, when an adapter throws an exception during a scan, it logs a warning `f"Adapter error: {e}"` and continues. At the end of the scan (line 458), the scan status is unconditionally set to `ScanStatus.COMPLETED.value`.
- As a consequence, a scan where all adapters failed to connect still marks itself as `COMPLETED` with 0 findings, creating a dangerous false sense of security.
- **Recommended Solution**:
  - Add a dedicated field `quality_status` to `Scan` model:
    ```python
    class ScanQualityState(str, Enum):
        SCANNED_SUCCESSFULLY = "SCANNED_SUCCESSFULLY"
        PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
        AUTH_REQUIRED = "AUTH_REQUIRED"
        SCANNER_FAILED = "SCANNER_FAILED"
        TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
    ```
  - Transition logic in `dispatcher.py`:
    - If DNS/HTTP connectivity check fails: set `quality_status = TARGET_UNAVAILABLE`.
    - If all probes receive 401/403: set `quality_status = AUTH_REQUIRED`.
    - If some adapters succeed and some fail: set `quality_status = PARTIAL_COVERAGE`.
    - If all succeed: set `quality_status = SCANNED_SUCCESSFULLY`.

---

## 5. Focus Area 4: Empire Business Module Security Taxonomy

### 5.1 Business Modules Architecture
Empire Educational Platform architecture is modeled in `backend/app/schemas/common.py:18-25` and `backend/app/api/empire_modules.py:16-53`:
```python
class EmpireModule(str, Enum):
    STUDENT_MANAGEMENT = "STUDENT_MANAGEMENT"
    LEARNING_MATERIALS = "LEARNING_MATERIALS"
    SUPPORTING_TOOLS = "SUPPORTING_TOOLS"
    API_SERVICES = "API_SERVICES"
    WEB_APPLICATION = "WEB_APPLICATION"
    SERVER_INFRASTRUCTURE = "SERVER_INFRASTRUCTURE"
```

### 5.2 Complete Security Taxonomy Breakdown

| Module | Primary Subdomains / Targets | Technology Stack | Core Security Vectors & Audit Rules | Baseline Policy |
|---|---|---|---|---|
| **Student Management & Identity** | `https://id.empire.edu.vn`, `https://gw.empire.edu.vn` | Better-Auth, Node.js, Next.js, PostgreSQL | - Unauthenticated student/user profile leakage (`EMPIRE-STUDENT-LEAK-01`)<br>- Broken Object-Level Authorization (BOLA/IDOR) on learning records (`EMPIRE-STUDENT-BOLA-02`)<br>- Credential spraying and user enumeration (`VULN-03`)<br>- Anti-automation & brute-force resistance (`EMPIRE-AUTH-BRUTEFORCE-01`) | Negative auth probe bounded to 5 attempts with synthetic identity |
| **Learning Materials & Content** | `https://mh.empire.edu.vn/media`, `https://voh.empire.edu.vn` | MinIO S3 Object Storage, Nginx, Static CDN | - Public anonymous bucket listing / MinIO exposure (`VULN-01`, `EMPIRE-MEDIA-DIRLIST-02`)<br>- Unintended sensitive files in `/media` (`EMPIRE-MEDIA-LEAK-01`: `.env`, `passwords.txt`, `student-records.csv`, `backup.zip`)<br>- Proprietary course video HLS & exam answer leakage (`VULN-05`) | **Approved Public Media Policy**: `/media/*` is `PUBLIC_BY_DESIGN` for curriculum previews; zero false alerts for public assets |
| **Supporting Educational Tools** | `https://gw.empire.edu.vn/news` | News Aggregator, English Vocabulary Service | - Server-Side Request Forgery (SSRF) in news feed fetcher (`EMPIRE-TOOL-SSRF-01`)<br>- Reflected Cross-Site Scripting (XSS) in news & dictionary search (`EMPIRE-TOOL-XSS-02`) | Outbound URL egress destination verification |
| **API Security (OWASP Top 10)** | `https://gw.empire.edu.vn` | FastAPI, Node.js Reverse Proxy, REST/JSON | - Broken Function-Level Authorization (BFLA) on admin routes (`EMPIRE-API-BFLA-01`)<br>- Unrestricted Resource Consumption & missing rate limiting (`EMPIRE-API-RATELIMIT-02`)<br>- Unauthenticated Social Intelligence & User Harvesting (`VULN-04`: 13 groups, >207,000 members exposed) | Rate limiting: 150 req/sec cap |
| **Web Security & Portals** | `https://console.empire.io.vn`, student portals | Vite React SPA, Client-side RBAC | - Client-side RBAC bypass & DOM menu unhiding (`VULN-02`)<br>- Hardcoded secrets in production JS bundles (`VULN-06`)<br>- Missing security headers (CSP, X-Frame-Options, X-Content-Type-Options: ZAP rules `10020`, `10038`, `10021`) | Server-side authorization verification required |
| **Brute-Force & Negative Auth Defense** | `https://id.empire.edu.vn/api/auth/sign-in/email` | Better-Auth | - Controlled negative auth resilience check (5 bounded probes)<br>- Progressive delay measurement<br>- HTTP 429 & RateLimit header detection | Non-destructive: Uses synthetic account `audit_synthetic_probe@empire.local` |
| **Server & Cloud Infrastructure** | `https://empire.edu.vn/` | Envoy proxy, Linux, Docker, TLS/SSL | - TLS certificate cipher suites<br>- Envoy proxy header leakage (`x-envoy-upstream-service-time`)<br>- Exposed management ports | Same-origin scope boundary |

### 5.3 Primary Target Registration Gap
- In `backend/app/core/empire_seeder.py:54-115`, six targets are seeded:
  1. `https://id.empire.edu.vn`
  2. `https://gw.empire.edu.vn`
  3. `https://mh.empire.edu.vn/media`
  4. `https://voh.empire.edu.vn`
  5. `https://console.empire.io.vn`
  6. `https://gw.empire.edu.vn/news`
- **Missing Root Target**: The root platform URL `https://empire.edu.vn/` (which is live, returns Envoy/Next.js headers, and was specified in R1 and Acceptance Criteria as primary target) is **absent from the seed inventory**.
- It must be registered as primary asset under `SERVER_INFRASTRUCTURE` / `WEB_APPLICATION`.

---

## 6. Focus Area 5: Finding Deduplication, Evidence Viewer, Risk Prioritization & Remediation Lifecycle

### 6.1 Finding Deduplication Architecture
- Deterministic hash computed in `backend/app/scanners/base.py:48-63`:
  ```python
  def compute_finding_fingerprint(
      asset_id: uuid.UUID,
      scanner_engine: str,
      scanner_rule_id: str,
      target_location: str,
      target_component: Optional[str] = None,
  ) -> str:
      norm_location = (target_location or "").strip().lower()
      norm_component = (target_component or "").strip().lower()
      norm_rule = (scanner_rule_id or "").strip().lower()
      norm_engine = (scanner_engine or "").strip().lower()
      raw_key = f"{asset_id}:{norm_engine}:{norm_rule}:{norm_location}:{norm_component}"
      return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
  ```
- **Deduplication Persistence Logic** (`dispatcher.py:384-440`):
  - Queries existing findings matching `(asset_id, fingerprint)`.
  - If existing finding is found:
    - Increments `occurrence_count += 1`.
    - Updates `last_seen_at = now`.
    - Updates `scan_id = current_scan.id`.
    - **Regression Detection**: If finding status was `FIXED` or `RESOLVED`, it automatically transitions to `REOPENED` and generates a critical regression audit log and alert.
  - If new finding: Creates `NormalizedFinding` with status `OPEN` and `occurrence_count = 1`.

### 6.2 Evidence Viewer Schema & Forensic Presentation
- In `backend/app/schemas/finding.py:49-86` (`FindingResponse`):
  - Returns `evidence: Dict[str, Any]` (which includes `request`, `response`, `matched_content`, `curl_command`, `file_path`, `triage_history`, `last_retest`).
  - Returns `raw_payload`.
- In `frontend/src/app/findings/page.tsx:304-375`:
  - Selecting a finding row opens a Forensic Detail Drawer.
  - Renders Scope, Component, Empire Module, Exposure Classification badge.
  - Description and Recommended Remediation boxes.
  - Formatted JSON pre-formatted block rendering `evidence`.
  - Retest verdict box (displaying `VERIFIED_FIXED` in emerald or `STILL_VULNERABLE` in rose).

### 6.3 Risk Prioritization Formula (Sentinel Risk Score - SRS)
Implemented in `backend/app/risk/calculator.py:134-216`:
$$\begin{aligned}
V_{\text{base}} &= \frac{\text{CVSS}}{10.0} \\
B_{\text{threat}} &= 0.20 \times \text{EPSS} + (0.30 \text{ if CISA KEV else } 0.0) \\
T_{\text{threat}} &= \min(1.0, V_{\text{base}} + B_{\text{threat}}) \quad (\text{if CISA KEV: } \max(0.75, T_{\text{threat}})) \\
M_{\text{context}} &= 0.50 \times C_{\text{asset}} + 0.50 \times E_{\text{net}} \\
T_{\text{contextual}} &= T_{\text{threat}} \times (0.35 + 0.65 \times M_{\text{context}}) \\
SRS &= \text{round}(\min(100.0, \max(0.0, T_{\text{contextual}} \times F_{\text{verif}} \times 100.0)), 1)
\end{aligned}$$

Where:
- $C_{\text{asset}} \in [0.40, 1.00]$ (Tier 1 Mission Critical = 1.0, Tier 4 Low = 0.40)
- $E_{\text{net}} \in [0.25, 1.00]$ (Internet Facing = 1.0, Isolated = 0.25)
- $F_{\text{verif}} \in [0.40, 1.00]$ (Confirmed PoC = 1.0, High Confidence = 0.90, Candidate = 0.40)
- Severity Tiers: $\ge 80.0 \to \text{CRITICAL}$, $\ge 60.0 \to \text{HIGH}$, $\ge 40.0 \to \text{MEDIUM}$, $\ge 20.0 \to \text{LOW}$, $< 20.0 \to \text{INFO}$.
- `RiskExplainabilityBuilder` (`explainability.py`) generates structured component breakdowns and plain-language narrative explanations for auditor reports.

### 6.4 Remediation Tracking Lifecycle
- **10 Lifecycle States** (`backend/app/schemas/common.py:87-100`):
  `NEW`, `POTENTIAL`, `CONFIRMED`, `OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`, `FALSE_POSITIVE`, `NOT_AFFECTED`.
- **Triage API** (`/api/v1/findings/{finding_id}/triage`):
  - Updates finding status, assignee, remediation notes.
  - Appends audit entry to `triage_history` array inside finding's `evidence` JSON.
  - Automatically emits a `SecurityAlert` when status changes to `FIXED` or `REOPENED`.
- **Live Retest Engine** (`/api/v1/findings/{finding_id}/retest`):
  - Executes live asynchronous HTTP GET probe against `finding.target_location`.
  - Evaluates response code:
    - If target now returns 401, 403, or 404 on an unauthenticated exposure finding: sets `retest_status = "VERIFIED_FIXED"`, automatically updates finding status to `FIXED`.
    - If target still returns 200 with exposed content: sets `retest_status = "STILL_VULNERABLE"`.
  - Records timestamp, verdict, and notes in `evidence["last_retest"]`.
- **Remediation Kanban Board** (`frontend/src/app/remediation/page.tsx`):
  - Displays 5 primary columns (`OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`).
  - Allows selecting any card, assigning engineers, adding notes, and triggering lifecycle transitions.

---

## 7. Command Center UI & Internationalization Audit (R4)

### 7.1 Navigation Views Audit
The frontend command center (`frontend/src/app`) implements all 14 views specified in R4:
1. `/dashboard` — Security Overview Dashboard with 10 KPIs and 8 chart datasets.
2. `/assets` — Targets Management with single and bulk import (CSV, JSON, OpenAPI).
3. `/empire-modules` — Empire Business Architecture Module Security Hub.
4. `/scans` — Scan Center with 7 profile selectors and engine picker.
5. `/active-assessments` — Live scan tracker with real-time logs and cancellation.
6. `/findings` — Vulnerability finding explorer with forensic evidence drawer.
7. `/threat-intel` — Vulnerability intelligence database (CVE, EPSS, CISA KEV).
8. `/remediation` — Kanban remediation lifecycle tracking board.
9. `/reports` — Vector PDF, HTML, and JSON audit report generator.
10. `/schedules` — Daily assessment scheduler (Asia/Ho_Chi_Minh 02:00 AM ICT).
11. `/detection-rules` — YAML detection rules validator, test runner, and lifecycle manager.
12. `/integrations` — Scanner engine and notification webhook integrations.
13. `/health` — System health telemetry, database, and process statuses.
14. `/settings` — Approved Public Media Policy, synthetic accounts, and SSRF CIDR boundaries.

### 7.2 Design System Compliance
- The UI adheres to the **Cyber-Slate / Black / Liquid Glass design system**:
  - Palette: Deep blacks (`bg-cyber-950`), dark charcoal cards (`bg-cyber-900`), borders (`border-cyber-800`), cyan accents (`text-cyan-400`, `bg-cyan-500`), and emerald/rose/amber severity badges.
  - Glass effect: Translucent backdrops with high contrast typography.

### 7.3 Internationalization Gap (R4)
- **Status: NON-COMPLIANT**.
- Currently, all labels, table headers, descriptions, and notifications across all 14 pages are hardcoded in English.
- Requirement R4 states: *"Provide complete bilingual internationalization (Vietnamese and English) with Vietnamese as the default locale."*
- **Required Implementation**:
  - Create a lightweight React context / dictionary (`lib/i18n.tsx`) containing Vietnamese (`vi`) and English (`en`) translations for all navigation items, KPI cards, table headers, buttons, and status descriptions.
  - Store locale preference in `localStorage` defaulting to `'vi'`.
  - Add a locale toggle button in `Shell.tsx` header (`[VI | EN]`).

---

## 8. Summary Gap Matrix & Technical Recommendations

| Component | Current State | Required State (R1-R5) | Action Needed for Implementation |
|---|---|---|---|
| **Root Target** | Only subdomains seeded (`id`, `gw`, `mh`, `voh`, `console`) | `https://empire.edu.vn/` registered as primary asset | Add `https://empire.edu.vn/` to `empire_seeder.py` under same-origin baseline policy. |
| **Target Verification** | Admin override flag set instantaneously | 8-step live verification pipeline (DNS, TLS, HTTP, Redirect, Web, Fingerprint) | Implement explicit 8-step verification helper and persist verification metadata in `Asset.verified_at` and `assessment_policy`. |
| **Quality States** | Generic `COMPLETED` and `FAILED` | Explicit states: `SCANNED_SUCCESSFULLY`, `PARTIAL_COVERAGE`, `AUTH_REQUIRED`, `SCANNER_FAILED`, `TARGET_UNAVAILABLE` | Add `quality_status` column to `Scan` table and evaluate per-adapter execution results. |
| **Bounded Crawling** | Static URL list | Bounded same-origin crawler | Implement an asynchronous BFS crawler bounded by max depth (3) and max pages (50). |
| **Process Safety PID** | `ProcessSafetyManager` defined but subprocess PID not registered | Subprocess PID registered on spawn | Call `process_safety.register_pid(request.scan_id, proc.pid)` in `nuclei.py` and `trivy.py`. |
| **ZAP Native Execution** | Falls back to lab runner with `pass` | Native ZAP CLI execution or ZAP API client | Implement ZAP automation plan or native CLI execution when available. |
| **Internationalization** | English only | Bilingual (Vietnamese default + English toggle) | Implement `lib/i18n.tsx` dictionary and integrate language switcher in `Shell.tsx`. |

---
*Report completed by `explorer_survey_2`. Ready for handoff to Orchestrator and Implementation Agents.*
