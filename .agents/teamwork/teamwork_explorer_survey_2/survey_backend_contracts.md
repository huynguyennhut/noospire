# NOOSFORGE Security Intelligence — Backend APIs & Test Contracts Survey

**Document Target**: `survey_backend_contracts.md`  
**Investigation Date**: 2026-11-08  
**Scope**: Backend Architecture, API Routers & Contracts, Database Models, Pydantic Schemas, Test Suites, and Zero-Regression Constraints.

---

## 1. Executive Summary & Architecture Overview

The NOOSFORGE Security Intelligence platform is a production-grade, UI-first cybersecurity assessment and continuous monitoring system tailored for educational ecosystems (specifically primary target `https://empire.edu.vn/`).

### Core Architecture Components
1. **Application Layer (`FastAPI`)**:
   - ASGI application defined in `backend/main.py` and exported through `backend/app/main.py` (`app = create_app()`).
   - API Version: `2.0.0`, Base prefix: `/api/v1` (configured via `Settings.API_V1_STR`).
   - Async Lifespan Manager: Automatically executes database table creation (`init_db()`), runs idempotent seeding (`seed_empire_ecosystem()`), cleans up stale/orphaned scan tasks on server boot, and starts/stops background workers (`AsyncWorkerDispatcher`).
   - CORS Middleware: Configured with `allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8000", "http://127.0.0.1:8000"]`, supporting credentials and all HTTP methods/headers.

2. **Persistence & Database ORM (`SQLAlchemy 2.0 Async`)**:
   - Primary database: SQLite via `aiosqlite` (`sqlite+aiosqlite:///./noospire.db`) with zero external dependencies, compatible with PostgreSQL (`asyncpg`).
   - UUID Handling: Custom `GUID` type decorator storing `CHAR(36)` to ensure cross-database compatibility between SQLite and Postgres.
   - Schema Migration/Bootstrap: `backend/app/core/database.py` with `init_db()` creating all declarative models.

3. **Background Dispatcher & Scanner Engine**:
   - Modes: In-process `AsyncWorkerDispatcher` (default) or `celery`.
   - Max concurrent scans: 4 (`SENTINEL_MAX_CONCURRENT_SCANS`).
   - Real scanner integrations: Nuclei CLI v3.11.1, OWASP ZAP adapter, Trivy, and Empire custom business engine (`EmpireAssessmentEngine`).
   - Real-time SSE streaming: `ScanLogBuffer` using async queues to stream scanner stdout/stderr live to connected browsers.

---

## 2. API Router Catalog & Contract Specifications

All API routes are served under prefix `/api/v1` (with `/health` and `/` at root).

### Summary Table of Routers & Endpoints

| Router / Tag | Prefix | Endpoints Count | Key Capabilities |
| :--- | :--- | :---: | :--- |
| **Assets** | `/api/v1/assets` | 7 | List, create, bulk import, bulk preview, retrieve, summary, update, delete, 8-step live probe verify |
| **Scans** | `/api/v1/scans` | 6 | List scans, dispatch scan, retrieve status, delete, cooperative cancel, paginated logs, SSE log stream |
| **Findings** | `/api/v1/findings` | 4 | List findings with multi-criteria filtering, retrieve finding details, 10-state triage, live retest probe |
| **Metrics** | `/api/v1/metrics` | 9 | Overview KPIs, severity breakdown, 8 database-backed chart datasets (trend, module risk, coverage, risk trend, scanner perf, intel, remediation) |
| **Empire Modules** | `/api/v1/empire-modules` | 1 | Real-time security posture and risk aggregation across 6 Empire operational modules |
| **Threat Intel** | `/api/v1/threat-intel` | 6 | Executive intel summary, manual/scheduled feed sync, CVE details with alias graph, CVE search, CISA KEV catalog, batch EPSS query |
| **Reports** | `/api/v1/reports` | 5 | List reports, generate audit-grade reports (technical/executive), get report, download artifacts (PDF/HTML/JSON), delete report |
| **Detection Rules** | `/api/v1/rules` | 8 | Syntax validation, list rules, create rule, get/update/delete rule, test against synthetic fixtures, lifecycle state transitions |
| **Baselines** | `/api/v1/baselines` | 3 | List approved exceptions, create baseline policy (e.g., `/media PUBLIC_BY_DESIGN`), revoke baseline |
| **Schedules** | `/api/v1/schedules` | 4 | List daily schedules, create schedule, manually trigger pipeline, toggle active state |
| **Alerts** | `/api/v1/alerts` | 3 | List in-app notifications, mark alert read, mark all read |
| **Auth** | `/api/v1/auth` | 3 | Form/JSON login (JWT Bearer token), `/me` identity inspection, token refresh |
| **Settings** | `/api/v1/settings` | 4 | System configuration, runtime settings update, SSRF blocker status, SSRF config update |
| **System** | `/`, `/health` | 2 | Root welcome message, health check probe |

---

### Detailed Endpoint Contracts

#### 2.1. Target & Asset Management (`/api/v1/assets`)
1. `GET /api/v1/assets`
   - **Query Parameters**:
     - `page`: int (default `1`, min `1`)
     - `size`: int (default `50`, min `1`, max `200`)
     - `asset_type`: `AssetType` enum (`DOMAIN`, `WEB_APP`, `API_ENDPOINT`, `PROJECT_ARCHIVE`, `CONTAINER_IMAGE`, `OBJECT_STORAGE`, `SERVER`)
     - `empire_module`: `EmpireModule` enum (`STUDENT_MANAGEMENT`, `LEARNING_MATERIALS`, `SUPPORTING_TOOLS`, `API_SERVICES`, `WEB_APPLICATION`, `SERVER_INFRASTRUCTURE`)
     - `environment`: str (`PRODUCTION`, `STAGING`, `DEV`)
     - `verification_status`: `VerificationStatus` enum (`PENDING`, `VERIFIED`, `FAILED`, `REVOKED`)
     - `search`: str (case-insensitive search against name, target_locator, description, technology)
   - **Response**: `PaginatedResponse[AssetResponse]` (`items`, `total`, `page`, `size`, `pages`)

2. `POST /api/v1/assets`
   - **Status Code**: `201 Created`
   - **Request Body**: `AssetCreate`
     - `name`: str (1-255 chars)
     - `asset_type`: `AssetType` (default `WEB_APP`)
     - `target_locator`: str (1-1024 chars, unique)
     - `empire_module`: `EmpireModule` (default `STUDENT_MANAGEMENT`)
     - `environment`: str (default `"PRODUCTION"`)
     - `technology`: str (default `"Web Service"`)
     - `criticality`: `Criticality` (default `MEDIUM`)
     - `exposure`: `Exposure` (default `INTERNET`)
     - `description`: Optional[str]
     - `tags`: List[str]
     - `approved_media_baseline`: bool (default `false`)
     - `assessment_policy`: Dict[str, Any]
     - `auth_profile`: Dict[str, Any]
     - `excluded_endpoints`: List[str]
   - **Response**: `AssetResponse`
   - **Error**: `400 Bad Request` if target locator already exists.

3. `POST /api/v1/assets/bulk-preview`
   - **Request Body**: `AssetBulkPreviewRequest`
     - `import_type`: str (e.g., `"AUTO"`, `"CSV"`, `"JSON"`, `"TXT"`, `"OPENAPI"`)
     - `raw_content`: Optional[str] (Raw text lines, CSV with header, JSON array, OpenAPI/Swagger JSON or YAML, CIDR notation)
     - `items`: Optional[List[AssetBulkImportItem]]
   - **Response**: `AssetBulkPreviewResponse`
     - `total`: int
     - `new`: List[BulkPreviewItem] (`target_locator`, `name`, `asset_type`, `empire_module`, `environment`, `criticality`, `is_duplicate=false`)
     - `duplicate`: List[BulkPreviewItem] (`target_locator`, `name`, `is_duplicate=true`, `existing_asset_id`, `reason`)

4. `POST /api/v1/assets/bulk-import`
   - **Request Body**: `AssetBulkImportRequest`
   - **Behavior**: Persists candidates with automatic URL normalization, module classification, and duplicate detection.
   - **Response**: `AssetBulkImportResponse` (`imported_count`, `skipped_duplicates`, `errors`, `imported_assets`)

5. `GET /api/v1/assets/{asset_id}`
   - **Response**: `AssetResponse`
   - **Error**: `404 Not Found` if asset ID does not exist.

6. `GET /api/v1/assets/{asset_id}/summary`
   - **Response**: Object containing findings rollup:
     - `asset_id`: str
     - `name`, `target_locator`, `empire_module`, `environment`
     - `critical_findings`, `high_findings`, `open_findings`, `fixed_findings`, `total_findings`
     - `last_assessment_at`: Optional[str]
     - `last_scan_status`: Optional[str]

7. `PUT /api/v1/assets/{asset_id}`
   - **Request Body**: `AssetUpdate` (all fields optional: `name`, `empire_module`, `environment`, `technology`, `criticality`, `exposure`, `description`, `tags`, `approved_media_baseline`, `assessment_policy`, `auth_profile`, `excluded_endpoints`)
   - **Response**: `AssetResponse`

8. `DELETE /api/v1/assets/{asset_id}`
   - **Status Code**: `204 No Content`
   - **Behavior**: Cascades deletion to scans, scan logs, and findings.

9. `POST /api/v1/assets/{asset_id}/verify`
   - **Request Body**: `AssetVerifyRequest`
     - `verification_type`: `VerificationType` (default `ADMIN_OVERRIDE`, options `DNS_TXT`, `HTTP_WELL_KNOWN`, `ADMIN_OVERRIDE`)
     - `allow_private`: bool (default `true`)
   - **Behavior**: Runs 8-step live probe pipeline (`TargetVerifier`) against `asset.target_locator`. Updates asset verification status and technology profile.
   - **Response**: `AssetVerifyResponse`
     - `asset_id`: UUID
     - `verification_status`: `VerificationStatus` (`VERIFIED` or `FAILED`)
     - `verified`: bool
     - `status`: str (`"VERIFIED"` or `"FAILED"`)
     - `message`: str
     - `steps`: List[VerificationStepResult] (`step`: 1-8, `name`, `status`, `detail`, `metadata`)
     - `fingerprint`: Dict[str, Any] (`server`, `reverse_proxy_waf`, `framework`, `technologies`, `security_headers`)

---

#### 2.2. Scan Center & Live Streaming (`/api/v1/scans`)
1. `GET /api/v1/scans`
   - **Query Parameters**:
     - `page`: int (default `1`)
     - `size`: int (default `20`, max `100`)
     - `asset_id`: Optional[UUID]
     - `status_filter`: Optional[ScanStatus] (`PENDING`, `QUEUED`, `INITIALIZING`, `RUNNING`, `COMPLETING`, `COMPLETED`, `FAILED`, `CANCELLED`, `TIMED_OUT`)
   - **Response**: `PaginatedResponse[ScanResponse]`

2. `POST /api/v1/scans`
   - **Status Code**: `201 Created`
   - **Request Body**: `ScanCreate`
     - `asset_id`: UUID
     - `engine`: str (default `"all"`, options: `"nuclei"`, `"zap"`, `"trivy"`, `"all"`)
     - `profile`: `ScanProfile` (default `BASELINE`, options: `QUICK`, `DAILY_SECURITY`, `STANDARD`, `AUTHENTICATED`, `API_ASSESSMENT`, `THOROUGH`, `INFRASTRUCTURE`, `LIGHT_PASSIVE`, `BASELINE`, `DEEP_ACTIVE`, `SCA_CONTAINER`)
     - `allow_private_targets`: bool (default `false`)
     - `timeout_seconds`: int (30-3600, default `600`)
   - **Gates & Safeguards**:
     - SSRF pre-flight validation: verifies host isn't an unauthorized private or cloud-metadata endpoint.
     - Active Scan Gate: `DEEP_ACTIVE` requires `asset.verification_status == "VERIFIED"` (returns `403 Forbidden` if unverified).
   - **Response**: `ScanResponse`

3. `GET /api/v1/scans/{scan_id}`
   - **Response**: `ScanResponse` (`id`, `asset_id`, `engine`, `profile`, `status`, `quality_status`, `progress_percentage`, `target_locator`, `allow_private_targets`, `timeout_seconds`, `error_message`, `started_at`, `completed_at`, `created_at`, `updated_at`)

4. `DELETE /api/v1/scans/{scan_id}`
   - **Status Code**: `204 No Content`

5. `POST /api/v1/scans/{scan_id}/cancel`
   - **Response**: `ScanCancelResponse` (`scan_id`, `status`, `message`)
   - **Behavior**: Triggers cooperative cancellation in `CancellationToken` and stops subprocesses.

6. `GET /api/v1/scans/{scan_id}/logs`
   - **Query Parameters**: `page` (default 1), `size` (default 50, max 200)
   - **Response**: `PaginatedResponse[ScanLogEntry]` (`id`, `scan_id`, `timestamp`, `level`, `message`, `source`)

7. `GET /api/v1/scans/{scan_id}/logs/stream`
   - **Protocol**: Server-Sent Events (`media_type="text/event-stream"`)
   - **Headers**: `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`
   - **Chunk Format**:
     ```
     data: {"id": "<uuid>", "scan_id": "<uuid>", "timestamp": "<iso8601>", "level": "INFO", "message": "...", "source": "system"}\n\n
     ```
   - **Behavior**: Replays existing in-memory buffer on connection, then yields live logs until scan finishes or connection closes.

---

#### 2.3. Findings Explorer & Remediation (`/api/v1/findings`)
1. `GET /api/v1/findings`
   - **Query Parameters**:
     - `page`: int (default `1`)
     - `size`: int (default `50`, max `200`)
     - `asset_id`: Optional[UUID]
     - `scan_id`: Optional[UUID]
     - `empire_module`: Optional[EmpireModule]
     - `exposure_classification`: Optional[ExposureClassification]
     - `severity`: Optional[FindingSeverity] (`INFO`, `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`)
     - `status_filter`: Optional[FindingStatus] (10 lifecycle states)
     - `scanner_engine`: Optional[str]
     - `cve_id`: Optional[str]
     - `search`: Optional[str] (searches `title`, `description`, `target_location`, `cve_id`, `scanner_rule_id`)
   - **Response**: `PaginatedResponse[FindingResponse]`

2. `GET /api/v1/findings/{finding_id}`
   - **Response**: `FindingResponse`
   - **Key Fields**:
     - `fingerprint`: SHA-256 deduplication key
     - `evidence`: JSON object containing raw HTTP proof:
       - `request`: Raw request text
       - `response`: Raw response text
       - `matched_content`: Vulnerable excerpt
       - `curl_command`: Reproducible cURL command
       - `triage_history`: Array of triage state transitions
       - `last_retest`: Timestamp, status, and verification notes
     - `occurrence_count`: int
     - `first_seen_at`, `last_seen_at`: ISO datetime

3. `POST /api/v1/findings/{finding_id}/triage`
   - **Request Body**: `FindingTriageRequest`
     - `status`: `FindingStatus` (mandatory; supports all 10 states: `NEW`, `POTENTIAL`, `CONFIRMED`, `OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`, `FALSE_POSITIVE`, `NOT_AFFECTED`)
     - `comment`: Optional[str]
     - `assignee`: Optional[str]
     - `retest_status`: Optional[str]
   - **Behavior**: Updates finding state, appends audit record into `evidence.triage_history`, automatically creates a `SecurityAlert` when marked `FIXED` or `REOPENED`.
   - **Response**: `FindingResponse`

4. `POST /api/v1/findings/{finding_id}/retest`
   - **Behavior**: Performs an immediate non-destructive network probe against `finding.target_location`. If target responds with 401/403/404 on an unauthenticated information leak, automatically updates status to `FIXED` with verdict `VERIFIED_FIXED`. Otherwise returns `STILL_VULNERABLE` or `RETEST_ERROR`.
   - **Response**:
     ```json
     {
       "finding_id": "...",
       "status": "FIXED",
       "retest_status": "VERIFIED_FIXED",
       "notes": "Target now returns HTTP 403 (access denied/not found). Vulnerability confirmed remediated."
     }
     ```

---

#### 2.4. Dashboard Metrics & Chart Telemetry (`/api/v1/metrics`)
1. `GET /api/v1/metrics/overview`
   - **Response**: `MetricsOverviewResponse`
     - `total_assets`: Total registered targets
     - `targets_assessed_today`: Distinct targets scanned since midnight UTC
     - `active_assessments`: Scans currently in QUEUED, INITIALIZING, or RUNNING
     - `failed_assessments`: Scans marked FAILED
     - `critical_findings`: Active (non-fixed) critical vulnerabilities
     - `high_findings`: Active (non-fixed) high vulnerabilities
     - `total_open_findings`: Findings in NEW, OPEN, CONFIRMED, REOPENED, IN_REMEDIATION
     - `fixed_findings`: Findings marked FIXED
     - `newly_discovered_cves`: Total CVE records indexed in intelligence store
     - `relevant_kev_count`: CISA Known Exploited Vulnerabilities
     - `overall_risk_score`: 0.0 - 100.0 composite risk score
     - `risk_posture`: `"OPTIMAL"`, `"MODERATE"`, `"ELEVATED"`, or `"CRITICAL"`

2. `GET /api/v1/metrics/severity-distribution`
   - **Response**: `{ "CRITICAL": int, "HIGH": int, "MEDIUM": int, "LOW": int, "INFO": int }`

3. `GET /api/v1/metrics/charts/vulnerability-trend?days=14`
   - **Response**: Array of `{ "date": "Nov 08", "new_findings": int, "fixed_findings": int, "reopened_findings": int }`

4. `GET /api/v1/metrics/charts/module-risk`
   - **Response**: Array of:
     - `module_key`: str
     - `module_name`: str
     - `risk_score`: float (0-100)
     - `critical_count`: int
     - `high_count`: int
     - `medium_count`: int
     - `total_findings`: int

5. `GET /api/v1/metrics/charts/coverage`
   - **Response**: `{ "total_targets": int, "assessed_today": int, "pending_assessment": int, "coverage_percentage": float }`

6. `GET /api/v1/metrics/charts/risk-trend?days=14`
   - **Response**: Array of `{ "date": "Nov 08", "risk_score": float, "active_findings": int }`

7. `GET /api/v1/metrics/charts/scanner-performance`
   - **Response**: Array of `{ "engine": "Nuclei", "total_executions": int, "completed": int, "failed": int, "success_rate": float, "avg_duration_seconds": float }`

8. `GET /api/v1/metrics/charts/intelligence-activity`
   - **Response**: `{ "total_cves_indexed": int, "cisa_kev_active": int, "high_epss_exploitable": int, "detection_rules_active": int, "last_sync": str }`

9. `GET /api/v1/metrics/charts/remediation-progress`
   - **Response**: `{ "OPEN": int, "IN_REMEDIATION": int, "FIXED": int, "REOPENED": int, "ACCEPTED_RISK": int, "FALSE_POSITIVE": int }`

---

#### 2.5. Empire Business Modules (`/api/v1/empire-modules`)
1. `GET /api/v1/empire-modules`
   - **Response**: Array of 6 operational modules:
     - `STUDENT_MANAGEMENT`: Student Registration & Better-Auth Identity
     - `LEARNING_MATERIALS`: Educational Materials, MinIO Object Storage, `/media` Policy
     - `SUPPORTING_TOOLS`: Vocabulary tools, English learning utilities, news feeds
     - `API_SERVICES`: Gateway (`gw.empire.edu.vn`), course/chapter REST & GraphQL APIs
     - `WEB_APPLICATION`: Student portal, teacher portals, Vite admin SPA
     - `SERVER_INFRASTRUCTURE`: Reverse proxies, Nginx, TLS/SSL certificates
   - **Module Object Attributes**:
     - `module_key`, `title`, `description`, `icon`
     - `asset_count`, `risk_score` (0-100), `risk_tier` (`LOW`/`MEDIUM`/`HIGH`/`CRITICAL`)
     - `total_findings`, `critical_count`, `high_count`, `medium_count`, `low_count`
     - `open_remediation_count`, `fixed_count`
     - `latest_assessment`, `next_scheduled_assessment`

---

#### 2.6. Threat Intelligence (`/api/v1/threat-intel`)
1. `GET /api/v1/threat-intel/summary` -> Aggregated statistics across NVD, KEV, EPSS, OSV feeds.
2. `POST /api/v1/threat-intel/sync` -> Dispatches feed synchronization (`sources`, `force_offline_fixtures`).
3. `GET /api/v1/threat-intel/cve/{cve_id}` -> Resolves CVE details (resolves GHSA aliases through alias graph).
4. `GET /api/v1/threat-intel/cves` -> Filterable catalog (`search`, `is_kev`, `min_epss`, `min_cvss`, `limit`, `offset`).
5. `GET /api/v1/threat-intel/kev` -> Filterable CISA KEV catalog (`ransomware_only`, `limit`, `offset`).
6. `POST /api/v1/threat-intel/epss/batch` -> Batch EPSS probability lookups for multiple CVE IDs.

---

#### 2.7. Reporting Engine (`/api/v1/reports`)
1. `GET /api/v1/reports` -> Lists generated reports (`report_type`, `asset_id`).
2. `POST /api/v1/reports` or `POST /api/v1/reports/generate`
   - **Request**: `{ "title": "...", "report_type": "technical" | "executive", "asset_id": "<uuid>", "scan_id": "<uuid>", "formats": ["pdf", "html", "json"] }`
   - **Response**: `ReportResponse` with generated file paths.
3. `GET /api/v1/reports/{report_id}` -> Returns report metadata and findings summary.
4. `GET /api/v1/reports/{report_id}/download?format=pdf|html|json` -> Streamed file download with appropriate MIME type.
5. `DELETE /api/v1/reports/{report_id}` -> Deletes report record and physical files from `storage/reports/`.

---

#### 2.8. Detection Rules (`/api/v1/rules`)
1. `POST /api/v1/rules/validate` -> Validates YAML syntax, schema structure, and regex compilability.
2. `GET /api/v1/rules` -> Paginated rule listings (`status`, `severity`, `search`).
3. `POST /api/v1/rules` -> Registers new detection rule.
4. `GET /api/v1/rules/{id}`, `PUT /api/v1/rules/{id}`, `DELETE /api/v1/rules/{id}`.
5. `POST /api/v1/rules/test` & `POST /api/v1/rules/{id}/test` -> Executes rule matchers against synthetic HTTP request/response fixtures.
6. `POST /api/v1/rules/{id}/lifecycle` -> Manages state transitions (`DRAFT` -> `IN_REVIEW` -> `APPROVED` -> `ACTIVE` -> `DEPRECATED` -> `DISABLED`) with audit logging.

---

#### 2.9. Approved Baselines (`/api/v1/baselines`)
1. `GET /api/v1/baselines` -> Lists baseline exceptions (e.g. `/media/*` classified as `PUBLIC_BY_DESIGN`).
2. `POST /api/v1/baselines` -> Creates exception policy with business justification.
3. `DELETE /api/v1/baselines/{id}` -> Deactivates/revokes exception.

---

#### 2.10. Continuous Schedules (`/api/v1/schedules`)
1. `GET /api/v1/schedules` -> Lists automated assessment schedules.
2. `POST /api/v1/schedules` -> Configures daily schedule (cron expression, timezone `Asia/Ho_Chi_Minh`, target list `ALL` or IDs).
3. `POST /api/v1/schedules/{id}/trigger` -> Manually triggers immediate pipeline execution across all scheduled targets.
4. `PUT /api/v1/schedules/{id}/toggle` -> Toggles `is_active` state.

---

#### 2.11. Security Alerts (`/api/v1/alerts`)
1. `GET /api/v1/alerts` -> In-app security notifications (`is_read`, `limit`).
2. `POST /api/v1/alerts/{id}/read` -> Marks single alert as read.
3. `POST /api/v1/alerts/read-all` -> Marks all unread alerts as read.

---

#### 2.12. Authentication (`/api/v1/auth`)
1. `POST /api/v1/auth/login` -> Supports JSON (`{"username": "...", "password": "..."}`) or form-data. Returns JWT access token and user info. In dev mode (`AUTH_ENABLED=false`), auto-authenticates default admin.
2. `GET /api/v1/auth/me` -> Inspects current user identity.
3. `POST /api/v1/auth/refresh` -> Issues refreshed JWT access token.

---

#### 2.13. System Settings & SSRF (`/api/v1/settings`)
1. `GET /api/v1/settings` -> Retrieves server configuration parameters.
2. `PUT /api/v1/settings` -> Updates runtime concurrency, scan timeout, SSRF private target allowance.
3. `GET /api/v1/settings/ssrf-config` -> Returns SSRF blocked CIDR counts and cloud metadata endpoints.
4. `PUT /api/v1/settings/ssrf-config` -> Toggles global private target permission.

---

## 3. Data Models & Schemas

### 3.1. Models (`backend/app/models/`)

#### 1. `Asset` (`assets` table)
- `id`: GUID (PK)
- `name`: String(255)
- `asset_type`: String(32) (default `"WEB_APP"`)
- `target_locator`: String(1024) (Unique locator, URL/domain/CIDR)
- `empire_module`: String(64) (default `"STUDENT_MANAGEMENT"`, index)
- `environment`: String(32) (`"PRODUCTION"`, `"STAGING"`, `"DEV"`)
- `technology`: String(255)
- `approved_media_baseline`: Boolean (default `False`)
- `assessment_policy`: JSON (e.g., `{"same_origin_only": true, "scope": "*.empire.edu.vn"}`)
- `auth_profile`: JSON
- `excluded_endpoints`: JSON (list of path prefixes to skip)
- `verification_status`: String(32) (`"VERIFIED"`, `"PENDING"`, `"FAILED"`, index)
- `verification_type`: String(32) (`"ADMIN_OVERRIDE"`, `"DNS_TXT"`, `"HTTP_WELL_KNOWN"`)
- `verification_token`: String(128)
- `verified_at`: String(64)
- `criticality`: String(32) (`"LOW"`, `"MEDIUM"`, `"HIGH"`, `"CRITICAL"`)
- `exposure`: String(32) (`"INTERNET"`, `"INTERNAL"`, `"ISOLATED"`)
- `description`: Text
- `tags`: JSON (list of strings)
- `created_at`, `updated_at`: DateTime(timezone=True)
- **Relationships**: `scans` (Scan[]), `findings` (NormalizedFinding[])

#### 2. `Scan` (`scans` table)
- `id`: GUID (PK)
- `asset_id`: GUID (FK -> `assets.id`, ondelete CASCADE, index)
- `engine`: String(64) (default `"all"`)
- `profile`: String(64) (default `"BASELINE"`)
- `status`: String(32) (default `"PENDING"`, index)
- `quality_status`: String(32) (Optional, index: `"SCANNED_SUCCESSFULLY"`, `"PARTIAL_COVERAGE"`, `"AUTH_REQUIRED"`, `"SCANNER_FAILED"`, `"TARGET_UNAVAILABLE"`)
- `progress_percentage`: Integer (0-100)
- `target_locator`: String(1024)
- `allow_private_targets`: Boolean
- `timeout_seconds`: Integer (default 600)
- `error_message`: Text
- `started_at`, `completed_at`: DateTime(timezone=True)
- `created_at`, `updated_at`: DateTime(timezone=True)
- **Relationships**: `asset` (Asset), `logs` (ScanLog[]), `findings` (NormalizedFinding[])

#### 3. `ScanLog` (`scan_logs` table)
- `id`: GUID (PK)
- `scan_id`: GUID (FK -> `scans.id`, ondelete CASCADE, index)
- `timestamp`: DateTime(timezone=True)
- `level`: String(16) (`"INFO"`, `"WARNING"`, `"ERROR"`, `"DEBUG"`)
- `message`: Text
- `source`: String(64) (default `"system"`, or engine name)
- **Relationships**: `scan` (Scan)

#### 4. `NormalizedFinding` (`findings` table)
- `id`: GUID (PK)
- `scan_id`: GUID (FK -> `scans.id`, ondelete CASCADE, index)
- `asset_id`: GUID (FK -> `assets.id`, ondelete CASCADE, index)
- `fingerprint`: String(64) (SHA-256 deterministic key, index)
- `empire_module`: String(64) (index)
- `exposure_classification`: String(64)
- `is_approved_baseline`: Boolean (default `False`)
- `scanner_engine`: String(64) (index)
- `scanner_rule_id`: String(128)
- `title`: String(512)
- `description`: Text
- `severity`: String(32) (`"CRITICAL"`, `"HIGH"`, `"MEDIUM"`, `"LOW"`, `"INFO"`, index)
- `original_severity`: String(64)
- `cve_id`: String(64) (index)
- `cwe_id`: String(64)
- `cvss_score`: Float
- `cvss_vector`: String(128)
- `epss_score`: Float
- `epss_percentile`: Float
- `is_kev`: Boolean
- `target_location`: String(1024)
- `target_component`: String(255)
- `affected_version`, `fixed_version`: String(128)
- `evidence`: JSON (`request`, `response`, `matched_content`, `curl_command`, `triage_history`, `last_retest`)
- `raw_payload`: Text
- `remediation`: Text
- `references`: JSON (list of URLs)
- `status`: String(32) (default `"OPEN"`, index)
- `remediation_notes`: Text
- `assignee`: String(128)
- `retest_status`: String(64)
- `occurrence_count`: Integer (default 1)
- `first_seen_at`, `last_seen_at`: DateTime(timezone=True)
- `created_at`, `updated_at`: DateTime(timezone=True)
- **Relationships**: `asset` (Asset), `scan` (Scan)

#### 5. Additional Models
- `BaselineException` (`baseline_exceptions`): `scope`, `classification`, `reason`, `owner`, `approved_by`, `is_active`, `evidence`, `review_history`.
- `DailySchedule` (`daily_schedules`): `name`, `profile`, `cron_expression`, `timezone`, `is_active`, `target_ids`, `last_run_at`, `last_status`.
- `SecurityAlert` (`security_alerts`): `severity`, `title`, `message`, `category`, `is_read`, `metadata_json`.
- `VulnerabilityIntelligence` (`vulnerability_intelligence`): Enriched CVE records with CVSS, EPSS, CISA KEV flags, SSVC scores.
- `VulnerabilityAlias` (`vulnerability_aliases`): Graph aliases (GHSA, PYSEC -> CVE).
- `DetectionRule` (`detection_rules`): YAML rules, severity, status, matchers, remediation blocks.
- `User` (`users`): `username`, `hashed_password`, `is_active`, `is_superuser`.

---

## 4. Key Workflows & Subsystem Mechanisms

### 4.1. 8-Step Live Target Verification Pipeline (`target_verifier.py`)
Triggered via `POST /api/v1/assets/{id}/verify`:
1. **Input Validation**: Validates URL scheme (`http`, `https`), parses netloc, checks SSRF whitelist/blacklist.
2. **DNS Resolution**: Resolves A/AAAA records via `socket.getaddrinfo`, extracts public IP.
3. **TLS Verification**: Establishes SSL handshake via `ssl.create_default_context`, checks certificate expiration, issuer, SAN domains, TLS version, and cipher suite.
4. **HTTP Connectivity**: Sends HTTP probe, measures latency (ms), records status code and server response headers.
5. **Redirect Inspection**: Follows hop-by-hop redirects, validates destination URL, detects protocol downgrades (HTTPS -> HTTP).
6. **Web Discovery**: Probes standard endpoints (`/robots.txt`, `/sitemap.xml`, `/.well-known/security.txt`).
7. **Target Fingerprint**: Identifies reverse proxies/WAFs (Cloudflare, Envoy, Nginx), frameworks (Next.js, Vite), and security headers posture (HSTS, CSP, X-Frame-Options, X-Content-Type-Options).
8. **Verification Result**: Aggregates metadata into final verdict (`PASS`/`FAIL`), updating `Asset.verification_status` and `Asset.technology`.

### 4.2. Live Scan Orchestration & SSE Real-Time Streaming
- Triggered via `POST /api/v1/scans`.
- Scan status transitions: `QUEUED` -> `INITIALIZING` -> `RUNNING` -> `COMPLETING` -> `COMPLETED` (or `FAILED` / `CANCELLED`).
- Quality states: `SCANNED_SUCCESSFULLY`, `PARTIAL_COVERAGE`, `AUTH_REQUIRED`, `SCANNER_FAILED`, `TARGET_UNAVAILABLE`.
- Live logging: `ScanLogBuffer` holds log entries in a ring buffer (1,000 entries) and multiplexes chunks to SSE clients subscribing at `GET /api/v1/scans/{id}/logs/stream`.
- Process safety: Processes are monitored with timeouts; cooperative cancellation via `CancellationToken` terminates child subprocesses and updates database state.

### 4.3. Finding Deduplication, 10-State Triage & Live Retest
- **Deduplication Key**: Deterministic SHA-256 fingerprint computed from `asset_id:scanner_engine:scanner_rule_id:target_location:target_component`.
- **Triage Lifecycle**: Findings transition through 10 distinct states: `NEW`, `POTENTIAL`, `CONFIRMED`, `OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`, `FALSE_POSITIVE`, `NOT_AFFECTED`.
- **Live Retest Engine**: `POST /api/v1/findings/{id}/retest` issues immediate HTTP probes to verify remediation. If target returns 401/403/404 on sensitive endpoints, status is updated to `FIXED` with audit trail appended.

---

## 5. Test Suites & Verification Harness Audit

### 5.1. Pytest Configuration & Test Inventory
- Configuration file: `pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`, `filterwarnings = ignore`).
- Test Harness: `tests/conftest.py` provides `client` (`httpx.ASGITransport(app=app)`), `db_session`, and `created_asset_ids` fixture for automatic cleanup.
- Test Inventory: **164 total test cases** across 8 test modules:
  1. `test_challenger_live_empire.py` (4 tests): Target registration, live 8-step probe, baseline scan, evidence deduplication.
  2. `test_empirical_challenger.py` (49 tests): SSRF loopback defense, RFC1918 subnets, cloud metadata blocks, URL normalization, non-destructive safety checks.
  3. `test_platform_core_m1.py` (7 tests): Root target seeding, seeder idempotency, bulk import preview deduplication, asset verification.
  4. `test_scan_intelligence_m2.py` (12 tests): Scanner quality states, process safety, raw evidence capture, finding deduplication.
  5. `test_tier1_feature_coverage.py` (31 tests): Target management, scan dispatch, empire modules, metrics KPIs, reporting artifacts.
  6. `test_tier2_boundary_corner.py` (30 tests): Adversarial inputs, duplicate locators, SSRF bypass vectors, triage 10-state transitions, SQLi defense.
  7. `test_tier3_cross_feature.py` (5 tests): Multi-stage workflows (Target -> Scan -> Finding -> Alert -> Retest -> Report).
  8. `test_tier4_real_world.py` (5 tests): Empire educational platform real-world scenarios, concurrent scan dispatch, approved public media policy.

### 5.2. Verification Script: `scripts/verify_empire_e2e.py`
Automated end-to-end verification script testing all 10 core subsystem capabilities:
1. Database initialization and Empire ecosystem seeding (106 targets, 46 findings).
2. Dashboard Overview KPIs & 8 database-backed chart datasets.
3. Empire 6-module architecture mapping & real-time risk scores.
4. Asset Inventory & Bulk Import Deduplication (CSV/JSON).
5. Approved Public Media Baseline Policy (`/media PUBLIC_BY_DESIGN`).
6. Scan Dispatch & Empire Assessment Engine execution (`DAILY_SECURITY` profile).
7. Vulnerability Triage Lifecycle (10 states) & Live Retest Engine.
8. Multi-Format Audit-Grade Report Generation (Vector PDF, Jinja2 HTML, structured JSON).
9. Daily Assessment Scheduler (`Asia/Ho_Chi_Minh` 02:00 AM ICT) and pipeline trigger.
10. Security Alerts & In-App Notification System.

**Execution Verification**: Passed with 10/10 PASS steps (`XANH MƯỢT 100% — READY FOR PRODUCTION COMBAT DEPLOYMENT`).

---

## 6. Zero-Regression Backend Preservation Constraints

When implementing frontend overhaul views, the following backend contracts must be strictly preserved:

1. **URL Paths & Query Parameters**:
   - Every existing endpoint path under `/api/v1/*` must remain unaltered.
   - Query parameter names (`page`, `size`, `asset_id`, `empire_module`, `severity`, `status_filter`, `search`) and pagination envelope structure (`items`, `total`, `page`, `size`, `pages`) must match existing frontend client expectations.

2. **Data Model Integrity**:
   - No modifications to database table column names, enum values, or foreign key cascades.
   - Pydantic schema validation models in `backend/app/schemas/` must remain compatible.

3. **Live SSE Streaming Protocol**:
   - The `/api/v1/scans/{id}/logs/stream` endpoint expects an SSE `text/event-stream` client receiving `data: {...}\n\n`. Frontend components must maintain EventSource or fetch-stream readers compatible with this format.

4. **10-State Finding Triage**:
   - Frontend triage selects must support all 10 states (`NEW`, `POTENTIAL`, `CONFIRMED`, `OPEN`, `IN_REMEDIATION`, `FIXED`, `REOPENED`, `ACCEPTED_RISK`, `FALSE_POSITIVE`, `NOT_AFFECTED`).

5. **Test Suite Invariants**:
   - `python scripts/verify_empire_e2e.py` must pass with 10/10 passing tests.
   - `pytest tests/` must pass cleanly without modifying test assertions or weakening backend security gates.
