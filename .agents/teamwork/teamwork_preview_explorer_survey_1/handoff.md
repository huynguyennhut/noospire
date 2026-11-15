# Handoff Report: Survey of Empire Pentest Checklist Catalog (R1), Customer Scope Gate (R2), and Synthetic Test Harness & File Policy (R4)

**Agent**: teamwork_preview_explorer_survey_1  
**Working Directory**: `/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_explorer_survey_1`  
**Date**: 2026-11-15T04:55:00Z  
**Type**: Hard Handoff (Investigation & Architecture Survey Complete)  

---

## 1. Observation

### 1.1 Codebase Layout and Existing Subsystems
- **Backend Core**: FastAPI application in `backend/main.py` with 19 mounted routers under `/api/v1` (`backend/main.py:148-152`):
  `auth_router`, `assets_router`, `scans_router`, `findings_router`, `settings_router`, `reports_router`, `metrics_router`, `intel_router`, `rules_router`, `empire_modules_router`, `baselines_router`, `schedules_router`, `alerts_router`, `logs_router`, `system_router`, `executions_router`, `engines_router`, `operations_router`, `console_router`.
- **Database Layer**: Async SQLAlchemy 2.0 with SQLite WAL mode (`backend/app/core/database.py:26-28`). Models defined under `backend/app/models/` and registered during `init_db()` (`backend/app/core/database.py:49-66`).
- **Scanner Orchestration**:
  - `backend/app/core/dispatcher.py:897-909`: Supports adapters for `NucleiAdapter`, `ZAPAdapter`, `TrivyAdapter`.
  - `backend/app/scanners/empire_engine.py`: `EmpireAssessmentEngine` runs tailored checks across Modules A through G.
  - `backend/app/engines/runner.py`: Executes defensive engines (`sbom`, `tls_health`) with worker lease fencing.

---

### 1.2 Observations for R1: Empire Pentest Checklist Catalog & Result Engine
- **Checklist Catalog Absence**:
  - A comprehensive search across the codebase for `WEB-001`, `API-001`, `FILE-001`, `AUTH-001`, `INFRA-001`, `DEP-001` yielded zero occurrences in `backend/app` or `frontend/src`.
  - `backend/app/models/` currently contains `rule.py` (`DetectionRule` for Sentinel YAML rules), `baseline.py` (`BaselineException`), and `finding.py` (`NormalizedFinding`), but **no model** exists for Pentest Check Definitions, Checklist Catalogs, or Checklist Run Results.
- **Result States & Invariants Absence**:
  - The required 7 immutable result states (`PASS`, `FAIL`, `NEEDS_REVIEW`, `NOT_APPLICABLE`, `BLOCKED`, `NOT_RUN`, `ERROR`) are not defined in `backend/app/schemas/common.py` or anywhere in the backend enum taxonomy.
  - The current scan execution statuses (`backend/app/schemas/common.py:54-64`) only track pipeline progress (`PENDING`, `QUEUED`, `INITIALIZING`, `RUNNING`, `COMPLETING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`).
  - Scan quality status (`backend/app/schemas/common.py:66-72`) only defines 5 legacy states (`SCANNED_SUCCESSFULLY`, `PARTIAL_COVERAGE`, `AUTH_REQUIRED`, `SCANNER_FAILED`, `TARGET_UNAVAILABLE`).
  - Finding statuses (`backend/app/schemas/common.py:96-109`) only define vulnerability triage states (`NEW`, `POTENTIAL`, `CONFIRMED`, `OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`, `FALSE_POSITIVE`, `NOT_AFFECTED`, `RESOLVED`, `MUTED`).
- **Metrics Calculation**:
  - Automated coverage percentage and manual review completion percentage are currently not computed on a checklist basis; current metrics (`backend/app/api/metrics.py`) focus only on finding severities, open/fixed counts, and SLA timers.

---

### 1.3 Observations for R2: Customer Scope & Authorization Gate
- **Scope Model**:
  - `backend/app/models/scope.py:10-37` defines `AssetAssessmentScope`:
    ```python
    class AssetAssessmentScope(Base, TimestampMixin):
        id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
        asset_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False)
        exact_origin: Mapped[str] = mapped_column(String(512), nullable=False)
        ports: Mapped[list] = mapped_column(JSON, default=lambda: [80, 443], nullable=False)
        allowed_path_patterns: Mapped[list] = mapped_column(JSON, default=lambda: ["/*"], nullable=False)
        permitted_checks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
        rate_limit_rps: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
        concurrency_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
        byte_budget: Mapped[int] = mapped_column(Integer, default=10485760, nullable=False) # 10MB
        max_requests_per_run: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
        emergency_stop_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
        time_window_start: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
        time_window_end: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
        expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
        created_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ```
- **Scope Verification & Dispatch Enforcement**:
  - In `backend/app/api/scans.py:146-152`:
    ```python
    scope_res = await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == asset.id))
    scope = scope_res.scalars().first()
    if scope and scope.emergency_stop_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scan dispatch blocked: emergency stop is active for this target asset.",
        )
    ```
  - In `backend/app/core/dispatcher.py:912-939`:
    When `asset_scope` is `None`, the dispatcher silently falls back to default values (`rate_limit_rps=2`, `byte_budget=10485760`, `permitted_checks=[]`), allowing the scan to proceed rather than rejecting it as unauthorized.
- **SSRF & Network Gatekeeper**:
  - `backend/app/core/ssrf.py:19-81`: `SSRFProtector` blocks RFC 1918 private subnets, loopbacks (`127.0.0.0/8`, `::1`), link-local, and cloud metadata (`169.254.169.254`, `metadata.google.internal`).
  - Active scanning (`DEEP_ACTIVE`) check in `backend/app/api/scans.py:167-172` blocks active scans if `asset.verification_status != VerificationStatus.VERIFIED.value`.
- **Emergency Stop & Process Tree Termination**:
  - `backend/app/core/dispatcher.py:160-197`: `ProcessSafetyManager` tracks spawned PIDs and invokes `terminate_process_tree`:
    ```python
    parent = psutil.Process(pid)
    children = parent.children(recursive=True)
    for child in children:
        child.terminate()
    parent.terminate()
    _, alive = psutil.wait_procs(children + [parent], timeout=3)
    for p in alive:
        p.kill()
    ```
    This satisfies the `< 3s` process termination requirement.
  - Endpoints available: `POST /api/v1/scans/stop-all` (`backend/app/api/scans.py:664-676`) and `POST /api/v1/scans/batch/{batch_id}/cancel` (`backend/app/api/scans.py:643-662`).
  - Missing endpoint: There is no granular `POST /api/v1/assets/{id}/emergency-stop` route exposed on `assets_router`.

---

### 1.4 Observations for R4: Custom Synthetic Test Harness & File Policy Engine
- **Synthetic Identity Model**:
  - `backend/app/models/synthetic_identity.py:10-21`:
    ```python
    class SyntheticIdentity(Base, TimestampMixin):
        id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
        identifier: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
        role: Mapped[str] = mapped_column(String(64), default="STUDENT", nullable=False) # STUDENT, TESTER, AUDITOR
        email: Mapped[str] = mapped_column(String(255), nullable=False)
        description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
        is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
        last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ```
  - Seeder in `backend/app/core/empire_seeder.py:433-463` seeds 3 identities: `studenttu1`, `test_student_a`, `test_student_b`.
  - Missing fields: No explicit token or credentials storage field on `SyntheticIdentity` (e.g. `auth_token`, `auth_headers`, `credentials_json`).
- **Current BOLA/BFLA Implementation**:
  - In `backend/app/scanners/empire_engine.py:196-235`, BOLA check uses hardcoded constants:
    ```python
    synthetic_student_id = "stu-test-7788"
    bola_url = urljoin(base_url, f"/api/users/{synthetic_student_id}/learning-records")
    resp = await client.get(bola_url, headers={"Authorization": "Bearer synthetic_student_token_a"})
    ```
    It does not query `SyntheticIdentity` from the database, nor does it mark the check `BLOCKED` if test accounts are missing.
  - In `backend/app/scanners/empire_engine.py:451-494`, BFLA check (`EMPIRE-API-BFLA-01`) only probes `admin_endpoints` without authentication headers; it does not test with low-privileged synthetic student credentials to prove function-level privilege escalation.
- **Approved Public Media Baseline & File Policy Engine**:
  - Model: `backend/app/models/baseline.py:11-29` (`BaselineException`) with `scope="https://mh.empire.edu.vn/media/*"`, `classification=ExposureClassification.PUBLIC_BY_DESIGN.value`.
  - Enum: `backend/app/schemas/common.py:111-116` defines `ExposureClassification.PUBLIC_BY_DESIGN`.
  - In `backend/app/scanners/empire_engine.py:252-330`:
    - Evaluates `/media/public-course.pdf`: logs validation without creating alerts.
    - Probes for unintended sensitive files (`/media/student-records.csv`, `/media/.env`, `/media/backup.zip`, `/media/passwords.txt`): produces `NormalizedFindingCreate` with `exposure_classification=PUBLIC_SENSITIVE_CONTENT`.
    - However, it hardcodes paths instead of querying active `BaselineException` rules from the database, and does not record explicit `PASS` or `FAIL` check runs into a checklist result ledger.

---

## 2. Logic Chain

1. **R1 Catalog & Result Engine Logic**:
   - Because the requirements demand a versioned catalog of 39 specific check definitions (`WEB-001..010`, `API-001..011`, `FILE-001..005`, `AUTH-001..005`, `INFRA-001..004`, `DEP-001..005`) with immutable 7-state results, bilingual metadata, and honest coverage calculation, and because no such catalog or result models currently exist in `backend/app/models/`:
   - A dedicated `backend/app/models/checklist.py` module must be established containing:
     - `ChecklistDefinition`: The 39 static/versioned definitions with `check_id`, `category`, bilingual VI/EN fields, automation type (`AUTOMATED`, `MANUAL`, `HYBRID`), severity, and target engine.
     - `ChecklistAssessmentRun`: The parent container representing a full assessment pass on a target or batch.
     - `ChecklistResult`: The immutable check execution record storing one of the 7 states (`PASS`, `FAIL`, `NEEDS_REVIEW`, `NOT_APPLICABLE`, `BLOCKED`, `NOT_RUN`, `ERROR`), with timestamp, evidence payload, execution duration, and audit trail.
   - Invariant enforcement: The result engine must guarantee that `NOT_RUN`, `BLOCKED`, and `ERROR` can never transition to `PASS`.

2. **R2 Scope & Authorization Gate Logic**:
   - `AssetAssessmentScope` exists in `backend/app/models/scope.py`, but `dispatcher.py` currently permits fallback execution when an asset lacks a scope record.
   - To make scope an **immutable backend gate**:
     - Preflight validation must reject any scan request for an asset that does not have an active, unexpired `AssetAssessmentScope` record.
     - Preflight must verify `exact_origin`, allowed ports, permitted checks, rate limits (`rate_limit_rps`), request budget (`max_requests_per_run`), and byte budget (`byte_budget`).
     - Active/destructive scans must be blocked by default unless explicit verification and active scan permissions are granted.
     - Granular emergency stop must be supported across 4 distinct tiers: Platform/Org (`POST /scans/stop-all`), Batch (`POST /scans/batch/{id}/cancel`), Target (`POST /assets/{id}/emergency-stop`), and Worker (`process_safety.terminate_process_tree` with timeout=3s).

3. **R4 Synthetic Test Harness & File Policy Engine Logic**:
   - The BOLA/BFLA tests currently use hardcoded string literals and unauthenticated probes in `empire_engine.py`.
   - To satisfy R4:
     - A modular `SyntheticTestHarness` must query `SyntheticIdentity` from the database.
     - If the required student credentials or test account records are absent or inactive, the harness must immediately mark `API-001` (BOLA) and `API-005` (BFLA) as `BLOCKED` (never `PASS`, never `NOT_APPLICABLE`).
     - When credentials are present, it must execute BOLA tests across student identities, and execute BFLA tests by attempting administrative endpoints with the low-privileged student persona.
   - For `/media`:
     - A dedicated `FilePolicyEngine` must query `BaselineException` where `classification == "PUBLIC_BY_DESIGN"`.
     - Valid educational assets under approved paths must evaluate to `PASS` on `FILE-001`.
     - Sensitive leaks (CSV, env, backup, keys) must evaluate to `FAIL` on `FILE-002`, producing high/critical findings.

---

## 3. Caveats

- **Existing Tests Compatibility**: Existing test suites (`tests/` and `tests_pilot/`) verify M1–M10 behavior and expect certain response schemas (e.g. `ScanResponse`, `AssetRead`, `BaselineResponse`). New checklist endpoints should be mounted as dedicated routes (`/api/v1/checklist/*`) to prevent breaking legacy test assertions.
- **Docker/External Scanners**: In local development environments where Nuclei CLI or OWASP ZAP binaries may not be installed on the host system, the checklist engine must gracefully utilize the embedded/synthetic lab runners (`backend/app/scanners/lab_runners.py` and `empire_engine.py`) to produce authentic evidence without hard failing on missing external binaries.
- **SQLite Concurrency**: SQLite with WAL mode supports concurrent readers but only one writer at a time. All checklist result batch writes must use atomic commits and handle busy timeouts (`PRAGMA busy_timeout=30000;`).

---

## 4. Conclusion & Concrete Architectural Specifications

### 4.1 Specification: R1 Empire Pentest Checklist Catalog & Result Engine
- **File to Create**: `backend/app/models/checklist.py`
  - Enums:
    - `ChecklistCategory`: `WEB`, `API`, `FILE`, `AUTH`, `INFRA`, `DEP`
    - `CheckResultState`: `PASS`, `FAIL`, `NEEDS_REVIEW`, `NOT_APPLICABLE`, `BLOCKED`, `NOT_RUN`, `ERROR`
    - `AutomationType`: `AUTOMATED`, `MANUAL`, `HYBRID`
  - Tables:
    - `checklist_definitions`: `id` (e.g. `WEB-001`), `category`, `title_vi`, `title_en`, `description_vi`, `description_en`, `remediation_vi`, `remediation_en`, `automation_type`, `default_severity`, `version`, `is_active`.
    - `checklist_runs`: `id`, `asset_id`, `batch_id`, `scan_id`, `status`, `started_at`, `completed_at`, `total_checks` (39), `pass_count`, `fail_count`, `needs_review_count`, `not_applicable_count`, `blocked_count`, `not_run_count`, `error_count`, `automated_coverage_pct`, `manual_review_pct`.
    - `checklist_results`: `id`, `run_id`, `check_id`, `state` (7-state enum), `evidence` (JSON), `error_message`, `executed_at`, `reviewed_by`, `review_notes`.
- **Authoritative Catalog Matrix (All 39 Checks)**:
  - `WEB-001` .. `WEB-010`: Web Application Security (TLS, Headers, XSS, CSRF, SQLi, SSRF, Open Redirect, Error Leakage, CORS, Directory Indexing).
  - `API-001` .. `API-011`: API Security (BOLA/IDOR, Broken Auth, Mass Assignment, Rate Limiting, BFLA, API SSRF, Gateway Misconfig, Anti-Automation, Inventory/Shadow API, Third-Party API, Introspection/Debug).
  - `FILE-001` .. `FILE-005`: Files & Learning Materials (Approved Media PUBLIC_BY_DESIGN, Sensitive File Leakage, MinIO/S3 Bucket Exposure, Arbitrary File Upload, Path Traversal/LFI).
  - `AUTH-001` .. `AUTH-005`: Authentication & Identity (Brute-Force & Credential Spraying, Session Token Entropy & Invalidation, Password Policy, User Enumeration, MFA & Privilege Escalation).
  - `INFRA-001` .. `INFRA-004`: Public Infrastructure (Port Exposure & Perimeter Attack Surface, DNS Zone Transfer & Subdomain Takeover, Server Fingerprinting, Firewall/WAF & Egress Filtering).
  - `DEP-001` .. `DEP-005`: Dependencies & Containers (Vulnerable Open-Source Dependencies, Container Base Image CVEs, SBOM Generation & Supply Chain, Hardcoded Secrets/Keys in Code, Deprecated Runtime Stacks).
- **Core Seeder & Catalog Definition**:
  - `backend/app/core/checklist_catalog.py`: Seeds all 39 check definitions with complete bilingual VI/EN content.
- **REST Router**:
  - `backend/app/api/checklist.py`:
    - `GET /api/v1/checklist/catalog`: Returns all 39 check definitions with bilingual metadata and category filters.
    - `POST /api/v1/checklist/runs`: Dispatches a checklist evaluation for an asset.
    - `GET /api/v1/checklist/runs/{id}`: Retrieves complete checklist run with immutable 7-state results and calculated coverage metrics.
    - `POST /api/v1/checklist/runs/{id}/review/{check_id}`: Records manual analyst review, strictly enforcing state transition invariants.
    - `GET /api/v1/checklist/summary`: Aggregated enterprise coverage summary across assets.

### 4.2 Specification: R2 Customer Scope & Authorization Gate
- **Enhancement to `backend/app/core/dispatcher.py` & `backend/app/api/scans.py`**:
  - Implement strict gatekeeper in `backend/app/core/scope_gate.py`:
    - Check that an active, non-expired `AssetAssessmentScope` exists for the target asset. If missing -> raise 403 Forbidden ("Target asset lacks authorized customer scope record").
    - Validate target origin, scheme, port against authorized scope.
    - Validate profile against permitted probes (block active/destructive scans if not permitted or if `asset.verification_status != VERIFIED`).
    - Enforce rate limit RPS, byte budget, and request budget during execution.
- **Target-Level Emergency Stop**:
  - Add `POST /api/v1/assets/{asset_id}/emergency-stop` to `backend/app/api/assets.py`:
    - Sets `emergency_stop_active=True` on the asset's `AssetAssessmentScope`.
    - Immediately cancels running scans for that asset using `process_safety.terminate_process_tree` (< 3s).

### 4.3 Specification: R4 Custom Synthetic Test Harness & File Policy Engine
- **Synthetic Test Harness (`backend/app/engines/synthetic_harness.py`)**:
  - Queries active `SyntheticIdentity` records from `synthetic_identities` table.
  - BOLA (`API-001`): If either Student Persona A or Student Persona B is missing -> sets state to `BLOCKED` with detailed audit log; if present -> probes `/api/users/{id}/learning-records` cross-account.
  - BFLA (`API-005`): If synthetic low-privileged student identity is missing -> sets state to `BLOCKED`; if present -> tests administrative routes with student credentials.
- **File Policy Engine (`backend/app/engines/file_policy.py`)**:
  - Queries `BaselineException` records where `classification == "PUBLIC_BY_DESIGN"`.
  - Check `FILE-001` (Approved Media Validation): Probes approved media paths; if returning 200/404 for authorized educational extensions (.pdf, .mp4, .mp3, etc.) -> sets state to `PASS` (zero false positive vulnerability alerts).
  - Check `FILE-002` (Sensitive File Leakage): Probes for forbidden patterns (.csv, .env, passwords.txt, backup.zip); if sensitive file content is detected -> sets state to `FAIL` and creates high/critical `NormalizedFinding`.

---

## 5. Verification Method

### 5.1 Programmatic Unit and Regression Verification
- Run test suite verification command:
  ```bash
  python3 -m pytest tests_pilot/ -q
  ```
- Run end-to-end capabilities verification script:
  ```bash
  python3 scripts/verify_empire_e2e.py
  ```

### 5.2 Independent Inspection Commands
- Inspect models:
  ```bash
  python3 -c "from backend.app.models.scope import AssetAssessmentScope; from backend.app.models.synthetic_identity import SyntheticIdentity; from backend.app.models.baseline import BaselineException; print('Core models loaded successfully.')"
  ```
- Inspect API route registrations:
  ```bash
  python3 -c "from backend.main import app; routes = [r.path for r in app.routes]; print(f'Total routes mounted: {len(routes)}')"
  ```
- Test SSRF gatekeeper:
  ```bash
  python3 -c "from backend.app.core.ssrf import SSRFProtector; print(SSRFProtector.validate_target('https://empire.edu.vn'))"
  ```

### 5.3 Invalidation Conditions
- Any implementation that defaults unrun, blocked, or error check states to `PASS` violates R1 acceptance criteria.
- Any implementation that allows scan dispatch without an active, recorded scope record violates R2 acceptance criteria.
- Any implementation where missing synthetic credentials marks BOLA/BFLA as `PASS` or `NOT_APPLICABLE` (instead of `BLOCKED`) violates R4 acceptance criteria.
