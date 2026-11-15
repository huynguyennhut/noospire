# Explorer Survey 2: Comprehensive Technical Investigation Report

## 1. Observation

### 1.1. Scanner Adapter Framework & Process Safety (R3)
- **Base Scanner Interface** (`backend/app/scanners/base.py:65-101`):
  `BaseScannerAdapter` specifies five abstract properties and methods: `engine_name`, `supported_asset_types`, `is_available() -> tuple[bool, str]`, `execute(request, cancel_token, log_callback) -> ScannerExecutionResult`, and `parse_findings(raw_output, request) -> List[NormalizedFindingCreate]`.
  Deduplication is implemented in `compute_finding_fingerprint()` (lines 48-63) via deterministic SHA-256 over:
  `raw_key = f"{asset_id}:{norm_engine}:{norm_rule}:{norm_location}:{norm_component}"`.
- **Nuclei Scanner Adapter** (`backend/app/scanners/nuclei.py:111-183`):
  Executes CLI binary when present (`shutil.which("nuclei")`) via `asyncio.create_subprocess_exec` (`shell=False`) with structured argument array:
  `cmd = [shutil.which("nuclei") or "nuclei", "-target", request.target_locator, "-jsonl", "-silent", "-nc", "-timeout", "5", "-tags", "cve,exposure", "-c", "10"]` (lines 123-132).
  Registers PID via `await process_safety.register_pid(request.scan_id, proc.pid)` (line 140).
  Falls back to embedded `NucleiLabRunner` (lines 160-182) which scans against 6 approved mock/lab templates (`cve-2023-default-creds`, `actuator-env-leak`, `swagger-ui-exposure`, `exposed-git-config`, `graphql-introspection`, `security-headers-missing`).
- **OWASP ZAP Scanner Adapter** (`backend/app/scanners/zap.py:135-217`):
  Enforces active probe authorization gate (lines 144-149):
  `if request.profile == "DEEP_ACTIVE": is_verified = request.custom_config.get("is_verified", False); if not is_verified: raise PermissionError(...)`.
  Executes CLI binary when present via `asyncio.create_subprocess_exec` with `-cmd -quickurl <target> -quickout <report_file>` (lines 158-163).
  Registers PID via `await process_safety.register_pid(request.scan_id, proc.pid)` (line 165).
  Falls back to embedded `ZAPLabRunner` (lines 193-217) implementing passive checks (`missing_csp`, `missing_hsts`, `x_content_type_options`, `cors_wildcard`, `server_tokens_leak`, `cookie_without_httponly`).
- **Trivy Scanner Adapter** (`backend/app/scanners/trivy.py:144-218`):
  Supported asset types: `PROJECT_ARCHIVE`, `CONTAINER_IMAGE`.
  Dynamically maps subcommand based on asset type: `image` for container images, `sbom` for SBOM inputs, `fs` for filesystem/archive directories (lines 155-161).
  Executes CLI binary via `asyncio.create_subprocess_exec` with `[subcommand, "--format", "json", "--security-checks", "vuln,secret", request.target_locator]` (lines 162-168).
  Registers PID via `await process_safety.register_pid(request.scan_id, proc.pid)` (line 176).
  Falls back to embedded `TrivyLabRunner` (lines 196-218) inspecting package lockfiles (`package-lock.json`, `requirements.txt`, `yarn.lock`, `go.sum`, `Cargo.lock`) and secret patterns.
- **Process Safety Architecture** (`backend/app/core/dispatcher.py:160-200`):
  `ProcessSafetyManager` is defined directly inside `backend/app/core/dispatcher.py` (not in a standalone `process_safety.py`).
  Stores PIDs in `self._scan_pids: Dict[uuid.UUID, List[int]]`.
  `terminate_process_tree(scan_id)` (lines 183-197) executes:
  ```python
  pids = self._scan_pids.pop(scan_id, [])
  for pid in pids:
      parent = psutil.Process(pid)
      children = parent.children(recursive=True)
      for child in children:
          child.terminate()
      parent.terminate()
      _, alive = psutil.wait_procs(children + [parent], timeout=3)
      for p in alive:
          p.kill()
  ```
  Missing: `backend/app/core/process_safety.py` file does NOT exist on disk.
  Missing: Process execution does NOT set `preexec_fn=os.setsid` or configure POSIX process groups.
  Missing: Process execution does NOT drop privileges to non-root users (`setuid`/`setgid`).
  Missing: Process execution does NOT configure resource limits (`resource.setrlimit` for `RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_NOFILE`).

### 1.2. Live Assessment Monitor, Triage & Remediation Lifecycle (R5)
- **Live Telemetry & Resource Monitoring** (`backend/app/core/dispatcher.py:46-74, 1257-1271`):
  `check_system_resources()` samples host CPU and virtual memory via `psutil`.
  Throttling flag `is_throttled = bool(cpu_pct > settings.THROTTLE_CPU_PCT or mem_pct > settings.THROTTLE_MEM_PCT)`.
  Dispatcher tracks in-flight threads in `self._active_threads: Dict[uuid.UUID, dict]` with fields: `thread_id`, `scan_id`, `target_locator`, `profile`, `engine`, `stage` (preflight, discovery, active, empire, scoring), `progress_percentage`, `started_at`, `elapsed_seconds`, `last_log`.
  Exposed via API endpoint `GET /scans/telemetry` (`backend/app/api/scans.py:1085-1115`).
- **SSE Event Stream** (`backend/app/api/scans.py:800-920`):
  Endpoints `GET /scans/{scan_id}/events/stream` and legacy alias `GET /scans/{scan_id}/logs/stream`.
  Supports monotonic cursor resumption via HTTP header `Last-Event-ID` or query parameter `cursor`.
  Two-phase replay:
  - Phase 1: Replays historic `ScanEvent` records from database where `id > start_id` ordered by `id.asc()`.
  - Phase 2: Subscribes to live async generator `event_broadcaster.subscribe_scan(scan_id)` with gap detection re-querying the database if `evt.id > last_emitted_id + 1`.
  - Heartbeat / Keep-Alive: Emits `: keep-alive\n\n` on 10.0-second timeout.
  - Periodic Authentication Invalidation: Evaluates `await session_still_valid(request, stream_asset_id)` every heartbeat; immediately drops stream with `AUTH_REVOKED_FRAME` if user account is disabled or permission revoked.
- **Finding Lifecycle State Model** (`backend/app/schemas/common.py:96-109` vs `ORIGINAL_REQUEST.md`):
  Current `FindingStatus` enum contains 12 values:
  `NEW`, `POTENTIAL`, `CONFIRMED`, `OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`, `FALSE_POSITIVE`, `NOT_AFFECTED`, `RESOLVED`, `MUTED`.
  Frontend `FindingLifecycleStatus` (`frontend/src/lib/types.ts:37-47`) contains 10 values:
  `NEW`, `POTENTIAL`, `CONFIRMED`, `OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`, `FALSE_POSITIVE`, `NOT_AFFECTED`.
  Required R5 lifecycle states (exact 10 states):
  `NEW`, `NEEDS_TRIAGE`, `CONFIRMED`, `FALSE_POSITIVE`, `ACCEPTED_RISK`, `ASSIGNED`, `IN_PROGRESS`, `FIXED_PENDING_RETEST`, `RESOLVED`, `REOPENED`.
- **Finding Triage & Audit Trail** (`backend/app/api/findings.py:131-213`):
  `POST /findings/{finding_id}/triage` updates `finding.status`, `finding.assignee`, `finding.remediation_notes`, and `finding.retest_status`.
  Appends structured entry to `finding.evidence["triage_history"]` with timestamp, `old_status`, `new_status`, `comment`, `actor`, and `assignee`.
  Calls `record_change()` (`backend/app/models/lifecycle.py`) to log immutable `FindingChange` records per modified field.
  Emits `SecurityAlert` (category="REMEDIATION") when finding transitions to `FIXED` or `REOPENED`.
- **Secret Redaction**:
  - `backend/app/engines/runner.py:49-62`: Regex substitution masks Bearer tokens, passwords, cookies, tokens, API keys, JWTs (`[REDACTED_JWT]`), and email addresses (`[REDACTED_EMAIL]`).
  - `backend/app/models/event.py:17-36`: `sanitize_event_details()` recursively scrubs keys matching `{"authorization", "token", "password", "secret", "cookie", "set-cookie", "api_key", "jwt"}` and truncates string values exceeding 4096 characters.
- **Targeted Retests** (`backend/app/api/findings.py:215-231` & `backend/app/api/console.py`):
  `POST /findings/{finding_id}/retest` redirects to `recheck_finding_impl()`, which re-queues the defensive rule that produced the finding rather than performing a naive HTTP GET.

### 1.3. Reporting Engine & Coverage Gap Disclosure
- **Multi-Format Report Generator** (`backend/app/reporting/generator.py:134-389`):
  `ReportGenerator` produces Technical Assessment and Executive Summary reports.
  Supported output formats: JSON (`render_json`), HTML (`render_html`), PDF (`render_pdf`).
  Persists generated metadata in `Report` ORM entity with `summary`, `file_paths`, and `status="READY"`.
  Zero fabrication: queries `NormalizedFinding` table from database filtered by `scan_id`, `asset_id`, or `batch_id`.
- **ReportLab Vector PDF Builder** (`backend/app/reporting/pdf_builder.py:49-96, 200-235`):
  Uses ReportLab 5.1.0 with `NumberedCanvas` (two-pass canvas calculating total page count `Page X of Y`, running header, running footer).
  Generates Cover Page with brand banner, metadata, and severity counts card; Executive Security Posture with Sentinel Risk Index (0-100), KEV count, and high EPSS count; Findings Ledger Summary Table; Detailed Vulnerability Dossiers (technical) or Strategic Recommendations (executive).
- **Jinja2 HTML Templates** (`backend/app/reporting/templates/`):
  `html_report.jinja2`: Obsidian Dark Mode theme (`--bg-primary: #070B14`, `--bg-surface: #0E1526`, `--accent-cyan: #06B6D4`), responsive grid, severity cards, findings summary table, detailed dossiers with forensic PoC blocks. Includes basic `@media print` light styles.
  `executive_summary.jinja2`: C-suite executive dashboard layout, Sentinel Risk Index badge, severity grid, strategic recommendations.
- **Immutable Snapshot & Coverage Calculations** (`backend/app/reporting/pilot_report.py:59-150`):
  Builds canonical JSON snapshot hashed with SHA-256 (`ReportSnapshot` table).
  Explicit coverage calculation:
  `covered = sum(1 for c in coverage if any(v["succeeded"] for v in c["engines"].values()))`
  `assets_with_successful_check / assets_in_scope`.
  Identifies scan-to-scan changes (`new`, `fixed`, `reopened`, `unchanged`).
  Appends `appendix_errors_exclusions` detailing failed/inapplicable executions.
- **Reporting Gaps**:
  1. `generator.py` and `pdf_builder.py` do NOT currently include an explicit "Coverage Gaps & Exclusions" section detailing targets or checks that could not be executed (unlike `pilot_report.py`).
  2. The Jinja2 HTML templates only provide Obsidian Dark theme without a dedicated Warm / Invert Light theme stylesheet (`Theme: Invert (Light) / Light Theme: Warm`).

---

## 2. Logic Chain

1. **Adapter Safety & Process Isolation**:
   - *Premise*: R3 mandates structured argument arrays (`shell=False`), non-root execution, resource limits, and complete process-tree cancellation.
   - *Evidence*: `nuclei.py`, `zap.py`, and `trivy.py` use `asyncio.create_subprocess_exec` with array arguments (`shell=False` invariant upheld). `ProcessSafetyManager` tracks PIDs and uses `psutil` recursive termination.
   - *Inference*: Process-tree termination works for standard child trees, but lacks process group isolation (`os.setsid`). If grandchild processes detach, `psutil` can encounter race conditions. Furthermore, missing `setuid`/`setgid` privilege dropping and lack of `setrlimit` (RLIMIT_AS/RLIMIT_CPU) means a compromised or runaway scanner binary can consume unbounded system memory or inherit root permissions in containerized deployments.
   - *Deduction*: Extracting `ProcessSafetyManager` into `backend/app/core/process_safety.py` and enhancing `create_subprocess_exec` with `preexec_fn` (process groups, `setrlimit`, non-root user switching) is required to satisfy R3.

2. **10-State Lifecycle Alignment**:
   - *Premise*: R5 explicitly specifies a 10-state lifecycle: `NEW`, `NEEDS_TRIAGE`, `CONFIRMED`, `FALSE_POSITIVE`, `ACCEPTED_RISK`, `ASSIGNED`, `IN_PROGRESS`, `FIXED_PENDING_RETEST`, `RESOLVED`, `REOPENED`.
   - *Evidence*: `backend/app/schemas/common.py:96-109` currently defines 12 states (`NEW`, `POTENTIAL`, `CONFIRMED`, `OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`, `FALSE_POSITIVE`, `NOT_AFFECTED`, `RESOLVED`, `MUTED`). Frontend `lib/types.ts:37-47` defines 10 states with legacy naming (`POTENTIAL`, `OPEN`, `IN_REMEDIATION`, `FIXED`, `NOT_AFFECTED`).
   - *Inference*: There is semantic drift between the agreed R5 specification and the legacy schema. Specifically:
     - `NEEDS_TRIAGE` replaces `POTENTIAL` / `OPEN`.
     - `ASSIGNED` is currently missing as an explicit lifecycle state (assignee is tracked only as a string field).
     - `IN_PROGRESS` replaces `IN_REMEDIATION`.
     - `FIXED_PENDING_RETEST` replaces `FIXED` (representing a state awaiting affirmative defensive verification).
   - *Deduction*: Aligning `FindingStatus` enum and database checks to the canonical 10 states with backward-compatible mapping ensures seamless triage transition and eliminates ambiguity.

3. **Reporting Pipeline & Honest Coverage Disclosure**:
   - *Premise*: R6 and Gate 4 mandate reproducible PDF/HTML/JSON reports with honest coverage gap disclosure and dual-theme Liquid Glass styling.
   - *Evidence*: `generator.py` and `pdf_builder.py` render audit-grade reports from database findings without data fabrication, but only report identified vulnerabilities. Conversely, `pilot_report.py` calculates explicit coverage ratios and lists failed/excluded checks, but uses internal template `noospire-pilot-report/1.0`.
   - *Inference*: Unifying the coverage matrix logic from `pilot_report.py` into `generator.py` and `pdf_builder.py` ensures both Technical and Executive reports transparently disclose what was NOT scanned or failed due to authentication/unreachability.
   - *Deduction*: Adding coverage gap sections to `pdf_builder.py`, `html_report.jinja2`, and `executive_summary.jinja2`, along with CSS variables for Warm Light Theme, completes R6 compliance.

---

## 3. Caveats

1. **Native Scanner Binaries**: The testing and development host does not have native CLI binaries for `nuclei`, `zap.sh`, or `trivy` installed in global PATH. The existing architecture is designed to gracefully fall back to embedded Lab Runners (`NucleiLabRunner`, `ZAPLabRunner`, `TrivyLabRunner`). In a live deployment, binaries must be installed in container images.
2. **Database Engine Differences**: In SQLite (development/test mode), alter column and enum constraints behave differently than in PostgreSQL (production mode). When updating `FindingStatus`, migration scripts or schema definitions must accommodate both dialect constraints.
3. **ReportLab Font Dependencies**: Vietnamese Unicode glyph rendering in ReportLab PDFs requires external TrueType fonts (`DejaVuSans.ttf` or `arial.ttf`). When fonts are absent, `_ascii()` transliteration is used in `pilot_report.py`.

---

## 4. Conclusion

The Noospire codebase possesses robust foundational building blocks for R3, R5, and Reporting:
- **R3**: Adapters execute safely with array arguments (`shell=False`) and fallback lab runners; however, process isolation must be extracted to `backend/app/core/process_safety.py` with process group termination (`os.setsid`), non-root execution, and resource limits.
- **R5**: Live assessment telemetry (`/scans/telemetry`), dual-phase SSE streaming (`/scans/{id}/events/stream`), secret redaction, and retest pipelines are operational. The finding lifecycle state machine must be aligned to the exact 10 canonical states (`NEW`, `NEEDS_TRIAGE`, `CONFIRMED`, `FALSE_POSITIVE`, `ACCEPTED_RISK`, `ASSIGNED`, `IN_PROGRESS`, `FIXED_PENDING_RETEST`, `RESOLVED`, `REOPENED`).
- **Reporting Engine**: Vector PDF builder (ReportLab 5.1.0) and HTML/JSON generators produce zero-fabrication reports. Honest coverage gap disclosure and Warm/Invert Light theme styling must be incorporated into `generator.py` and templates.

---

## 5. Verification Method

To independently verify the observations and contracts identified in this report:

1. **Verify Shell & UI Primitives**:
   ```bash
   /home/nhut-nguyen/.local/bin/uv run --with-requirements backend/requirements-dev.txt pytest tests/test_shell_primitives_adversarial.py -v
   ```
   *Expected outcome*: 9 passed tests confirming UI and modal contract resilience.

2. **Verify Scanner Quality State Machine**:
   ```bash
   /home/nhut-nguyen/.local/bin/uv run --with-requirements backend/requirements-dev.txt pytest tests/test_scan_intelligence_m2.py -k "test_m2_01 or test_m2_02 or test_m2_03 or test_m2_04 or test_m2_05 or test_m2_06" -v
   ```
   *Expected outcome*: 6 passed tests verifying `ScanQualityStatus` enum, crawler bounding, and `ProcessSafetyManager` PID registration.

3. **Inspect Core Codebase Locations**:
   - `backend/app/scanners/base.py`: Lines 48-101 (Fingerprint deduplication & adapter interface).
   - `backend/app/core/dispatcher.py`: Lines 160-199 (`ProcessSafetyManager`), lines 777-792 (Telemetry), lines 900-909 (Adapter dispatch).
   - `backend/app/api/scans.py`: Lines 800-920 (SSE stream with Last-Event-ID replay and gap detection).
   - `backend/app/schemas/common.py`: Lines 96-109 (`FindingStatus` enum definition).
   - `backend/app/reporting/generator.py`: Lines 134-294 (`ReportGenerator` multi-format pipeline).
   - `backend/app/reporting/pdf_builder.py`: Lines 49-96 (`NumberedCanvas`), lines 200-235 (`build_pdf`).
