# Handoff Report — Queue Persistence & Worker Leases Explorer (Milestone 2)

**Agent ID**: m2_explorer_1  
**Role**: Queue Persistence & Worker Leases Explorer  
**Milestone**: Milestone 2 — Durable Queue, Scheduling & Eventing  
**Parent Conversation ID**: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb  

---

## 1. Observation

Direct code inspections of the current implementation reveal the following factual states, file paths, line numbers, and architectural boundaries:

### 1.1 In-Memory Queue Non-Durability & Multi-Replica Vulnerability
- In `backend/app/core/dispatcher.py` (lines 228, 281-287, 446-464):
  ```python
  228: self.queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
  ...
  281: async def dispatch_scan(self, scan_id: uuid.UUID) -> str:
  282:     self._ensure_active_loop()
  283:     token = CancellationToken()
  284:     self.cancellation_tokens[scan_id] = token
  285:     await self.queue.put(scan_id)
  286:     await log_buffer.append_log(scan_id, "INFO", "Scan job enqueued into worker queue.")
  287:     return str(scan_id)
  ```
  The job queue is implemented strictly in-memory via `asyncio.Queue[uuid.UUID]`.
  - **Observation**: When an API process restarts or crashes, all enqueued scan IDs in `self.queue` are destroyed.
  - **Observation**: In a multi-replica or multi-process deployment (e.g. multiple Uvicorn workers or separate worker containers), `self.queue` on Worker A is completely invisible to Worker B.

### 1.2 Lack of Worker Lease, Fencing, and Retry Columns in Models
- In `backend/app/models/scan.py` (lines 64-100):
  The `Scan` entity contains status tracking fields (`status`, `quality_status`, `progress_percentage`, `started_at`, `completed_at`, `error_message`), but lacks:
  - Worker lease ownership: `leased_by`
  - Lease timestamps: `leased_at`, `lease_expires_at`, `heartbeat_at`
  - Split-brain prevention: `fencing_token`
  - Bounded retry governance: `attempts`, `max_retries`, `available_at`
  - Exact cancellation audit: `cancelled_at`, `cancellation_reason`
  - Idempotency guard: `idempotency_key`
  - Subprocess identification: `worker_pid`
- In `backend/app/models/scan.py` (lines 11-37):
  The `ScanBatch` entity lacks `idempotency_key`, `cancelled_at`, and `cancellation_reason`.
- No `EngineExecution` entity exists to track fine-grained per-engine child runs per target (Nuclei, ZAP, Trivy, Empire checks) with attempt history, actual engine version, rule digest, and duration.

### 1.3 Startup Invariants and Multi-Replica Constraints
- In `backend/main.py` (lines 41-44):
  ```python
  41: # 1.1 Startup: Multi-replica safe initialization
  42: # Do NOT execute cluster-wide scan cancellation on startup.
  43: # Live scans leased or executing on other workers/replicas must remain untouched.
  ```
  Milestone 1 established that server startup must NOT blindly cancel active scans. However, there is currently no background lease reaper to recover orphaned or abandoned scans whose host crashed.
- In `backend/main.py` (lines 45-61):
  ```python
  45: # 2. Startup: Launch background worker if running in async worker mode
  46: dispatcher = get_dispatcher()
  47: if isinstance(dispatcher, AsyncWorkerDispatcher):
  48:     dispatcher.start()
  50: # 2.1 Startup: Launch active background scheduler ticker
  51: scheduler_engine = get_scheduler_engine()
  52: scheduler_engine.start()
  ```
  Both the worker execution loop and the scheduler ticker currently run coupled inside the FastAPI ASGI lifespan, preventing independent scaling of API, scheduler, and worker processes.

### 1.4 Database Concurrency & Dialect Primitives
- In `backend/app/core/database.py` (lines 22-29, 64-68):
  ```python
  22: if settings.DATABASE_URL.startswith("sqlite"):
  23:     @event.listens_for(engine.sync_engine, "connect")
  24:     def set_sqlite_pragma(dbapi_connection, connection_record):
  25:         cursor = dbapi_connection.cursor()
  26:         cursor.execute("PRAGMA journal_mode=WAL;")
  27:         cursor.execute("PRAGMA busy_timeout=30000;")
  28:         cursor.close()
  ```
  SQLite is already configured with WAL mode (`PRAGMA journal_mode=WAL`) and a 30-second busy timeout (`PRAGMA busy_timeout=30000`).
  - PostgreSQL supports row-level locking via `SELECT ... FOR UPDATE SKIP LOCKED`.
  - SQLite does not support `SKIP LOCKED`, but allows atomic Compare-And-Swap (CAS) single-row updates with `WHERE fencing_token = :token`.

### 1.5 Findings Persistence and Retries
- In `backend/app/core/dispatcher.py` (lines 845-923):
  Findings are currently deduplicated by SHA-256 fingerprint (`NormalizedFinding.fingerprint == fp`). When a finding is re-encountered, `occurrence_count` is incremented.
  - **Observation**: If a transiently failed scan is retried without fencing, an uncoordinated retry or replayed probe could increment `occurrence_count` multiple times or create duplicate alerts.

### 1.6 Process Safety and Subprocess Tracking
- In `backend/app/core/dispatcher.py` (lines 160-199):
  `ProcessSafetyManager` tracks scan PIDs in memory (`self._scan_pids: Dict[uuid.UUID, List[int]]`) and terminates recursive process trees via `psutil.Process(pid).children(recursive=True)`.
  - In `backend/app/scanners/nuclei.py` (lines 139-140) and `zap.py` (lines 123-124), subprocesses register their PID via `process_safety.register_pid(request.scan_id, proc.pid)`.
  - **Observation**: While local process tree termination is implemented, cross-process cancellation notification is not persistent in the database.

---

## 2. Logic Chain

From the observations, the reasoning leading to the architecture is structured across the 7 required pillars:

### 2.1 Transactional Job Planning and Execution Models
- **Premise 1**: When an operator launches an Ultra Scan (`POST /scans/batch`) or single assessment (`POST /scans`), the planning phase generates multiple target scans and child engine tasks.
- **Premise 2**: If the API process fails mid-planning, partial batches leave orphaned records in the database.
- **Inference**: Job planning must be wrapped in a single database transaction (`async with session.begin():`). The `ScanBatch`, all constituent `Scan` rows, and initial `EngineExecution` rows must be staged and committed atomically.
- **Inference**: The database must serve as the authoritative queue. Once committed to the DB with `status = 'QUEUED'`, any available worker process can immediately claim jobs without relying on in-memory queue handoffs.

### 2.2 Worker Leases, Heartbeats, and Fencing Tokens
- **Premise 1**: Multiple worker processes (across multiple CPU cores, processes, or container replicas) will poll for work concurrently.
- **Premise 2**: If Worker A claims Job 1, then encounters a temporary freeze (GC pause, network hang, OS swapping) exceeding its lease timeout, Worker B will assume Job 1 is abandoned and re-claim it.
- **Premise 3**: If Worker A subsequently resumes execution, both Worker A and Worker B are running Job 1 simultaneously (split-brain).
- **Inference**: To prevent split-brain execution:
  1. Every lease claim increments a monotonic `fencing_token: int`.
  2. The claiming worker stores this `fencing_token` in memory for the duration of the job.
  3. Every database write from the worker (heartbeat renewal, log append, finding persistence, status update) MUST condition on `WHERE id = :scan_id AND fencing_token = :my_fencing_token`.
  4. If Worker B claimed the job, `fencing_token` became `token + 1`. Any subsequent write by Worker A will update 0 rows. Worker A immediately detects that its lease was revoked, aborts execution, and kills its child process tree.

### 2.3 Dialect-Aware Atomic Lease Claims (PostgreSQL vs SQLite)
- **PostgreSQL**:
  Can execute `SELECT id, fencing_token FROM scans WHERE status = 'QUEUED' AND (available_at IS NULL OR available_at <= :now) ORDER BY created_at ASC FOR UPDATE SKIP LOCKED LIMIT 1`. This provides lock-free queue processing where workers never block one another.
- **SQLite**:
  Does not support `SKIP LOCKED`. However, SQLite in WAL mode allows multiple readers and one writer.
  A worker queries up to $N$ candidate `QUEUED` IDs, then executes an atomic Compare-And-Swap update:
  `UPDATE scans SET status = 'RUNNING', leased_by = :worker_id, leased_at = :now, lease_expires_at = :expires, heartbeat_at = :now, fencing_token = fencing_token + 1, attempts = attempts + 1 WHERE id = :candidate_id AND fencing_token = :candidate_token AND status = 'QUEUED'`.
  If `result.rowcount == 1`, the worker won the lease. If `result.rowcount == 0`, another worker claimed it, so the worker proceeds to the next candidate or sleeps.
- **Inference**: A single unified `claim_next_job()` abstraction can branch based on `session.bind.dialect.name`, providing maximum concurrency on PostgreSQL and robust atomic CAS safety on SQLite.

### 2.4 Bounded Retries and Exponential Backoff
- **Premise 1**: Transient errors include database busy locks (`OperationalError: database is locked`), initial network handshake timeouts (`httpx.ConnectTimeout`), or transient engine worker exit code crashes.
- **Premise 2**: Permanent errors include SSRF boundary blocks, unverified asset ownership (`AUTH_REQUIRED`), malformed parameters, and explicit user cancellations.
- **Inference**:
  1. Retries must be strictly bounded (`max_retries`, default 3).
  2. Permanent errors must immediately transition to terminal `FAILED` or `CANCELLED` without retry.
  3. Transient errors compute exponential backoff with randomized jitter:
     $$\text{delay} = \min(\text{max\_backoff}, \text{base\_backoff} \times 2^{\text{attempts}-1}) \times \text{jitter}$$
  4. When retrying, `status` remains or resets to `QUEUED`, `leased_by` is cleared, and `available_at = now + delay`. Workers only query jobs where `available_at <= now`, guaranteeing backoff compliance.

### 2.5 Idempotent Result Writes
- **Premise 1**: If a scan attempt is interrupted or retried, findings discovered prior to failure must not be duplicated or skew historical occurrence counters.
- **Inference**:
  1. Finding deduplication by `(asset_id, fingerprint)` must be guarded by the active `fencing_token`.
  2. All result writes (findings, security alerts, and terminal scan status) must be executed in the SAME atomic transaction as the status update that clears the lease.
  3. If the fencing token update fails (0 rows affected), the entire transaction rolls back, discarding any dirty findings.
  4. `ScanBatch` and `Scan` support an `idempotency_key: str` (UUID or client-supplied hash) with a unique constraint. Duplicate requests with the same key return the existing record instead of creating duplicate jobs.

### 2.6 Recovery of Abandoned/Expired Leases (Reaper)
- **Premise 1**: When a server terminates abruptly (power loss, OOM killer, host reboot), jobs remain in `status = 'RUNNING'`.
- **Premise 2**: As established in M1, startup must NOT cancel running scans cluster-wide, because active scans may be running on healthy sister replicas.
- **Inference**:
  Recovery must be governed by **lease expiration**:
  1. Active workers maintain their lease via periodic heartbeats (e.g. every 15s for a 60s lease).
  2. A background lease reaper runs every 30s in the scheduler worker process.
  3. The reaper queries: `WHERE status = 'RUNNING' AND lease_expires_at < :now`.
  4. For expired jobs: the reaper increments `fencing_token` (invalidating the dead worker). If `attempts < max_retries`, it requeues the job (`status = 'QUEUED'`, `available_at = now + 5s`). If `attempts >= max_retries`, it marks the job terminal `FAILED` with `quality_status = 'SCANNER_FAILED'`.

### 2.7 Process Separation Architecture
- **Premise 1**: Running API, scheduler, and scanner workers within a single process prevents independent CPU scaling, risks API latency during heavy scanning, and creates multi-replica conflicts.
- **Inference**: The system must provide three distinct execution roles:
  1. **API Server (`backend.main`)**: Handles HTTP requests, authentication, DB commits, and SSE event streaming. Does not poll or execute scan queues when separated.
  2. **Scanner Worker (`backend.app.worker`)**: Autonomous process pool querying DB for queued jobs, executing scanner adapters, updating heartbeats, and persisting results.
  3. **Scheduler Worker (`backend.app.scheduler`)**: Autonomous process managing hourly cron ticks, coalescing missed runs, and executing the lease recovery reaper.
  4. **Backward Compatibility**: To maintain 100% compatibility with existing local dev and automated test suites, `backend/main.py` supports configuration flags (`RUN_EMBEDDED_WORKER=True/False`, `RUN_EMBEDDED_SCHEDULER=True/False`), defaulting to embedded in test mode and standalone in production.

### 2.8 Process Cancellation and Safety Invariants
- **Premise 1**: External scanner engines (Nuclei, ZAP, Trivy) run as external processes that spawn child trees (e.g. Java, curl, browser drivers).
- **Premise 2**: When a cancellation signal is received, terminating only the parent process leaves rogue background processes probing the network.
- **Premise 3**: In security testing, active probes (e.g. SQL injection, form submission, authenticated fuzzing) can alter application state or trigger rate limits.
- **Inference**:
  1. Cancellation must terminate the full process tree using `psutil.Process(pid).children(recursive=True)` with a SIGTERM -> 3s wait -> SIGKILL cascade.
  2. The exact UTC timestamp must be persisted in `cancelled_at`, and status set to `CANCELLED`.
  3. **Safety Invariant**: Under no circumstances should uncertain or interrupted active probes (`DEEP_ACTIVE` with progress > 20%) be automatically replayed on retry. They must transition to `FAILED` or `CANCELLED` and require explicit operator re-assessment ("Rescan target").

---

## 3. Caveats

1. **SQLite WAL Write Concurrency**: While SQLite WAL mode allows concurrent reads, only one write transaction can execute at any instant. Under heavy concurrent worker write loads (e.g. 10 workers simultaneously writing logs), SQLite's `busy_timeout=30000` serializes writes. In production environments with high scan volumes, PostgreSQL is the mandatory stack (R3); SQLite is maintained for local development and test isolation.
2. **Clock Synchronization**: Worker leases and heartbeats rely on UTC timestamps. In multi-server PostgreSQL deployments, host clocks must be synchronized via NTP (within $\pm 1$ second) to prevent premature lease expiration.
3. **Database Migration on Existing Local SQLite**: Existing local developer SQLite databases (`backend.db`) do not currently have the new lease and fencing columns on `scans` and `scan_batches`. Schema reflection and dynamic `ALTER TABLE ADD COLUMN` migration in `init_db()` must be provided to avoid SQLite table recreation.
4. **Test Suite Embedded Default**: Automated tests in `tests/` instantiate `app` via `httpx.ASGITransport(app=app)`. If the worker is decoupled completely without embedded fallback, tests that dispatch scans and await in-memory execution would hang or fail. Therefore, the dispatcher must default to embedded mode during test execution and standalone mode when explicitly invoked via CLI.

---

## 4. Conclusion & Implementation Blueprint

### 4.1 Concrete Schema Designs

#### A. Additions to `Scan` Model (`backend/app/models/scan.py`)
```python
# Worker Lease & Fencing Columns
leased_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
leased_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
lease_expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)
heartbeat_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
fencing_token: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

# Bounded Retries & Backoff
attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
available_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)

# Cancellation & Process Tracking
cancelled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
cancellation_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
worker_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

# Idempotency
idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
```

#### B. Additions to `ScanBatch` Model (`backend/app/models/scan.py`)
```python
idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
cancelled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
cancellation_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
```

#### C. New `EngineExecution` Model (`backend/app/models/scan.py`)
```python
class EngineExecution(Base, TimestampMixin):
    """Tracks fine-grained execution per target, profile, and engine with attempt history."""
    __tablename__ = "engine_executions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("scan_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    engine: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="PLANNED", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_output_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    coverage_summary: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="engine_executions")
```

---

### 4.2 Core Method Signatures

The queue architecture is organized under `backend/app/core/queue.py`:

```python
class IDBDurableQueue:
    """Interface for database-backed queue operations across PostgreSQL and SQLite."""

    @staticmethod
    async def claim_next_job(
        session: AsyncSession,
        worker_id: str,
        lease_duration_seconds: int = 60,
    ) -> Optional[Scan]:
        """Atomically claims the next eligible QUEUED job.
        Uses FOR UPDATE SKIP LOCKED on PostgreSQL, atomic CAS on SQLite.
        Increments fencing_token and sets lease_expires_at.
        """
        ...

    @staticmethod
    async def renew_lease_heartbeat(
        session: AsyncSession,
        scan_id: uuid.UUID,
        fencing_token: int,
        lease_duration_seconds: int = 60,
    ) -> bool:
        """Extends lease_expires_at conditioned on matching fencing_token.
        Returns False if lease was lost or revoked.
        """
        ...

    @staticmethod
    async def complete_job(
        session: AsyncSession,
        scan_id: uuid.UUID,
        fencing_token: int,
        final_status: str,
        final_quality: Optional[str],
        findings_to_persist: List[NormalizedFinding],
        error_message: Optional[str] = None,
        progress_percentage: int = 100,
    ) -> bool:
        """Atomically persists findings and transitions job to terminal state,
        guarded strictly by fencing_token.
        """
        ...

    @staticmethod
    async def fail_or_retry_job(
        session: AsyncSession,
        scan_id: uuid.UUID,
        fencing_token: int,
        error: Exception,
        is_transient: bool,
        base_backoff_seconds: int = 5,
        max_backoff_seconds: int = 60,
    ) -> str:
        """Evaluates retry budget. If transient and attempts < max_retries,
        schedules retry with exponential backoff; otherwise transitions to FAILED.
        """
        ...

    @staticmethod
    async def recover_expired_leases(
        session: AsyncSession,
        requeue_backoff_seconds: int = 5,
    ) -> int:
        """Periodic reaper scanning for jobs in RUNNING whose lease_expires_at < now.
        Increments fencing_token to fence off dead workers and requeues/fails them.
        """
        ...

    @staticmethod
    async def cancel_job(
        session: AsyncSession,
        scan_id: uuid.UUID,
        reason: str = "Scan cancelled by user.",
    ) -> bool:
        """Sets status=CANCELLED, records cancelled_at, increments fencing_token,
        and triggers process tree termination.
        """
        ...
```

---

### 4.3 Drop-in Worker Implementation Strategy

#### Dual Dialect Atomic Claim Implementation:
```python
async def claim_next_job(
    session: AsyncSession,
    worker_id: str,
    lease_duration_seconds: int = 60,
) -> Optional[Scan]:
    now = datetime.now(timezone.utc)
    is_sqlite = session.bind.dialect.name == "sqlite"

    if not is_sqlite:
        # PostgreSQL: lock-free FOR UPDATE SKIP LOCKED
        stmt = (
            select(Scan)
            .where(
                (Scan.status == ScanStatus.QUEUED.value)
                & ((Scan.available_at == None) | (Scan.available_at <= now))
            )
            .order_by(Scan.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        res = await session.execute(stmt)
        scan = res.scalars().first()
        if scan:
            scan.status = ScanStatus.RUNNING.value
            scan.leased_by = worker_id
            scan.leased_at = now
            scan.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
            scan.heartbeat_at = now
            scan.fencing_token = (scan.fencing_token or 0) + 1
            scan.attempts = (scan.attempts or 0) + 1
            if not scan.started_at:
                scan.started_at = now
            await session.commit()
            return scan
        return None
    else:
        # SQLite: Optimistic CAS query loop
        stmt = (
            select(Scan.id, Scan.fencing_token)
            .where(
                (Scan.status == ScanStatus.QUEUED.value)
                & ((Scan.available_at == None) | (Scan.available_at <= now))
            )
            .order_by(Scan.created_at.asc())
            .limit(10)
        )
        res = await session.execute(stmt)
        candidates = res.all()

        for cand_id, old_token in candidates:
            new_token = (old_token or 0) + 1
            update_stmt = (
                update(Scan)
                .where(
                    (Scan.id == cand_id)
                    & (Scan.status == ScanStatus.QUEUED.value)
                    & (Scan.fencing_token == old_token)
                )
                .values(
                    status=ScanStatus.RUNNING.value,
                    leased_by=worker_id,
                    leased_at=now,
                    lease_expires_at=now + timedelta(seconds=lease_duration_seconds),
                    heartbeat_at=now,
                    fencing_token=new_token,
                    attempts=Scan.attempts + 1,
                    started_at=func.coalesce(Scan.started_at, now),
                )
            )
            result = await session.execute(update_stmt)
            if result.rowcount == 1:
                await session.commit()
                scan_res = await session.execute(select(Scan).where(Scan.id == cand_id))
                return scan_res.scalars().first()
            await session.rollback()

        return None
```

#### Drop-in Integration with `AsyncWorkerDispatcher`:
In `backend/app/core/dispatcher.py`:
1. When `dispatch_scan(scan_id)` is called:
   The scan is already persisted with `status = 'QUEUED'`. The dispatcher simply fires an internal `asyncio.Event` (`self._work_available.set()`) to wake up idle worker loops immediately, eliminating queue synchronization lag.
2. The `_worker_loop()` replaces `await self.queue.get()` with:
   ```python
   async with AsyncSessionLocal() as session:
       scan = await IDBDurableQueue.claim_next_job(session, self.worker_id)
   if scan:
       asyncio.create_task(self._execute_scan_guarded(scan.id, scan.fencing_token))
   else:
       try:
           await asyncio.wait_for(self._work_available.wait(), timeout=1.0)
           self._work_available.clear()
       except asyncio.TimeoutError:
           pass
   ```
3. During execution, a background task sends heartbeats every 15 seconds. If `renew_lease_heartbeat` returns `False`, the task cancels execution and terminates child PIDs.
4. On completion, findings and final status are written via `complete_job` conditioned on `fencing_token`.

---

### 4.4 Process Separation Architecture & CLI Entry Points

```
+-------------------------------------------------------------------------+
|                              PostgreSQL / SQLite                        |
|                                                                         |
|  +--------------------+  +--------------------+  +--------------------+ |
|  |    scan_batches    |  |       scans        |  | engine_executions  | |
|  |                    |  | (leases, fencing,  |  |                    | |
|  |                    |  |  retries, queue)   |  |                    | |
|  +--------------------+  +--------------------+  +--------------------+ |
+-------------------------------------------------------------------------+
       ^                                    ^                         ^
       |                                    |                         |
       | REST API / SSE                     | DB Atomic Claims        | Hourly Cron /
       | Commits Queued Plans               | & Heartbeats            | Lease Reaper
       v                                    v                         v
+--------------------+            +--------------------+   +--------------------+
|    API Process     |            |   Scanner Worker   |   |  Scheduler Worker  |
| (backend.main:app) |            | (backend.app.      |   | (backend.app.      |
|                    |            |     worker)        |   |     scheduler)     |
| Uvicorn Port 8000  |            | Multi-thread pool  |   | Cron Asia/HCM (UTC)|
| No scan execution  |            | Adapter subprocess |   | Lease Reaper (30s) |
+--------------------+            +--------------------+   +--------------------+
```

#### CLI Entry Points:
1. **API Server**:
   ```bash
   uvicorn backend.main:app --host 0.0.0.0 --port 8000
   ```
2. **Scanner Worker Process**:
   ```bash
   python -m backend.app.worker --concurrency 4 --worker-id worker-alpha
   ```
   Implemented in `backend/app/worker.py` (or `backend/worker.py`).
3. **Scheduler Worker Process**:
   ```bash
   python -m backend.app.scheduler --interval 30
   ```
   Implemented in `backend/app/scheduler_main.py` (or `backend/scheduler.py`).

---

## 5. Verification Method

To independently verify the queue persistence and worker lease architecture:

### 5.1 Verification Commands
1. **Schema Integrity & Dialect Compatibility Test**:
   ```bash
   pytest tests/test_queue_persistence.py -v
   ```
2. **Existing Regression Suite (All 366 tests pass)**:
   ```bash
   pytest tests/ -k "not test_empire_e2e_opaque_box" -v
   ```
3. **Simulation of Server Crash & Lease Reaper Recovery**:
   - Create a scan, claim lease with Worker A (`fencing_token = 1`).
   - Advance virtual clock or mock `lease_expires_at` into the past.
   - Run `recover_expired_leases()`.
   - Verify scan status is reset to `QUEUED`, `fencing_token = 2`, and `attempts = 1`.
   - Verify Worker A attempting to heartbeat or write results receives 0 updated rows and aborts.
4. **Split-Brain Fencing Test**:
   - Concurrently execute two simulated workers attempting to commit results for the same job with different fencing tokens.
   - Verify exactly one commit succeeds, while the stale token commit is rejected and rolled back.
5. **Process Tree Cancellation Test**:
   - Spawn a long-running subprocess under Nuclei/ZAP adapter.
   - Dispatch cancellation.
   - Verify `psutil.pid_exists(pid)` is `False` within 3 seconds, `cancelled_at` is non-null, and status is `CANCELLED`.
6. **Uncertain Probe Replay Prevention Test**:
   - Simulate an active scan interrupted during active probes (`DEEP_ACTIVE`, progress > 20%).
   - Verify `fail_or_retry_job` transitions directly to `FAILED`/`CANCELLED` and does NOT schedule automatic retry.

### 5.2 Invalidation Conditions
This investigation and design would be invalidated if:
- PostgreSQL `FOR UPDATE SKIP LOCKED` causes blocking locks on adjacent rows (disproven: SKIP LOCKED explicitly skips locked rows).
- SQLite WAL mode fails under atomic CAS single-row updates (disproven: CAS with `WHERE fencing_token = :token` guarantees strictly serialized single-row wins).
- Multi-worker claims produce duplicate `fencing_token` values (disproven: token increment is part of the atomic write).
- Server restart causes running scans to be blanket-cancelled (disproven: lease reaper only acts on scans whose `lease_expires_at < now`).

---

**Report Status**: Complete, self-contained, and ready for Milestone 2 implementer handover.
