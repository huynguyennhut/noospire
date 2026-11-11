## 2026-11-09T00:56:19Z
You are teamwork_worker for Milestone M8: "Scan All" Batch Scan Orchestration & Device Resource Optimization.
Working directory: C:\Users\nguye\desktop\noospire
State folder: C:\Users\nguye\desktop\noospire\.agents\teamwork\worker_m8_1\
Original request file: C:\Users\nguye\desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md
Scope document: C:\Users\nguye\desktop\noospire\.agents\teamwork\orchestrator_4\SCOPE.md
Explorer findings files:
- C:\Users\nguye\desktop\noospire\.agents\teamwork\explorer_survey_1\handoff.md
- C:\Users\nguye\desktop\noospire\.agents\teamwork\explorer_survey_3\handoff.md

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership
You exclusively own and may edit the following files:
- `backend/app/models/scan.py`
- `backend/app/schemas/scan.py`
- `backend/app/core/database.py`
- `backend/app/core/dispatcher.py`
- `backend/app/api/scans.py`
- `tests/test_scan_all_batch_orchestration.py`

Do NOT edit frontend files or unrelated backend files.

## Technical Requirements for M8
1. **Domain Model & SQLite WAL Mode**:
   - In `backend/app/models/scan.py`: Define `ScanBatch` model (`scan_batches` table) with fields `id` (UUID), `name`, `status` (String, default QUEUED), `total_scans` (int), `completed_scans` (int, default 0), `failed_scans` (int, default 0), `cancelled_scans` (int, default 0), `progress_percentage` (int, default 0), `target_count` (int), `engines` (JSON/Text), `profiles` (JSON/Text), `created_at`, `started_at`, `completed_at`, `metadata_json`.
   - Add `batch_id` column to `Scan` table (UUID, ForeignKey("scan_batches.id", ondelete="SET NULL"), nullable=True, index=True).
   - In `backend/app/schemas/scan.py`: Add `ScanBatchCreate`, `ScanBatchRead`, `BatchScanResponse`, `TrackCurrentResponse`, `ActiveThreadInfo`, `SystemResourcesInfo`.
   - In `backend/app/core/database.py`: Configure SQLite with WAL mode (`PRAGMA journal_mode=WAL;`), `PRAGMA busy_timeout=30000;`, and in `init_db()` ensure auto-migration (e.g. check if `batch_id` column exists on `scans` table and add if missing: `ALTER TABLE scans ADD COLUMN batch_id CHAR(36) REFERENCES scan_batches(id)`).
2. **Resource Optimization & Concurrency Throttling in Dispatcher**:
   - In `backend/app/core/dispatcher.py`:
     - Implement dynamic host resource check `check_system_resources()` using `psutil.cpu_percent(interval=None)` and `psutil.virtual_memory()`.
     - When CPU > 85.0% or RAM > 88.0%, worker delays dequeuing next scan by cooperative backoff (e.g. 1.0–2.0s) and logs a throttling warning.
     - Bound max concurrency dynamically: `min(settings.MAX_CONCURRENT_SCANS, max(2, os.cpu_count() or 4))`.
     - Maintain per-asset locks (`self.asset_locks[asset.id]`) to prevent target flooding.
     - Maintain `self._active_threads: Dict[uuid.UUID, Dict[str, Any]]` in `AsyncWorkerDispatcher` recording thread_id, scan_id, target_locator, profile, engine, stage, progress_percentage, started_at, elapsed_seconds, last_log.
     - Cooperative batch cancellation: cancel running scans via `CancellationToken` and `process_safety.terminate_process_tree(scan_id)`, and cancel queued scans immediately.
     - Emit `SecurityAlert` (`category="SCAN"`) when scans complete, fail, or complete with warnings.
3. **REST Endpoints in `backend/app/api/scans.py`**:
   - `POST /api/v1/scans/batch` (with route alias `POST /api/v1/scans/scan-all`): Dispatches scans across all registered targets (or selected targets), across specified profiles (default all or selected), and engines. Returns `BatchScanResponse`.
   - `GET /api/v1/scans/batches`: Returns list of batches.
   - `GET /api/v1/scans/batch/{batch_id}`: Returns batch detail with constituent scan status breakdown and aggregate progress %.
   - `POST /api/v1/scans/batch/{batch_id}/cancel`: Cooperatively halts running and queued scans in the batch.
   - `POST /api/v1/scans/stop-all`: Platform-wide emergency stop.
   - `GET /api/v1/scans/trackcurrent`: Returns live active threads, active worker count, queue count, and host CPU/RAM resources.
4. **Automated Tests**:
   - In `tests/test_scan_all_batch_orchestration.py`, implement test cases matching Explorer 3's BAT-01 through BAT-13 (batch dispatch across all targets/engines/profiles, concurrency throttling strict cap, per-asset locks mutual exclusion, cooperative batch cancellation, active threads telemetry endpoint, scan lifecycle notifications, and backward compatibility for single scan API).

## Verification Requirements
You MUST run the tests yourself using `run_command`:
1. Run `pytest tests/test_scan_all_batch_orchestration.py -v` (all new batch tests must pass).
2. Run `pytest tests/ -q` (all existing 182 tests + new tests must pass).
3. Run `python scripts/verify_empire_e2e.py` (all 10 checks must pass).


## 2026-11-09T01:12:32Z
**Context**: Milestone M8 Implementation
**Content**: Pytest task-78 on `tests/test_scan_all_batch_orchestration.py` has been running for over 7 minutes and is currently stalled at `test_concurrency_throttling_strict_cap`. Notice that in `AsyncWorkerDispatcher._worker_loop`, if `check_system_resources()["is_throttled"]` is true (e.g. host RAM > 88%), the loop sleeps without calling `queue.get()`, causing `await dispatcher.queue.join()` to hang indefinitely. Also, `dispatcher.cancellation_tokens[sid] = AsyncMock()` causes `cancel_token.is_cancelled` to be truthy. Check task-78 and fix these issues so the test suite finishes promptly.
**Action**: Check task-78 status, kill/cancel it if hung, fix the throttling check in tests / dispatcher, and finish the verification.
