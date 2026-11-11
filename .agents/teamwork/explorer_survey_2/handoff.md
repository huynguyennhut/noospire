# Handoff Report: Backend Core, Job Queue, Pipeline, Dispatcher, Scheduler & RBAC Architecture Survey

- **Author**: Explorer 2 (Backend & Queue Explorer)
- **Target Audience**: Orchestrator, Backend Engineers, Implementer Agents
- **Requirements Covered**: R1, R2, R3, R5, and Gates 1, 3, 5
- **Working Directory**: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\explorer_survey_2`
- **Date**: 2026-11-10T08:35:00Z

---

## 1. Observation

Direct code observations from the repository:

### 1.1 `backend/main.py` & In-Process Lifecycle
- **Lines 41–52**: Blind cancellation of all unfinished scans on ASGI startup:
  ```python
  async with AsyncSessionLocal() as session:
      await session.execute(
          update(Scan)
          .where(Scan.status.in_([ScanStatus.QUEUED.value, ScanStatus.INITIALIZING.value, ScanStatus.RUNNING.value]))
          .values(status=ScanStatus.CANCELLED.value, error_message="Session interrupted / server restarted.")
      )
      await session.commit()
  ```
  *Observed defect*: In a multi-replica or multi-process cluster, whenever an API container or second process boots, it indiscriminately marks all running or queued scans as `CANCELLED`, destroying active work on healthy worker nodes.
- **Lines 55–62**: Worker and scheduler tickers are launched in-process inside the FastAPI ASGI lifespan:
  ```python
  dispatcher = get_dispatcher()
  if isinstance(dispatcher, AsyncWorkerDispatcher):
      dispatcher.start()

  scheduler_engine = get_scheduler_engine()
  scheduler_engine.start()
  ```
  *Observed defect*: The dispatcher worker loop (`_worker_loop`) and scheduler ticker (`_run_loop`) run as `asyncio.create_task` inside the web API process. They are not decoupled CLI worker processes.

### 1.2 `backend/app/core/dispatcher.py` & Engine Permissions
- **Line 633**: Hardcoded `or True` in target SSRF check:
  ```python
  norm_url, resolved_ip = SSRFProtector.validate_target(
      scan.target_locator, allow_private=scan.allow_private_targets or True
  )
  ```
  *Observed defect*: `or True` bypasses SSRF private target protection unconditionally.
- **Lines 704–705**: Hardcoded `True` constants passed to scanner execution requests:
  ```python
  exec_request = ScanExecutionRequest(
      scan_id=scan.id,
      asset_id=asset.id,
      asset_type=AssetType(asset.asset_type),
      target_locator=scan.target_locator,
      profile=scan.profile,
      timeout_seconds=scan.timeout_seconds,
      allow_private_targets=True,
      custom_config={"is_verified": True},
  )
  ```
  *Observed defect*: Regardless of whether an asset is actually verified or private targets are restricted, `allow_private_targets=True` and `custom_config={"is_verified": True}` are hardcoded constants.
- **Lines 228–230 & 281–287**: In-memory queue without DB leases or fencing tokens:
  ```python
  self.queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
  ...
  await self.queue.put(scan_id)
  ```
  *Observed defect*: Jobs reside in an in-memory `asyncio.Queue`. There is zero DB-level worker claim, no `worker_id`, no `lease_expires_at`, no `heartbeat_at`, and no `fencing_token`.
- **Line 840**: Finding scan association mutation destroying historical integrity:
  ```python
  if existing_finding:
      existing_finding.occurrence_count += 1
      existing_finding.last_seen_at = now
      existing_finding.scan_id = scan.id  # <-- Overwrites historical scan_id!
  ```
  *Observed defect*: Re-observed findings have their `scan_id` foreign key updated to the latest scan. When Day 1 scan reports are generated (`backend/app/reporting/generator.py:315`), Day 1 scans show 0 findings because the association was overwritten.
- **Lines 966–999**: `CeleryDispatcher` is an inert mock:
  `CeleryDispatcher` only executes `logger.info` and returns dummy constants. Celery is not installed in the Python environment.

### 1.3 `backend/app/api/scans.py` & SSE Streaming
- **Lines 500–530**: In-memory, non-resumable SSE stream:
  ```python
  @router.get("/{scan_id}/logs/stream")
  async def stream_scan_logs(scan_id: uuid.UUID, current_user: User = Depends(require_viewer)) -> StreamingResponse:
      async def event_generator():
          try:
              async for log_entry in log_buffer.subscribe(scan_id):
                  payload = {
                      "id": str(log_entry.id),
                      "scan_id": str(log_entry.scan_id),
                      "timestamp": log_entry.timestamp.isoformat(),
                      "level": log_entry.level,
                      "message": log_entry.message,
                      "source": log_entry.source,
                  }
                  yield f"data: {json.dumps(payload)}\n\n"
          except Exception:
              pass
  ```
  *Observed defects*:
  1. Subscribes only to `log_buffer` (in-memory ring buffer in current process). Events produced by a worker in another process are invisible.
  2. SSE frame omits `id: <event_id>\n`. Reconnecting clients cannot provide `Last-Event-ID`.
  3. No support for `Last-Event-ID` header or `cursor` query parameter.
  4. Once established, the loop never re-verifies `current_user.is_active` or session validity. Deactivated users stream indefinitely.
- **Events 101+ concealment / truncation**:
  - `frontend/src/lib/api.ts:994`: `getScanLogs` queries `/scans/${scanId}/logs?size=100`.
  - `backend/app/api/scans.py:444`: `size: int = Query(50, ge=1, le=200)`. Only page 1 is returned.
  - When SSE drops and `fetchScanLogsFallback` is called in `frontend/src/app/active-assessments/page.tsx:223`, logs 101+ are truncated and concealed from the UI terminal.

### 1.4 `backend/app/api/metrics.py` & Inferred History
- **Lines 141–165 & 232–253**:
  ```python
  @router.get("/charts/vulnerability-trend")
  async def get_vulnerability_trend(days: int = 14, db: AsyncSession = Depends(get_db)) -> Any:
  ...
  @router.get("/charts/risk-trend")
  async def get_risk_score_trend(days: int = 14, db: AsyncSession = Depends(get_db)) -> Any:
  ```
  *Observed defects*:
  1. Both endpoints default to `days: int = 14` instead of the mandated 7 calendar days.
  2. Inferred history: Trend is calculated by querying current `NormalizedFinding` rows and projecting backwards based on `created_at.date() <= d` and current `status`. If a finding was open for 6 days and fixed on day 7, it is evaluated as fixed on all previous days because `status == 'FIXED'`.
- **Line 355**: Fabricated intelligence sync timestamp:
  `"last_sync": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")` dynamically returns current clock time on every request rather than recorded feed sync timestamps.
- **Frontend Fallbacks**:
  - `frontend/src/app/dashboard/page.tsx:75`: `const [timeRange, setTimeRange] = useState<TimeRangeDays>(14);`
  - `frontend/src/app/dashboard/page.tsx:43`: `const EMPIRE_BASELINE_METRICS: OverviewMetrics = { total_assets: 379, ... }` hardcoded fallback constant.

### 1.5 Database Models (`backend/app/models/scan.py`, `schedule.py`)
- `Scan` table lacks:
  - `worker_id: Mapped[Optional[str]]`
  - `lease_token: Mapped[Optional[str]]`
  - `lease_expires_at: Mapped[Optional[datetime]]`
  - `heartbeat_at: Mapped[Optional[datetime]]`
  - `fencing_token: Mapped[int]` (default 0)
  - `retry_count: Mapped[int]`, `max_retries: Mapped[int]`
  - `cancelled_at: Mapped[Optional[datetime]]`, `cancellation_reason: Mapped[Optional[str]]`
  - `exit_code: Mapped[Optional[int]]`, `process_error: Mapped[Optional[str]]`, `parse_error: Mapped[Optional[str]]`
  - `subtarget_path: Mapped[Optional[str]]`, `http_method: Mapped[Optional[str]]`, `tenant_id: Mapped[Optional[str]]`, `environment: Mapped[Optional[str]]`, `policy_revision: Mapped[Optional[str]]`
- Missing Entity Models:
  - `RunPlan`: To record inventory accounting, snapshot targets, execution aliases, and exclusions.
  - `CheckExecution`: Child engine execution record per target, profile, and engine (tracking version, rule digest, worker, start/end timestamps, result, report link).
  - `Observation`: Per-check observation record preserving finding identity across runs without mutating `finding.scan_id`.

### 1.6 Hourly Scheduler (`backend/app/core/scheduler.py`, `backend/app/api/schedules.py`)
- **Lines 140–206 in `scheduler.py`**:
  - `DailySchedule` default is `cron_expression="0 2 * * *"` (2 AM once a day) instead of hourly `0 * * * *` in `Asia/Ho_Chi_Minh`.
  - When `next_run_at <= now`, it loops through targets and adds individual `Scan` objects without creating a `ScanBatch`.
  - Zero overrun check: If a scan takes >1 hour, at the next hour `tick()` triggers another full sweep, creating overlapping, un-coalesced batches.
  - Zero active batch deduplication: `POST /api/v1/scans/batch` and `POST /api/v1/scans/scan-all` create new batches unconditionally even when an identical batch is already `RUNNING`.
  - Missing Health/Status endpoint: No endpoint exposing `server_time_utc`, `next_due_instant`, `last_scheduled_run`, `last_completed_run`, `scheduler_health`, `missed_slots_count`.

### 1.7 Sole Owner RBAC & Privileged Enforcement (`backend/app/api/auth.py`, `deps.py`, `config.py`)
- `POST /api/v1/auth/bootstrap` in `backend/app/api/auth.py:74`:
  Accepts arbitrary username/email; does not bind exclusively to `dangnhutnguyen0910@gmail.com`.
- Hardcoded literals:
  - `backend/app/core/config.py:25`: `SECRET_KEY = "noospire-super-secret-key-change-in-production-2026"`
  - `backend/app/core/config.py:30`: `ADMIN_USERNAME = "admin"`
  - `backend/app/core/database.py:104`: `email="admin@sentinel.local"`
  - `backend/app/core/empire_seeder.py:411`: `approved_by="Security Operations Lead (Nhut)"`
- Missing user management endpoints:
  No API endpoints for owner to invite users, activate/deactivate accounts, grant/revoke scoped permissions, or view cross-user audit activity.
- Immediate session revocation gap:
  When an account is deactivated, existing active SSE stream connections continue streaming indefinitely because `stream_scan_logs` only authenticates on handshake.

### 1.8 Scanner Adapters
- `backend/app/scanners/nuclei.py:122`: Missing `ScanProfile` import in `timeout_limit` condition raises `NameError` if triggered.
- `backend/app/scanners/zap.py:117`: `-quickout zap_report.json` outputs to a shared static filename, causing race conditions; code attempts to parse STDOUT rather than the output file.
- `backend/app/scanners/trivy.py:157`: `cmd = [..., "fs", ...]` hardcodes `fs`, passing container image locators to filesystem scanning.

---

## 2. Logic Chain

1. **Failure Handling & Three-Line Incident (R1 & Gate 1)**:
   - Because `main.py` blindly cancels scans on startup, any transient reload or multi-process launch marks healthy scans as cancelled.
   - Because `frontend/src/lib/api.ts` contained `handleFallback` with `dispatchNewScan` storing mock scans in `localStorage`, backend 503 or SPA HTML responses silently produced fabricated local scans.
   - When `fetchScanLogsFallback` queries logs, `size=100` truncates events at 100, concealing events 101+.
   - Resolving R1 requires:
     1. Removing unconditional startup cancellation in `main.py`.
     2. Implementing DB-backed worker claims with leases and heartbeats.
     3. Replacing hardcoded `True` constants in `dispatcher.py` with real dynamic values.
     4. Fixing `scans.py` SSE to emit `id:` frames, support `Last-Event-ID` / cursor replay, and streaming from database events.
     5. Eliminating all client-side fallback simulation and hardcoded constants.

2. **Ultra Scan Orchestration & Inventory Accounting (R2 & Gate 2)**:
   - Ultra Scan requires evaluating 379 synthetic inventory IDs into 368 execution targets, 728 engine executions, 6 shared results, and 5 explained exclusions.
   - Because the existing `Scan` model groups all engines into `engine="all"` in a single scan row, per-engine child execution tracking is impossible without a `CheckExecution` entity.
   - Overwriting `finding.scan_id` on re-detection breaks historical audit trails. An `Observation` model or association table must link scans to findings without mutating the finding's original discovery context.
   - Adapters must be fixed (Nuclei import, ZAP unique report path, Trivy `image` vs `fs`).

3. **Hourly Scheduling, Durability & Queue (R3 & Gate 3)**:
   - The scheduler and scanner workers must be executable as independent processes outside the FastAPI ASGI web server.
   - The hourly schedule must be configured at `0 * * * *` with initial timezone `Asia/Ho_Chi_Minh` and UTC storage.
   - Overrun protection requires checking active batches before scheduling: if a run takes >1 hour, missed hourly occurrences must be recorded as missed slots and coalesced into at most ONE pending follow-up run.
   - Manual launches during an active run must return the active batch with deduplication via idempotency keys.
   - Workers must acquire jobs via atomic DB leases (`UPDATE scans SET status='RUNNING', worker_id=:wid, lease_expires_at=:exp, fencing_token=fencing_token+1 WHERE status='QUEUED'`).
   - Abandoned jobs are recovered by a reaper loop checking `lease_expires_at < utcnow()`, bounding retries, and recording failure reasons.

4. **Sole Owner RBAC & Privileged Enforcement (R5 & Gate 5)**:
   - The one-time bootstrap endpoint must enforce binding to `dangnhutnguyen0910@gmail.com` with immutable account ID.
   - Hardcoded secret literals in `config.py` and `database.py` must be replaced by dynamic deployment environment variables.
   - Full user management endpoints (`/auth/users`, `/auth/invite`, `/auth/users/{id}/deactivate`, `/auth/users/{id}/role`) must be implemented for the sole owner.
   - Disabling an account must set `is_active=False` and update `tokens_valid_after=utcnow()`, immediately terminating active SSE streams and API tokens.

---

## 3. Caveats

- **No Live Celery/Redis**: The project currently uses SQLite/PostgreSQL with async SQLAlchemy. The `CeleryDispatcher` in the codebase is a dummy mock; Celery and Redis are not installed. The durable DB-backed queue must be implemented cleanly using SQLAlchemy transactions without requiring external broker daemons.
- **Python 3.14 Environment**: The test runner uses Python 3.14.7 on Windows. Subprocess execution, signals, and SQLite busy timeouts must account for Windows OS semantics (`PRAGMA busy_timeout=30000`, WAL mode).
- **Test Authentication**: Existing test files (e.g. `test_platform_core_m1.py`, `test_scan_all_batch_orchestration.py`) fail with 401 Unauthorized because they use an unauthenticated `client` fixture without JWT tokens. `conftest.py` must provide authenticated test client fixtures or pass valid test JWT headers.

---

## 4. Conclusion & Recommended Architecture

The backend architecture requires five core refactoring interventions across database models, dispatcher, scheduler, SSE streaming, and auth/RBAC:

### 4.1 Data Model Extensions (`backend/app/models/`)
1. **Extend `Scan` and `ScanBatch`**:
   - Add queue/lease fields: `worker_id`, `lease_token`, `lease_expires_at`, `heartbeat_at`, `fencing_token`, `attempt_count`, `max_retries`.
   - Add execution details: `cancelled_at`, `cancellation_reason`, `exit_code`, `process_error`, `parse_error`.
   - Add scope metadata: `subtarget_path`, `http_method`, `tenant_id`, `environment`, `policy_revision`.
2. **Add `RunPlan` Model**:
   - Table `run_plans`: `id`, `batch_id`, `accounted_inventory_count`, `execution_target_count`, `engine_execution_count`, `shared_result_count`, `excluded_count`, `plan_matrix_json`.
3. **Add `CheckExecution` Model**:
   - Table `check_executions`: `id`, `scan_id`, `batch_id`, `target_locator`, `engine`, `profile`, `status` (`PLANNED`, `QUEUED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, `CANCELLED`, `UNAVAILABLE`, `SKIPPED`), `attempt_count`, `worker_id`, `started_at`, `completed_at`, `duration_seconds`, `rule_digest`, `engine_version`, `findings_count`, `report_path`, `error_message`.
4. **Add `FindingObservation` Model**:
   - Table `finding_observations`: `id`, `finding_id`, `scan_id`, `check_execution_id`, `observed_at`, `is_reopened`, `raw_evidence`.
   - Stop overwriting `finding.scan_id` so historical reports remain immutable.

### 4.2 Durable DB-Backed Dispatcher & Worker (`backend/app/core/dispatcher.py` & `backend/worker.py`)
1. **Remove Unconditional Startup Cancellation in `backend/main.py`**:
   - Replace with lease-based reaper: only mark jobs failed if `status in ('RUNNING', 'INITIALIZING')` AND `lease_expires_at < utcnow()` AND `attempt_count >= max_retries`.
2. **Dynamic Permissions**:
   - Set `allow_private_targets=scan.allow_private_targets and not settings.is_production and settings.SSRF_ALLOW_PRIVATE_TARGETS`.
   - Set `custom_config={"is_verified": (asset.verification_status == VerificationStatus.VERIFIED.value)}`.
3. **Atomic DB Claim**:
   ```sql
   UPDATE scans 
   SET status = 'RUNNING', worker_id = :worker_id, lease_token = :lease_token, 
       lease_expires_at = :lease_exp, fencing_token = fencing_token + 1, attempt_count = attempt_count + 1
   WHERE id = :scan_id AND status = 'QUEUED'
   ```
4. **Heartbeat & Process Tree Termination**:
   - Background worker coroutine ticks every 5s renewing `lease_expires_at` and `heartbeat_at`.
   - On cancellation: worker verifies `fencing_token`, terminates child process tree via `psutil`, sets `status='CANCELLED'`, `cancelled_at=utcnow()`.

### 4.3 Resumable Database-Backed SSE Streaming (`backend/app/api/scans.py`)
1. **Durable Event Storage**:
   - Extend `ScanLog` with an auto-incrementing integer sequence `seq: Mapped[int]` (or composite `(scan_id, seq)` index).
2. **Resumable Stream Handler**:
   - Accept `Last-Event-ID` header and `cursor: Optional[int] = Query(None)`.
   - On connection: query `ScanLog` where `scan_id == :scan_id AND seq > :cursor ORDER BY seq ASC`.
   - Yield SSE formatted frames:
     ```
     id: <seq>
     event: log
     data: {"id": "...", "seq": 105, "scan_id": "...", "timestamp": "...", "level": "INFO", "message": "...", "source": "..."}
     ```
   - In-loop authorization guard: every 2 seconds, verify `current_user.is_active` in DB. If deactivated or `tokens_valid_after > issued_at`, terminate stream immediately with HTTP 401/403.
3. **Fix Polling Fallback**:
   - In `backend/app/api/scans.py:get_scan_logs`, support cursor-based pagination `after_seq: Optional[int]`.
   - In `frontend/src/lib/api.ts:getScanLogs`, loop or pass cursor so events 101+ are never truncated.

### 4.4 Accurate Metrics Engine (`backend/app/api/metrics.py`)
1. **Default to 7 Calendar Days**:
   - Change `days: int = Query(7, ge=1, le=365)` in `/charts/vulnerability-trend` and `/charts/risk-trend`.
2. **Replace Inferred History with Measured Data**:
   - Calculate metrics from daily completed scans / check executions and durable `finding_observations`.
   - For days without scans, record explicit zero activity rather than projecting today's state backward.
3. **Replace Fabricated Feed Timestamps**:
   - Return actual timestamps recorded from `VulnerabilityIntelligence` or `sync_manager` tables.

### 4.5 Hourly Scheduler Engine (`backend/app/core/scheduler.py`, `backend/app/api/schedules.py`)
1. **Hourly Schedule Setting**:
   - Cron expression: `0 * * * *` (top of every hour).
   - Timezone: Initial `Asia/Ho_Chi_Minh` (ICT, UTC+7), persistent timestamps stored in UTC.
2. **Overrun Coalescing (Max 1 Follow-up)**:
   - When top-of-hour fires: check if an existing scheduled batch for the scope is `RUNNING` or `QUEUED`.
   - If running: increment `missed_slots_count += 1` and mark `has_pending_followup = True`.
   - When running batch terminates: if `has_pending_followup` is True, launch exactly one coalesced batch and reset `has_pending_followup = False`.
3. **Manual Batch Deduplication**:
   - In `POST /api/v1/scans/batch`, if an identical batch is currently `RUNNING`, return the active batch object with a status flag indicating active execution.
4. **Scheduler Health API**:
   - Expose `GET /api/v1/schedules/health`:
     ```json
     {
       "server_time_utc": "2026-11-10T08:00:00Z",
       "next_due_instant": "2026-11-10T09:00:00Z",
       "last_scheduled_run": "2026-11-10T08:00:00Z",
       "last_completed_run": "2026-11-10T07:42:15Z",
       "scheduler_health": "HEALTHY",
       "missed_slots_count": 0,
       "active_batch_id": null
     }
     ```

### 4.6 Sole Owner RBAC & Privileged Enforcement (`backend/app/api/auth.py`, `deps.py`)
1. **Bootstrap Enforcement**:
   - Restrict `POST /api/v1/auth/bootstrap` to email `dangnhutnguyen0910@gmail.com`.
   - Credentials injected via deployment environment variables (`SENTINEL_OWNER_PASSWORD`). Zero hardcoded literals in code.
2. **Owner-Only Endpoints**:
   - `POST /api/v1/auth/users`: Create/invite user (Owner only).
   - `PATCH /api/v1/auth/users/{id}/status`: Activate/deactivate user (Owner only).
   - `PATCH /api/v1/auth/users/{id}/role`: Grant/revoke roles (Owner only).
   - `POST /api/v1/scans/batch`: Estate-wide Ultra Scan restricted to Owner.
3. **Scoped Developer Enforcement**:
   - Scoped developers have an asset assignment table `user_asset_assignments`.
   - Enforce in `deps.py` and API endpoints: queries filter by `Asset.id.in_(allowed_assets)`.
4. **Immediate Stream Revocation**:
   - Deactivating a user immediately sets `tokens_valid_after = utcnow()`.
   - SSE streams re-verify user status on every event tick and abort immediately upon deactivation.

---

## 5. Verification Method

To independently verify these findings and subsequent fixes:

1. **Test Suite Verification Commands**:
   ```bash
   # Run existing tests with auth header fixture:
   pytest tests/test_scan_all_batch_orchestration.py -v
   pytest tests/test_empire_e2e_opaque_box.py -v

   # Check scanner adapter imports and CLI fallbacks:
   pytest -k "test_nuclei or test_zap or test_trivy" -v
   ```

2. **Files to Inspect**:
   - `backend/main.py` lines 41–52 (Verify unconditional cancellation is replaced by lease reaper).
   - `backend/app/core/dispatcher.py` lines 633, 704–705 (Verify removal of hardcoded `True` constants).
   - `backend/app/api/scans.py` lines 500–530 (Verify `Last-Event-ID` header, `id:` SSE frames, and sequence numbers for events 101+).
   - `backend/app/api/metrics.py` lines 142, 233 (Verify default is 7 calendar days with measured data).
   - `backend/app/models/scan.py` (Verify lease, fencing, worker, retry fields added).
   - `backend/app/core/scheduler.py` (Verify hourly `0 * * * *` in Asia/Ho_Chi_Minh and overrun coalescing).
   - `backend/app/api/auth.py` (Verify sole owner bootstrap for `dangnhutnguyen0910@gmail.com` and zero hardcoded secrets).

3. **Invalidation Conditions**:
   - Any implementation leaving `ScanStatus.CANCELLED` unconditional update on ASGI startup is invalid.
   - Any implementation truncating or losing log events beyond 100 on SSE disconnect or polling fallback is invalid.
   - Any implementation projecting trend metrics from current finding status without durable historical observations is invalid.
   - Any implementation allowing a non-owner to launch estate-wide scans or invite users is invalid.
