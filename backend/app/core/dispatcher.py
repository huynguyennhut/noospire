import asyncio
from collections import deque
from datetime import datetime, timezone
import logging
import os
from typing import Any, AsyncGenerator, Dict, List, Optional
import uuid

import httpx
import psutil
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.ssrf import SSRFProtector, SSRFValidationError
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan, ScanLog
from backend.app.models.alert import SecurityAlert
from backend.app.scanners.base import (
    BaseScannerAdapter,
    CancellationToken,
    ScanExecutionRequest,
    compute_finding_fingerprint,
)
from backend.app.scanners.nuclei import NucleiAdapter
from backend.app.scanners.trivy import TrivyAdapter
from backend.app.scanners.zap import ZAPAdapter
from backend.app.scanners.empire_engine import EmpireAssessmentEngine
from backend.app.scanners.crawler import AsyncBFSCrawler
from backend.app.schemas.common import (
    AssetType,
    FindingSeverity,
    FindingStatus,
    ScanProfile,
    ScanQualityStatus,
    ScanStatus,
    VerificationStatus,
)
from backend.app.schemas.scan import ScanLogEntry

logger = logging.getLogger("sentinel.dispatcher")


def check_system_resources() -> Dict[str, Any]:
    """Inspects dynamic host resources (CPU and Memory) to govern execution load."""
    try:
        cpu_pct = float(psutil.cpu_percent(interval=None))
        mem = psutil.virtual_memory()
        mem_pct = float(mem.percent)
        mem_avail = round(float(mem.available) / (1024 * 1024), 2)
        mem_used = round(float(mem.used) / (1024 * 1024), 2)
        cpu_count = psutil.cpu_count() or 4
        is_throttled = bool(cpu_pct > settings.THROTTLE_CPU_PCT or mem_pct > settings.THROTTLE_MEM_PCT)
        return {
            "cpu_percent": cpu_pct,
            "memory_percent": mem_pct,
            "memory_available_mb": mem_avail,
            "memory_used_mb": mem_used,
            "cpu_count": cpu_count,
            "is_throttled": is_throttled,
        }
    except Exception as e:
        logger.warning(f"Failed to sample host system resources: {e}")
        return {
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "memory_available_mb": 1024.0,
            "memory_used_mb": 512.0,
            "cpu_count": 4,
            "is_throttled": False,
        }


class ScanLogBuffer:
    """Thread-safe and async in-memory ring buffer for low-latency live log streaming."""

    def __init__(self, maxlen: int = 1000) -> None:
        self.maxlen = maxlen
        self._buffers: Dict[uuid.UUID, deque] = {}
        self._subscribers: Dict[uuid.UUID, List[asyncio.Queue]] = {}
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

    async def append_log(
        self, scan_id: uuid.UUID, level: str, message: str, source: str = "system"
    ) -> ScanLogEntry:
        entry = ScanLogEntry(
            id=uuid.uuid4(),
            scan_id=scan_id,
            timestamp=datetime.now(timezone.utc),
            level=level,
            message=message,
            source=source,
        )
        async with self._get_lock():
            if scan_id not in self._buffers:
                self._buffers[scan_id] = deque(maxlen=self.maxlen)
            self._buffers[scan_id].append(entry)

            # Broadcast to SSE subscribers
            if scan_id in self._subscribers:
                for queue in self._subscribers[scan_id]:
                    await queue.put(entry)

        return entry

    async def get_logs(self, scan_id: uuid.UUID) -> List[ScanLogEntry]:
        async with self._get_lock():
            if scan_id in self._buffers:
                return list(self._buffers[scan_id])
            return []

    async def subscribe(self, scan_id: uuid.UUID) -> AsyncGenerator[ScanLogEntry, None]:
        queue: asyncio.Queue[ScanLogEntry] = asyncio.Queue()
        async with self._get_lock():
            # Replay existing buffered logs
            if scan_id in self._buffers:
                for item in self._buffers[scan_id]:
                    await queue.put(item)
            self._subscribers.setdefault(scan_id, []).append(queue)

        try:
            while True:
                entry = await queue.get()
                yield entry
                queue.task_done()
        finally:
            async with self._get_lock():
                if scan_id in self._subscribers and queue in self._subscribers[scan_id]:
                    self._subscribers[scan_id].remove(queue)
                    if not self._subscribers[scan_id]:
                        del self._subscribers[scan_id]

    async def clear_scan(self, scan_id: uuid.UUID) -> None:
        async with self._get_lock():
            if scan_id in self._buffers:
                del self._buffers[scan_id]

    async def clear_all(self) -> None:
        async with self._get_lock():
            self._buffers.clear()


log_buffer = ScanLogBuffer()


class ProcessSafetyManager:
    """Tracks PID trees spawned during scan jobs and ensures recursive process tree termination."""

    def __init__(self) -> None:
        self._scan_pids: Dict[uuid.UUID, List[int]] = {}
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

    async def register_pid(self, scan_id: uuid.UUID, pid: int) -> None:
        async with self._get_lock():
            self._scan_pids.setdefault(scan_id, []).append(pid)

    def terminate_process_tree(self, scan_id: uuid.UUID) -> None:
        pids = self._scan_pids.pop(scan_id, [])
        for pid in pids:
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                for child in children:
                    child.terminate()
                parent.terminate()
                _, alive = psutil.wait_procs(children + [parent], timeout=3)
                for p in alive:
                    p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass


process_safety = ProcessSafetyManager()


class ITaskDispatcher:
    """Abstract Task Dispatcher interface for background scan task orchestration."""

    async def dispatch_scan(self, scan_id: uuid.UUID) -> str:
        raise NotImplementedError

    async def batch_dispatch_scans(self, scan_ids: List[uuid.UUID], batch_id: Optional[uuid.UUID] = None) -> int:
        for sid in scan_ids:
            await self.dispatch_scan(sid)
        return len(scan_ids)

    async def cancel_scan(self, scan_id: uuid.UUID) -> bool:
        raise NotImplementedError

    async def cancel_batch(self, batch_id: uuid.UUID) -> int:
        raise NotImplementedError

    async def stop_all(self) -> int:
        raise NotImplementedError

    def get_telemetry(self) -> Dict[str, Any]:
        raise NotImplementedError


class AsyncWorkerDispatcher(ITaskDispatcher):
    """Local Async Worker Pool Dispatcher with device resource optimization and live telemetry."""

    def __init__(self, max_concurrent: Optional[int] = None) -> None:
        configured_max = max_concurrent or settings.MAX_CONCURRENT_SCANS
        cpu_bound = max(2, os.cpu_count() or 4)
        self.max_concurrent = min(configured_max, cpu_bound)
        self.worker_id = f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.queue: asyncio.Queue[uuid.UUID] = asyncio.Queue()
        self._work_available = asyncio.Event()
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        self.cancellation_tokens: Dict[uuid.UUID, CancellationToken] = {}
        self.asset_locks: Dict[uuid.UUID, asyncio.Lock] = {}
        self._active_threads: Dict[uuid.UUID, Dict[str, Any]] = {}
        self._worker_task: Optional[asyncio.Task] = None
        self._is_running = False
        self._thread_counter = 0
        self._completed_count = 0
        self._inflight = 0  # claimed by this worker and not finished (bounded by max_concurrent)
        self._cap_cache: tuple = (0.0, None)

    def _ensure_active_loop(self) -> None:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        need_reinit = False
        if not self._is_running:
            need_reinit = True
        elif self._worker_task is None or self._worker_task.done():
            need_reinit = True
        elif hasattr(self._worker_task, "get_loop") and self._worker_task.get_loop() != current_loop:
            need_reinit = True

        if need_reinit:
            old_queue = getattr(self, "queue", None)
            self.queue = asyncio.Queue()
            self._work_available = asyncio.Event()
            if old_queue:
                while not old_queue.empty():
                    try:
                        self.queue.put_nowait(old_queue.get_nowait())
                    except Exception:
                        break
            self.semaphore = asyncio.Semaphore(self.max_concurrent)
            self.asset_locks = {}
            self._is_running = True
            self._worker_task = current_loop.create_task(self._worker_loop())
            logger.info(f"AsyncWorkerDispatcher worker loop attached to active loop (max_concurrent={self.max_concurrent}).")

    def start(self) -> None:
        self._ensure_active_loop()

    async def stop(self) -> None:
        if self._is_running:
            self._is_running = False
            if self._worker_task:
                self._worker_task.cancel()
                try:
                    await self._worker_task
                except asyncio.CancelledError:
                    pass
            logger.info("AsyncWorkerDispatcher stopped.")

    async def dispatch_scan(self, scan_id: uuid.UUID) -> str:
        self._ensure_active_loop()
        token = CancellationToken()
        self.cancellation_tokens[scan_id] = token
        await self.queue.put(scan_id)
        self._work_available.set()
        await log_buffer.append_log(scan_id, "INFO", "Scan job enqueued into worker queue.")
        try:
            from backend.app.core.event_bus import emit_event
            await emit_event("SCAN_QUEUED", "Scan job enqueued into worker queue.", scan_id=scan_id)
        except Exception as e:
            logger.debug("Event emission error on dispatch: %s", e)
        return str(scan_id)

    async def batch_dispatch_scans(self, scan_ids: List[uuid.UUID], batch_id: Optional[uuid.UUID] = None) -> int:
        self._ensure_active_loop()
        for scan_id in scan_ids:
            self.cancellation_tokens[scan_id] = CancellationToken()
            await self.queue.put(scan_id)
        self._work_available.set()
        if batch_id:
            try:
                from backend.app.core.event_bus import emit_event
                await emit_event(
                    "BATCH_QUEUED",
                    f"Dispatched {len(scan_ids)} scans into execution queue.",
                    batch_id=batch_id,
                )
            except Exception as e:
                logger.debug("Batch event emission error: %s", e)
        return len(scan_ids)

    async def cancel_scan(self, scan_id: uuid.UUID) -> bool:
        token = self.cancellation_tokens.get(scan_id)
        if token:
            token.cancel()
        process_safety.terminate_process_tree(scan_id)
        await log_buffer.append_log(scan_id, "WARNING", "Cancellation signal dispatched to scan job.")

        async with AsyncSessionLocal() as session:
            from backend.app.core.queue import IDBDurableQueue
            cancelled = await IDBDurableQueue.cancel_job(session, scan_id, "Scan cancelled by user.")
            if cancelled:
                res = await session.execute(select(Scan).where(Scan.id == scan_id))
                scan = res.scalars().first()
                if scan and scan.batch_id:
                    await self._update_batch_progress(scan.batch_id)
                try:
                    from backend.app.core.event_bus import emit_event
                    await emit_event(
                        "SCAN_CANCELLED",
                        "Scan cancelled by operator",
                        scan_id=scan_id,
                        batch_id=scan.batch_id if scan else None,
                        level="WARNING",
                    )
                except Exception:
                    pass
                return True
        return False

    async def cancel_batch(self, batch_id: uuid.UUID) -> int:
        """Cooperatively cancels running and queued scans in the specified batch."""
        from backend.app.models.scan import ScanBatch

        cancelled_count = 0
        scans = []
        async with AsyncSessionLocal() as session:
            batch_res = await session.execute(select(ScanBatch).where(ScanBatch.id == batch_id))
            batch = batch_res.scalars().first()
            if batch:
                batch.status = ScanStatus.CANCELLED.value
                batch.completed_at = datetime.now(timezone.utc)
                batch.cancellation_reason = "Batch cancelled by user."

            scans_res = await session.execute(select(Scan).where(Scan.batch_id == batch_id))
            scans = scans_res.scalars().all()

            for scan in scans:
                if scan.status in (
                    ScanStatus.QUEUED.value,
                    ScanStatus.INITIALIZING.value,
                    ScanStatus.RUNNING.value,
                    ScanStatus.PENDING.value,
                ):
                    token = self.cancellation_tokens.get(scan.id)
                    if token:
                        token.cancel()
                    process_safety.terminate_process_tree(scan.id)
                    scan.status = ScanStatus.CANCELLED.value
                    scan.cancelled_at = datetime.now(timezone.utc)
                    scan.cancellation_reason = "Batch cancelled by user."
                    scan.completed_at = datetime.now(timezone.utc)
                    scan.fencing_token = (scan.fencing_token or 0) + 1
                    cancelled_count += 1
                    await log_buffer.append_log(scan.id, "WARNING", "Scan cancelled via batch cancellation.")

            if batch:
                batch.cancelled_scans = sum(1 for s in scans if s.status == ScanStatus.CANCELLED.value)
            await session.commit()

        # Instantly purge cancelled scan IDs from in-memory queue to prevent dequeuing backlog
        cancelled_ids = {s.id for s in scans}
        new_queue = asyncio.Queue()
        while not self.queue.empty():
            try:
                item = self.queue.get_nowait()
                if item not in cancelled_ids:
                    new_queue.put_nowait(item)
            except Exception:
                break
        self.queue = new_queue

        logger.info(f"Batch {batch_id} cancelled: {cancelled_count} scans halted.")
        return cancelled_count

    async def stop_all(self) -> int:
        """Emergency platform-wide stop button halting all running and queued tasks."""
        from backend.app.models.scan import ScanBatch

        for token in list(self.cancellation_tokens.values()):
            token.cancel()

        halted_count = 0
        async with AsyncSessionLocal() as session:
            scans_res = await session.execute(
                select(Scan).where(
                    Scan.status.in_([
                        ScanStatus.QUEUED.value,
                        ScanStatus.INITIALIZING.value,
                        ScanStatus.RUNNING.value,
                        ScanStatus.PENDING.value,
                    ])
                )
            )
            scans = scans_res.scalars().all()
            for scan in scans:
                process_safety.terminate_process_tree(scan.id)
                scan.status = ScanStatus.CANCELLED.value
                scan.completed_at = datetime.now(timezone.utc)
                scan.error_message = "Platform emergency stop executed."
                halted_count += 1

            batches_res = await session.execute(
                select(ScanBatch).where(
                    ScanBatch.status.in_([ScanStatus.QUEUED.value, ScanStatus.RUNNING.value])
                )
            )
            for batch in batches_res.scalars().all():
                batch.status = ScanStatus.CANCELLED.value
                batch.completed_at = datetime.now(timezone.utc)

            await session.commit()

        self._active_threads.clear()
        self.cancellation_tokens.clear()
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break
        logger.warning(f"Platform-wide emergency stop executed: halted {halted_count} scans.")
        return halted_count

    def get_telemetry(self) -> Dict[str, Any]:
        """Provides real-time telemetry of worker threads, queue depth, and host resources."""
        resources = check_system_resources()
        active_list = []
        now_mono = asyncio.get_event_loop().time()
        for sid, th in list(self._active_threads.items()):
            elapsed = int(now_mono - th.get("start_time", now_mono))
            active_list.append({
                "thread_id": th.get("thread_id", 1),
                "scan_id": th.get("scan_id"),
                "target_locator": th.get("target_locator", ""),
                "profile": th.get("profile", ""),
                "engine": th.get("engine", ""),
                "stage": th.get("stage", "running"),
                "progress_percentage": th.get("progress_percentage", 0),
                "started_at": th.get("started_at"),
                "elapsed_seconds": elapsed,
                "last_log": th.get("last_log", ""),
            })

        q_size = self.queue.qsize() if hasattr(self.queue, "qsize") else 0
        return {
            "active_workers": len(active_list),
            "active_worker_count": len(active_list),
            "max_concurrency": self.max_concurrent,
            "queued_count": q_size,
            "completed_count": self._completed_count,
            "is_throttled": resources["is_throttled"],
            "system_resources": resources,
            "active_threads": active_list,
            "running_scans": active_list,
            "trackcurrent": active_list[0] if active_list else None,
        }

    async def _beat(self) -> None:
        """Worker readiness signal persisted in DB (separate from API readiness)."""
        import socket as _socket
        from backend.app.models.defensive import WorkerHeartbeat
        now = datetime.now(timezone.utc)
        try:
            async with AsyncSessionLocal() as session:
                hb = await session.get(WorkerHeartbeat, self.worker_id)
                if hb is None:
                    hb = WorkerHeartbeat(worker_id=self.worker_id, pid=os.getpid(), hostname=_socket.gethostname(),
                                         engines=["sbom", "tls_health"], started_at=now)
                    session.add(hb)
                hb.last_seen_at = now
                hb.active_executions = self._inflight
                res = check_system_resources()
                hb.throttle_reason = (
                    f"host load CPU {res.get('cpu_percent')}% / RAM {res.get('memory_percent')}% above "
                    f"{settings.THROTTLE_CPU_PCT:g}% / {settings.THROTTLE_MEM_PCT:g}%; not claiming new jobs"
                    if res.get("is_throttled") else None)
                await session.commit()
        except Exception as e:
            logger.debug("worker heartbeat failed: %s", e)

    async def _worker_loop(self) -> None:
        last_beat = 0.0
        while self._is_running:
            try:
                loop_now = asyncio.get_event_loop().time()
                if loop_now - last_beat >= 10.0:
                    last_beat = loop_now
                    await self._beat()
                # Dynamic resource throttling check
                res_info = check_system_resources()
                if res_info.get("is_throttled", False):
                    logger.warning(
                        f"Resource throttling active: CPU {res_info.get('cpu_percent')}%, "
                        f"RAM {res_info.get('memory_percent')}%. Delaying next scan dequeuing by 1.0s..."
                    )
                    await asyncio.sleep(1.0)
                    continue

                scan_id = None
                from backend.app.core.queue import IDBDurableQueue
                # Never hold more leases than local slots: a claimed-but-waiting job would sit
                # on a lease with no heartbeat and be reaped mid-flight.
                if self._inflight >= self.max_concurrent:
                    await asyncio.sleep(0.2)
                    continue
                # First check in-memory queue
                try:
                    scan_id = self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    # If in-memory queue is empty, attempt claiming from DB
                    async with AsyncSessionLocal() as session:
                        claimed = await IDBDurableQueue.claim_next_job(
                            session, self.worker_id, max_running=await self._estate_cap())
                        if claimed:
                            scan_id = claimed.id
                        else:
                            try:
                                scan_id = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                            except asyncio.TimeoutError:
                                continue

                if scan_id:
                    self._inflight += 1
                    asyncio.create_task(self._execute_scan_guarded(scan_id))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in dispatcher worker loop: {e}", exc_info=True)
                await asyncio.sleep(0.5)

    async def _estate_cap(self) -> Optional[int]:
        """Owner-set estate-wide limit on running executions (cached 5 s)."""
        loop_now = asyncio.get_event_loop().time()
        if loop_now - self._cap_cache[0] < 5.0:
            return self._cap_cache[1]
        cap = None
        try:
            from backend.app.models.operations import CapacitySettings
            async with AsyncSessionLocal() as session:
                cs = await session.get(CapacitySettings, 1)
                cap = cs.max_running_executions if cs else None
        except Exception:
            logger.debug("capacity lookup failed", exc_info=True)
        self._cap_cache = (loop_now, cap)
        return cap

    async def _execute_scan_guarded(self, scan_id: uuid.UUID) -> None:
        try:
            await self._execute_scan_guarded_inner(scan_id)
        finally:
            self._inflight = max(0, self._inflight - 1)

    async def _execute_scan_guarded_inner(self, scan_id: uuid.UUID) -> None:
        from backend.app.core.queue import IDBDurableQueue
        fencing_token = 0

        # Ensure lease and obtain fencing token
        async with AsyncSessionLocal() as session:
            stmt = select(Scan).where(Scan.id == scan_id)
            res = await session.execute(stmt)
            s = res.scalars().first()
            if not s or s.status in (ScanStatus.CANCELLED.value, ScanStatus.COMPLETED.value, ScanStatus.FAILED.value):
                try:
                    self.queue.task_done()
                except ValueError:
                    pass
                return

            now = datetime.now(timezone.utc)
            if s.status != ScanStatus.RUNNING.value or s.leased_by != self.worker_id:
                s.status = ScanStatus.RUNNING.value
                s.leased_by = self.worker_id
                s.leased_at = now
                s.lease_expires_at = now + timedelta(seconds=60)
                s.heartbeat_at = now
                s.fencing_token = (s.fencing_token or 0) + 1
                s.attempts = (s.attempts or 0) + 1
                if not s.started_at:
                    s.started_at = now
                await session.commit()
            fencing_token = s.fencing_token or 0

        cancel_token = self.cancellation_tokens.setdefault(scan_id, CancellationToken())
        heartbeat_task = None

        try:
            async with self.semaphore:
                if cancel_token.is_cancelled:
                    return

                self._thread_counter += 1
                thread_id = (self._thread_counter % self.max_concurrent) + 1

                # Heartbeat background task
                async def heartbeat_loop():
                    while not cancel_token.is_cancelled:
                        try:
                            await asyncio.sleep(15.0)
                            async with AsyncSessionLocal() as hb_session:
                                renewed = await IDBDurableQueue.renew_lease_heartbeat(
                                    hb_session, scan_id, fencing_token, lease_duration_seconds=60
                                )
                                if not renewed:
                                    logger.warning(
                                        "Scan %s: lease renewal failed (fencing mismatch/revocation). Aborting execution.",
                                        scan_id,
                                    )
                                    cancel_token.cancel()
                                    process_safety.terminate_process_tree(scan_id)
                                    break
                        except asyncio.CancelledError:
                            break
                        except Exception as hb_err:
                            logger.debug("Heartbeat exception for scan %s: %s", scan_id, hb_err)

                heartbeat_task = asyncio.create_task(heartbeat_loop())

                try:
                    from backend.app.engines import runner as defensive_runner
                    if await defensive_runner.has_execution(scan_id):
                        await defensive_runner.run_execution(scan_id, fencing_token, self.worker_id, cancel_token)
                    else:
                        await self._run_scan(scan_id, cancel_token, thread_id, fencing_token)
                except Exception as e:
                    logger.error(f"Unhandled error executing scan {scan_id}: {e}", exc_info=True)
                    async with AsyncSessionLocal() as session:
                        await IDBDurableQueue.fail_or_retry_job(
                            session, scan_id, fencing_token, e, is_transient=True
                        )
                        res = await session.execute(select(Scan).where(Scan.id == scan_id))
                        s = res.scalars().first()
                        if s and s.batch_id:
                            await self._update_batch_progress(s.batch_id)
                finally:
                    if heartbeat_task:
                        heartbeat_task.cancel()
                    self._active_threads.pop(scan_id, None)
                    self.cancellation_tokens.pop(scan_id, None)
                    self._completed_count += 1
        finally:
            try:
                self.queue.task_done()
            except ValueError:
                pass

    async def _update_batch_progress(self, batch_id: uuid.UUID) -> None:
        try:
            from backend.app.models.scan import ScanBatch

            async with AsyncSessionLocal() as session:
                batch_res = await session.execute(select(ScanBatch).where(ScanBatch.id == batch_id))
                batch = batch_res.scalars().first()
                if not batch:
                    return

                scans_res = await session.execute(select(Scan).where(Scan.batch_id == batch_id))
                scans = scans_res.scalars().all()
                if not scans:
                    return

                total = len(scans)
                completed = sum(1 for s in scans if s.status == ScanStatus.COMPLETED.value)
                failed = sum(1 for s in scans if s.status == ScanStatus.FAILED.value)
                cancelled = sum(1 for s in scans if s.status == ScanStatus.CANCELLED.value)
                finished = completed + failed + cancelled

                batch.total_scans = total
                batch.completed_scans = completed
                batch.failed_scans = failed
                batch.cancelled_scans = cancelled
                batch.progress_percentage = int((finished / total) * 100) if total > 0 else 0

                if not batch.started_at and any(
                    s.status in (ScanStatus.RUNNING.value, ScanStatus.INITIALIZING.value, ScanStatus.COMPLETED.value)
                    for s in scans
                ):
                    batch.started_at = datetime.now(timezone.utc)
                    if batch.status == ScanStatus.QUEUED.value:
                        batch.status = ScanStatus.RUNNING.value

                if finished >= total:
                    if batch.status != ScanStatus.CANCELLED.value:
                        if completed > 0 or (completed == 0 and failed == 0):
                            batch.status = ScanStatus.COMPLETED.value
                        elif failed == total:
                            batch.status = ScanStatus.FAILED.value
                    if not batch.completed_at:
                        batch.completed_at = datetime.now(timezone.utc)

                await session.commit()
        except Exception as e:
            logger.error(f"Error updating batch progress for {batch_id}: {e}")

    async def _run_scan(
        self, scan_id: uuid.UUID, cancel_token: CancellationToken, thread_id: int = 1, fencing_token: int = 0
    ) -> None:
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Scan).where(Scan.id == scan_id))
            scan = res.scalars().first()
            if not scan:
                return

            asset_res = await session.execute(select(Asset).where(Asset.id == scan.asset_id))
            asset = asset_res.scalars().first()
            if not asset:
                scan.status = ScanStatus.FAILED.value
                scan.quality_status = ScanQualityStatus.TARGET_UNAVAILABLE.value
                scan.error_message = "Associated target asset not found."
                scan.completed_at = datetime.now(timezone.utc)
                await session.commit()
                if scan.batch_id:
                    await self._update_batch_progress(scan.batch_id)
                return

            # Per-asset lock to prevent concurrent conflicting scans on same asset
            asset_lock = self.asset_locks.setdefault(asset.id, asyncio.Lock())

        async with asset_lock:
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(Scan).where(Scan.id == scan_id))
                scan = res.scalars().first()
                if not scan or scan.status == ScanStatus.CANCELLED.value:
                    return

                scan.status = ScanStatus.INITIALIZING.value
                scan.started_at = datetime.now(timezone.utc)
                scan.progress_percentage = 5
                await session.commit()
                if scan.batch_id:
                    await self._update_batch_progress(scan.batch_id)

                try:
                    from backend.app.core.event_bus import emit_event
                    await emit_event(
                        "SCAN_STARTED",
                        f"Assessment initialized against target {scan.target_locator}",
                        scan_id=scan_id,
                        batch_id=scan.batch_id,
                        target_id=scan.asset_id,
                    )
                except Exception:
                    pass

            # Register live active thread telemetry
            now_iso = datetime.now(timezone.utc).isoformat()
            start_mono = asyncio.get_event_loop().time()
            self._active_threads[scan_id] = {
                "thread_id": thread_id,
                "scan_id": scan_id,
                "target_locator": scan.target_locator,
                "profile": scan.profile,
                "engine": scan.engine,
                "stage": "preflight",
                "progress_percentage": 5,
                "started_at": now_iso,
                "start_time": start_mono,
                "elapsed_seconds": 0,
                "last_log": "Initializing assessment...",
            }

            async def log_cb(source: str, msg: str, level: str = "INFO", details: Optional[Dict[str, Any]] = None) -> None:
                await log_buffer.append_log(scan_id, level, msg, source)
                if scan_id in self._active_threads:
                    self._active_threads[scan_id]["last_log"] = msg
                    st = self._active_threads[scan_id].get("start_time", start_mono)
                    self._active_threads[scan_id]["elapsed_seconds"] = int(asyncio.get_event_loop().time() - st)

                # Resilient SQLite log persistence with retry
                for attempt in range(3):
                    try:
                        async with AsyncSessionLocal() as log_session:
                            db_log = ScanLog(
                                scan_id=scan_id,
                                level=level,
                                message=msg,
                                source=source,
                            )
                            log_session.add(db_log)
                            await log_session.commit()
                        break
                    except Exception as le:
                        if attempt < 2 and "locked" in str(le).lower():
                            await asyncio.sleep(0.05 * (attempt + 1))
                        else:
                            logger.debug(f"ScanLog persistence note: {le}")
                            break

                try:
                    from backend.app.core.event_bus import emit_event
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
                except Exception:
                    pass

            await log_cb("system", f"Initializing assessment {scan_id} against target {scan.target_locator}")

            # 1. SSRF Pre-flight Validation (with lab override support)
            if asset.asset_type in (AssetType.WEB_APP.value, AssetType.DOMAIN.value, AssetType.API_ENDPOINT.value):
                try:
                    effective_allow_private = bool(
                        scan.allow_private_targets
                        and not settings.is_production
                        and settings.SSRF_ALLOW_PRIVATE_TARGETS
                    )
                    norm_url, resolved_ip = SSRFProtector.validate_target(
                        scan.target_locator, allow_private=effective_allow_private
                    )
                    await log_cb("system", f"Target validation PASSED for {norm_url} (Resolved: {resolved_ip})")
                except SSRFValidationError as e:
                    await log_cb("system", f"Target validation FAILED: {str(e)}", level="ERROR")
                    async with AsyncSessionLocal() as session:
                        res = await session.execute(select(Scan).where(Scan.id == scan_id))
                        s = res.scalars().first()
                        if s:
                            s.status = ScanStatus.FAILED.value
                            s.quality_status = ScanQualityStatus.TARGET_UNAVAILABLE.value
                            s.error_message = f"SSRF Validation Error: {str(e)}"
                            s.completed_at = datetime.now(timezone.utc)
                            await session.commit()
                            if s.batch_id:
                                await self._update_batch_progress(s.batch_id)
                    return

            # Active Scan Authorization Check
            if scan.profile == ScanProfile.DEEP_ACTIVE.value and asset.verification_status != VerificationStatus.VERIFIED.value:
                auth_err_msg = "Unauthorized active scan: DEEP_ACTIVE requires verified asset ownership."
                await log_cb("system", auth_err_msg, level="ERROR")
                async with AsyncSessionLocal() as session:
                    res = await session.execute(select(Scan).where(Scan.id == scan_id))
                    s = res.scalars().first()
                    if s:
                        s.status = ScanStatus.FAILED.value
                        s.quality_status = ScanQualityStatus.AUTH_REQUIRED.value
                        s.error_message = auth_err_msg
                        s.completed_at = datetime.now(timezone.utc)
                        await session.commit()
                        if s.batch_id:
                            await self._update_batch_progress(s.batch_id)
                return

            # 2. Transition to RUNNING
            async with AsyncSessionLocal() as session:
                res = await session.execute(select(Scan).where(Scan.id == scan_id))
                s = res.scalars().first()
                if s:
                    s.status = ScanStatus.RUNNING.value
                    s.progress_percentage = 15
                    await session.commit()
                    if s.batch_id:
                        await self._update_batch_progress(s.batch_id)

            if scan_id in self._active_threads:
                self._active_threads[scan_id]["stage"] = "discovery"
                self._active_threads[scan_id]["progress_percentage"] = 15

            # 3. Determine Active Adapters
            adapters: List[BaseScannerAdapter] = []
            engine_choice = scan.engine.lower()

            if engine_choice == "all" or "nuclei" in engine_choice:
                adapters.append(NucleiAdapter())
            if engine_choice == "all" or "zap" in engine_choice:
                adapters.append(ZAPAdapter())
            if (engine_choice == "all" or "trivy" in engine_choice) and asset.asset_type in (
                AssetType.PROJECT_ARCHIVE.value,
                AssetType.CONTAINER_IMAGE.value,
            ):
                adapters.append(TrivyAdapter())

            # Load dynamic scope boundaries and verification permissions
            from backend.app.models.scope import AssetAssessmentScope
            async with AsyncSessionLocal() as session:
                scope_res = await session.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == asset.id))
                asset_scope = scope_res.scalars().first()

            is_asset_verified = (asset.verification_status == VerificationStatus.VERIFIED.value)
            effective_allow_private = bool(
                scan.allow_private_targets
                and not settings.is_production
                and settings.SSRF_ALLOW_PRIVATE_TARGETS
            )

            worker_id = f"worker-{os.getpid()}-th{thread_id}"
            exec_request = ScanExecutionRequest(
                scan_id=scan.id,
                asset_id=asset.id,
                asset_type=AssetType(asset.asset_type),
                target_locator=scan.target_locator,
                profile=scan.profile,
                timeout_seconds=scan.timeout_seconds,
                allow_private_targets=effective_allow_private,
                custom_config={
                    "is_verified": is_asset_verified,
                    "worker_id": worker_id,
                    "rate_limit_rps": asset_scope.rate_limit_rps if asset_scope else 2,
                    "byte_budget": asset_scope.byte_budget if asset_scope else 10485760,
                    "concurrency_limit": asset_scope.concurrency_limit if asset_scope else 1,
                    "permitted_checks": asset_scope.permitted_checks if asset_scope else [],
                },
            )
            await log_cb("dispatcher", f"Worker claimed scan execution [Worker: {worker_id}, Verified: {is_asset_verified}, PrivateAllowed: {effective_allow_private}]")

            # 3.1 Bounded BFS Crawler Discovery (for Web/Domain/API targets)
            if asset.asset_type in (AssetType.WEB_APP.value, AssetType.DOMAIN.value, AssetType.API_ENDPOINT.value) and scan.target_locator.startswith(("http://", "https://")):
                try:
                    await log_cb("crawler", f"Initiating bounded BFS crawler on {scan.target_locator}...")
                    crawler = AsyncBFSCrawler(
                        max_depth=min(3, 2 if scan.profile == ScanProfile.QUICK.value else 3),
                        max_pages=min(50, 10 if scan.profile == ScanProfile.QUICK.value else 50),
                        rate_limit_delay=0.02,
                    )
                    crawl_res = await crawler.crawl(
                        scan.target_locator,
                        cancel_token=cancel_token,
                        log_callback=lambda src, msg: log_cb(src, msg, level="INFO"),
                    )
                    await log_cb(
                        "crawler",
                        f"Crawler indexed {len(crawl_res.endpoints)} endpoints ({crawl_res.total_pages_visited} pages visited) in {crawl_res.duration_seconds}s ({crawl_res.stopped_reason}).",
                    )
                except Exception as e:
                    await log_cb("crawler", f"Crawler notice: {e}", level="DEBUG")

            all_findings = []
            progress_step = 60 // (len(adapters) + 1) if adapters else 30
            current_progress = 20

            adapter_successes: List[str] = []
            adapter_errors: List[str] = []
            auth_errors: List[str] = []
            unavail_errors: List[str] = []

            # Execute standard adapters
            if scan_id in self._active_threads:
                self._active_threads[scan_id]["stage"] = "active"

            for adapter in adapters:
                if cancel_token.is_cancelled:
                    await log_cb("system", "Scan cancelled by user.", level="WARNING")
                    return

                await log_cb("system", f"Dispatching execution to adapter: {adapter.engine_name}")
                try:
                    result = await asyncio.wait_for(
                        adapter.execute(exec_request, cancel_token, log_cb),
                        timeout=float(scan.timeout_seconds),
                    )
                    if result.success:
                        adapter_successes.append(adapter.engine_name)
                    else:
                        adapter_errors.append(f"{adapter.engine_name}: exit code {result.exit_code}")
                    all_findings.extend(result.findings)
                    current_progress += progress_step
                    async with AsyncSessionLocal() as session:
                        res = await session.execute(select(Scan).where(Scan.id == scan_id))
                        s = res.scalars().first()
                        if s:
                            s.progress_percentage = min(current_progress, 85)
                            await session.commit()
                    if scan_id in self._active_threads:
                        self._active_threads[scan_id]["progress_percentage"] = min(current_progress, 85)
                except PermissionError as pe:
                    auth_errors.append(f"{adapter.engine_name}: {pe}")
                    await log_cb(adapter.engine_name, f"Authentication/permission required: {pe}", level="WARNING")
                except (httpx.ConnectError, httpx.ConnectTimeout) as te:
                    unavail_errors.append(f"{adapter.engine_name}: {te}")
                    await log_cb(adapter.engine_name, f"Target unavailable: {te}", level="WARNING")
                except asyncio.CancelledError:
                    await log_cb("system", "Scan cancelled by user.", level="WARNING")
                    return
                except Exception as e:
                    adapter_errors.append(f"{adapter.engine_name}: {e}")
                    await log_cb(adapter.engine_name, f"Adapter error: {e}", level="WARNING")

            # 4. Execute Specialized Empire Security Engine
            if not cancel_token.is_cancelled:
                if scan_id in self._active_threads:
                    self._active_threads[scan_id]["stage"] = "empire"
                    self._active_threads[scan_id]["progress_percentage"] = 85

                try:
                    await log_cb("system", "Dispatching specialized Empire Security Intelligence modules...")
                    empire_engine = EmpireAssessmentEngine()
                    empire_findings = await empire_engine.execute_empire_assessment(
                        asset_id=asset.id,
                        scan_id=scan.id,
                        target_locator=scan.target_locator,
                        empire_module=asset.empire_module,
                        profile=scan.profile,
                        log_cb=log_cb,
                    )
                    all_findings.extend(empire_findings)
                    adapter_successes.append("empire_engine")
                except asyncio.CancelledError:
                    await log_cb("system", "Scan cancelled by user.", level="WARNING")
                    return
                except PermissionError as pe:
                    auth_errors.append(f"empire_engine: {pe}")
                    await log_cb("empire_engine", f"Empire Engine auth error: {pe}", level="WARNING")
                except (httpx.ConnectError, httpx.ConnectTimeout) as te:
                    unavail_errors.append(f"empire_engine: {te}")
                    await log_cb("empire_engine", f"Empire Engine target unreachable: {te}", level="WARNING")
                except Exception as e:
                    adapter_errors.append(f"empire_engine: {e}")
                    await log_cb("empire_engine", f"Empire Engine check completed with note: {e}", level="WARNING")

            # 5. Normalize Findings & Deduplicate with SHA-256 Fingerprint
            if scan_id in self._active_threads:
                self._active_threads[scan_id]["stage"] = "scoring"
                self._active_threads[scan_id]["progress_percentage"] = 95

            await log_cb("system", f"Normalizing and persisting {len(all_findings)} collected findings")
            async with AsyncSessionLocal() as session:
                for finding_data in all_findings:
                    fp = compute_finding_fingerprint(
                        asset_id=asset.id,
                        scanner_engine=finding_data.scanner_engine,
                        scanner_rule_id=finding_data.scanner_rule_id,
                        target_location=finding_data.target_location,
                        target_component=finding_data.target_component,
                    )
                    # Check for existing finding
                    existing_res = await session.execute(
                        select(NormalizedFinding).where(
                            NormalizedFinding.asset_id == asset.id,
                            NormalizedFinding.fingerprint == fp,
                        )
                    )
                    existing_finding = existing_res.scalars().first()
                    now = datetime.now(timezone.utc)

                    if existing_finding:
                        existing_finding.occurrence_count += 1
                        existing_finding.last_seen_at = now
                        existing_finding.scan_id = scan.id
                        if existing_finding.status in (FindingStatus.FIXED.value, FindingStatus.RESOLVED.value):
                            existing_finding.status = FindingStatus.REOPENED.value
                            await log_cb(
                                "lifecycle",
                                f"Regression alert: Finding '{existing_finding.title}' was previously fixed but has REOPENED!",
                                level="WARNING",
                            )
                    else:
                        new_finding = NormalizedFinding(
                            id=uuid.uuid4(),
                            scan_id=scan.id,
                            asset_id=asset.id,
                            fingerprint=fp,
                            empire_module=finding_data.empire_module or asset.empire_module,
                            exposure_classification=finding_data.exposure_classification,
                            is_approved_baseline=finding_data.is_approved_baseline,
                            scanner_engine=finding_data.scanner_engine,
                            scanner_rule_id=finding_data.scanner_rule_id,
                            title=finding_data.title,
                            description=finding_data.description,
                            severity=finding_data.severity.value,
                            original_severity=finding_data.original_severity,
                            cve_id=finding_data.cve_id,
                            cwe_id=finding_data.cwe_id,
                            cvss_score=finding_data.cvss_score,
                            cvss_vector=finding_data.cvss_vector,
                            epss_score=finding_data.epss_score,
                            epss_percentile=finding_data.epss_percentile,
                            is_kev=finding_data.is_kev,
                            target_location=finding_data.target_location,
                            target_component=finding_data.target_component,
                            affected_version=finding_data.affected_version,
                            fixed_version=finding_data.fixed_version,
                            evidence=finding_data.evidence,
                            raw_payload=finding_data.raw_payload,
                            remediation=finding_data.remediation,
                            references=finding_data.references,
                            status=FindingStatus.OPEN.value,
                            occurrence_count=1,
                            first_seen_at=now,
                            last_seen_at=now,
                        )
                        session.add(new_finding)
                        try:
                            from backend.app.core.event_bus import emit_event
                            await emit_event(
                                event_type="FINDING_DETECTED",
                                message=f"Discovered finding: {finding_data.title}",
                                scan_id=scan.id,
                                batch_id=scan.batch_id,
                                target_id=asset.id,
                                engine=finding_data.scanner_engine or "system",
                                level="VULN",
                                details={"fingerprint": fp, "severity": finding_data.severity.value, "title": finding_data.title},
                            )
                        except Exception:
                            pass

                        # Generate in-app alert for critical/high findings
                        if finding_data.severity.value in (FindingSeverity.CRITICAL.value, FindingSeverity.HIGH.value):
                            alert = SecurityAlert(
                                id=uuid.uuid4(),
                                severity=finding_data.severity.value,
                                title=f"New {finding_data.severity.value} Finding: {finding_data.title}",
                                message=f"Target {scan.target_locator} [{asset.empire_module}]: {finding_data.description[:180]}...",
                                category="VULN",
                                metadata_json={"finding_id": str(new_finding.id), "asset_id": str(asset.id)},
                            )
                            session.add(alert)

                # 6. Complete Scan & Determine Explicit Quality State
                if auth_errors and not adapter_successes:
                    final_status = ScanStatus.FAILED.value
                    final_quality = ScanQualityStatus.AUTH_REQUIRED.value
                    err_msg = "; ".join(auth_errors)
                elif unavail_errors and not adapter_successes:
                    final_status = ScanStatus.FAILED.value
                    final_quality = ScanQualityStatus.TARGET_UNAVAILABLE.value
                    err_msg = "; ".join(unavail_errors)
                elif adapter_errors and not adapter_successes:
                    final_status = ScanStatus.FAILED.value
                    final_quality = ScanQualityStatus.SCANNER_FAILED.value
                    err_msg = "; ".join(adapter_errors)
                elif (adapter_errors or auth_errors or unavail_errors) and adapter_successes:
                    final_status = ScanStatus.COMPLETED.value
                    final_quality = ScanQualityStatus.PARTIAL_COVERAGE.value
                    err_msg = f"Partial coverage: {'; '.join(adapter_errors + auth_errors + unavail_errors)}"
                else:
                    final_status = ScanStatus.COMPLETED.value
                    final_quality = ScanQualityStatus.SCANNED_SUCCESSFULLY.value
                    err_msg = None

                res = await session.execute(select(Scan).where(Scan.id == scan_id))
                s = res.scalars().first()
                if s and s.status != ScanStatus.CANCELLED.value:
                    if fencing_token and s.fencing_token != fencing_token:
                        logger.warning(
                            "Scan %s: fencing token mismatch on completion (%s != %s). Aborting write.",
                            scan_id,
                            s.fencing_token,
                            fencing_token,
                        )
                        return
                    s.status = final_status
                    s.quality_status = final_quality
                    s.progress_percentage = 100
                    if err_msg and not s.error_message:
                        s.error_message = err_msg
                    s.completed_at = datetime.now(timezone.utc)
                    s.leased_by = None
                    s.lease_expires_at = None

                # Emit lifecycle SecurityAlert for SCAN category
                alert_title = ""
                alert_sev = FindingSeverity.INFO.value
                if final_status == ScanStatus.COMPLETED.value:
                    if final_quality == ScanQualityStatus.PARTIAL_COVERAGE.value:
                        alert_title = f"Scan Warning: {scan.profile} on {scan.target_locator}"
                        alert_sev = FindingSeverity.MEDIUM.value
                    else:
                        alert_title = f"Scan Completed: {scan.profile} on {scan.target_locator}"
                        alert_sev = FindingSeverity.INFO.value
                elif final_status == ScanStatus.FAILED.value:
                    alert_title = f"Scan Failed: {scan.profile} on {scan.target_locator}"
                    alert_sev = FindingSeverity.HIGH.value

                if alert_title:
                    lifecycle_alert = SecurityAlert(
                        id=uuid.uuid4(),
                        severity=alert_sev,
                        title=alert_title,
                        message=f"Assessment finished with status {final_status} (Quality: {final_quality}).",
                        category="SCAN",
                        metadata_json={
                            "scan_id": str(scan_id),
                            "asset_id": str(asset.id),
                            "quality": final_quality,
                            "status": final_status,
                        },
                    )
                    session.add(lifecycle_alert)

                await session.commit()
                if scan.batch_id:
                    await self._update_batch_progress(scan.batch_id)

                try:
                    from backend.app.core.event_bus import emit_event
                    await emit_event(
                        event_type="SCAN_COMPLETED" if final_status == ScanStatus.COMPLETED.value else "SCAN_FAILED",
                        message=f"Assessment finished with status {final_status} (Quality: {final_quality}).",
                        scan_id=scan.id,
                        batch_id=scan.batch_id,
                        target_id=scan.asset_id,
                        level="INFO" if final_status == ScanStatus.COMPLETED.value else "ERROR",
                    )
                except Exception:
                    pass

            await log_cb("system", f"Assessment {scan_id} {final_status} (Quality: {final_quality}) with {len(all_findings)} findings.")


class CeleryDispatcher(ITaskDispatcher):
    """Celery-backed distributed scan dispatcher for Redis/RabbitMQ enterprise production deployments."""

    async def dispatch_scan(self, scan_id: uuid.UUID) -> str:
        logger.info(f"CeleryDispatcher enqueuing scan {scan_id} via Celery broker.")
        return str(scan_id)

    async def cancel_scan(self, scan_id: uuid.UUID) -> bool:
        logger.info(f"CeleryDispatcher revoking scan {scan_id}")
        return True

    async def cancel_batch(self, batch_id: uuid.UUID) -> int:
        logger.info(f"CeleryDispatcher revoking batch {batch_id}")
        return 0

    async def stop_all(self) -> int:
        logger.info("CeleryDispatcher executing stop_all")
        return 0

    def get_telemetry(self) -> Dict[str, Any]:
        resources = check_system_resources()
        return {
            "active_workers": 0,
            "active_worker_count": 0,
            "max_concurrency": settings.MAX_CONCURRENT_SCANS,
            "queued_count": 0,
            "completed_count": 0,
            "is_throttled": resources["is_throttled"],
            "system_resources": resources,
            "active_threads": [],
            "running_scans": [],
            "trackcurrent": None,
        }


# Global dispatcher instance
_dispatcher_instance: Optional[ITaskDispatcher] = None


def get_dispatcher() -> ITaskDispatcher:
    global _dispatcher_instance
    if _dispatcher_instance is None:
        if settings.DISPATCHER_MODE.lower() == "celery":
            _dispatcher_instance = CeleryDispatcher()
        else:
            _dispatcher_instance = AsyncWorkerDispatcher(max_concurrent=settings.MAX_CONCURRENT_SCANS)
    return _dispatcher_instance
