# DISPATCH — 2026-11-10T07:30:00Z

## Assigned Task: Survey Repository - Backend Core, Pipeline, Dispatcher & Job Queue Architecture & Gaps
Working Directory: c:\Users\nguye\Desktop\noospire\.agents\teamwork\explorer_survey_2
Authoritative Request: c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md

Investigate backend codebase, database models, worker processes, and APIs to identify all requirements, bugs, and gaps for:
1. R1: Worker claim & dispatcher invocation in `backend/main.py` and `backend/app/core/dispatcher.py`. Replacing hardcoded true constants in adapter permissions with real dynamic permissions. Actual worker claim tracing.
2. R1 & R4: Scan endpoints & SSE streaming in `backend/app/api/scans.py`. Ensuring events 101+ are not concealed. Resumable SSE with Last-Event-ID / cursor replay and bounded polling fallback.
3. R1 & R4: Metrics endpoint in `backend/app/api/metrics.py`. Replacing inferred history / constant intel metrics with genuine measured 7-day data.
4. R3: Durable DB-backed job queue with PostgreSQL (and SQLite for local dev). Separate scheduler/scanner worker processes. Leases, bounded retries, fencing, idempotent result writes. Abandoned work recovery on restart. Heartbeats/deadlines for slow engines. Cancellation handling.
5. R3: Hourly scheduling for Empire scope at the top of each hour (Asia/Ho_Chi_Minh initial setting, stored in UTC). Missed run coalescing (max 1 pending follow-up). Active run deduplication.
6. R5: Sole owner RBAC & Privileged Enforcement. Bootstrap `dangnhutnguyen0910@gmail.com` as sole owner. Dynamic secret management, zero hardcoded secrets. Strict permission enforcement across API, DB, streams. Immediate session revocation on account disablement.

Output handoff report to: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\explorer_survey_2\handoff.md`.

## 2026-11-10T07:31:30Z
[Message] timestamp=2026-11-10T07:31:30Z sender=eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb priority=MESSAGE_PRIORITY_HIGH
Content:
You are Explorer 2 (Backend & Queue Explorer).
Your working directory is: c:\Users\nguye\Desktop\noospire\.agents\teamwork\explorer_survey_2
Read your instructions in: c:\Users\nguye\Desktop\noospire\.agents\teamwork\explorer_survey_2\DISPATCH.md
Read the authoritative user request at: c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md

Your mission:
Survey the backend core, job queue, pipeline, dispatcher, scheduler, and auth/RBAC architecture. Map out all existing files, implementation details, bugs, and gaps according to R1, R2, R3, R5, and Gates 1, 3, 5. Specifically investigate:
1. `backend/main.py` and `backend/app/core/dispatcher.py`:
   - Worker claim mechanism and dispatcher invocation.
   - Hardcoded true constants in adapter permissions vs real dynamic permissions.
   - How jobs are traced through worker claims and engine invocations.
2. `backend/app/api/scans.py` and SSE streaming:
   - Event generation, storage, and streaming.
   - Why events 101+ are concealed or truncated.
   - Resumable SSE with Last-Event-ID, cursor replay, gap detection, bounded polling fallback.
3. `backend/app/api/metrics.py`:
   - Metric calculation logic, inferred history vs genuine measured data defaulting to 7 calendar days.
4. Job queue & execution engine:
   - Database schema (PostgreSQL and SQLite support), SQLAlchemy models.
   - Separate scheduler and scanner workers from API processes.
   - Leases, bounded retries, fencing, idempotent result writes.
   - Abandoned work recovery on restart, heartbeats, cancellation, process tree termination.
5. Hourly scheduler:
   - Hourly schedule execution at the top of each hour (Asia/Ho_Chi_Minh initial setting, UTC storage).
   - Overrun handling (>1 hour run): coalescing missed runs into max 1 pending follow-up.
   - Active batch deduplication on manual runs.
6. Sole owner RBAC & Privileged Enforcement:
   - Bootstrap mechanism for `dangnhutnguyen0910@gmail.com`.
   - Secret management without hardcoded literals.
   - Permission enforcement across APIs, DB queries, stream subscriptions.
   - Immediate session revocation upon account deactivation.

Write your complete, structured survey report to:
`c:\Users\nguye\Desktop\noospire\.agents\teamwork\explorer_survey_2\handoff.md`
Include concrete file paths, line references, root cause analysis of existing bugs, and recommended fix strategies. When done, send a message to orchestrator with your report path.
