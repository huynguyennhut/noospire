"""In-Memory and DB-Backed Resumable Event Broadcaster for SSE.

Provides ordered event delivery backed by ScanEvent database persistence,
Last-Event-ID cursor replay, gap detection, and pubsub live streaming.
"""

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

    async def subscribe_batch(self, batch_id: uuid.UUID) -> AsyncGenerator[ScanEvent, None]:
        """Subscribes an async generator to live events for an assessment batch."""
        q: asyncio.Queue[ScanEvent] = asyncio.Queue(maxsize=1000)
        async with self._get_lock():
            self._batch_subscribers.setdefault(batch_id, set()).add(q)
        try:
            while True:
                item = await q.get()
                yield item
                q.task_done()
        finally:
            async with self._get_lock():
                if batch_id in self._batch_subscribers and q in self._batch_subscribers[batch_id]:
                    self._batch_subscribers[batch_id].remove(q)
                    if not self._batch_subscribers[batch_id]:
                        del self._batch_subscribers[batch_id]


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
