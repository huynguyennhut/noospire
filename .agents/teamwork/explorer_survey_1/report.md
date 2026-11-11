# NOOSFORGE Security Intelligence — Technical Survey & Architecture Report

- **Date**: 2026-11-08T12:35:00Z
- **Author**: `explorer_survey_1`
- **Scope**: Codebase Survey (`c:\Users\nguye\Desktop\noospire`)
- **Target Platform**: Empire Educational Platform (`https://empire.edu.vn/`)
- **Status**: Complete & Verified (10/10 E2E Tests Passing)

---

## Executive Summary

The Noospire / NOOSFORGE platform is a security assessment, continuous attack surface monitoring, and vulnerability management platform purpose-built for the Empire Educational Ecosystem. The architecture comprises:
1. **Async FastAPI Backend (`backend/`)**: High-performance Python async REST API exposing 13 specialized routers, a background task dispatcher with an in-memory ring-buffer for live SSE log streaming, SSRF egress protection, and a multi-format reporting engine (ReportLab vector PDF, HTML, JSON).
2. **Database & ORM (`noospire.db`)**: Dual SQLite/PostgreSQL support via SQLAlchemy 2.0 async engine (`aiosqlite` / `asyncpg`), platform-independent UUID type (`CHAR(36)`), and deterministic database seeding (`backend/app/core/empire_seeder.py`).
3. **Target Management Subsystem**: Asset inventory with bulk CSV/JSON/OpenAPI import deduplication, automatic Empire module categorization, approved public exposure policy management (`BaselineException`), and administrative ownership override.
4. **End-to-End Verification Harness (`scripts/verify_empire_e2e.py`)**: 10 automated test steps evaluating database seeding, metrics, module mapping, deduplication, `/media` baseline policy, scan execution, vulnerability triage lifecycle, report generation, daily scheduler triggering, and security alerts.
5. **Launcher & Doctor Validation Scripts (`run.cmd`, `run.ps1`, `run.sh`)**: Unified cross-platform launchers providing interactive command menus and `--check` / `doctor` flags directly invoking the 10-step E2E verification suite.

---

## 1. Backend Architecture, FastAPI App Entrypoint, Routers & Configuration

### 1.1 Entrypoint Structure
- **Canonical ASGI Entrypoint**: `backend/app/main.py`
  - Canonical module path: `backend.app.main:app`
  - Re-exports `app`, `create_app`, and `lifespan` from `backend.main` to support ASGI servers targeting either module.
- **Application Factory & Lifespan**: `backend/main.py`
  - Entrypoint: `backend.main:app`
  - Fast-start via `create_app()` configuring CORS middleware (`settings.CORS_ORIGINS`), OpenAPI title, version (`settings.VERSION`), and 13 API routers under prefix `/api/v1`.
  - **Lifespan Management (`lifespan(app: FastAPI)`)**:
    1. *Database Initialization & Seeding*: Calls `await init_db()` to register all models, execute `Base.metadata.create_all`, seed the default admin account (`admin`/`admin123`), and populate the Empire ecosystem baseline.
    2. *Stale Job Recovery*: Scans the `scans` table for leftover jobs in `QUEUED`, `INITIALIZING`, or `RUNNING` status from previous crashes or restarts, updating them to `CANCELLED` with error message `"Session interrupted / server restarted."`.
    3. *Background Worker Startup*: Retrieves the task dispatcher via `get_dispatcher()`. If configured as `AsyncWorkerDispatcher`, spawns the asynchronous consumer loop.
    4. *Clean Shutdown*: Signals `await dispatcher.stop()`, canceling worker tasks and releasing resources.

### 1.2 Router Inventory (`/api/v1/*`)
All routers are mounted in `backend/main.py` under `settings.API_V1_STR` (`/api/v1`):

| Router Module | Route Prefix | Tags | Primary Endpoints & Operations |
|---|---|---|---|
| `backend/app/api/auth.py` | `/auth` | Authentication | `/login`, `/me`, `/refresh`, token issuance (JWT HS256) |
| `backend/app/api/assets.py` | `/assets` | Target & Asset Management | `GET /`, `POST /` (create), `POST /bulk-import` (deduped import), `GET /{id}`, `GET /{id}/summary`, `PUT /{id}`, `DELETE /{id}`, `POST /{id}/verify` |
| `backend/app/api/scans.py` | `/scans` | Scan Center | `GET /`, `POST /` (dispatch), `GET /{id}`, `DELETE /{id}`, `POST /{id}/cancel`, `GET /{id}/logs`, `GET /{id}/logs/stream` (SSE) |
| `backend/app/api/findings.py` | `/findings` | Findings Explorer & Remediation | `GET /` (paginated filters), `GET /{id}`, `POST /{id}/triage` (10-state transition), `POST /{id}/retest` (live HTTP retest) |
| `backend/app/api/metrics.py` | `/metrics` | Metrics & Dashboard Telemetry | `GET /overview` (10 core KPIs), `GET /severity-distribution`, `GET /charts/vulnerability-trend`, `GET /charts/module-risk` |
| `backend/app/api/empire_modules.py` | `/empire-modules` | Empire Modules | `GET /` (posture, asset count, findings, and risk score across 6 business units) |
| `backend/app/api/baselines.py` | `/baselines` | Approved Baseline Exceptions | `GET /`, `POST /` (register `/media/*` exception), `DELETE /{id}` (revoke) |
| `backend/app/api/schedules.py` | `/schedules` | Continuous Daily Schedules | `GET /`, `POST /` (create cron), `POST /{id}/trigger` (manual pipeline run), `PUT /{id}/toggle` |
| `backend/app/api/alerts.py` | `/alerts` | Security Alerts & Notifications | `GET /` (in-app alerts), `POST /{id}/read`, `POST /read-all` |
| `backend/app/api/reports.py` | `/reports` | Reporting | `GET /`, `POST /` & `POST /generate` (generates PDF, HTML, JSON), `GET /{id}`, `GET /{id}/download/{fmt}`, `DELETE /{id}` |
| `backend/app/api/rules.py` | `/rules` | Detection Rules | YAML detection rule management, syntax validation, test fixture execution |
| `backend/app/api/intel.py` | `/intel` | Threat Intelligence | CVE lookup, CISA KEV synchronization, EPSS scores |
| `backend/app/api/settings.py` | `/settings` | System Settings | General system settings, environment flags, and operational parameters |

### 1.3 System Endpoints
- `GET /health`: Returns JSON payload:
  ```json
  {
    "status": "healthy",
    "service": "NOOSFORGE Security Intelligence",
    "target": "Empire Educational Ecosystem",
    "version": "2.0.0",
    "timezone": "Asia/Ho_Chi_Minh",
    "dispatcher_mode": "async_worker"
  }
  ```
- `GET /`: Returns welcome message, version, and `/docs` link.

### 1.4 Configuration Architecture (`backend/app/core/config.py`)
- Subclasses `pydantic_settings.BaseSettings` reading environment variables and optional `.env` file (`case_sensitive=False`, `extra="ignore"`).
- Key Settings:
  - `DATABASE_URL`: Defaults to `sqlite+aiosqlite:///./noospire.db`. Overrideable via `SENTINEL_DATABASE_URL` (e.g. `postgresql+asyncpg://user:pass@host/db`).
  - `DISPATCHER_MODE`: `async_worker` (default embedded concurrency) or `celery` (distributed queue).
  - `MAX_CONCURRENT_SCANS`: 4 concurrent worker slots.
  - `DEFAULT_SCAN_TIMEOUT`: 600 seconds.
  - `DEFAULT_TIMEZONE`: `"Asia/Ho_Chi_Minh"`.
  - `DEV_AUTH_BYPASS` / `AUTH_ENABLED`: In `development` mode, auth bypass is enabled to facilitate seamless API and testing integration without constant token renegotiation.
  - `SSRF_ALLOW_PRIVATE_TARGETS`: Defaults to `true` in lab environments to permit testing against staging and local endpoints while retaining strict cloud metadata protections.

---

## 2. Database Models, ORM, SQLite/PostgreSQL Configuration & Migrations

### 2.1 Async Engine & Session Factory (`backend/app/core/database.py`)
- Engine: `create_async_engine(settings.DATABASE_URL, **engine_kwargs)`
  - Dialect branch:
    - SQLite: `connect_args={"check_same_thread": False}`.
    - PostgreSQL: `pool_size=10`, `max_overflow=20`.
- Session Maker: `AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False)`.
- Dependency: `get_db()` async generator yielding active `AsyncSession` with guaranteed session closure.

### 2.2 Platform-Independent UUID Type (`backend/app/models/base.py`)
- Implements `GUID(TypeDecorator)` backed by `String(36)`.
- Converts `uuid.UUID` objects to strings during `process_bind_param` and back to `uuid.UUID` instances during `process_result_value`.
- Guarantees 100% binary/string compatibility whether running against SQLite or PostgreSQL.

### 2.3 Comprehensive Entity Model Mapping

| Table Name | Model Class | Key Columns & Indexes | Description & Relationships |
|---|---|---|---|
| `users` | `User` | `id` (GUID PK), `username` (VARCHAR unique index), `hashed_password`, `is_active`, `is_superuser`, timestamps | Admin and analyst accounts. |
| `assets` | `Asset` | `id` (GUID PK), `name` (index), `asset_type`, `target_locator`, `empire_module` (index), `environment`, `technology`, `approved_media_baseline`, `assessment_policy` (JSON), `auth_profile` (JSON), `excluded_endpoints` (JSON), `verification_status` (index), `verification_type`, `verification_token`, `verified_at`, `criticality`, `exposure`, `description`, `tags` (JSON), timestamps | Inventory targets; `scans` (1:N, cascade delete), `findings` (1:N, cascade delete). |
| `scans` | `Scan` | `id` (GUID PK), `asset_id` (GUID FK index), `engine`, `profile`, `status` (index), `progress_percentage`, `target_locator`, `allow_private_targets`, `timeout_seconds`, `error_message`, `started_at`, `completed_at`, timestamps | Assessment execution runs; `asset` (N:1), `logs` (1:N, cascade delete), `findings` (1:N, cascade delete). |
| `scan_logs` | `ScanLog` | `id` (GUID PK), `scan_id` (GUID FK index), `timestamp`, `level`, `message`, `source` | Audit execution logs per scan. |
| `findings` | `NormalizedFinding` | `id` (GUID PK), `scan_id` (GUID FK index), `asset_id` (GUID FK index), `fingerprint` (VARCHAR 64 index), `empire_module` (index), `exposure_classification`, `is_approved_baseline`, `scanner_engine` (index), `scanner_rule_id`, `title`, `description`, `severity` (index), `original_severity`, `cve_id` (index), `cwe_id`, `cvss_score`, `cvss_vector`, `epss_score`, `epss_percentile`, `is_kev`, `target_location`, `target_component`, `evidence` (JSON), `raw_payload`, `remediation`, `references` (JSON), `status` (index), `remediation_notes`, `assignee`, `retest_status`, `occurrence_count`, `first_seen_at`, `last_seen_at`, timestamps | Deduplicated vulnerability findings; `asset` (N:1), `scan` (N:1). |
| `baseline_exceptions` | `BaselineException` | `id` (GUID PK), `scope` (index), `classification`, `reason`, `owner`, `approved_by`, `is_active`, `expiration_date`, `evidence` (JSON), `review_history` (JSON), timestamps | Approved public exposure baseline policies (`/media/*`). |
| `daily_schedules` | `DailySchedule` | `id` (GUID PK), `name`, `profile`, `cron_expression`, `timezone`, `is_active`, `target_ids` (JSON), `last_run_at`, `next_run_at`, `last_status`, timestamps | Automated scheduled scan pipelines. |
| `security_alerts` | `SecurityAlert` | `id` (GUID PK), `severity` (index), `title`, `message`, `category`, `is_read` (index), `metadata_json` (JSON), timestamps | SOC notifications and regression alerts. |
| `synthetic_identities` | `SyntheticIdentity` | `id` (GUID PK), `identifier` (unique index), `role`, `email`, `description`, `is_active`, `last_used_at`, timestamps | Personas for non-destructive authorization testing. |
| `reports` | `Report` | `id` (GUID PK), `title`, `report_type`, `asset_id` (GUID index), `scan_id` (GUID index), `target_scope`, `formats` (JSON), `status`, `summary` (JSON), `file_paths` (JSON), `created_by`, timestamps | Audit report generation metadata. |
| `detection_rules` | `DetectionRule` | `id` (VARCHAR PK index), `name`, `severity`, `status` (index), `target_types` (JSON), `detection_json` (JSON), `raw_yaml`, timestamps | Declarative YAML detection rules. |
| `rule_audit_logs` | `RuleAuditLog` | `id` (GUID PK), `rule_id` (FK index), `action`, `performed_by`, `timestamp` | Rule lifecycle change auditing. |
| `rule_test_fixtures` | `RuleTestFixture` | `id` (GUID PK), `rule_id` (FK index), `fixture_name`, `expected_result` | Rule regression test fixtures. |
| `vulnerability_intelligence` | `VulnerabilityIntelligence` | `cve_id` (VARCHAR PK index), `cvss_v3_score` (index), `epss_score` (index), `is_cisa_kev` (index), `cwe_ids` (JSON), `source_provenance` (JSON), timestamps | Aggregated threat intelligence (NVD, KEV, EPSS). |
| `vulnerability_aliases` | `VulnerabilityAlias` | `id` (GUID PK), `cve_id` (FK index), `alias_id` (index), `alias_type` | Cross-referenced CVE aliases (GHSA, OSV). |

### 2.4 Database State & Migration Model
- **Current Live DB**: `noospire.db` (458 KB SQLite database).
- **Row Counts in Live DB**:
  - `users`: 1 (Default admin)
  - `assets`: 6 (Empire targets)
  - `findings`: 24 (Historical and verified findings)
  - `baseline_exceptions`: 1 (`https://mh.empire.edu.vn/media/*`)
  - `daily_schedules`: 1 (`0 2 * * *` `Asia/Ho_Chi_Minh`)
  - `security_alerts`: 5
  - `synthetic_identities`: 3 (`studenttu1`, `test_student_a`, `test_student_b`)
  - `reports`: 8
  - `scans`: 83
  - `scan_logs`: 401
  - `vulnerability_intelligence`: 15
  - `vulnerability_aliases`: 5
- **Migration Strategy**: The project utilizes declarative table registration via `Base.metadata.create_all` during `init_db()`. No Alembic migration scripts exist in the repository; the schema is maintained via declarative SQLAlchemy metadata and initialized idempotently.

---

## 3. Target Management Logic, Verification Pipeline, Target Models & Schema

### 3.1 Target Asset Schema & Data Model
- Pydantic models defined in `backend/app/schemas/asset.py`:
  - `AssetBase`: Validates `name`, `asset_type` (`AssetType` enum), `target_locator` (URL/domain), `empire_module` (`EmpireModule` enum), `environment` (default: `"PRODUCTION"`), `technology`, `criticality` (`Criticality` enum), `exposure` (`Exposure` enum), `approved_media_baseline` (boolean), `assessment_policy` (dict), `auth_profile` (dict), `excluded_endpoints` (list of strings).
  - `AssetCreate` / `AssetUpdate`: Creation and partial update schemas.
  - `AssetResponse`: Adds `id`, `verification_status`, `verification_type`, `verification_token`, `verified_at`, and timestamps.
  - `AssetBulkImportRequest` & `AssetBulkImportResponse`: Supports multi-target bulk ingestion with duplicate tracking and preview data.

### 3.2 Bulk Import & Deduplication Logic
Located in `backend/app/api/assets.py` (`POST /api/v1/assets/bulk-import`):
1. **Multi-Format Parsing**:
   - JSON array: Parses lists of strings or objects.
   - CSV text: Reads comma-separated lines with headers (`target_locator`, `url`, `target`, `name`, `environment`).
   - Plain line-delimited URLs / hostnames.
2. **URL Normalization**: Automatically prepends `https://` if protocol scheme is omitted.
3. **Duplicate Detection**: Queries the database for existing `Asset.target_locator == locator`. If found, increments `skipped_duplicates` counter and skips insertion.
4. **Heuristic Module Classification**: If no module is specified in the import row, automatically assigns `empire_module` based on domain/path tokens:
   - Contains `id.`, `auth`, or `student` ➔ `STUDENT_MANAGEMENT`
   - Contains `media`, `voh.`, `mh.`, or `storage` ➔ `LEARNING_MATERIALS`
   - Contains `news`, `tool`, or `vocab` ➔ `SUPPORTING_TOOLS`
   - Contains `gw.` or `api` ➔ `API_SERVICES`
   - Contains `console`, `admin`, or `app` ➔ `WEB_APPLICATION`
   - Default fallback ➔ `SERVER_INFRASTRUCTURE`
5. **Immediate Authorization**: Automatically assigns `verification_status = VERIFIED` and `verification_type = ADMIN_OVERRIDE` to allow immediate assessment.

### 3.3 Verification Pipeline State & R1 Requirements Analysis
- **Current Verification Implementation**:
  - `POST /api/v1/assets/{asset_id}/verify`: Sets `asset.verification_status = VERIFIED`, `asset.verification_type = ADMIN_OVERRIDE`, and `asset.verified_at = now()`.
  - SSRF pre-flight validation in `SSRFProtector.validate_target` (`backend/app/core/ssrf.py`):
    - URL syntax parsing (scheme validation, port range check, embedded credential rejection).
    - Hostname resolution (`socket.getaddrinfo`).
    - Cloud metadata blocking (`169.254.169.254`, `metadata.google.internal`, etc.).
    - Blocked CIDR network filtering (RFC 1918, loopback, multicast, unroutable).
- **R1 Specification Gap**: Requirement R1 calls for an **8-step live verification pipeline**:
  1. Input validation (syntax, scheme, credential check)
  2. DNS resolution (records, IPv4/IPv6 address resolution)
  3. TLS verification (certificate chain, expiry, cipher)
  4. HTTP connectivity (status codes, latency)
  5. Redirect inspection (tracking hops, destination target matching)
  6. Web discovery (robots.txt, sitemap.xml, common endpoints)
  7. Target fingerprint (Server header, technology headers, favicon hash)
  8. Verification result (compiling metadata into asset profile)
  Currently, steps 1-2 are handled inside SSRF validation, and target verification defaults to `ADMIN_OVERRIDE`. Implementing the full 8-step live pipeline will enhance target onboarding into an active discovery workflow.

---

## 4. Thorough Analysis of `scripts/verify_empire_e2e.py` (All 10 Tests)

`scripts/verify_empire_e2e.py` is the official vertical slice verification suite. It tests all 10 core subsystem capabilities using `httpx.ASGITransport(app=app)` against the live in-memory ASGI application and SQLite database.

```
+---------------------------------------------------------------------------------------------------+
|                        verify_empire_e2e.py — 10 Automated Capability Tests                       |
+--------+------------------------------------------+--------------------+--------------------------+
| Step # | Subsystem Tested                         | Target Endpoint/Op | Key Verification Metric  |
+--------+------------------------------------------+--------------------+--------------------------+
| Step 1 | DB Init & Ecosystem Seeding              | init_db() [ORM]    | Assets >= 6, Vulns >= 6  |
| Step 2 | Overview KPIs & Metrics Charts           | /metrics/overview  | Risk score, module chart |
| Step 3 | Empire Business Module Hub               | /empire-modules    | 4 core module keys exist |
| Step 4 | Bulk Import & Deduplication              | /assets/bulk-import| 1 new, 2 deduped skipped |
| Step 5 | Approved Public Media Baseline Policy    | /baselines         | /media PUBLIC_BY_DESIGN  |
| Step 6 | Scan Dispatch & Execution Engine         | /scans             | HTTP 201, audit logs > 0 |
| Step 7 | Vulnerability Triage Lifecycle & Retest  | /findings/{id}/*   | CONFIRMED status, retest |
| Step 8 | Multi-Format Audit-Grade Report Gen      | /reports/generate  | PDF/HTML/JSON on disk    |
| Step 9 | Daily Assessment Scheduler Pipeline      | /schedules/{id}/trg| Dispatched scan jobs > 0 |
| Step 10| Security Alerts & In-App Notifications   | /alerts/{id}/read  | Alert marked as read     |
+--------+------------------------------------------+--------------------+--------------------------+
```

### Detailed Breakdown of Every Step:

#### Step 1: Database Initialization & Empire Seed Verification
- **Execution Mechanism**: Direct async invocation `await init_db()`.
- **Database Assertions**:
  1. `Asset`: `select(Asset)` ➔ Expects `len(assets) >= 6` (id, gw, mh/media, voh, console, news).
  2. `NormalizedFinding`: `select(NormalizedFinding)` ➔ Expects `len(findings) >= 6` (VULN-01 through VULN-06).
  3. `BaselineException`: `select(BaselineException)` ➔ Expects `len(baselines) >= 1` with scope containing `"/media"` and classification `"PUBLIC_BY_DESIGN"`.
  4. `DailySchedule`: `select(DailySchedule)` ➔ Expects `len(schedules) >= 1` configured for `0 2 * * *` in `Asia/Ho_Chi_Minh`.
- **Outcome**: Verified. (Live DB currently contains 6 assets, 24 findings, 1 baseline, 1 schedule).

#### Step 2: Dashboard Overview KPIs & Analytics Verification
- **Inputs**: HTTP GET `/api/v1/metrics/overview` and HTTP GET `/api/v1/metrics/charts/module-risk`.
- **Expected Responses**:
  - Overview: Status 200, JSON dict containing `overall_risk_score` (float 0-100), `risk_posture` (`CRITICAL`, `ELEVATED`, `MODERATE`, or `OPTIMAL`), `total_assets`, `total_open_findings`, `critical_findings`, `high_findings`.
  - Module Risk Chart: Status 200, array of operational module risk metrics.
- **Assertions**: `resp.status_code == 200`, valid metrics dict returned, module risk chart returned distinct operational modules.

#### Step 3: Empire Business Architecture Modules Verification
- **Inputs**: HTTP GET `/api/v1/empire-modules`.
- **Expected Responses**: Status 200, JSON list of module objects with `module_key`, `title`, `risk_score`, `total_findings`.
- **Assertions**:
  - `resp.status_code == 200`
  - `assert "STUDENT_MANAGEMENT" in module_keys`
  - `assert "LEARNING_MATERIALS" in module_keys`
  - `assert "SUPPORTING_TOOLS" in module_keys`
  - `assert "API_SERVICES" in module_keys`

#### Step 4: Asset Inventory & Bulk Import Deduplication
- **Inputs**: HTTP POST `/api/v1/assets/bulk-import` with CSV payload:
  ```csv
  target,name,empire_module,environment
  https://id.empire.edu.vn,Empire ID Service,STUDENT_MANAGEMENT,PRODUCTION
  https://new-student-portal.empire.edu.vn,New Student Onboarding Portal,STUDENT_MANAGEMENT,STAGING
  https://voh.empire.edu.vn,Empire Media CDN,LEARNING_MATERIALS,PRODUCTION
  ```
- **Expected Responses**: Status 200, JSON payload with `imported_count == 1`, `skipped_duplicates == 2`.
- **Assertions**:
  - Correctly imports the single new target (`new-student-portal.empire.edu.vn`).
  - Correctly identifies and rejects the two pre-existing targets as duplicates.
  - Clean-up: Loops through `imported_assets` and calls `DELETE /api/v1/assets/{id}` to ensure zero pollution of the production inventory.

#### Step 5: Approved Public Media Baseline Verification
- **Inputs**: HTTP GET `/api/v1/baselines`.
- **Expected Responses**: Status 200, JSON list of baseline exceptions.
- **Assertions**:
  - Locates entry where `"/media" in b["scope"]`.
  - Validates `classification == "PUBLIC_BY_DESIGN"`.
  - Validates `is_active == True`.

#### Step 6: Scan Dispatch & Empire Assessment Engine Execution
- **Inputs**:
  1. Identifies `id.empire.edu.vn` asset from inventory.
  2. HTTP POST `/api/v1/scans` with payload:
     ```json
     {
       "asset_id": "<asset_uuid>",
       "profile": "DAILY_SECURITY",
       "name": "E2E Automated Empire Daily Security Assessment",
       "parameters": { "safe_mode": true, "concurrency": 2 }
     }
     ```
  3. Sleeps 2 seconds for worker processing.
  4. HTTP GET `/api/v1/scans/{scan_id}/logs`.
- **Expected Responses**:
  - Dispatch: Status 201 Created with scan ID and initial `QUEUED` status.
  - Logs: Status 200 with generated audit log entries.
- **Assertions**: `resp.status_code == 201`, `log_resp.status_code == 200`.

#### Step 7: Vulnerability Triage Lifecycle & Live Retest Verification
- **Inputs**:
  1. Picks first finding from database.
  2. HTTP POST `/api/v1/findings/{finding_id}/triage` with payload:
     ```json
     {
       "status": "CONFIRMED",
       "assignee": "lead-sec-engineer@empire.edu.vn",
       "comment": "Triaged by E2E test harness. Evidence verified against live environment."
     }
     ```
  3. HTTP POST `/api/v1/findings/{finding_id}/retest`.
- **Expected Responses**:
  - Triage: Status 200, finding status updated to `CONFIRMED`, assignee updated.
  - Retest: Status 200, returns retest evaluation (`status`, `retest_status`, `notes`).
- **Assertions**: `resp.status_code == 200` for both endpoints, finding updated and verified.

#### Step 8: Multi-Format Audit-Grade Report Generation
- **Inputs**: HTTP POST `/api/v1/reports/generate` with payload:
  ```json
  {
    "title": "Empire Educational Platform — Comprehensive Security Audit",
    "report_type": "technical",
    "asset_id": "<asset_uuid>",
    "formats": ["pdf", "html", "json"]
  }
  ```
- **Expected Responses**: Status 200 or 201, `status == "READY"`, `file_paths` dictionary containing local disk paths for each format (`storage/reports/{report_id}.*`).
- **Assertions**:
  - Each artifact (`.pdf`, `.html`, `.json`) is validated for existence and non-zero byte size on disk.
  - Example verified sizes: JSON (~8.6 KB), HTML (~19.4 KB), PDF (~9.8 KB).

#### Step 9: Daily Assessment Scheduler Trigger
- **Inputs**:
  1. HTTP GET `/api/v1/schedules`.
  2. HTTP POST `/api/v1/schedules/{sched_id}/trigger`.
- **Expected Responses**: Status 200, returns confirmation message and list of `dispatched_scans` UUIDs dispatched across all scheduled targets.
- **Assertions**: `resp.status_code == 200`, `len(dispatched_scans) == len(targets)` (dispatched 6 scans for the 6 assets).

#### Step 10: Security Alerts & In-App Notification System
- **Inputs**:
  1. HTTP GET `/api/v1/alerts`.
  2. HTTP POST `/api/v1/alerts/{alert_id}/read`.
- **Expected Responses**:
  - List alerts: Status 200, returns list of alerts.
  - Mark read: Status 200, returns `{"id": "...", "is_read": true}`.
- **Assertions**: Alerts retrieved successfully; first alert marked as read.

---

## 5. Launcher & Doctor Validation Scripts (`run.cmd`, `run.ps1`, `run.sh`)

### 5.1 Windows CMD Launcher (`run.cmd`)
- **Flags Supported**:
  - `--check`, `doctor`, `verify`, `check`, `--test`: Triggers `python scripts\verify_empire_e2e.py`. Evaluates `%ERRORLEVEL%`. Prints green `[+] HE THONG XANH MUOT 100% - SAN SANG TAC CHIEN!` if exit code is 0, or red `[-] BAO DONG DO: He thong gap su co kiem dinh!` on error.
  - `--preset all`: Spawns both backend (`uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload`) and frontend (`cd frontend && npm run dev`) in separate windows using `start cmd /c`, waits 3 seconds, and opens browser to `http://localhost:3000/dashboard`.
  - `--backend`: Starts FastAPI on port 8000.
  - `--frontend`: Starts Next.js on port 3000.
- **Interactive TUI**: If no arguments are passed, displays an ASCII banner and numeric menu options [1-5].

### 5.2 PowerShell Launcher (`run.ps1`)
- **Parameters**: `param ([string]$Preset = "", [switch]$Check, [switch]$Backend, [switch]$Frontend, [switch]$Y)`.
- **Positional Argument Fallback**: Handles `--check`, `doctor`, `verify`, `--preset all`, `--backend`, `--frontend` passed in `$args`.
- **Execution Consistency**: Directly executes `python scripts\verify_empire_e2e.py` and checks `$LASTEXITCODE == 0`.
- **Process Spawning**: Uses `Start-Process cmd.exe -ArgumentList '/c', ...` for background process isolation.

### 5.3 Linux / macOS Launcher (`run.sh`)
- Written in POSIX-compliant Bash with color codes (`\033[0;32m`, etc.).
- Mirror parity with `run.cmd` and `run.ps1` for `--check`, `--preset all`, `--backend`, `--frontend`, and interactive CLI menu.

---

## 6. Architecture Synthesis & Recommendations for Subsequent Agents

### 6.1 Agent 1: Platform Core (Target Management & Pipeline)
- Primary target `https://empire.edu.vn/` is the core assessment target.
- Currently, `backend/app/core/empire_seeder.py` seeds subdomains (`id.empire.edu.vn`, `gw.empire.edu.vn`, `mh.empire.edu.vn`, `voh.empire.edu.vn`, `console.empire.io.vn`), but the root domain `https://empire.edu.vn/` should be explicitly registered as the primary target in the asset inventory.
- Implement the formal **8-step verification pipeline** service (`verify_target_pipeline`) in `backend/app/core/` and expose it via `POST /api/v1/assets/{id}/verify-pipeline`, returning the complete 8-stage verification object (DNS, TLS, HTTP, Redirects, Discovery, Fingerprint, Policy).

### 6.2 Agent 2: Scanning & Intelligence (Real Scanner Orchestration)
- `EmpireAssessmentEngine` (`backend/app/scanners/empire_engine.py`) and `NucleiLabRunner` / `ZAPAdapter` (`backend/app/scanners/lab_runners.py`) provide robust probe logic.
- Ensure bounded real-world HTTP probing against `https://empire.edu.vn/` collects genuine TLS certificates, HTTP response headers, redirect chains, and technologies without synthetic mocking.
- Maintain strict non-destructive testing boundaries: max 5 negative-auth attempts, no mass spraying, and respect for `/media` `PUBLIC_BY_DESIGN` policy.

### 6.3 Agent 3: UI & Product Experience (Next.js 14 Frontend)
- Next.js 14 App Router frontend is structured under `frontend/src/app/` with 14 views (`dashboard`, `assets`, `empire-modules`, `scans`, `active-assessments`, `findings`, `threat-intel`, `remediation`, `reports`, `schedules`, `integrations`, `health`, `settings`).
- Complete bilingual i18n support (Vietnamese default, English toggle) across all 14 views.
- Ensure the Black/White/Liquid Glass design tokens and Cyber-Slate theme are consistently rendered across charts and tables.
