# DISPATCH: m2_explorer_2

**Agent ID**: m2_explorer_2
**Role**: Hourly Cron & Overrun Coalescing Explorer
**Archetype**: teamwork_explorer
**Working Directory**: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_2
**Parent Conversation ID**: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb
**Milestone**: Milestone 2 — Durable Queue, Scheduling & Eventing

## Mandatory Reading
1. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md` (specifically R3)
2. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\PROJECT.md` (Feature 9)
3. `c:\Users\nguye\Desktop\noospire\.agents\teamwork\orchestrator\GATE_STATUS.md`

## Investigation Scope
Investigate the scheduling engine and API endpoints:
- Examine `backend/app/core/scheduler.py`, `backend/app/api/schedules.py`, `backend/app/models/scan.py`.
- Analyze requirements for R3 hourly scheduling:
  1. Top-of-hour cron in `Asia/Ho_Chi_Minh` timezone (UTC stored).
  2. Next due instant calculation, last scheduled run, last completed run, and scheduler health metrics.
  3. Overrun protection: If a run takes longer than 1 hour, keep current run intact, coalesce missed slots into at most ONE pending follow-up for the same scope (no unbounded backlog).
  4. Active run deduplication: If owner clicks Run during active work, show matching active batch and offer one fresh follow-up or start independent non-overlapping work within global budget; repeated clicks reuse the request.
  5. UI countdown support (1-second countdown, pause/resume, reason if overdue).
- Provide concrete class designs, state transition models, and drop-in implementation strategy for the worker.
- Deliver your report to `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_2\handoff.md`.
