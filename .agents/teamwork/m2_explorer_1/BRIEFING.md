# BRIEFING — 2026-11-10T20:57:00Z

## Mission
Investigate DB-backed queue persistence, worker leases, fencing tokens, retries, recovery, process separation, and process cancellation for PostgreSQL and SQLite in Milestone 2.

## 🔒 My Identity
- Archetype: teamwork_explorer
- Roles: Queue Persistence & Worker Leases Explorer
- Working directory: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_1
- Original parent: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb
- Milestone: Milestone 2 — Durable Queue, Scheduling & Eventing

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Deliver report to c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_1\handoff.md
- Support both PostgreSQL (FOR UPDATE SKIP LOCKED) and SQLite (concurrency-safe transaction / atomic lease acquisition)
- Concrete schema designs, method signatures, drop-in worker implementation strategy

## Current Parent
- Conversation ID: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb
- Updated: not yet

## Investigation State
- **Explored paths**:
  - `backend/app/models/scan.py` (ScanBatch and Scan domain models)
  - `backend/app/models/base.py` (GUID, UTCDateTime TypeDecorators)
  - `backend/app/core/dispatcher.py` (AsyncWorkerDispatcher, in-memory queue, ProcessSafetyManager)
  - `backend/app/core/database.py` (AsyncSessionLocal, SQLite WAL/busy_timeout pragma, migrations)
  - `backend/app/core/scheduler.py` (SchedulerEngine, compute_next_run cron evaluator)
  - `backend/main.py` (FastAPI lifespan, embedded worker and scheduler lifecycle)
  - `backend/app/scanners/base.py`, `nuclei.py`, `zap.py` (adapters and subprocess tracking)
  - `backend/app/api/scans.py` (scan endpoints, batch creation, cancellation, stop-all)
- **Key findings**:
  1. `AsyncWorkerDispatcher` uses an in-memory `asyncio.Queue` which is not durable across restarts or multi-replica deployments.
  2. Database models currently lack worker lease fields (`leased_by`, `leased_at`, `lease_expires_at`, `heartbeat_at`, `fencing_token`, `attempts`, `available_at`, `cancelled_at`).
  3. PostgreSQL supports `FOR UPDATE SKIP LOCKED`, while SQLite in WAL mode can execute atomic Compare-And-Swap (CAS) updates to guarantee lock-free, zero-conflict lease claims.
  4. Fencing tokens prevent split-brain by conditioning heartbeats, log writes, finding persistence, and terminal state transitions on `fencing_token`.
  5. Abandoned job recovery (reaper) must be decoupled from startup to preserve multi-replica safety, running periodically to recover jobs with expired leases.
  6. Process separation requires standalone entry points (`backend.app.worker`, `backend.app.scheduler`) alongside `backend.main`, with configuration toggle for embedded vs standalone execution.
  7. Process cancellation requires recursive process tree termination (`psutil.children`), persisted `cancelled_at` timestamps, and an explicit invariant withholding automatic retry for uncertain active probes.
- **Unexplored areas**: None for M2 scope; all 7 required investigation areas examined and synthesized.

## Key Decisions Made
- Architecture formulated for dual-dialect queue persistence (PostgreSQL + SQLite).
- Designed complete schema additions to `scans`, `scan_batches`, and `engine_executions`.
- Designed atomic lease acquisition, heartbeat renewal, and fencing token validation logic.
- Established process separation architecture with standalone CLI entry points and embedded fallback.

## Artifact Index
- DISPATCH.md — Task dispatch and instructions
- BRIEFING.md — Persistent working memory
- progress.md — Liveness heartbeat
- handoff.md — Comprehensive 5-component handoff report
