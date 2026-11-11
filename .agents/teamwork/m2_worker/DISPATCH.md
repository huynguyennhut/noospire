# DISPATCH: m2_worker

**Agent ID**: m2_worker
**Role**: Milestone 2 Implementation Worker
**Archetype**: teamwork_worker
**Working Directory**: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_worker
**Parent Conversation ID**: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb
**Milestone**: Milestone 2 — Durable Queue, Scheduling & Eventing

## MANDATORY INTEGRITY WARNING
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Mandatory Reading
1. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md` (specifically R1 active assessments logging & R3 durable queue/scheduling)
2. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\PROJECT.md`
3. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_1\handoff.md` (Queue persistence & worker leases)
4. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_2\handoff.md` (Hourly cron & overrun coalescing)
5. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_3\handoff.md` (SSE stream & events 101+ cursor replay)

## Exclusive File Ownership
You have exclusive write access to:
- `backend/app/models/event.py` (create)
- `backend/app/models/scan.py`
- `backend/app/models/schedule.py`
- `backend/app/models/__init__.py`
- `backend/app/core/event_bus.py` (create)
- `backend/app/core/queue.py` (create)
- `backend/app/core/scheduler.py`
- `backend/app/core/dispatcher.py`
- `backend/app/core/database.py`
- `backend/app/core/empire_seeder.py`
- `backend/app/api/deps.py`
- `backend/app/api/scans.py`
- `backend/app/api/schedules.py`
- `backend/app/worker.py` (create)
- `backend/app/scheduler_main.py` (create)
- `frontend/src/lib/api.ts`
- `frontend/src/app/active-assessments/page.tsx`
- `tests/test_milestone_b_queue_and_scheduler.py` (create)

## Implementation Tasks

### 1. Durable Event Logging & SSE Stream (Feature 11)
- Create `backend/app/models/event.py` defining `ScanEvent` with auto-incrementing BigInteger sequence (`BigInteger().with_variant(Integer, "sqlite")`), compound indexes on `(scan_id, id)` and `(batch_id, id)`, strict UTC `occurred_at`, and `sanitize_event_details`.
- Create `backend/app/core/event_bus.py` with `ResumableEventBroadcaster` and `emit_event`.
- In `backend/app/api/deps.py:get_current_user`, allow authentication via query parameter `request.query_params.get("token")` for native browser EventSource.
- In `backend/app/api/scans.py`, update `stream_scan_logs` and `stream_scan_events` to accept `Last-Event-ID` header and `cursor` query param. Replay committed DB events with `id > start_id` (Phase 1), followed by live stream with gap detection and `: keep-alive\n\n` heartbeats (Phase 2).
- In `backend/app/api/scans.py`, implement `GET /{scan_id}/events` supporting cursor pagination (`after_id`, `limit`).
- In `frontend/src/lib/api.ts`, add `getScanEvents(scanId, afterId, limit)`.
- In `frontend/src/app/active-assessments/page.tsx`, update SSE connection with `?token=...`, track `lastEventIdRef`, and fall back to incremental cursor polling so events 101+ are never dropped or concealed.

### 2. DB-Backed Queue Persistence & Worker Leases (Feature 8 & 10)
- In `backend/app/models/scan.py`, add lease, heartbeat, fencing (`fencing_token`), retry (`attempts`, `max_retries`, `available_at`), and cancellation (`cancelled_at`, `cancellation_reason`, `worker_pid`, `idempotency_key`) columns to `Scan` and `ScanBatch`. Add `EngineExecution` model.
- In `backend/app/core/database.py:init_db`, add defensive SQLite `ALTER TABLE ADD COLUMN` statements for smooth local dev migration.
- Create `backend/app/core/queue.py` with `IDBDurableQueue`:
  - `claim_next_job`: uses PostgreSQL `FOR UPDATE SKIP LOCKED` or SQLite atomic CAS (`WHERE id = :id AND fencing_token = :token`).
  - `renew_lease_heartbeat`: extends lease conditioned on `fencing_token`.
  - `complete_job`: writes results atomically conditioned on `fencing_token`.
  - `fail_or_retry_job`: calculates exponential backoff with jitter for transient errors, bounds retries at `max_retries`, transitions permanent errors directly to `FAILED`.
  - `recover_expired_leases`: periodic reaper finding `status = 'RUNNING'` with `lease_expires_at < now`, increments fencing token, requeues or fails expired jobs.
  - `cancel_job`: sets `status = 'CANCELLED'`, records `cancelled_at`, terminates process tree recursively (SIGTERM -> 3s -> SIGKILL).
- Integrate `IDBDurableQueue` into `backend/app/core/dispatcher.py`.
- Create standalone entry points `backend/app/worker.py` and `backend/app/scheduler_main.py`.

### 3. Hourly Cron & Overrun Coalescing (Feature 9)
- In `backend/app/models/schedule.py`, update `DailySchedule` with `cron_expression="0 * * * *"`, `timezone="Asia/Ho_Chi_Minh"`, strict `UTCDateTime`, `active_batch_id`, `last_completed_at`, `pending_followup`, `missed_slots_count`, `overrun_active`, `overdue_reason`.
- In `backend/app/models/scan.py:ScanBatch`, add `schedule_id`, `is_followup`, `missed_slots_coalesced`.
- In `backend/app/core/empire_seeder.py`, set default schedule to `"0 * * * *"`.
- In `backend/app/core/scheduler.py`:
  - Wrap scheduled launches in `ScanBatch`.
  - Implement Overrun Coalescing: if run > 1 hour, keep active run intact, set `overrun_active = True`, coalesce missed slots into at most ONE follow-up (`pending_followup = True`, `missed_slots_count`), auto-trigger follow-up immediately upon batch completion.
  - Implement periodic lease reaper call in scheduler loop.
- In `backend/app/api/schedules.py`:
  - Add `GET /{id}/status`: returns server time, countdown metrics, active batch status, and overdue diagnostic reason.
  - Update `POST /{id}/trigger`: deduplicates against running batch, offers single follow-up queuing, reuses repeated requests idempotently.
  - Add `PUT /{id}/toggle`: pauses/resumes schedule and recalculates next due instant.

### 4. Verification Suite
- Create `tests/test_milestone_b_queue_and_scheduler.py` covering:
  1. Transactional queue claims, worker leases, and split-brain fencing token rejection.
  2. Bounded retries with backoff and lease reaper recovery of abandoned jobs after restart.
  3. Safe recursive process tree cancellation and uncertain probe replay prevention.
  4. Hourly cron calculation in `Asia/Ho_Chi_Minh` (stored in UTC).
  5. Overrun coalescing: multi-hour runs coalesce missed slots to at most ONE follow-up.
  6. Active run deduplication and idempotency on manual trigger.
  7. Schedule status endpoint: server time, 1s countdown data, pause/resume, overdue reason.
  8. Durable event stream: `ScanEvent` persistence, SSE replay from `Last-Event-ID` cursor, and events 101+ delivery without concealment.
- Run complete test regression:
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`
  - `python -m pytest tests/test_milestone_a_control_plane.py tests/test_platform_core_m1.py tests/test_m1_challenger2_backend_boundaries.py tests/test_m1_adversarial_challenge.py tests/test_m1_it2_empirical_challenger.py tests/test_milestone_b_queue_and_scheduler.py -v`
  - `python -m pytest tests/test_enhancement_suite.py -v`
  - `npx tsx tests/test_m1_challenger2_frontend_failures.ts`

Deliver full 5-component handoff report to `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_worker\handoff.md`.

## 2026-11-10T21:04:26Z
You are m2_worker, Milestone 2 Implementation Worker.
Working directory: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_worker
Read your task assignment in c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_worker\DISPATCH.md.
