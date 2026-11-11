# NOOSFORGE Security Intelligence — Backend Technical Gap Analysis Report

**Date:** 2026-11-09T19:20:00Z  
**Author:** Survey Explorer Agent (`teamwork_explorer_enh_1`)  
**Mission:** NOOSFORGE Security Intelligence Enhancement Phase  
**Target Platform:** Empire Educational Ecosystem (`https://empire.edu.vn/`)  
**Repository Working Directory:** `c:\Users\nguye\Desktop\noospire`  

---

## 1. Executive Summary & Context

The NOOSFORGE Security Intelligence platform is an enterprise-grade cybersecurity command center engineered for the Empire Education Platform (`https://empire.edu.vn/`). The backend is built on **FastAPI (Python 3.12/3.14)** and asynchronous **SQLAlchemy 2.0** ORM backed by SQLite with WAL mode (`noospire.db`).

Following the user directive and architectural evaluation across `backend/app/` and related components, this investigation analyzed five mission-critical operational pillars:
1. **Scan Scheduling & Process Orchestration**
2. **Log Management, Date/Day Tracking, Purging & System State Reset**
3. **Scanner Engine Health, Versioning, Updates & Availability**
4. **User Authentication & Ultra Admin Provisioning (`dangnhutnguyen0910@gmail.com`)**
5. **Loop Testing & Real-Time Notification Tracking**

### Summary Matrix of Architectural Findings

| Domain | Current State | Critical Architectural Gaps | Recommended Enhancement |
|---|---|---|---|
| **1. Scan Scheduling** | `DailySchedule` model & basic CRUD/trigger in `api/schedules.py` | No active background cron loop/ticker; passive database records only; no one-time future scheduling | Implement asyncio background scheduler task (`SchedulerEngine`) evaluating cron expressions and triggering scheduled scans |
| **2. Log Management & Reset** | `ScanLog` table (per-scan) and in-memory ring buffer; `SecurityAlert` table | No date-range filtering, no unified log viewer across all scans, no export (CSV/JSON), no log purging, no system reset endpoint | Add unified `/api/v1/logs` endpoint with date/day filters, export/purge API, and `/api/v1/system/reset` to restore initial seeded state |
| **3. Engine Management** | Adapters for Nuclei, ZAP, Trivy, Empire Engine, Crawler; `nuclei.exe` v3.11.1 detected | No `/api/v1/engines` router; no engine health check endpoint; no version or template updater (`nuclei -ut`, `nuclei -up`) | Build `/api/v1/engines` router with `/health`, `/versions`, `/update`, and template update commands |
| **4. Authentication & Ultra Admin** | Basic username/password with dev bypass; only `admin` seeded; client-side fake auth in frontend | `dangnhutnguyen0910@gmail.com` NOT seeded in DB; `User` model lacks `email` and `role` fields; no admin dev audit tracking | Seed Ultra Admin in `init_db()`, enhance `User` resolution (username/email), and implement admin activity logging |
| **5. Loop Testing & Notifications** | `SecurityAlert` model with polling endpoints; no loop testing engine | No continuous loop testing runner against primary target; no real-time SSE stream for alerts; no alert purge | Implement `/api/v1/scans/loop-test` with drift analysis and SSE alert streaming (`/api/v1/alerts/stream`) |

---

## 2. Domain 1: Scan Scheduling & Processes

### 2.1 Existing Capabilities Observed

1. **Single Scan Dispatch (`backend/app/api/scans.py` lines 71–122):**
   - Endpoint: `POST /api/v1/scans`.
   - Validates target asset existence in database (`Asset`).
   - Runs SSRF Pre-flight Validation (`SSRFProtector.validate_target`).
   - Active scan authorization gate: `DEEP_ACTIVE` requires `asset.verification_status == VERIFIED`.
   - Inserts `Scan` record into `scans` table in `QUEUED` state.
   - Enqueues scan ID into `AsyncWorkerDispatcher.queue`.

2. **Batch / "Scan All" Dispatch (`backend/app/api/scans.py` lines 128–260):**
   - Endpoints: `POST /api/v1/scans/batch` and `POST /api/v1/scans/scan-all`.
   - Expands target list (`ALL` or specified UUIDs) against configured profile list and engine list.
   - Creates a parent `ScanBatch` entity (`scan_batches` table).
   - Enqueues child scans into `dispatcher`.
   - Manages batch lifecycle progress updates through `_update_batch_progress()`.

3. **Execution Queue & Resource Throttling (`backend/app/core/dispatcher.py` lines 212–455):**
   - `AsyncWorkerDispatcher`: In-memory `asyncio.Queue[uuid.UUID]` backed by `asyncio.Semaphore(max_concurrent)`.
   - Concurrency bounded by `min(settings.MAX_CONCURRENT_SCANS, os.cpu_count() or 4)`.
   - System resource monitoring via `psutil`: If CPU > 90% or RAM > 95%, dequeuing is throttled by 1.0s delays.
   - Per-asset mutual exclusion lock (`asset_locks`) prevents concurrent conflicting scans on the same target.

4. **Cancellation & Emergency Stop (`backend/app/core/dispatcher.py` lines 280–402):**
   - `cancel_scan(scan_id)`: Cooperatively aborts token and invokes `ProcessSafetyManager.terminate_process_tree(scan_id)` to kill spawned sub-processes.
   - `cancel_batch(batch_id)`: Cooperatively terminates all scans in the batch and purges pending queue entries.
   - `stop_all()`: Platform-wide emergency stop halting all running scans and queued tasks (`POST /api/v1/scans/stop-all`).

5. **Live Telemetry & SSE Streaming (`backend/app/core/dispatcher.py` lines 76–148, 403–436):**
   - In-memory ring buffer `ScanLogBuffer` broadcasting via `asyncio.Queue` subscribers.
   - Endpoint `GET /api/v1/scans/{scan_id}/logs/stream` yields SSE `text/event-stream`.
   - Endpoint `GET /api/v1/scans/trackcurrent` (and `/telemetry`) returns active worker matrix, queue depth, and host resources.

### 2.2 Schedule Domain Model & API Endpoints

- **Model:** `DailySchedule` in `backend/app/models/schedule.py`:
  - Table: `daily_schedules`
  - Columns:
    - `id`: `GUID` (UUIDv4 primary key)
    - `name`: `String(255)`
    - `profile`: `String(64)` (default `DAILY_SECURITY`)
    - `cron_expression`: `String(64)` (default `"0 2 * * *"`)
    - `timezone`: `String(64)` (default `"Asia/Ho_Chi_Minh"`)
    - `is_active`: `Boolean` (default `True`)
    - `target_ids`: `JSON` (list of UUIDs or `["ALL"]`)
    - `last_run_at`: `DateTime(timezone=True)`
    - `next_run_at`: `DateTime(timezone=True)`
    - `last_status`: `String(32)`
    - `created_at`, `updated_at`: Timestamps
- **Existing Endpoints in `backend/app/api/schedules.py`:**
  - `GET /api/v1/schedules`: Lists all schedules ordered by `created_at` descending.
  - `POST /api/v1/schedules`: Creates a new schedule record.
  - `POST /api/v1/schedules/{id}/trigger`: Manually triggers batch scan execution for the scheduled targets.
  - `PUT /api/v1/schedules/{id}/toggle`: Toggles `is_active` boolean.

### 2.3 Technical Gaps in Scheduling

1. **Passive DB Record — No Background Scheduling Engine:**
   - Although `DailySchedule` records exist and are seeded by `seed_empire_ecosystem()` (daily run at 02:00 AM ICT), **there is NO background cron loop, timer, or scheduler runner** active in the application.
   - The FastAPI lifespan in `backend/main.py` starts `AsyncWorkerDispatcher`, but does not spawn any scheduler ticker task.
   - If no external cron invokes `POST /api/v1/schedules/{id}/trigger`, scheduled scans **never execute automatically**.
2. **Missing Calculation of `next_run_at`:**
   - When a schedule is created or triggered, `next_run_at` remains `None`. No cron parser (such as `croniter`) is wired to calculate the next execution timestamp based on `cron_expression` and `timezone`.
3. **No One-Time Future Scan Scheduling:**
   - Neither `Scan` nor `ScanBatch` possesses a `scheduled_at` field. Operators cannot schedule a single scan or batch for a specific future datetime (e.g., maintenance window at 23:00 tonight).
4. **Missing Schedule CRUD Operations:**
   - There is no `GET /api/v1/schedules/{id}` (single schedule detail).
   - There is no `PUT /api/v1/schedules/{id}` (full update for name, cron expression, targets, profile).
   - There is no `DELETE /api/v1/schedules/{id}` (deletion of obsolete schedules).

---

## 3. Domain 2: Log Management, Retention & State Reset

### 3.1 Where Logs Are Stored

Logs in the current architecture are split across four distinct storage mechanisms:

1. **`scan_logs` Table in `noospire.db` (`backend/app/models/scan.py` lines 123–138):**
   - Schema:
     - `id`: `GUID` primary key.
     - `scan_id`: Foreign key to `scans.id` with `ondelete="CASCADE"`, indexed.
     - `timestamp`: UTC datetime, defaults to current time.
     - `level`: `String(16)` (`INFO`, `WARNING`, `ERROR`, `DEBUG`).
     - `message`: `Text`.
     - `source`: `String(64)` (`system`, `nuclei`, `zap`, `crawler`, `empire_engine`, `lifecycle`).
   - Persisted via `log_cb` callback in `AsyncWorkerDispatcher._run_scan` with SQLite lock retry logic (3 attempts).
2. **`security_alerts` Table in `noospire.db` (`backend/app/models/alert.py` lines 11–22):**
   - Stores in-app alerts generated when new `CRITICAL` or `HIGH` vulnerabilities are discovered (`category="VULN"`) or when a scan reaches completion/failure (`category="SCAN"`).
   - Columns: `id`, `severity`, `title`, `message`, `category`, `is_read`, `metadata_json`, `created_at`, `updated_at`.
3. **`rule_audit_logs` Table in `noospire.db` (`backend/app/models/rule.py` lines 132–154):**
   - Immutable audit trail specifically for detection rule lifecycle transitions (Draft -> Review -> Active). Not general system audit.
4. **In-Memory Live Stream Buffer (`backend/app/core/dispatcher.py` lines 76–148):**
   - `ScanLogBuffer`: In-memory `deque(maxlen=1000)` per scan ID. Powers SSE `/scans/{scan_id}/logs/stream`. Discarded on process restart.
5. **File Logs:**
   - **Currently nonexistent.** The Python logging system is not configured with a `RotatingFileHandler`. Standard log output goes solely to standard output (`stdout`/`stderr`).

### 3.2 Date/Day Tracking Analysis

- **Current API Limitation:** The only endpoint that reads `scan_logs` is `GET /api/v1/scans/{scan_id}/logs`.
  - It filters strictly by `scan_id`.
  - It does **NOT** accept `start_date`, `end_date`, `level`, `source`, or keyword `search` parameters.
- **Cross-Scan Tracking Gap:** There is **no platform-wide endpoint** to query logs across all scans. An operator investigating what occurred on a specific day (e.g. `2026-11-09`) across the entire platform cannot query logs by date.
- **Scans by Date Gap:** `GET /api/v1/scans` only filters by `asset_id` and `status_filter`. It lacks date range filters (`date_from`, `date_to`).

### 3.3 Log Export, Purge & State Reset Gaps

1. **Export Functionality (Missing):**
   - There is no API endpoint to export logs to standard export formats (`JSON`, `CSV`, `TXT`).
   - Operators cannot download raw forensic logs for audit compliance or external ingestion (SIEM/ELK).
2. **Log Purging & Truncation (Missing):**
   - Deleting a scan via `DELETE /api/v1/scans/{scan_id}` deletes its associated `scan_logs` via database CASCADE.
   - However, there is no bulk purge endpoint:
     - No endpoint to delete logs older than $N$ days (`days_older_than=30`).
     - No endpoint to purge all `scan_logs` while retaining `Scan` summary records.
     - No endpoint to clear or truncate `security_alerts`.
3. **System State Reset / "Quay về trạng thái ban đầu" (Missing):**
   - The user request explicitly demands: *"Quét toàn bộ hệ thống, xóa logs- kiểm tra kỹ, đdầyddur, hoàn toàn - lưu logs, xóa logs, quay về trạng thái ban đầu, track by days"*.
   - Currently, there is **no system reset endpoint or script** that can:
     1. Cooperatively stop all running scans and background workers (`stop_all()`).
     2. Truncate/wipe dynamic assessment data: `scan_logs`, `scans`, `scan_batches`, `findings`, `security_alerts`.
     3. Clear in-memory log buffers and thread tracking telemetry.
     4. Re-execute `seed_empire_ecosystem()` and re-seed clean baseline state for Empire targets, baselines, and default rules.
     5. Re-seed default admin accounts (including Ultra Admin).

---

## 4. Domain 3: Scanner Engine Health, Updates & Management

### 4.1 How Scanner Engines Are Managed

The scanner subsystem in `backend/app/scanners/` uses an adapter pattern rooted at `BaseScannerAdapter` (`backend/app/scanners/base.py`):

1. **ProjectDiscovery Nuclei CLI (`backend/app/scanners/nuclei.py`):**
   - Detects CLI via `shutil.which("nuclei")` or `shutil.which("nuclei.exe")`.
   - **Host Audit Observation:** `nuclei.exe` **IS INSTALLED** on the system at:
     ```
     C:\Users\nguye\go\bin\nuclei.exe
     ```
   - **Engine Version Verified:** Running `nuclei -version` confirmed:
     ```
     [INF] Nuclei Engine Version: v3.11.1
     [INF] Nuclei Config Directory: C:\Users\nguye\AppData\Roaming\nuclei
     [INF] Nuclei Cache Directory: C:\Users\nguye\AppData\Local\nuclei
     [INF] PDCP Directory: C:\Users\nguye\.pdcp
     ```
   - When executed, `NucleiAdapter` calls:
     ```bash
     nuclei -target <url> -jsonl -silent -nc -timeout 5
     ```
   - If execution fails or binary is absent, it falls back to `NucleiLabRunner` (evaluating 25 approved security templates with raw HTTP probes).
2. **OWASP ZAP (`backend/app/scanners/zap.py`):**
   - Detects CLI via `shutil.which("zap.bat")`, `zap.sh`, `zap`.
   - **Host Audit Observation:** Native ZAP binary is absent on this host.
   - Automatically executes high-fidelity fallback `ZAPLabRunner` (`backend/app/scanners/lab_runners.py` lines 150–480), performing real HTTP probes for security headers, cookie flags, anti-CSRF, and directory traversal.
3. **Trivy Container & SCA Scanner (`backend/app/scanners/trivy.py`):**
   - Detects CLI via `shutil.which("trivy")`.
   - **Host Audit Observation:** Native Trivy binary is absent on this host.
   - Automatically executes embedded `TrivyLabRunner` inspecting manifests and package dependencies.
4. **Empire Specialized Assessment Engine (`backend/app/scanners/empire_engine.py`):**
   - Pure Python in-process async engine (831 lines) utilizing `httpx.AsyncClient`.
   - Tailored specifically to Empire business modules:
     - Module A: Student Management & Authentication (Better-Auth, BOLA, BFLA, password reset).
     - Module B: Educational Materials & `/media` Approved Public Exposure Policy.
     - Module C: Supporting Educational Tools (news feeds, vocabulary utilities, SSRF).
     - Module D: OWASP API Security Top 10 checks.
     - Module E: Web application security & HTTP header hardening.
     - Module F: Controlled brute-force resistance & credential stuffing resilience.
5. **Bounded BFS Web Crawler (`backend/app/scanners/crawler.py`):**
   - Pure Python in-process asynchronous BFS crawler (251 lines).
   - Enforces same-origin domain restrictions, max depth (default 3), max pages (default 50), and rate-limiting.

### 4.2 Technical Gaps in Engine Management

1. **No Engine Health Check Endpoint (`/api/v1/engines/health`):**
   - There is **no router mounted at `/api/v1/engines`**.
   - The application has `/health`, but that only returns service-level uptime (`{"status": "healthy"}`).
   - There is no endpoint returning structured diagnostics for each engine:
     - Availability mode (`binary_cli` vs `lab_engine` vs `in_process`).
     - Absolute binary path on host.
     - Version string (e.g. `v3.11.1` for Nuclei).
     - Template directory and template counts.
     - Operational status (`ONLINE`, `DEGRADED`, `STANDBY`).
2. **No Engine Update or Template Update Trigger:**
   - Nuclei supports updating templates (`nuclei -update-templates` or `nuclei -ut`) and updating the binary (`nuclei -update` or `nuclei -up`).
   - Currently, there is **no backend endpoint or management action** to trigger an update or check if updates are available.
   - The user request explicitly demands: *"Update if engine got update. Check UI, evidence, target... Mange engine, update, work, healthy"*.
3. **No Engine Configuration Management:**
   - Operators cannot view or modify engine parameters (e.g., custom binary paths, extra CLI flags, template filters) via API.

---

## 5. Domain 4: User Authentication & Ultra Admin Provisioning

### 5.1 Current Authentication Architecture

1. **User Model (`backend/app/models/base.py` lines 48–56):**
   ```python
   class User(Base, TimestampMixin):
       __tablename__ = "users"
       id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
       username: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
       hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
       is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
       is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
   ```
2. **Password Security (`backend/app/core/security.py` lines 19–38):**
   - Uses PBKDF2-HMAC-SHA256 with 100,000 iterations and a 16-byte cryptographically random salt (`salt.hex():key.hex()`).
   - Constant-time comparison via `hmac.compare_digest`.
3. **Database Seeding (`backend/app/core/database.py` lines 78–92):**
   - Seeds a single default user:
     - `username`: `settings.ADMIN_USERNAME` (defaults to `"admin"` from `os.getenv("SENTINEL_ADMIN_USER", "admin")`).
     - `hashed_password`: Hashed from `settings.ADMIN_PASSWORD` (defaults to `"admin123"`).
     - `is_superuser`: `True`.
4. **Login Endpoint (`backend/app/api/auth.py` lines 32–119):**
   - Handles JSON and form bodies.
   - **Development Bypass Logic (lines 98–101):**
     If running in development (`settings.is_development == True`), almost any login attempt or empty credential is automatically granted a valid token and superuser privileges.
5. **Frontend Login Page (`frontend/src/app/login/page.tsx` lines 23–95):**
   - Hardcodes Ultra Admin credentials:
     ```typescript
     const ULTRA_ADMIN_CREDENTIALS = {
       email: 'dangnhutnguyen0910@gmail.com',
       password: 'Hahanguyen09@',
       role: 'SUPER_ADMIN',
       name: 'Đại Ca Tú (Ultra Admin)',
     };
     ```
   - **Critical Architectural Disconnect:** The frontend login page **never makes a network request to the backend `/api/v1/auth/login` endpoint**!
   - Instead, it intercepts credentials locally and writes fake dummy tokens (`jwt_ultra_admin_${Date.now()}`) into `localStorage`.
   - When the frontend attempts to make authenticated API calls to the backend, it sends a client-generated dummy token that does not decode properly against backend `SECRET_KEY` unless dev mode bypass catches it.

### 5.2 Ultra Admin Gaps & Requirements

1. **Ultra Admin User Not Seeded in Database:**
   - The user `dangnhutnguyen0910@gmail.com` with password `Hahanguyen09@` **does not exist in `noospire.db`**.
   - If `AUTH_ENABLED=True` or `DEV_AUTH_BYPASS=False` is set (production mode), login with `dangnhutnguyen0910@gmail.com` immediately returns HTTP `401 Unauthorized`.
2. **User Model Schema Lacks `email` and `role` Fields:**
   - The `User` model only has `username`.
   - In production enterprise SaaS, users log in using either email or username.
   - There is no `role` column (e.g. `SUPER_ADMIN`, `SECURITY_LEAD`, `DEV_ADMIN`) or tracking of dev privileges.
3. **Dev Tracking & Admin Audit Trail:**
   - User request: *"Login page first - admin track dev, ..."*
   - There is no backend audit log recording administrator actions, token issuances, API access, scan dispatches, or state resets.

---

## 6. Domain 5: Loop Testing & Notification Tracking Support

### 6.1 Loop Testing Support Analysis

- **Current State:**
  - The backend only supports **one-shot scans** (`POST /api/v1/scans`) and **one-shot batch sweeps** (`POST /api/v1/scans/batch`).
  - There is **NO automated loop testing harness** in the backend.
- **Requirements from User Request:**
  - *"Loop test, notification track... Quét toàn bộ hệ thống... Launch all primary target (empire.edu.vn), all with client, admin, track, test, api, backend, test, track. Loop test, notification track."*
- **Gaps:**
  - No endpoint exists to dispatch a recurring verification loop against `https://empire.edu.vn/` (e.g., run scan every $M$ seconds for $N$ iterations to test stability, verify zero-fabrication, and detect regression).
  - No comparison/drift engine exists to verify whether findings across consecutive loop iterations are identical (idempotence verification) or if any intermittent issues appear.
  - No stop-on-failure condition exists for loop testing.

### 6.2 Notification & Alert Architecture Analysis

1. **Existing Model (`backend/app/models/alert.py`):**
   - `SecurityAlert` table:
     - `id`: GUID primary key.
     - `severity`: String (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`).
     - `title`: String(255).
     - `message`: Text.
     - `category`: String(64) (`VULN`, `SCAN`, `KEV`, `BASELINE`).
     - `is_read`: Boolean (indexed).
     - `metadata_json`: JSON dict.
     - `created_at`, `updated_at`: Timestamps.
2. **Automatic Alert Generation in Dispatcher (`backend/app/core/dispatcher.py`):**
   - High-severity finding alerts (lines 876–887): Created whenever a `CRITICAL` or `HIGH` finding is detected.
   - Scan lifecycle alerts (lines 920–949): Created when a scan reaches `COMPLETED` or `FAILED` state.
3. **Existing API Endpoints (`backend/app/api/alerts.py`):**
   - `GET /api/v1/alerts`: Returns list of alerts with optional `is_read` filter and limit.
   - `POST /api/v1/alerts/{id}/read`: Marks single alert as read.
   - `POST /api/v1/alerts/read-all`: Marks all unread alerts as read.

### 6.3 Technical Gaps in Notification Tracking

1. **No Real-Time Notification Stream (SSE / WebSocket):**
   - While scan logs have SSE streaming (`/scans/{id}/logs/stream`), alerts only support polling `GET /api/v1/alerts`.
   - There is no SSE endpoint (e.g. `GET /api/v1/alerts/stream`) to immediately notify the SOC operator dashboard when an alert triggers.
2. **Missing Notification Management Endpoints:**
   - No `DELETE /api/v1/alerts/{id}` (dismiss/delete single alert).
   - No `DELETE /api/v1/alerts` (clear all alerts or purge alerts older than $N$ days).
   - No `GET /api/v1/alerts/unread-count` (lightweight unread counter for navigation badges).
3. **No Date Range or Category Filtering:**
   - Cannot filter alerts by day (`date_from`, `date_to`) or category (`category="SCAN"` vs `category="VULN"`).
4. **No External Notification Dispatcher:**
   - No webhook or notification bridge to external dispatchers (e.g., Telegram, Discord, Slack, email) for critical security alerts.

---

## 7. Comprehensive Architecture Implementation Roadmap

To resolve all identified gaps and fulfill the user request to perfection, the following backend architecture enhancements are designed:

```
                               ┌────────────────────────────────────────────────────────┐
                               │           NOOSFORGE REST API (/api/v1)                 │
                               └──────────────────────────┬─────────────────────────────┘
                                                          │
          ┌───────────────────────┬───────────────────────┼────────────────────────┬────────────────────────┐
          ▼                       ▼                       ▼                        ▼                        ▼
 ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐    ┌────────────────────┐    ┌──────────────────┐
 │  Scan & Batch   │    │ Continuous Daily │    │ Engine Health &  │    │  Log Management &  │    │ Authentication & │
 │ Orchestration   │    │ Scheduler Engine │    │ Lifecycle API    │    │ State Reset API    │    │ Ultra Admin & Dev│
 ├─────────────────┤    ├──────────────────┤    ├──────────────────┤    ├────────────────────┤    ├──────────────────┤
 │- Single Scans   │    │- Async Ticker    │    │- GET /engines    │    │- GET /logs (Day/   │    │- Seed Ultra Admin│
 │- Batch Scans    │    │  (Cron Evaluator)│    │- /engines/health │    │  Date Filters)     │    │  dangnhutnguyen0910│
 │- Process Safety │    │- next_run_at     │    │- /engines/update │    │- POST /logs/export │    │  @gmail.com      │
 │- Loop Test API  │    │  Calculation     │    │- Template Update │    │- POST /logs/purge  │    │- Admin Audit Log │
 │  (/scans/loop)  │    │- CRUD Endpoints  │    │- CLI Version/Path│    │- POST /system/reset│    │- Real JWT Sync   │
 └────────┬────────┘    └────────┬─────────┘    └────────┬─────────┘    └─────────┬──────────┘    └────────┬─────────┘
          │                      │                       │                        │                        │
          └──────────────────────┴───────────────────────┼────────────────────────┴────────────────────────┘
                                                         │
                                                         ▼
                                       ┌──────────────────────────────────┐
                                       │     Persistence: noospire.db     │
                                       │   (SQLite WAL + Asyncpg-ready)   │
                                       └──────────────────────────────────┘
```

### Detailed Component Specifications

### 7.1 Component 1: Engine Management Router (`/api/v1/engines`)
- **New File:** `backend/app/api/engines.py`
- **Endpoints:**
  - `GET /api/v1/engines`: Lists all 5 engines (Nuclei, ZAP, Trivy, Empire Engine, BFS Crawler) with operational status, binary path, version, and capabilities.
  - `GET /api/v1/engines/health`: Diagnostic health check returning detailed connectivity, execution permissions, template count, and version strings.
  - `POST /api/v1/engines/nuclei/update-templates`: Dispatches `nuclei -update-templates` asynchronously and streams output.
  - `POST /api/v1/engines/nuclei/update`: Dispatches `nuclei -update` to pull the latest engine release.
- **Integration:** Registered in `backend/main.py` under `/api/v1/engines`.

### 7.2 Component 2: Background Scheduler Loop (`SchedulerEngine`)
- **File to Enhance:** `backend/app/core/scheduler.py` & `backend/main.py` lifespan
- **Capabilities:**
  - Spawns an asyncio background worker in `lifespan(app)` that runs every 30 seconds.
  - Queries active `DailySchedule` rows where `is_active == True`.
  - Parses `cron_expression` against current UTC/ICT timestamp.
  - Calculates `next_run_at`.
  - Automatically triggers scan batch when the schedule is due, updates `last_run_at`, and generates a lifecycle `SecurityAlert`.
- **API Enhancements in `backend/app/api/schedules.py`:**
  - Add `GET /api/v1/schedules/{id}`.
  - Add `PUT /api/v1/schedules/{id}` (full update for name, cron, targets, timezone).
  - Add `DELETE /api/v1/schedules/{id}`.

### 7.3 Component 3: Unified Log Management, Date Tracking, Export & Reset
- **New/Enhanced Router:** `backend/app/api/logs.py` (or integrated into `settings.py` / `scans.py`)
- **Endpoints:**
  - `GET /api/v1/logs`: Unified log stream querying `scan_logs` across all scans, with query parameters:
    - `day` (e.g. `2026-11-09`), `start_date`, `end_date`
    - `level` (`INFO`, `WARNING`, `ERROR`)
    - `source` (`system`, `nuclei`, `zap`, `empire_engine`, `crawler`)
    - `search` (text search in `message`)
    - `page`, `size` pagination
  - `GET /api/v1/logs/stats/by-day`: Returns daily log counts broken down by log level for date-based visualization.
  - `POST /api/v1/logs/export`: Generates downloadable or streaming log export in `JSON`, `CSV`, or plaintext format.
  - `POST /api/v1/logs/purge`: Deletes logs with options: `days_older_than: int`, `scan_id: Optional[UUID]`, or `purge_all: bool`.
  - `POST /api/v1/system/reset`: **Platform State Reset (Quay về trạng thái ban đầu)**:
    1. Stops all active scans (`dispatcher.stop_all()`).
    2. Purges operational tables: `scan_logs`, `scans`, `scan_batches`, `findings`, `security_alerts`, `rule_audit_logs`.
    3. Clears in-memory ring buffers (`log_buffer`).
    4. Re-seeds clean baseline data (`seed_empire_ecosystem()`).
    5. Re-seeds default admin & Ultra Admin credentials.
    6. Returns clean baseline status report.

### 7.4 Component 4: Ultra Admin Seeding & Dev Activity Tracking
- **Enhancement in `backend/app/core/database.py`:**
  - In `init_db()`, unconditionally seed or update the Ultra Admin user:
    - `username`: `"dangnhutnguyen0910@gmail.com"`
    - `hashed_password`: Hashed from `"Hahanguyen09@"`
    - `is_active`: `True`
    - `is_superuser`: `True`
- **Enhancement in `backend/app/core/config.py`:**
  - Add `ULTRA_ADMIN_EMAIL: str = "dangnhutnguyen0910@gmail.com"`
  - Add `ULTRA_ADMIN_PASS: str = "Hahanguyen09@"`
- **Enhancement in `backend/app/api/auth.py`:**
  - Accept either username or email in login payload.
  - Authenticate against database hashed password regardless of dev mode.
  - Return user profile with `role: "SUPER_ADMIN"`, `is_ultra_admin: True`, and full permissions.
- **Admin Audit Trail Model:**
  - Table: `admin_audit_logs` tracking user, action, target, timestamp, and IP address for full dev/admin operation tracking.

### 7.5 Component 5: Loop Testing & Real-Time Alert Streaming
- **Loop Testing Endpoint (`POST /api/v1/scans/loop-test`):**
  - Payload:
    - `target_locator`: Primary target `https://empire.edu.vn/`
    - `iterations`: Number of scan cycles (e.g. 3 to 10)
    - `interval_seconds`: Cooldown between cycles (e.g. 5s)
    - `profile`: Scan profile (`DAILY_SECURITY`, `QUICK`, `BASELINE`)
    - `engines`: Engines to engage (`all`, `nuclei`, `empire_engine`)
    - `stop_on_failure`: Boolean
  - Execution: Executes consecutive assessment passes, tracks finding drift (new vs recurring findings), and produces a stability report.
- **Real-Time Alert SSE Stream (`GET /api/v1/alerts/stream`):**
  - Provides Server-Sent Events stream for `security_alerts` so notifications appear instantly on the dashboard without polling.
  - Add `DELETE /api/v1/alerts/{id}` and `DELETE /api/v1/alerts` (clear notifications).
  - Add `GET /api/v1/alerts/unread-count`.

---

## 8. Verification Strategy & Acceptance Criteria

1. **Scheduling Verification:**
   - Verify `GET /api/v1/schedules` lists the seeded 02:00 AM ICT schedule with calculated `next_run_at`.
   - Verify `POST /api/v1/schedules/{id}/trigger` initiates batch scan across targets.
   - Verify background scheduler executes scans when due.
2. **Log Management & State Reset Verification:**
   - Verify `GET /api/v1/logs?day=YYYY-MM-DD` returns filtered logs.
   - Verify `POST /api/v1/logs/export` returns complete structured log payload.
   - Verify `POST /api/v1/logs/purge` deletes logs without corrupting foreign key relationships.
   - Verify `POST /api/v1/system/reset` wipes operational data and cleanly re-seeds baseline targets (`https://empire.edu.vn/`) and findings.
3. **Engine Health & Update Verification:**
   - Verify `GET /api/v1/engines/health` returns status `ONLINE` and reports `nuclei v3.11.1` binary path.
   - Verify `POST /api/v1/engines/nuclei/update-templates` executes and updates templates.
4. **Ultra Admin Authentication Verification:**
   - Verify `POST /api/v1/auth/login` authenticates `dangnhutnguyen0910@gmail.com` with password `Hahanguyen09@` and returns a signed JWT.
   - Verify `GET /api/v1/auth/me` returns `is_superuser=True`.
5. **Loop Testing & Notifications Verification:**
   - Verify `POST /api/v1/scans/loop-test` completes multiple iterations against `https://empire.edu.vn/` with drift reporting.
   - Verify `GET /api/v1/alerts/stream` receives real-time alert events.
