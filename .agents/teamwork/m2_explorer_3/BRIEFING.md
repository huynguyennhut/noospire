# BRIEFING — 2026-11-10T21:05:00Z

## Mission
Investigate durable SSE streaming, event persistence, and solve the "Events 101+ concealed" bug for Milestone 2, designing a resumable cursor replay mechanism.

## 🔒 My Identity
- Archetype: teamwork_explorer
- Roles: SSE Stream & Events 101+ Cursor Replay Explorer
- Working directory: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_3
- Original parent: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb
- Milestone: Milestone 2 — Durable Queue, Scheduling & Eventing

## 🔒 Key Constraints
- Read-only investigation — do NOT implement production changes directly
- All output in `.agents/teamwork/m2_explorer_3`
- Must provide concrete schema, API route implementation, and frontend integration strategy for the worker in handoff.md

## Current Parent
- Conversation ID: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb
- Updated: 2026-11-10T21:05:00Z

## Investigation State
- **Explored paths**:
  - `backend/app/models/scan.py`, `backend/app/models/base.py`, `backend/app/models/__init__.py`
  - `backend/app/api/scans.py`, `backend/app/api/deps.py`, `backend/app/api/logs.py`
  - `backend/app/core/dispatcher.py`, `backend/app/core/database.py`, `backend/main.py`
  - `frontend/src/app/active-assessments/page.tsx`, `frontend/src/lib/api.ts`, `frontend/src/lib/types.ts`
  - `tests/test_tier1_feature_coverage.py`
- **Key findings**:
  1. Root cause of "Events 101+ concealed":
     - `frontend/src/lib/api.ts`: `getScanLogs` queried page 1 only with hardcoded limit (`size=100`, bumped to 500 in M1), never requesting subsequent pages.
     - `frontend/src/app/active-assessments/page.tsx`: Native `new EventSource(sseUrl)` failed with 401 Unauthorized because browser EventSource cannot send `Authorization: Bearer` headers and backend `deps.py:get_current_user` did not check `request.query_params.get("token")`.
     - When SSE failed with 401, frontend fell back to polling `api.getScanLogs()` which continuously fetched page 1 only, concealing events 101+.
     - `backend/app/api/scans.py`: `stream_scan_logs` only streamed from in-memory `log_buffer` without reading `Last-Event-ID` or replaying past events from DB. It did not format lines with `id: <id>\n`.
     - `backend/app/models/scan.py`: `ScanLog` has random UUID primary key, making monotonic cursor query `WHERE id > :last_event_id` impossible.
  2. Durable Event Logging Schema designed: `ScanEvent` in `backend/app/models/event.py` with monotonic `BigInteger().with_variant(Integer, "sqlite")` primary key, `scan_id`, `batch_id`, `target_id`, `engine`, `attempt`, `actor_id`, `actor_type`, `event_type`, `level`, `message`, `occurred_at` (UTC), `details_json` (sanitized).
  3. Resumable SSE Stream & Event Broadcaster designed: `ResumableEventBroadcaster` with pubsub + DB replay, accepting `Last-Event-ID` header and `cursor` query param, dual-route `/scans/{scan_id}/events/stream` and `/scans/{scan_id}/logs/stream`, formatting SSE with `id: {id}\nevent: {type}\ndata: {json}\n\n`, gap detection, and keep-alive comments.
  4. Cursor-based incremental polling fallback designed: `GET /scans/{scan_id}/events?after_id={cursor}&limit=200`.
  5. Frontend integration strategy: Add token to SSE URL query param, track `lastEventIdRef`, implement incremental cursor polling fallback, preserve incoming events without drops or DOM thrashing.
- **Unexplored areas**: None within scope.

## Key Decisions Made
- Use dual routes (`/events/stream` and `/logs/stream`) for complete backward compatibility.
- Use `BigInteger().with_variant(Integer, "sqlite")` for cross-database monotonic auto-increment.
- Support `?token=` query parameter in `get_current_user` to unblock native EventSource browser authentication.

## Artifact Index
- DISPATCH.md — Task assignment and message log
- BRIEFING.md — Persistent situational awareness
- progress.md — Liveness heartbeat and step tracking
- handoff.md — Complete 5-component report for worker and parent
