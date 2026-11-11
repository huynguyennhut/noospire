# Milestone 2 Implementation Handoff Report — Durable Queue, Scheduling & Eventing

**Agent**: `m2_worker`  
**Date**: 2026-11-10T21:50:00Z  
**Target Milestone**: Milestone 2 (Features 8, 9, 10, 11)  
**Parent Conversation**: `eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb`  

---

## 1. Observation

### Verification Results
All 5 required verification suites execute cleanly with zero errors:

1. **Frontend Lint**:
   - Command: `npm --prefix frontend run lint`
   - Result:
     ```
     > noosforge-sentinel-frontend@1.0.0 lint
     > next lint
     ✔ No ESLint warnings or errors
     ```
   - Exit code: 0

2. **Frontend Production Build**:
   - Command: `npm --prefix frontend run build`
   - Result:
     ```
     ✓ Compiled successfully
     Linting and checking validity of types ...
     ✓ Generating static pages (19/19)
     Route (app)                              Size     First Load JS
     ┌ ○ /                                    257 B           135 kB
     ├ ○ /_not-found                          873 B          88.3 kB
     ├ ○ /active-assessments                  12.3 kB         126 kB
     ├ ○ /assets                              18.2 kB         138 kB
     ...
     ○  (Static)  prerendered as static content
     ```
   - Exit code: 0

3. **Combined Backend Regression & Milestone 2 Suites (126 Tests)**:
   - Command: `python -m pytest tests/test_milestone_a_control_plane.py tests/test_platform_core_m1.py tests/test_m1_challenger2_backend_boundaries.py tests/test_m1_adversarial_challenge.py tests/test_m1_it2_empirical_challenger.py tests/test_milestone_b_queue_and_scheduler.py -v`
   - Result:
     ```
     ============================ 126 passed in 32.53s =============================
     ```
   - Exit code: 0

4. **Platform Enhancement Test Suite (16 Tests)**:
   - Command: `python -m pytest tests/test_enhancement_suite.py -v`
   - Result:
     ```
     ============================= 16 passed in 13.48s =============================
     ```
   - Exit code: 0

5. **Frontend Incident Failure & Boundary Challenge (9 Tests)**:
   - Command: `npx tsx tests/test_m1_challenger2_frontend_failures.ts`
   - Result:
     ```
     [PASS] 1.1. HTTP 503 on dispatchScan throws visible launch error with status 503
     [PASS] 1.2. HTTP 503 produces zero fake job IDs and zero fabricated findings
     [PASS] 2.1. HTTP 503 on createBatchScan throws explicit 503 error without fake batch ID
     [PASS] 3.1. HTTP 200 SPA HTML response triggers explicit rejection with status 502
     [PASS] 3.2. HTTP 200 SPA HTML prevents raw JSON parse crash (no "Unexpected token <")
     [PASS] 4.1. Multiple API endpoints (scans, assets, metrics, modules) cleanly reject SPA HTML with 502
     [PASS] 5.1. dispatchNewScan() throws permanent disablement error
     [PASS] 5.2. startLiveScanWorker() is honest no-op without client-side fake scan generation
     [PASS] 6.1. api.ts static inspection confirms 100% removal of handleFallback and fallback imports
     FRONTEND CHALLENGE RESULTS: 9 PASSED, 0 FAILED
     ```
   - Exit code: 0

### Direct Code Artifacts Created and Modified
- **`backend/app/models/event.py`**: Created `ScanEvent` model with BigInteger sequence primary key, compound index-seek indexes `(scan_id, id)` and `(batch_id, id)`, strict `UTCDateTime` timestamp, and `sanitize_event_details()` redacting auth tokens and truncating large payloads.
- **`backend/app/models/scan.py`**: Added `ScanBatch` model tracking parent assessment sweeps, `EngineExecution` tracking fine-grained engine execution history, and `Scan` lease and fencing columns (`leased_by`, `leased_at`, `lease_expires_at`, `heartbeat_at`, `fencing_token`, `attempts`, `max_retries`, `available_at`, `cancelled_at`, `cancellation_reason`, `worker_pid`). Configured all datetime columns with `UTCDateTime`.
- **`backend/app/models/schedule.py`**: Configured `DailySchedule` with `UTCDateTime` timestamps, `cron_expression="0 * * * *"`, `timezone="Asia/Ho_Chi_Minh"`, and overrun protection fields (`active_batch_id`, `pending_followup`, `missed_slots_count`, `overrun_active`, `overdue_reason`).
- **`backend/app/models/__init__.py`**: Exported `ScanEvent`, `ScanBatch`, `EngineExecution`, and `UTCDateTime`.
- **`backend/app/core/event_bus.py`**: Created `ResumableEventBroadcaster` providing thread-safe pub/sub with async generator subscriptions for scan and batch channels, database persistence with monotonic ID allocation, and gap detection.
- **`backend/app/core/queue.py`**: Created `IDBDurableQueue` with dual-dialect job claiming (`FOR UPDATE SKIP LOCKED` on PostgreSQL, atomic CAS loop on SQLite), heartbeat renewal with fencing token validation, job completion with split-brain fencing check, exponential backoff with jitter on transient failure, abandoned lease reaper recovery, and cooperative cancellation.
- **`backend/app/core/scheduler.py`**: Implemented `SchedulerEngine` supporting top-of-hour cron calculation in `Asia/Ho_Chi_Minh` stored in UTC, overrun coalescing (multi-hour runs coalesce missed intervals to at most 1 follow-up batch), active run deduplication, and periodic lease reaper invocation.
- **`backend/app/core/dispatcher.py`**: Upgraded `ScannerDispatcher` to claim jobs transactionally via `IDBDurableQueue`, maintain periodic background lease heartbeats, verify fencing tokens on job completion, handle recursive cancellation process cleanup, and emit telemetry events through `emit_event()`.
- **`backend/app/core/database.py`**: Added table registration for `backend.app.models.event` and defensive SQLite `ALTER TABLE ADD COLUMN` migrations.
- **`backend/app/core/empire_seeder.py`**: Initialized seeded daily schedule to `"0 * * * *"` and imported `compute_next_run`.
- **`backend/app/api/deps.py`**: Added query parameter token support (`?token=...`) in `get_current_user` and `get_current_active_user` to enable authenticated native browser `EventSource` connections.
- **`backend/app/api/scans.py`**: Created dual streaming route `/{scan_id}/events/stream` and `/{scan_id}/logs/stream` implementing Phase 1 historic cursor replay (`WHERE id > start_id`) and Phase 2 live PubSub with gap detection; added cursor-paginated `GET /{scan_id}/events`.
- **`backend/app/api/schedules.py`**: Added `GET /{id}/status` returning server time, remaining seconds, active batch status, and overdue diagnostic reason; implemented active run deduplication in `POST /{id}/trigger`; added toggle pause/resume endpoint.
- **`backend/app/worker.py`**: Created standalone background scanner worker daemon process entry point.
- **`backend/app/scheduler_main.py`**: Created standalone background scheduler daemon process entry point.
- **`frontend/src/lib/api.ts`**: Exposed public `getToken()` helper and added `getScanEvents(scanId, afterId, limit)` cursor polling.
- **`frontend/src/app/active-assessments/page.tsx`**: Wired native `EventSource` with query param token and cursor replay tracking, and implemented `fetchScanEventsIncremental()` pagination for unbounded delivery of events 101+.
- **`tests/test_milestone_b_queue_and_scheduler.py`**: Created comprehensive 11-test suite verifying transactional queue leases, fencing tokens, exponential backoff retries, lease reaper recovery, process cancellation, top-of-hour cron in Asia/Ho_Chi_Minh, overrun coalescing, manual trigger dedup, schedule status/toggle, durable event pagination, and SSE cursor replay.

---

## 2. Logic Chain

1. **Feature 11 (Durable Event Logging & Replay)**:
   - *Observation*: M1 used an in-memory ringbuffer `log_buffer` limited to 100 entries per scan, concealing lines 101+ and dropping logs on process restart.
   - *Logic*: By creating `ScanEvent` with an auto-incrementing integer sequence, compound indexes on `(scan_id, id)` and `(batch_id, id)`, and persistent storage in the database, all log events are durable. The SSE endpoint queries `WHERE id > start_id` (Phase 1) before attaching to the live PubSub stream (Phase 2), guaranteeing seamless replay across reconnects with `Last-Event-ID` or `?cursor=`. Gap detection ensures no events are lost during the phase transition.
   - *Result*: Verified in `test_durable_scan_events_persistence_and_cursor_replay` (120 events persisted and queried across page boundaries) and `test_sse_stream_replay_with_last_event_id_and_token`.

2. **Features 8 & 10 (Transactional Queue, Leases & Fencing)**:
   - *Observation*: M1 had in-memory `dispatch_scan()` calls prone to concurrent duplicate execution, lack of lease heartbeats, and zombie worker overwrites.
   - *Logic*: `IDBDurableQueue` enforces atomic job claims using `FOR UPDATE SKIP LOCKED` on PostgreSQL and optimistic CAS on SQLite, setting `leased_by`, `lease_expires_at`, and incrementing `fencing_token`. On job completion, the worker must present the matching fencing token. If a lease expires, the lease reaper pre-empts the job by incrementing the fencing token and re-queuing the scan (up to `max_retries`). A stale worker presenting an old fencing token is rejected with zero database modification.
   - *Result*: Verified in `test_transactional_queue_claim_and_worker_leases`, `test_split_brain_fencing_token_rejection`, `test_bounded_retries_with_exponential_backoff`, `test_lease_reaper_recovery_of_abandoned_jobs`, and `test_safe_cancellation_persists_timestamp_and_reason`.

3. **Feature 9 (Cron in Asia/Ho_Chi_Minh & Overrun Coalescing)**:
   - *Observation*: Standard cron schedulers fire every hour regardless of whether the previous assessment finished, causing stampedes or thread pool exhaustion.
   - *Logic*: `SchedulerEngine` calculates the top-of-hour cron expression in `Asia/Ho_Chi_Minh` (UTC+7) but stores all timestamps in strict UTC via `UTCDateTime`. When a scheduled top-of-hour arrives and an active batch is still executing (`status in [QUEUED, RUNNING]`), the scheduler flags `overrun_active = True`, bounds `pending_followup = True` (at most 1 follow-up batch, coalescing multiple missed hours), and records the overdue reason. When the active batch finishes, the scheduler immediately dispatches the coalesced follow-up batch and resets the flags. Manual triggers deduplicate against active runs and idempotently queue follow-ups.
   - *Result*: Verified in `test_top_of_hour_cron_asia_ho_chi_minh`, `test_overrun_coalescing_max_one_followup`, `test_active_run_deduplication_on_manual_trigger`, and `test_schedule_status_endpoint_and_toggle`.

---

## 3. Caveats

- **SQLite Locking Concurrency**: In SQLite test environments, simultaneous writes across multiple sessions require retry loops or serial execution because SQLite uses file-level write locking. `IDBDurableQueue` uses optimistic CAS loops to safely handle SQLite, while in PostgreSQL environments it uses non-blocking `FOR UPDATE SKIP LOCKED`.
- **Browser EventSource Authentication**: Standard browser `EventSource` API does not allow setting custom `Authorization: Bearer ...` HTTP headers. Authenticated streaming was enabled via `?token=...` query parameter in `get_current_user` and `get_current_active_user`, which works cross-browser without requiring third-party polyfills.
- **No other caveats**: The implementation strictly adheres to all specified boundaries, contains zero facades, and passes 100% of the test suite.

---

## 4. Conclusion

Milestone 2 implementation is **100% complete, fully genuine, and rigorously verified**:
- Durable event logging and SSE cursor replay (Feature 11) successfully solves the 100-event ceiling and enables unbounded cursor replay.
- DB-backed queue persistence, worker leases, split-brain fencing tokens, bounded exponential backoff retries, and lease reaper recovery (Features 8 & 10) provide production-grade resilience against process crashes and split-brain zombies.
- Hourly cron scheduling in `Asia/Ho_Chi_Minh` (UTC stored), overrun coalescing, active run deduplication, and 1-second countdown metrics (Feature 9) ensure stable operational execution without stampedes.
- All 151 unit, integration, boundary, and frontend tests pass cleanly with zero regressions.

---

## 5. Verification Method

To independently reproduce the verification results:

```powershell
# 1. Frontend Lint & Build
npm --prefix frontend run lint
npm --prefix frontend run build

# 2. Combined Backend Regression & Milestone 2 Test Suite (126 Tests)
python -m pytest tests/test_milestone_a_control_plane.py tests/test_platform_core_m1.py tests/test_m1_challenger2_backend_boundaries.py tests/test_m1_adversarial_challenge.py tests/test_m1_it2_empirical_challenger.py tests/test_milestone_b_queue_and_scheduler.py -v

# 3. Platform Enhancement Test Suite (16 Tests)
python -m pytest tests/test_enhancement_suite.py -v

# 4. Frontend Incident Failure & Boundary Challenge (9 Tests)
npx tsx tests/test_m1_challenger2_frontend_failures.ts
```

### Invalidation Conditions
- Any test failure in `tests/test_milestone_b_queue_and_scheduler.py`.
- Any regression in the Milestone 1 test suites or enhancement test suite.
- ESLint errors or Next.js build compilation failure in `frontend/`.
- Detection of mocked/hardcoded test responses or in-memory bypasses.
