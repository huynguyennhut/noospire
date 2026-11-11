# Milestone 2 Technical Handoff Report: Durable SSE Stream & Events 101+ Cursor Replay

**Agent**: `m2_explorer_3`  
**Role**: SSE Stream & Events 101+ Cursor Replay Explorer  
**Milestone**: Milestone 2 — Durable Queue, Scheduling & Eventing (Feature 11)  
**Recipient**: Parent Orchestrator (`eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb`) & Milestone 2 Worker (`teamwork_worker`)  
**Working Directory**: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_3`  
**Date**: 2026-11-10T21:10:00Z  

---

## 1. Observation

### 1.1 The "Events 101+ Concealed" Multi-Layer Defect

We directly inspected the frontend polling code, the SSE stream endpoint, the authentication layer, and the database logging models. The concealing of events past 100 is caused by a chain of compounding design flaws:

1. **Frontend Hardcoded Pagination Size (`size=100`) and Zero Offset/Cursor Advancement**:
   - Location: `frontend/src/lib/api.ts:243-246` (and originally line 991 prior to M1)
   - Verbatim Code:
     ```typescript
     public async getScanLogs(scanId: string, size: number = 500): Promise<Array<{ timestamp: string; level: string; message: string; source: string }>> {
       const data = await this.fetchJson<any>(`/scans/${scanId}/logs?size=${size}`);
       return Array.isArray(data) ? data : (data.items || []);
     }
     ```
   - *Observation*: `getScanLogs` queries page 1 only (`/scans/${scanId}/logs?size=...`). In the initial codebase prior to M1, `size` was hardcoded to `100`. In Milestone 1, it was bumped to `500`, but it remains fundamentally single-page without any cursor parameter (`after_id`) or pagination loop. Any log entries beyond page 1 (events 101+ originally, or events 501+ currently) are never requested.

2. **Frontend Fallback Polling Without Cursor or Incremental State**:
   - Location: `frontend/src/app/active-assessments/page.tsx:223-237`
   - Verbatim Code:
     ```typescript
     const fetchScanLogsFallback = useCallback(async (id: string) => {
       try {
         const logsData = await api.getScanLogs(id).catch(() => []);
         if (logsData && logsData.length > 0) {
           setLogs((prev) => {
             const map = new Map<string, LogEntry>();
             prev.forEach((l) => map.set(`${l.timestamp}-${l.message}`, l));
             logsData.forEach((l: LogEntry) => map.set(`${l.timestamp}-${l.message}`, l));
             return Array.from(map.values());
           });
         }
       } catch (err) {
         console.error(err);
       }
     }, []);
     ```
   - *Observation*: The polling loop executes every 2500ms, repeatedly requesting only the first page. Deduplication relies on `${l.timestamp}-${l.message}` string keys, which fails when timestamps collision or lack sub-millisecond precision. Furthermore, as new rows are inserted in the database, offset-based pagination drifts, concealing new items.

3. **Browser Native `EventSource` Authentication Blocker (Silent 401 Rejection)**:
   - Location: `frontend/src/app/active-assessments/page.tsx:273-275`
     ```typescript
     const sseUrl = `/api/v1/scans/${activeScanId}/logs/stream`;
     const es = new EventSource(sseUrl);
     ```
   - Location: `backend/app/api/deps.py:20-33`
     ```python
     async def get_current_user(
         request: Request,
         token: Optional[str] = Depends(oauth2_scheme),
         db: AsyncSession = Depends(get_db),
     ) -> Optional[User]:
         auth_via_cookie = False
         if not token:
             token = request.cookies.get("sentinel_access_token") or request.cookies.get("access_token")
             if token:
                 auth_via_cookie = True
         if not token:
             return None
     ```
   - *Observation*: Native browser `new EventSource(url)` cannot send custom HTTP headers like `Authorization: Bearer <token>`. The frontend stores its JWT in `localStorage.getItem('sentinel_jwt_token')`, but no cookie is set on login. `deps.py:get_current_user` does NOT inspect `request.query_params.get("token")`. As a result, the SSE endpoint `/api/v1/scans/{scan_id}/logs/stream` immediately rejects the browser connection with `HTTP 401 Unauthorized`. The browser fires `es.onerror()`, transitions to `sseConnected = false`, and forces the frontend into fallback polling, where events 101+ are concealed!

4. **SSE Stream Lacks `Last-Event-ID` Handling, Monotonic Event ID, and DB Replay**:
   - Location: `backend/app/api/scans.py:553-583`
   - Verbatim Code:
     ```python
     @router.get("/{scan_id}/logs/stream")
     async def stream_scan_logs(
         scan_id: uuid.UUID,
         current_user: User = Depends(require_viewer),
     ) -> StreamingResponse:
         async def event_generator():
             try:
                 async for log_entry in log_buffer.subscribe(scan_id):
                     payload = {
                         "id": str(log_entry.id),
                         "scan_id": str(log_entry.scan_id),
                         "timestamp": log_entry.timestamp.isoformat(),
                         "level": log_entry.level,
                         "message": log_entry.message,
                         "source": log_entry.source,
                     }
                     yield f"data: {json.dumps(payload)}\n\n"
             except Exception:
                 pass
     ```
   - *Observation*:
     a. The endpoint does NOT accept `Last-Event-ID` header or a cursor parameter.
     b. It does NOT emit `id: <event_id>\n` required by the SSE specification.
     c. It relies exclusively on an in-memory `log_buffer` in `dispatcher.py`. If the client connects late, reconnects after a disconnect, or if the scan is executing on a different worker replica/process, `log_buffer` contains 0 historical events.
     d. There is no keep-alive heartbeat comment (`: keep-alive\n\n`), causing proxies and browsers to terminate silent streams after 30-60 seconds.

5. **Existing Database Model Lacks Stable Monotonic Event Sequence**:
   - Location: `backend/app/models/scan.py:123-138`
   - Verbatim Code:
     ```python
     class ScanLog(Base):
         __tablename__ = "scan_logs"
         id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
         scan_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True)
         timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
         level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
         message: Mapped[str] = mapped_column(Text, nullable=False)
         source: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
     ```
   - *Observation*: `ScanLog.id` is a random `uuid.uuid4()`. Random UUIDs cannot be ordered monotonically with `id > :last_event_id`. Furthermore, `ScanLog` lacks `batch_id`, `target_id`, `engine`, `attempt`, `actor_id`, `actor_type`, `event_type`, and structured/sanitized `details_json`.

---

## 2. Logic Chain

```
[Observation 1.1: Frontend polls page 1 with size=100/500 only]
                     +
[Observation 1.3: EventSource fails with 401 because token cannot be sent in header]
                     │
                     ▼
[Inference A: Native SSE stream is always rejected; frontend is forced into fallback polling]
                     │
                     ▼
[Inference B: Fallback polling only retrieves the first 100 (or 500) items of page 1]
                     │
                     ▼
[Conclusion 1: Any events produced after item 100 are permanently concealed from operator view]
```

```
[Observation 1.4: SSE endpoint does not accept Last-Event-ID or emit id: <id>]
                     +
[Observation 1.5: ScanLog uses random UUID primary keys without monotonic ordering]
                     │
                     ▼
[Inference C: Reconnection cannot identify where the stream dropped or query `WHERE id > :last_id`]
                     │
                     ▼
[Inference D: In-memory log_buffer is lost across worker processes and restarts]
                     │
                     ▼
[Conclusion 2: Event delivery cannot survive worker restarts, high volumes (728 jobs), or multi-replica clusters]
```

To satisfy Milestone 2 Feature 11, the architecture requires:
1. A durable database table (`scan_events`) with an auto-incrementing monotonic integer ID (`BigInteger`), compound indices on `(scan_id, id)` and `(batch_id, id)`, and structured sanitized details.
2. An event bus (`ResumableEventBroadcaster`) that transactionally writes to DB first, then broadcasts to active in-memory subscriber queues.
3. An enhanced SSE endpoint (`/scans/{scan_id}/events/stream` and `/scans/{scan_id}/logs/stream`) that:
   - Authenticates via query parameter `?token=` (for browser native EventSource) as well as standard Bearer header and cookie.
   - Accepts `Last-Event-ID` header (or `cursor` query param).
   - Performs **Phase 1: DB Cursor Replay** (`WHERE id > :last_event_id ORDER BY id ASC`) before live streaming.
   - Performs **Phase 2: Live PubSub** with **gap detection** and deduplication.
   - Emits compliant SSE syntax: `id: {id}\nevent: {type}\ndata: {json}\n\n`.
   - Sends periodic `: keep-alive\n\n` comments.
4. A cursor-based incremental polling endpoint (`GET /scans/{scan_id}/events?after_id={cursor}&limit=200`) as a guaranteed fallback.
5. A frontend consumer in `active-assessments/page.tsx` that authenticates SSE with `?token=...`, tracks `lastEventIdRef`, and falls back to cursor-based polling without losing events 101+.

---

## 3. Caveats

1. **SQLite vs PostgreSQL BigInteger Autoincrement**: In SQLite, an auto-incrementing primary key must use `INTEGER PRIMARY KEY`. In PostgreSQL, it uses `BIGSERIAL` / `BIGINT GENERATED BY DEFAULT AS IDENTITY`. SQLAlchemy's `BigInteger().with_variant(Integer, "sqlite")` with `primary_key=True, autoincrement=True` handles this transparently across both database engines.
2. **Event Details Sanitization**: Sanitization must strip authorization headers, bearer tokens, passwords, and sensitive cookies before persistence. Very large diagnostic strings must be truncated (e.g. at 4KB) to protect SQLite/PostgreSQL storage from bloat during high-volume scans (such as Ultra Scan with 728 engine executions).
3. **No Direct Production Implementation in Explorer Role**: In accordance with the Explorer archetype constraint, all production implementations below are provided as concrete, drop-in specifications for `teamwork_worker`.

---

## 4. Conclusion & Concrete Implementation Strategy

### 4.1 Durable Event Logging Schema (`backend/app/models/event.py`)

Create `backend/app/models/event.py` defining `ScanEvent`:

```python
"""Durable Security Event Model for Noosforge Sentinel.

Provides monotonically ordered event records supporting Last-Event-ID cursor replay,
high-volume multi-engine audit trails, and multi-replica event bus dispatch.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, GUID


def sanitize_event_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively sanitizes event details dictionary: redacting credentials and truncating large blobs."""
    if not details:
        return {}
    sanitized: Dict[str, Any] = {}
    SENSITIVE_KEYS = {"authorization", "token", "password", "secret", "cookie", "set-cookie", "api_key", "jwt"}
    for k, v in details.items():
        k_lower = str(k).lower()
        if any(s in k_lower for s in SENSITIVE_KEYS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 4096:
            sanitized[k] = v[:4096] + "... [TRUNCATED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_event_details(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_event_details(item) if isinstance(item, dict) else item for item in v[:50]]
        else:
            sanitized[k] = v
    return sanitized


class ScanEvent(Base):
    """Durable security event entity backed by auto-incrementing monotonic integer ID."""
    __tablename__ = "scan_events"

    # Monotonic Sequence Primary Key (SQLite INTEGER / PostgreSQL BIGSERIAL)
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        index=True,
    )

    # Scoping Identifiers
    scan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("scan_batches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Engine & Execution Details
    engine: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Actor & Origin Provenance
    actor_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32), default="SYSTEM", nullable=False)

    # Event Type & Severity Level
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)

    # Message Description
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Strict UTC Timestamp
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Structured Sanitized Payload
    details_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )

    # Compound Indexes for O(1) Index-Seek Cursor Queries
    __table_args__ = (
        Index("ix_scan_events_scan_cursor", "scan_id", "id"),
        Index("ix_scan_events_batch_cursor", "batch_id", "id"),
        Index("ix_scan_events_occurred_at", "occurred_at"),
        Index("ix_scan_events_type_scan", "event_type", "scan_id"),
    )
```

Register model in `backend/app/models/__init__.py` and `backend/app/core/database.py:init_db()`.

---

### 4.2 Event Broadcaster & PubSub Bus (`backend/app/core/event_bus.py`)

Create `backend/app/core/event_bus.py`:

```python
"""In-Memory and DB-Backed Resumable Event Broadcaster for SSE."""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Set
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.event import ScanEvent, sanitize_event_details

logger = logging.getLogger("sentinel.event_bus")


class ResumableEventBroadcaster:
    """Thread-safe PubSub dispatcher bridging transactional DB commits to active SSE streams."""

    def __init__(self) -> None:
        self._scan_subscribers: Dict[uuid.UUID, Set[asyncio.Queue]] = {}
        self._batch_subscribers: Dict[uuid.UUID, Set[asyncio.Queue]] = {}
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._lock is None:
            self._lock = asyncio.Lock()
        elif current_loop and getattr(self._lock, "_loop", None) is not None and self._lock._loop != current_loop:
            self._lock = asyncio.Lock()
        return self._lock

    async def emit(
        self,
        event_type: str,
        message: str,
        scan_id: Optional[uuid.UUID] = None,
        batch_id: Optional[uuid.UUID] = None,
        target_id: Optional[uuid.UUID] = None,
        engine: Optional[str] = None,
        attempt: int = 1,
        actor_id: Optional[str] = None,
        actor_type: str = "SYSTEM",
        level: str = "INFO",
        details: Optional[Dict[str, Any]] = None,
        session: Optional[AsyncSession] = None,
    ) -> ScanEvent:
        """Transactionally commits an event to DB and broadcasts to live stream queues."""
        clean_details = sanitize_event_details(details)
        now_utc = datetime.now(timezone.utc)

        db_event = ScanEvent(
            scan_id=scan_id,
            batch_id=batch_id,
            target_id=target_id,
            engine=engine,
            attempt=attempt,
            actor_id=actor_id,
            actor_type=actor_type,
            event_type=event_type,
            level=level,
            message=message,
            occurred_at=now_utc,
            details_json=clean_details,
        )

        # 1. Commit/Flush to DB to obtain the monotonic auto-increment ID
        if session is not None:
            session.add(db_event)
            await session.flush()
            await session.refresh(db_event)
        else:
            async with AsyncSessionLocal() as local_session:
                local_session.add(db_event)
                await local_session.commit()
                await local_session.refresh(db_event)

        # 2. Fan-out to live subscriber queues
        async with self._get_lock():
            if scan_id and scan_id in self._scan_subscribers:
                for q in list(self._scan_subscribers[scan_id]):
                    try:
                        q.put_nowait(db_event)
                    except asyncio.QueueFull:
                        pass
            if batch_id and batch_id in self._batch_subscribers:
                for q in list(self._batch_subscribers[batch_id]):
                    try:
                        q.put_nowait(db_event)
                    except asyncio.QueueFull:
                        pass

        return db_event

    async def subscribe_scan(self, scan_id: uuid.UUID) -> AsyncGenerator[ScanEvent, None]:
        """Subscribes an async generator to live events for a scan job."""
        q: asyncio.Queue[ScanEvent] = asyncio.Queue(maxsize=1000)
        async with self._get_lock():
            self._scan_subscribers.setdefault(scan_id, set()).add(q)
        try:
            while True:
                item = await q.get()
                yield item
                q.task_done()
        finally:
            async with self._get_lock():
                if scan_id in self._scan_subscribers and q in self._scan_subscribers[scan_id]:
                    self._scan_subscribers[scan_id].remove(q)
                    if not self._scan_subscribers[scan_id]:
                        del self._scan_subscribers[scan_id]


event_broadcaster = ResumableEventBroadcaster()


async def emit_event(
    event_type: str,
    message: str,
    scan_id: Optional[uuid.UUID] = None,
    batch_id: Optional[uuid.UUID] = None,
    target_id: Optional[uuid.UUID] = None,
    engine: Optional[str] = None,
    attempt: int = 1,
    actor_id: Optional[str] = None,
    actor_type: str = "SYSTEM",
    level: str = "INFO",
    details: Optional[Dict[str, Any]] = None,
    session: Optional[AsyncSession] = None,
) -> ScanEvent:
    """Convenience functional interface for project event emission."""
    return await event_broadcaster.emit(
        event_type=event_type,
        message=message,
        scan_id=scan_id,
        batch_id=batch_id,
        target_id=target_id,
        engine=engine,
        attempt=attempt,
        actor_id=actor_id,
        actor_type=actor_type,
        level=level,
        details=details,
        session=session,
    )
```

---

### 4.3 Query Parameter Token Authentication (`backend/app/api/deps.py`)

In `backend/app/api/deps.py:get_current_user`, add query param `token` resolution so browser `EventSource` can authenticate without custom headers:

```python
    auth_via_cookie = False
    if not token:
        token = request.cookies.get("sentinel_access_token") or request.cookies.get("access_token")
        if token:
            auth_via_cookie = True
    
    # Enable native EventSource authentication via query parameter
    if not token and request.query_params.get("token"):
        token = request.query_params.get("token")

    if not token:
        return None
```

---

### 4.4 Resumable SSE Stream & Cursor Polling Endpoints (`backend/app/api/scans.py`)

In `backend/app/api/scans.py`, update `stream_scan_logs` and add `get_scan_events`:

```python
from backend.app.core.event_bus import event_broadcaster
from backend.app.models.event import ScanEvent
from fastapi import Header, Request


@router.get("/{scan_id}/events/stream")
@router.get("/{scan_id}/logs/stream")  # Backward-compatible dual route
async def stream_scan_events(
    scan_id: uuid.UUID,
    request: Request,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    cursor: Optional[int] = Query(None, description="Monotonic integer event cursor"),
    current_user: User = Depends(require_viewer),
) -> StreamingResponse:
    """Server-Sent Events (SSE) stream supporting Last-Event-ID cursor replay and DB gap detection."""
    # 1. Parse starting cursor
    start_id = 0
    if last_event_id:
        try:
            start_id = int(last_event_id.strip())
        except ValueError:
            start_id = 0
    elif cursor is not None:
        start_id = max(0, cursor)

    async def event_generator():
        last_emitted_id = start_id

        # Phase 1: Replay all historic committed events from DB where id > start_id
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ScanEvent)
                .where(ScanEvent.scan_id == scan_id)
                .where(ScanEvent.id > start_id)
                .order_by(ScanEvent.id.asc())
            )
            res = await session.execute(stmt)
            for evt in res.scalars().all():
                payload = {
                    "id": evt.id,
                    "scan_id": str(evt.scan_id) if evt.scan_id else None,
                    "timestamp": evt.occurred_at.isoformat(),
                    "level": evt.level,
                    "message": evt.message,
                    "source": evt.engine or "system",
                    "event_type": evt.event_type,
                    "details": evt.details_json or {},
                }
                yield f"id: {evt.id}\nevent: {evt.event_type}\ndata: {json.dumps(payload)}\n\n"
                last_emitted_id = max(last_emitted_id, evt.id)

        # Phase 2: Live PubSub stream with gap detection and periodic heartbeats
        live_gen = event_broadcaster.subscribe_scan(scan_id)
        try:
            while True:
                try:
                    # 15s heartbeat timeout
                    evt = await asyncio.wait_for(live_gen.__anext__(), timeout=15.0)

                    # Deduplicate against Phase 1 replay
                    if evt.id <= last_emitted_id:
                        continue

                    # Gap Detection: Check if events were committed while switching from replay to queue
                    if evt.id > last_emitted_id + 1:
                        async with AsyncSessionLocal() as gap_session:
                            gap_stmt = (
                                select(ScanEvent)
                                .where(ScanEvent.scan_id == scan_id)
                                .where(ScanEvent.id > last_emitted_id)
                                .where(ScanEvent.id < evt.id)
                                .order_by(ScanEvent.id.asc())
                            )
                            gap_res = await gap_session.execute(gap_stmt)
                            for g_evt in gap_res.scalars().all():
                                g_payload = {
                                    "id": g_evt.id,
                                    "scan_id": str(g_evt.scan_id) if g_evt.scan_id else None,
                                    "timestamp": g_evt.occurred_at.isoformat(),
                                    "level": g_evt.level,
                                    "message": g_evt.message,
                                    "source": g_evt.engine or "system",
                                    "event_type": g_evt.event_type,
                                    "details": g_evt.details_json or {},
                                }
                                yield f"id: {g_evt.id}\nevent: {g_evt.event_type}\ndata: {json.dumps(g_payload)}\n\n"
                                last_emitted_id = g_evt.id

                    # Yield live event
                    payload = {
                        "id": evt.id,
                        "scan_id": str(evt.scan_id) if evt.scan_id else None,
                        "timestamp": evt.occurred_at.isoformat(),
                        "level": evt.level,
                        "message": evt.message,
                        "source": evt.engine or "system",
                        "event_type": evt.event_type,
                        "details": evt.details_json or {},
                    }
                    yield f"id: {evt.id}\nevent: {evt.event_type}\ndata: {json.dumps(payload)}\n\n"
                    last_emitted_id = evt.id

                except asyncio.TimeoutError:
                    # Keep-alive comment to prevent proxy timeouts
                    yield ": keep-alive\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            await live_gen.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{scan_id}/events")
async def get_scan_events(
    scan_id: uuid.UUID,
    after_id: int = Query(0, ge=0, description="Monotonic integer cursor: returns events with id > after_id"),
    limit: int = Query(200, ge=1, le=1000, description="Batch size for bounded polling"),
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Bounded incremental event polling endpoint with cursor pagination for events 101+."""
    stmt = (
        select(ScanEvent)
        .where(ScanEvent.scan_id == scan_id)
        .where(ScanEvent.id > after_id)
        .order_by(ScanEvent.id.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    total_stmt = select(func.count()).select_from(
        select(ScanEvent).where(ScanEvent.scan_id == scan_id).subquery()
    )
    total_res = await db.execute(total_stmt)
    total = total_res.scalar() or 0

    return {
        "items": [
            {
                "id": e.id,
                "scan_id": str(e.scan_id) if e.scan_id else None,
                "timestamp": e.occurred_at.isoformat(),
                "level": e.level,
                "message": e.message,
                "source": e.engine or "system",
                "event_type": e.event_type,
                "details": e.details_json or {},
            }
            for e in items
        ],
        "total": total,
        "page": 1,
        "size": len(items),
        "pages": 1,
    }
```

---

### 4.5 Dispatcher Event Emission Integration (`backend/app/core/dispatcher.py`)

In `backend/app/core/dispatcher.py`, bind log output and pipeline state transitions to `emit_event`:

```python
from backend.app.core.event_bus import emit_event

# Inside _run_scan:
async def log_cb(source: str, msg: str, level: str = "INFO", details: Optional[Dict[str, Any]] = None) -> None:
    # 1. Update in-memory active thread tracking
    if scan_id in self._active_threads:
        self._active_threads[scan_id]["last_log"] = msg
        st = self._active_threads[scan_id].get("start_time", start_mono)
        self._active_threads[scan_id]["elapsed_seconds"] = int(asyncio.get_event_loop().time() - st)

    # 2. Emit durable event (persisted in DB and broadcast via SSE)
    await emit_event(
        event_type="LOG",
        message=msg,
        scan_id=scan_id,
        batch_id=scan.batch_id,
        target_id=scan.asset_id,
        engine=source,
        level=level,
        details=details or {},
    )
```

Also emit structured lifecycle events:
- On job enqueue: `emit_event("SCAN_QUEUED", "Scan enqueued into worker queue", ...)`
- On execution start: `emit_event("SCAN_STARTED", "Scan execution started", ...)`
- On stage transitions: `emit_event("STAGE_TRANSITION", f"Entered stage: {stage_name}", details={"stage": stage_name, "stage_idx": idx})`
- On finding discovery: `emit_event("FINDING_DETECTED", f"Discovered finding: {title}", level="VULN", details={"fingerprint": fp, "severity": sev})`
- On completion: `emit_event("SCAN_COMPLETED", "Assessment completed successfully", ...)`
- On cancellation: `emit_event("SCAN_CANCELLED", "Scan cancelled by operator", level="WARNING", ...)`
- On failure: `emit_event("SCAN_FAILED", f"Scan failed: {error_msg}", level="ERROR", ...)`

---

### 4.6 Frontend Integration Strategy (`frontend/src/lib/api.ts` & `frontend/src/app/active-assessments/page.tsx`)

#### 1. In `frontend/src/lib/api.ts`:
Add `getScanEvents`:
```typescript
  public async getScanEvents(scanId: string, afterId: number = 0, limit: number = 200): Promise<{
    items: Array<{
      id: number;
      scan_id?: string;
      timestamp: string;
      level: string;
      message: string;
      source: string;
      event_type?: string;
      details?: Record<string, any>;
    }>;
    total: number;
  }> {
    return this.fetchJson(`/scans/${scanId}/events?after_id=${afterId}&limit=${limit}`);
  }
```

#### 2. In `frontend/src/app/active-assessments/page.tsx`:
Update SSE and fallback polling logic:

```typescript
  // Cursor Tracking Ref
  const lastEventIdRef = useRef<number>(0);

  // Incremental Cursor-Based Fallback Polling (No 100-event ceiling)
  const fetchScanEventsIncremental = useCallback(async (id: string) => {
    try {
      const res = await api.getScanEvents(id, lastEventIdRef.current, 200).catch(() => null);
      if (res && res.items && res.items.length > 0) {
        let maxId = lastEventIdRef.current;
        setLogs((prev) => {
          const existingIds = new Set(prev.map((p) => p.id).filter(Boolean));
          const existingKeys = new Set(prev.map((p) => `${p.timestamp}-${p.message}`));
          const fresh: LogEntry[] = [];
          for (const item of res.items) {
            if (item.id && !existingIds.has(item.id)) {
              fresh.push(item);
              maxId = Math.max(maxId, item.id);
            } else if (!existingKeys.has(`${item.timestamp}-${item.message}`)) {
              fresh.push(item);
              if (item.id) maxId = Math.max(maxId, item.id);
            }
          }
          if (fresh.length === 0) return prev;
          return [...prev, ...fresh];
        });
        lastEventIdRef.current = maxId;
      }
    } catch (err) {
      console.error('Incremental polling error:', err);
    }
  }, []);

  // Resumable SSE Connection with Auth & Last-Event-ID Cursor
  useEffect(() => {
    if (!activeScanId) return;

    setLogs([]);
    lastEventIdRef.current = 0;
    fetchScanJobStatus(activeScanId);
    fetchScanEventsIncremental(activeScanId);

    if (typeof window !== 'undefined' && window.EventSource) {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }

      const token = api.getToken();
      const params = new URLSearchParams();
      if (token) params.set('token', token);
      if (lastEventIdRef.current > 0) params.set('cursor', String(lastEventIdRef.current));

      const sseUrl = `/api/v1/scans/${activeScanId}/events/stream?${params.toString()}`;
      const es = new EventSource(sseUrl);
      eventSourceRef.current = es;

      es.onopen = () => {
        setSseConnected(true);
      };

      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload && payload.message) {
            const eventId = Number(event.lastEventId || payload.id || 0);
            if (eventId > 0) {
              lastEventIdRef.current = Math.max(lastEventIdRef.current, eventId);
            }
            setLogs((prev) => {
              if (payload.id && prev.some((p) => p.id === payload.id)) {
                return prev;
              }
              const key = `${payload.timestamp}-${payload.message}`;
              if (prev.some((p) => `${p.timestamp}-${p.message}` === key)) {
                return prev;
              }
              return [...prev, payload];
            });
            setSseConnected(true);
          }
        } catch (_) {}
      };

      es.onerror = () => {
        setSseConnected(false);
      };
    }

    const interval = setInterval(() => {
      fetchScanJobStatus(activeScanId);
      fetchScanEventsIncremental(activeScanId);
    }, 2500);

    return () => {
      clearInterval(interval);
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      setSseConnected(false);
    };
  }, [activeScanId, fetchScanJobStatus, fetchScanEventsIncremental]);
```

---

## 5. Verification Method

### 5.1 Verification Commands

1. **Verify Backend Tests & Route Health**:
   ```bash
   python -m pytest tests/test_tier1_feature_coverage.py -k "test_t1_scn_06_scan_sse_log_stream" -v
   ```
2. **Execute Full Backend Boundary Tests**:
   ```bash
   python -m pytest tests/test_m1_challenger2_backend_boundaries.py tests/test_m1_it2_empirical_challenger.py -v
   ```
3. **Frontend Typecheck & Build Validation**:
   ```bash
   cd frontend
   npm run build
   ```

### 5.2 Verification Script Specification for Worker (`test_sse_events_101_replay.py`)

The implementer/worker must author an empirical test verifying the following assertions:

```python
@pytest.mark.asyncio
async def test_sse_cursor_replay_events_101_plus(client: httpx.AsyncClient, db: AsyncSession):
    # 1. Create target scan
    scan_id = uuid.uuid4()
    # 2. Insert 150 events into ScanEvent with monotonic sequence 1..150
    for i in range(1, 151):
        evt = ScanEvent(
            scan_id=scan_id,
            event_type="LOG",
            message=f"Synthetic test event {i}",
            level="INFO",
            occurred_at=datetime.now(timezone.utc),
        )
        db.add(evt)
    await db.commit()

    # 3. Request SSE stream with Last-Event-ID: 100
    headers = {"Last-Event-ID": "100"}
    async with client.stream("GET", f"/api/v1/scans/{scan_id}/events/stream", headers=headers) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        lines = []
        async for line in response.aiter_lines():
            if line.startswith("id: "):
                lines.append(int(line.split("id: ")[1]))
            if len(lines) >= 50:
                break
                
        # Assertion 1: All events 101 to 150 are delivered
        assert lines == list(range(101, 151))
        # Assertion 2: Events 1 to 100 were NOT replayed
        assert 100 not in lines

    # 4. Verify incremental polling endpoint
    poll_resp = await client.get(f"/api/v1/scans/{scan_id}/events?after_id=100&limit=50")
    assert poll_resp.status_code == 200
    data = poll_resp.json()
    assert len(data["items"]) == 50
    assert data["items"][0]["id"] == 101
    assert data["items"][-1]["id"] == 150
```

### 5.3 Invalidation Conditions
- If any event with `id > 100` fails to appear in either the SSE stream or the polling response, the verification fails.
- If `EventSource` rejects the `?token=` parameter with HTTP 401 when a valid JWT is supplied, the verification fails.
- If inserting high-speed events causes non-monotonic ordering or dropped records across page boundaries, the verification fails.
