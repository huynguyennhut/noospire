---
name: noosforge-backend
description: Implement NOOSFORGE FastAPI endpoints, SQLAlchemy persistence, durable jobs, scheduler and finding lifecycles. Use for server behavior changes; scanner safety policy belongs to security-scanners.
---

# Backend and API engineering

Read root `AGENTS.md`. Own server contracts and persistence; retain compatibility
with the static frontend and existing process roles.

## Workflow

1. Trace router registration in `backend/main.py`; `backend/app/main.py` re-exports
   it. Reuse `app/api/deps.py`, `schemas/`, async sessions and existing model types
   (`models/base.py` includes GUID/time helpers). Keep `/api/v1`, JSON error codes,
   request IDs and pagination aligned with `frontend/src/lib/api.ts` and `types.ts`.
2. Inspect actual dependencies for identity and object scope. Cookie mutations need
   CSRF; bearer credentials are header-only; sessions re-read revocation/user state.
   Use server permission checks on every affected object, including exports/SSE.
   `load_scope` grants estate-wide access only to the immutable configured owner;
   all other roles need asset grants. `require_admin` is an owner-only compatibility
   alias. Preserve these boundaries with `test_platform_access_security.py`; legacy
   superuser flags and role names must not substitute for authorization.
3. Inspect `core/database.py`: boot uses metadata `create_all` plus additive SQLite
   alterations, not Alembic. A model edit does not migrate an existing database.
   Test fresh schema and a synthetic older schema for affected columns. Boot must
   not seed users/assets/findings/schedules unless isolated demo mode opts in.
4. For tasks follow `core/planner.py` → `queue.py` → `dispatcher.py` →
   `engines/runner.py`; read `models/operations.py` and `models/defensive.py`.
   Preserve atomic lease claims, fencing-token commits, heartbeat, cancellation,
   attempts, idempotency and terminal-state accounting. Do not implement a second
   queue or turn the compatibility `CeleryDispatcher` stub into a claimed service.
5. For schedules use `core/monitor_scheduler.py`, slot claims, coalesced catch-up
   and capacity limits. Honor `SENTINEL_PROCESS_ROLE` in `backend/main.py`,
   `app/worker.py` and `app/scheduler_main.py`; API-only tests must not start workers.
6. For findings/retests follow `core/lifecycle.py`, `models/lifecycle.py`,
   `api/console.py` and `engines/runner.py`. Preserve observation/change provenance,
   hidden-record reversibility and frozen report snapshots. An unavailable or
   unevaluated check must not resolve an existing finding. `FIXED_PENDING_RETEST`
   and legacy `FIXED` remain open; equivalent successful verification writes
   `RESOLVED`. Manual triage cannot create verified resolution (409). The legacy
   `/retest` URL delegates to a durable recheck, never an ad-hoc HTTP probe.

## Practical validation

```bash
.venv/bin/python .agents/skills/noosforge-qa/scripts/run_checks.py backend
.venv/bin/python scripts/contract_audit.py
```

The preset exercises existing isolated API, SBOM and lifecycle tests. Select
additional pilot queue/scheduler/restart tests when those paths change. Add targeted
regressions for changed behavior. Never verify server mutations using the shared
repository database. Deliver contract/data changes, regression evidence and any
schema compatibility or permission risk.
