# DISPATCH: m2_explorer_1

**Agent ID**: m2_explorer_1
**Role**: Queue Persistence & Worker Leases Explorer
**Archetype**: teamwork_explorer
**Working Directory**: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_1
**Parent Conversation ID**: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb
**Milestone**: Milestone 2 — Durable Queue, Scheduling & Eventing

## Mandatory Reading
1. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md` (specifically R3)
2. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\PROJECT.md` (Features 8 & 10)
3. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\GATE_STATUS.md`

## Investigation Scope
Investigate the current queue, job execution models, and worker claim mechanisms:
- Examine `backend/app/models/scan.py`, `backend/app/models/base.py`, `backend/app/core/dispatcher.py`, `backend/main.py`.
- Analyze requirements for durable DB-backed job queue supporting both PostgreSQL and SQLite:
  1. Transactional job planning and execution models.
  2. Worker leases with heartbeat/expiration timeout and fencing tokens to prevent split-brain execution.
  3. Bounded retries for transient failures.
  4. Idempotent result writes (prevent duplicate findings on retry/replay).
  5. Recovery of abandoned/orphaned leased jobs after server restart.
  6. Process separation between API processes, scheduler worker, and scanner workers.
  7. Process cancellation: stop worker/process tree, persist cancelled timestamp, do not replay uncertain probes.
- Provide concrete schema additions, method signatures, and drop-in implementation strategy for the worker.
- Deliver your report to `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_1\handoff.md`.

## 2026-11-10T20:49:05Z
[Message] timestamp=2026-11-10T20:49:05Z sender=eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb priority=MESSAGE_PRIORITY_HIGH content=You are m2_explorer_1, Queue Persistence & Worker Leases Explorer for Milestone 2.
Working directory: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_1
Read your task assignment in c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_1\DISPATCH.md.
Mandatory reading:
- c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md (specifically R3)
- c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\PROJECT.md (Features 8 & 10)
- c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\GATE_STATUS.md

Investigate:
DB-backed queue architecture supporting PostgreSQL and SQLite:
1. Transactional job planning and execution models (batch, target execution, engine execution).
2. Worker leases with heartbeat/expiration timeout and fencing tokens to prevent split-brain.
3. Bounded retries and backoff for transient failures.
4. Idempotent result writes.
5. Recovery of abandoned/orphaned leased jobs after server restart.
6. Process separation between API processes, scheduler worker, and scanner workers.
7. Process cancellation: stop worker/process tree, persist cancelled timestamp, do not replay uncertain probes.

Provide concrete schema designs, method signatures, and drop-in implementation strategy for the worker.
Deliver your report to c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_1\handoff.md.
Send a message to your parent (conv: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb) when complete.
