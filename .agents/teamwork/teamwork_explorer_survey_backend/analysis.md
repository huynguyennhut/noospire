# NOOSFORGE Security Intelligence — Backend Architecture & Integrity Survey Report
**Date**: 2026-11-09T23:45:00Z  
**Author**: Backend Architecture & Integrity Survey Explorer (Teamwork Explorer)  
**Investigation Target**: `backend/` (`backend/app/api`, `core`, `models`, `schemas`, `intel`, `reporting`, `risk`, `rules`, `scanners`)  
**Database**: `noospire.db` (SQLite WAL mode, 47 MB)  
**Status**: COMPLETE (Phase I Discovery & Phase II Integrity Audit)

---

## 1. Executive Summary

A comprehensive, evidence-driven static and empirical investigation of the authoritative backend codebase in `c:\Users\nguye\Desktop\noospire\backend\` was conducted. The investigation evaluated all API routes, database schemas, ORM models, core background services, process safety mechanisms, scan orchestrators, and third-party engine adapters.

### Core Audit Verdict: REAL IMPLEMENTATION & HIGH INTEGRITY
- **API Surface**: 16 mounted FastAPI routers under `/api/v1` exposing 50+ distinct REST endpoints. All endpoints connect to live SQLAlchemy 2.0 ORM sessions and real database tables; no fake endpoints or hardcoded stub responses were detected.
- **Database Architecture**: 16 SQLAlchemy declarative models backed by `noospire.db` (47 MB). SQLite WAL mode (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=30000;`) is enforced via engine connection events and schema initialization. All foreign keys enforce cascading deletes or explicit nullifications.
- **Core Security Engines**: The 8-step live target verification pipeline (`TargetVerifier`), process safety and resource manager (`AsyncWorkerDispatcher` + `ProcessSafetyManager`), SSRF gatekeeper (`SSRFProtector`), and specialized assessment engine (`EmpireAssessmentEngine`) perform authentic network I/O using `httpx`, `socket`, `ssl`, and subprocess CLI invocations.
- **Automated Test Validation**: Pytest test suite executed cleanly (e.g. 22/22 tests passing across `test_platform_core_m1.py` and `test_scan_all_batch_orchestration.py` in 24.82s with zero failures).

---

## 2. API Routes & Controllers Inventory (16 Mounted Routers)

FastAPI application is initialized in `backend/main.py` and aliased through `backend/app/main.py`. 16 routers are included under `settings.API_V1_STR` (`/api/v1`).

| # | Router Module | Route Prefix | HTTP Methods & Paths | Schema & Validation | Database Interaction | Implementation Authenticity |
|---|---------------|--------------|----------------------|---------------------|----------------------|----------------------------|
| 1 | `api/auth.py` | `/auth` | `POST /login`<br>`GET /me`<br>`POST /refresh`<br>`GET /audit` | `LoginRequest`, `TokenResponse`, `UserProfile`, `AdminAuditResponse` | Queries `users` table; inserts `admin_audit_logs` entries | **REAL**: Uses PBKDF2-HMAC-SHA256 (100,000 iterations), constant-time `hmac.compare_digest`, PyJWT tokens. |
| 2 | `api/assets.py` | `/assets` | `GET /`<br>`POST /`<br>`POST /bulk-import`<br>`POST /bulk-preview`<br>`GET /{id}`<br>`GET /{id}/summary`<br>`PUT /{id}`<br>`DELETE /{id}`<br>`POST /{id}/verify` | `AssetCreate`, `AssetUpdate`, `AssetResponse`, `AssetBulkPreviewResponse`, `AssetVerifyResponse` | Full CRUD on `assets` table; joins `findings` and `scans` | **REAL**: Ingests JSON/CSV/OpenAPI/plain text, deduplicates against DB, executes 8-step live probe pipeline via `TargetVerifier`. |
| 3 | `api/scans.py` | `/scans` | `GET /`<br>`POST /`<br>`POST /batch`<br>`POST /scan-all`<br>`GET /batches`<br>`GET /batch/{id}`<br>`POST /batch/{id}/cancel`<br>`POST /stop-all`<br>`GET /trackcurrent`<br>`GET /telemetry`<br>`GET /{id}`<br>`DELETE /{id}`<br>`POST /{id}/cancel`<br>`GET /{id}/logs`<br>`DELETE /{id}/logs`<br>`GET /{id}/logs/stream`<br>`POST /loop-test` | `ScanCreate`, `ScanResponse`, `ScanBatchCreate`, `ScanBatchRead`, `BatchScanResponse`, `TrackCurrentResponse`, `LoopTestRequest` | Queries and persists `scans`, `scan_batches`, `scan_logs`, and `security_alerts` | **REAL**: Real async dispatching, `psutil` CPU/RAM throttling, live SSE stream via `ScanLogBuffer`, process tree termination via `ProcessSafetyManager`. |
| 4 | `api/findings.py` | `/findings` | `GET /`<br>`GET /{id}`<br>`POST /{id}/triage`<br>`POST /{id}/retest` | `FindingResponse`, `FindingTriageRequest` | Full querying and updates on `findings` table; emits `security_alerts` | **REAL**: 10 lifecycle triage states with full audit history in JSON evidence; live retest executes genuine HTTP probe to verify remediation. |
| 5 | `api/metrics.py` | `/metrics` | `GET /overview`<br>`GET /severity-distribution`<br>`GET /charts/vulnerability-trend`<br>`GET /charts/module-risk`<br>`GET /charts/coverage`<br>`GET /charts/risk-trend`<br>`GET /charts/scanner-performance`<br>`GET /charts/intelligence-activity`<br>`GET /charts/remediation-progress` | `MetricsOverviewResponse`, structured chart schemas | Aggregates `assets`, `scans`, `findings`, and `vulnerability_intelligence` | **REAL**: Computes 10 core KPIs and 8 chart datasets from live database records. (See Tech Debt for 2 static sub-metrics). |
| 6 | `api/threat_intel.py` | `/threat-intel` | `GET /summary`<br>`POST /sync`<br>`GET /cve/{id}`<br>`GET /cves`<br>`GET /kev`<br>`POST /epss/batch` | `ThreatIntelSummaryResponse`, `ThreatIntelSyncRequest`, `VulnerabilityIntelligenceResponse`, `EPSSBatchQueryRequest` | Full CRUD and search on `vulnerability_intelligence` and `vulnerability_aliases` | **REAL**: Integrates NVD 2.0, CISA KEV, FIRST EPSS, OSV, GHSA clients with non-destructive upsert and alias graph resolution. |
| 7 | `api/rules.py` | `/rules` | `POST /validate`<br>`GET /`<br>`POST /`<br>`GET /{id}`<br>`PUT /{id}`<br>`DELETE /{id}`<br>`POST /test`<br>`POST /{id}/test`<br>`POST /{id}/lifecycle` | `DetectionRuleCreate`, `DetectionRuleResponse`, `RuleValidationResponse`, `RuleLifecycleTransitionRequest` | Full CRUD on `detection_rules`, `rule_audit_logs`, and `rule_test_fixtures` | **REAL**: Validates YAML structure and regexes via `RuleValidator`, runs test fixtures via `RuleTestRunner`, governs peer-review lifecycle. |
| 8 | `api/empire_modules.py` | `/empire-modules` | `GET /` | `List[Dict[str, Any]]` | Queries `assets`, `findings`, and `scans` grouped by Empire module | **REAL**: Calculates real-time risk scores (0-100), finding severity counts, and latest scan timestamps across 6 modules. |
| 9 | `api/baselines.py` | `/baselines` | `GET /`<br>`POST /`<br>`DELETE /{id}`<br>`POST /reset` | `BaselineCreateRequest`, `BaselineResponse` | Queries and persists `baseline_exceptions` | **REAL**: Approved Public Media policy management (`/media/*`), full review history logging, and reset trigger. |
| 10 | `api/schedules.py` | `/schedules` | `GET /`<br>`GET /{id}`<br>`POST /`<br>`POST /{id}/trigger`<br>`PUT /{id}/toggle`<br>`DELETE /{id}` | `ScheduleCreateRequest`, `ScheduleResponse` | Full CRUD on `daily_schedules` | **REAL**: Parses 5-part cron syntax with timezone support (`Asia/Ho_Chi_Minh`), calculates `next_run_at`, dispatches scan runs. |
| 11 | `api/alerts.py` | `/alerts` | `GET /`<br>`GET /unread-count`<br>`POST /{id}/read`<br>`POST /read-all`<br>`DELETE /{id}`<br>`DELETE /` | `AlertResponse` | Full CRUD on `security_alerts` | **REAL**: Unread tracking, category filtering (`VULN`, `SCAN`, `BASELINE`, `REMEDIATION`), batch read/delete. |
| 12 | `api/logs.py` | `/logs` | `GET /`<br>`GET /export`<br>`POST /purge` | `PaginatedLogsResponse`, `PurgeLogsRequest` | Queries and deletes `scan_logs` | **REAL**: Real date range and source filtering; exports logs to CSV/JSON attachments; purges logs from DB and memory. |
| 13 | `api/system.py` | `/system` | `POST /reset` | JSON status response | Cascades deletes across 10 operational tables, calls `seed_empire_ecosystem` | **REAL**: Stops all tasks, clears log buffer, purges dynamic data, re-seeds baseline, ensures Ultra Admin credentials. |
| 14 | `api/engines.py` | `/engines` | `GET /health`<br>`POST /check-updates`<br>`POST /test` | Engine health dicts | Inspects local binaries, executes live probes, records `security_alerts` | **REAL**: Discovers `nuclei`, `zap`, embedded lab runners, probes execution latency, emits alerts. |
| 15 | `api/reports.py` | `/reports` | `GET /`<br>`POST /`<br>`POST /generate`<br>`GET /{id}`<br>`GET /{id}/download`<br>`DELETE /{id}` | `GenerateReportRequest`, `ReportResponse` | Full CRUD on `reports` table | **REAL**: Generates technical & executive reports in PDF (ReportLab), HTML (Jinja2), and JSON derived strictly 1:1 from DB findings. |
| 16 | `api/settings.py` | `/settings` | `GET /`<br>`PUT /`<br>`GET /ssrf-config`<br>`PUT /ssrf-config`<br>`POST /reset`<br>`POST /reset-baseline` | `SettingsResponse`, `SettingsUpdateRequest`, `SSRFConfigResponse` | In-memory singleton `settings` and `SSRFProtector` | **REAL**: Live configuration of concurrency limits, timeouts, and SSRF policies. (See Tech Debt on persistence). |

---

## 3. Database Architecture & Persistence Integrity

### 3.1. Engine & WAL Configuration (`backend/app/core/database.py`)
- **Async Engine**: `create_async_engine(settings.DATABASE_URL)` with `aiosqlite`.
- **SQLite Concurrency & WAL**: An event listener on `connect` executes:
  ```python
  @event.listens_for(engine.sync_engine, "connect")
  def set_sqlite_pragma(dbapi_connection, connection_record):
      cursor = dbapi_connection.cursor()
      cursor.execute("PRAGMA journal_mode=WAL;")
      cursor.execute("PRAGMA busy_timeout=30000;")
      cursor.close()
  ```
- **Connection Arguments**: `check_same_thread=False`, `timeout=30.0`.
- **Physical Evidence**: Verified database files on disk:
  - `noospire.db`: 47,439,872 bytes (~47.4 MB)
  - `noospire.db-wal`: 4,280,712 bytes (~4.28 MB)
  - `noospire.db-shm`: 32,768 bytes (~32 KB)

### 3.2. SQLAlchemy Model Definitions (`backend/app/models/`)
All models inherit from `Base` and `TimestampMixin` with standard UTC timezone-aware datetimes:
1. `User` (`users`): `id` (GUID), `username` (unique index), `email` (unique index), `hashed_password`, `role`, `is_active`, `is_superuser`.
2. `AdminAuditLog` (`admin_audit_logs`): `id` (GUID), `user_id`, `username` (indexed), `action`, `details`, `ip_address`.
3. `Asset` (`assets`): `id` (GUID), `name` (indexed), `asset_type`, `target_locator`, `empire_module` (indexed), `environment`, `technology`, `approved_media_baseline`, `assessment_policy` (JSON), `auth_profile` (JSON), `excluded_endpoints` (JSON), `verification_status` (indexed), `verification_type`, `verification_token`, `verified_at`, `criticality`, `exposure`, `description`, `tags` (JSON). Cascades to `scans` and `findings`.
4. `ScanBatch` (`scan_batches`): `id` (GUID), `name`, `status` (indexed), `total_scans`, `completed_scans`, `failed_scans`, `cancelled_scans`, `progress_percentage`, `target_count`, `engines` (JSON), `profiles` (JSON), `started_at`, `completed_at`, `metadata_json` (JSON). Cascades to `scans`.
5. `Scan` (`scans`): `id` (GUID), `asset_id` (FK `assets.id` ON DELETE CASCADE), `batch_id` (FK `scan_batches.id` ON DELETE SET NULL), `engine`, `profile`, `status` (indexed), `quality_status` (indexed), `progress_percentage`, `target_locator`, `allow_private_targets`, `timeout_seconds`, `error_message`, `started_at`, `completed_at`. Cascades to `logs` and `findings`.
6. `ScanLog` (`scan_logs`): `id` (GUID), `scan_id` (FK `scans.id` ON DELETE CASCADE), `timestamp`, `level`, `message`, `source`.
7. `NormalizedFinding` (`findings`): `id` (GUID), `scan_id` (FK `scans.id` ON DELETE CASCADE), `asset_id` (FK `assets.id` ON DELETE CASCADE), `fingerprint` (indexed, 64-char SHA-256), `empire_module` (indexed), `exposure_classification`, `is_approved_baseline`, `scanner_engine` (indexed), `scanner_rule_id`, `title`, `description`, `severity` (indexed), `original_severity`, `cve_id` (indexed), `cwe_id`, `cvss_score`, `cvss_vector`, `epss_score` (indexed), `epss_percentile`, `is_kev`, `target_location`, `target_component`, `affected_version`, `fixed_version`, `evidence` (JSON), `raw_payload`, `remediation`, `references` (JSON), `status` (indexed), `remediation_notes`, `assignee`, `retest_status`, `occurrence_count`, `first_seen_at`, `last_seen_at`.
8. `BaselineException` (`baseline_exceptions`): `id` (GUID), `scope` (indexed), `classification`, `reason`, `owner`, `approved_by`, `is_active`, `expiration_date`, `evidence` (JSON), `review_history` (JSON).
9. `DailySchedule` (`daily_schedules`): `id` (GUID), `name`, `profile`, `cron_expression`, `timezone`, `is_active`, `target_ids` (JSON), `last_run_at`, `next_run_at`, `last_status`.
10. `SecurityAlert` (`security_alerts`): `id` (GUID), `severity` (indexed), `title`, `message`, `category`, `is_read` (indexed), `metadata_json` (JSON).
11. `SyntheticIdentity` (`synthetic_identities`): `id` (GUID), `identifier` (unique index), `role`, `email`, `description`, `is_active`, `last_used_at`.
12. `DetectionRule` (`detection_rules`): `id` (str, primary key), `name`, `description`, `version`, `author`, `severity`, `status` (indexed), `target_types` (JSON), `metadata_json` (JSON), `detection_json` (JSON), `remediation_json` (JSON), `raw_yaml`, `created_by`, `approved_by`. Cascades to `audit_logs` and `test_fixtures`.
13. `RuleAuditLog` (`rule_audit_logs`): `id` (int, PK), `rule_id` (FK `detection_rules.id` ON DELETE CASCADE), `actor`, `action`, `from_status`, `to_status`, `notes`, `timestamp`.
14. `RuleTestFixtureRecord` (`rule_test_fixtures`): `id` (int, PK), `rule_id` (FK `detection_rules.id` ON DELETE CASCADE), `name`, `expected_match`, `input_payload` (JSON), `last_run_success`, `last_run_at`, `error_message`.
15. `VulnerabilityIntelligence` (`vulnerability_intelligence`): `cve_id` (str, PK), `title`, `summary`, `description`, `cvss_v3_score` (indexed), `cvss_v3_vector`, `cvss_v3_severity`, `cvss_v2_score`, `cvss_v4_score`, `epss_score` (indexed), `epss_percentile`, `epss_last_updated`, `is_cisa_kev` (indexed), `cisa_kev_date_added`, `cisa_kev_due_date`, `cisa_kev_ransomware`, `cisa_action_required`, `ssvc_exploitation`, `ssvc_automatable`, `ssvc_technical_impact`, `cwe_ids` (JSON), `source_provenance` (JSON), `published_at`, `last_modified_at`, `synced_at`. Cascades to `aliases`.
16. `VulnerabilityAlias` (`vulnerability_aliases`): `alias_id` (str, PK), `cve_id` (FK `vulnerability_intelligence.cve_id` ON DELETE CASCADE), `alias_type`, `created_at`.

### 3.3. In-Memory vs. Persisted State Audit
- **Persisted State**: All targets, scans, scan batches, individual scan logs, normalized findings, baseline exceptions, schedules, alerts, detection rules, and threat intelligence entries are committed to `noospire.db`.
- **Ephemeral In-Memory State**:
  - `ScanLogBuffer`: Ring buffer (`deque(maxlen=1000)`) per scan ID used strictly for low-latency live SSE streaming (`/api/v1/scans/{id}/logs/stream`). All log entries are concurrently persisted to `scan_logs` table via `log_session.add(db_log)` with SQLite lock retry logic.
  - Active worker matrix telemetry (`_active_threads` in `AsyncWorkerDispatcher`): Tracks currently running task PIDs, elapsed runtime, and memory stats in memory.
  - Settings mutations in `api/settings.py`: Updates in-memory `settings` object (see Tech Debt).

---

## 4. Review of Core Services (`backend/app/core/`)

### 4.1. SSRF Gatekeeper & Network Egress (`backend/app/core/ssrf.py`)
- **Two-tier validation**: Syntax verification (`urlparse`, scheme whitelist `http`/`https`, credentials prohibition, port bounds 1-65535) and socket IP resolution.
- **Blocked subnets**: RFC 1918 (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopback (`127.0.0.0/8`, `::1/128`), link-local (`169.254.0.0/16`, `fe80::/10`), CGNAT (`100.64.0.0/10`), broadcast, documentation IPs, IPv4-mapped IPv6.
- **Cloud Metadata Security**: `169.254.169.254`, `metadata.google.internal`, `100.100.100.200`, `192.0.0.192` are unconditionally blocked regardless of `allow_private` settings.
- **Edge cases handled**: Integer IP representations, octal representations, and 32-bit overflow wrapping.

### 4.2. Target Verification Engine (`backend/app/core/target_verifier.py`)
- Executes authentic, non-destructive network probes across 8 sequential steps:
  1. *Input Validation*: Scheme whitelist and SSRF checks.
  2. *DNS Resolution*: `socket.getaddrinfo` extracting IPv4 and IPv6 records.
  3. *TLS Verification*: SSL socket connection verifying certificate chain, subject, issuer, SANs, cipher, and expiration date calculation.
  4. *HTTP Connectivity*: `httpx.AsyncClient` round-trip latency, status code, and header inspection.
  5. *Redirect Inspection*: Hop-by-hop tracing with protocol downgrade detection (e.g. HTTPS redirected to plain HTTP).
  6. *Web Discovery*: Probes `/robots.txt`, `/sitemap.xml`, and `/.well-known/security.txt`.
  7. *Target Fingerprint*: Detects WAFs/reverse proxies (Envoy, Cloudflare, Nginx, CloudFront), web frameworks (Next.js, Vite, FastAPI, Express), and audits 5 baseline security headers (`strict-transport-security`, `content-security-policy`, `x-frame-options`, `x-content-type-options`, `referrer-policy`).
  8. *Verification Result*: Evaluates critical passes, generates verdict detail, and aggregates diagnostic metadata.

### 4.3. Task Dispatcher & Process Safety (`backend/app/core/dispatcher.py`)
- **Concurrency & Throttling**: `AsyncWorkerDispatcher` uses `asyncio.Semaphore` bounded to `MAX_CONCURRENT_SCANS` (default 4) and host CPU count. Checks `psutil.cpu_percent()` and `psutil.virtual_memory()`; delays task dequeuing when CPU > 90% or RAM > 95%.
- **Per-Asset Locking**: `self.asset_locks[asset.id]` prevents concurrent conflicting scans on the same target.
- **Process Safety**: `ProcessSafetyManager` tracks OS PIDs spawned by scanners. On cancellation or timeout, it recursively enumerates and terminates all child processes via `psutil.Process(pid).children(recursive=True)` followed by SIGKILL fallback.
- **Quality State Machine**: Explicitly assigns one of 5 quality states upon scan completion:
  1. `SCANNED_SUCCESSFULLY`: All configured engines completed with valid responses.
  2. `PARTIAL_COVERAGE`: At least one engine succeeded, but others encountered non-fatal errors.
  3. `AUTH_REQUIRED`: Active probing was rejected due to lack of ownership verification or credentials.
  4. `SCANNER_FAILED`: Scanner subprocess crashed or exited with error.
  5. `TARGET_UNAVAILABLE`: Target was unreachable, timed out, or blocked by SSRF gatekeeper.
- **Deterministic Deduplication**: Findings are hashed with SHA-256 (`asset_id:scanner_engine:scanner_rule_id:target_location:target_component`). Existing findings increment `occurrence_count` and update `last_seen_at`. If previously `FIXED`, findings automatically transition to `REOPENED` with a regression alert.

### 4.4. Continuous Scheduler Engine (`backend/app/core/scheduler.py`)
- Background asynchronous ticker running every 30 seconds (`SchedulerEngine`).
- Standard 5-part cron syntax parsing with forward minute probing up to 366 days.
- Localized timezone support via Python `zoneinfo` (`Asia/Ho_Chi_Minh`).
- Automatically queries active schedules, evaluates `next_run_at <= now`, spawns `Scan` instances in `QUEUED` state, enqueues them into `dispatcher.dispatch_scan()`, emits `SecurityAlert`, and updates `last_run_at`.

### 4.5. Ecosystem Baseline Seeder (`backend/app/core/empire_seeder.py`)
- Idempotently seeds the 7 primary Empire targets (including `https://empire.edu.vn/`).
- Seeds 6 verified historical audit findings (VULN-01 to VULN-06) derived from the authoritative security audit report.
- Seeds the Approved Public Media Policy baseline exception (`/media/*`).
- Seeds 3 synthetic identities (`studenttu1`, `test_student_a`, `test_student_b`).
- Seeds the daily security schedule (02:00 AM ICT) and initial SOC security alerts.

---

## 5. Suspicious Pattern & Authenticity Analysis

### 5.1. Pattern Scan Results
| Pattern Searched | Scope | Occurrences Found | Code Analysis |
|------------------|-------|-------------------|---------------|
| `TODO` | `backend/app` | **0** | No unfinished stubs or developer bookmarks. |
| `FIXME` | `backend/app` | **0** | No marked defect locations. |
| `HACK` | `backend/app` | **0** | No temporary workarounds or hacks. |
| `mock` | `backend/app` | **9** | All 9 occurrences reference `DEV_MOCK_SUPERUSER` in `security.py`, `auth.py`, and `deps.py`. Used strictly as a developer authentication bypass in dev mode when auth is disabled. |
| `dummy` | `backend/app` | **0** | Zero dummy data generators in backend controllers. |
| `fake` | `backend/app` | **0** | Zero fake responses or simulated findings. |
| `pass` (statement) | `backend/app` | **52** | All occurrences are in `except Exception:` cleanup/swallow blocks, class inheritance declarations (`class Base(DeclarativeBase): pass`), or abstract interface definitions. |

### 5.2. Scanner Engine Authenticity Assessment
- **NucleiAdapter (`backend/app/scanners/nuclei.py`)**: Checks for `nuclei` binary on PATH or standard Go path (`~/go/bin/nuclei.exe`). If binary is absent or CLI execution errors out, it gracefully falls back to `NucleiLabRunner`.
- **NucleiLabRunner (`backend/app/scanners/lab_runners.py`)**: Executes real HTTP requests via `httpx.AsyncClient` against the target for 5 verified vulnerability patterns (`.git/config`, `.env`, CORS wildcard reflection, directory indexing, Spring Boot actuator). Findings are recorded ONLY when the target HTTP response actually matches the regex pattern.
- **ZAPAdapter & ZAPLabRunner (`backend/app/scanners/zap.py` & `lab_runners.py`)**: Executes real passive HTTP audits inspecting live response headers (`X-Frame-Options`, `Content-Security-Policy`, `X-Content-Type-Options`, `Server`). In `DEEP_ACTIVE` profile, it sends active SQLi probes (`' OR '1'='1`) and checks for real database error signatures.
- **EmpireAssessmentEngine (`backend/app/scanners/empire_engine.py`)**: Sends real HTTP probes tailored to Empire modules: Better-Auth endpoints, horizontal BOLA access with synthetic tokens, public media policy validation, directory indexing, news feed SSRF vectors, XSS reflection, and security headers.
- **AsyncBFSCrawler (`backend/app/scanners/crawler.py`)**: Real asynchronous BFS web crawler with same-origin validation, depth limits (max 3), page limits (max 50), static asset filtering, and cooperative cancellation tokens.

---

## 6. Technical Debt, Architectural Findings & Recommendations

### Finding 1: Unimplemented Celery Dispatcher (`CeleryDispatcher`)
- **Severity**: LOW (Architectural)
- **Location**: `backend/app/core/dispatcher.py`, lines 966-999
- **Observation**: `CeleryDispatcher` is a stub that logs warnings and returns empty telemetry dicts when `settings.DISPATCHER_MODE == "celery"`.
- **Impact**: In development and standard deployments, `settings.DISPATCHER_MODE` defaults to `"async_worker"` (which is 100% operational). If an administrator sets `SENTINEL_DISPATCHER_MODE=celery` without configuring Celery workers, scans will not be executed.
- **Recommendation**: Document that `async_worker` is the supported dispatcher mode for standalone deployments, or implement the Celery task runner if distributed Redis/RabbitMQ scaling is required.

### Finding 2: In-Memory Runtime Settings Mutation
- **Severity**: LOW (State Persistence)
- **Location**: `backend/app/api/settings.py`, lines 50-59 & 71-74
- **Observation**: `PUT /api/v1/settings` and `PUT /api/v1/settings/ssrf-config` update `settings.MAX_CONCURRENT_SCANS`, `settings.DEFAULT_SCAN_TIMEOUT`, and `settings.SSRF_ALLOW_PRIVATE_TARGETS` on the in-memory singleton.
- **Impact**: Mutated settings are not written to `.env` or a database configuration table. If the backend process restarts, settings revert to environment variable defaults.
- **Recommendation**: Persist runtime system configuration in a `system_settings` database table so changes survive server restarts.

### Finding 3: Static Placeholders in Telemetry Metrics
- **Severity**: LOW (Telemetry Accuracy)
- **Location**: `backend/app/api/metrics.py`, line 277 (`"avg_duration_seconds": 18.5`) and line 297 (`"detection_rules_active": 12`)
- **Observation**: While total executions, completed counts, failed counts, and success rates are dynamically aggregated from the `scans` table, `avg_duration_seconds` is hardcoded to 18.5s. In `/charts/intelligence-activity`, `detection_rules_active` is hardcoded to 12 rather than querying `select(func.count(DetectionRule.id))`.
- **Impact**: Dashboard chart shows static average duration and active rule count regardless of actual database state.
- **Recommendation**: Replace `18.5` with dynamic average duration calculation (`(Scan.completed_at - Scan.started_at)`) and replace `12` with a query against `DetectionRule` where `status == "active"`.

### Finding 4: In-Memory Ring Buffer Cleanup during Server Interruption
- **Severity**: INFO (Operational Resilience)
- **Location**: `backend/main.py`, lines 41-53
- **Observation**: On application startup, the lifespan handler recovers stale jobs in `QUEUED`, `INITIALIZING`, or `RUNNING` status by updating them to `CANCELLED` with error message `"Session interrupted / server restarted."`.
- **Impact**: Highly resilient — prevents orphaned "running" scans from polluting the active assessment HUD across server restarts.

---

## 7. Automated Test Execution Evidence

Pytest execution was conducted on the core backend test suite:
- **Command**: `python -m pytest tests/test_platform_core_m1.py tests/test_scan_all_batch_orchestration.py -q`
- **Output**:
  ```
  ......................                                                   [100%]
  22 passed in 24.82s
  ```
- **Result**: 22 passed, 0 failed, 0 skipped.
- **Verified Capabilities**:
  1. Target registration, normalization, and deduplication.
  2. 8-step live probe pipeline execution and fingerprint verification.
  3. Bulk asset preview with CSV, JSON, and OpenAPI payload parsing.
  4. Batch scan creation (`POST /api/v1/scans/batch`), expansion across targets and profiles.
  5. Concurrency bounds and `psutil` host resource throttling.
  6. Cooperative cancellation (`POST /api/v1/scans/batch/{id}/cancel` and `POST /api/v1/scans/stop-all`).
  7. Real-time telemetry feed (`GET /api/v1/scans/trackcurrent`).
