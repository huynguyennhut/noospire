"""Background Asynchronous Cron Scheduling and Coalescing Engine for Noosforge Sentinel.

Implements top-of-hour cron scheduling in Asia/Ho_Chi_Minh (stored in UTC),
active run deduplication, overrun coalescing (max 1 pending follow-up),
and periodic lease reaper recovery.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional, Set
import uuid
import zoneinfo

from sqlalchemy import select
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.dispatcher import get_dispatcher
from backend.app.core.queue import IDBDurableQueue
from backend.app.models.alert import SecurityAlert
from backend.app.models.asset import Asset
from backend.app.models.scan import Scan, ScanBatch
from backend.app.models.schedule import DailySchedule
from backend.app.schemas.common import ScanProfile, ScanStatus

logger = logging.getLogger("sentinel.scheduler")


def parse_cron_field(field_str: str, min_val: int, max_val: int) -> Set[int]:
    """Parses standard cron field syntax (*, */step, range, list, single number)."""
    values = set()
    for part in field_str.split(","):
        part = part.strip()
        if not part:
            continue
        if part == "*":
            values.update(range(min_val, max_val + 1))
        elif part.startswith("*/"):
            try:
                step = int(part[2:])
                values.update(range(min_val, max_val + 1, step))
            except ValueError:
                values.update(range(min_val, max_val + 1))
        elif "-" in part:
            try:
                start, end = part.split("-")
                values.update(range(int(start), int(end) + 1))
            except ValueError:
                pass
        else:
            try:
                values.add(int(part))
            except ValueError:
                pass
    return values or set(range(min_val, max_val + 1))


def compute_next_run(
    cron_expr: str,
    from_dt: Optional[datetime] = None,
    tz_str: str = "Asia/Ho_Chi_Minh",
) -> datetime:
    """Calculates next execution datetime based on standard 5-part cron syntax in specified timezone."""
    if from_dt is None:
        from_dt = datetime.now(timezone.utc)
    elif from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=timezone.utc)

    try:
        tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        tz = timezone.utc

    local_dt = from_dt.astimezone(tz)
    candidate = local_dt.replace(second=0, microsecond=0) + timedelta(minutes=1)

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return from_dt + timedelta(hours=1)

    try:
        minutes = parse_cron_field(parts[0], 0, 59)
        hours = parse_cron_field(parts[1], 0, 23)
        days = parse_cron_field(parts[2], 1, 31)
        months = parse_cron_field(parts[3], 1, 12)
        weekdays = parse_cron_field(parts[4], 0, 7)
        if 7 in weekdays:
            weekdays.add(0)

        # Probe forward up to 366 days
        max_probe_minutes = 60 * 24 * 366
        for _ in range(max_probe_minutes):
            if candidate.month not in months:
                candidate = (candidate.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
                continue
            wday = (candidate.weekday() + 1) % 7
            if candidate.day not in days or wday not in weekdays:
                candidate = (candidate + timedelta(days=1)).replace(hour=0, minute=0)
                continue
            if candidate.hour not in hours:
                candidate = (candidate + timedelta(hours=1)).replace(minute=0)
                continue
            if candidate.minute in minutes:
                return candidate.astimezone(timezone.utc)
            candidate += timedelta(minutes=1)
    except Exception:
        pass

    return from_dt + timedelta(hours=1)


class SchedulerEngine:
    """Background asynchronous cron scheduling ticker with overrun coalescing and lease recovery."""

    def __init__(self, interval_seconds: int = 30) -> None:
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._run_loop())
            logger.info("SchedulerEngine started with tick interval %ss", self.interval_seconds)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            logger.info("SchedulerEngine stopped cleanly")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in SchedulerEngine tick: %s", e, exc_info=True)
            await asyncio.sleep(self.interval_seconds)

    async def _launch_schedule_batch(
        self,
        session,
        sched: DailySchedule,
        is_followup: bool = False,
        missed_slots: int = 0,
    ) -> Optional[ScanBatch]:
        """Atomically plans and dispatches a scheduled assessment batch for all target assets."""
        now = datetime.now(timezone.utc)

        # 1. Resolve Target Assets
        if "ALL" in sched.target_ids:
            targets_res = await session.execute(select(Asset))
            targets = targets_res.scalars().all()
        else:
            uids = [uuid.UUID(t) if isinstance(t, str) else t for t in sched.target_ids]
            targets_res = await session.execute(select(Asset).where(Asset.id.in_(uids)))
            targets = targets_res.scalars().all()

        if not targets:
            logger.warning("No targets configured for schedule %s (id=%s)", sched.name, sched.id)
            sched.last_run_at = now
            sched.last_status = "NO_TARGETS"
            sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
            await session.commit()
            return None

        # 2. Instantiate Parent ScanBatch
        batch_name = f"{'[FOLLOW-UP] ' if is_followup else ''}Scheduled Assessment: {sched.name}"
        batch = ScanBatch(
            id=uuid.uuid4(),
            name=batch_name,
            schedule_id=sched.id,
            status=ScanStatus.QUEUED.value,
            target_count=len(targets),
            engines=["all"],
            profiles=[sched.profile],
            is_followup=is_followup,
            missed_slots_coalesced=missed_slots,
            metadata_json={
                "schedule_id": str(sched.id),
                "is_followup": is_followup,
                "missed_slots_coalesced": missed_slots,
                "triggered_at": now.isoformat(),
            },
        )
        session.add(batch)
        await session.flush()

        # 3. Create Scans under this Batch
        dispatcher = get_dispatcher()
        dispatched_scan_ids: List[uuid.UUID] = []
        allow_private = False if settings.is_production else settings.SSRF_ALLOW_PRIVATE_TARGETS

        for target in targets:
            scan = Scan(
                id=uuid.uuid4(),
                asset_id=target.id,
                batch_id=batch.id,
                engine="all",
                profile=sched.profile,
                status=ScanStatus.QUEUED.value,
                progress_percentage=0,
                target_locator=target.target_locator,
                allow_private_targets=allow_private,
                timeout_seconds=600,
            )
            session.add(scan)
            dispatched_scan_ids.append(scan.id)

        batch.total_scans = len(dispatched_scan_ids)

        # 4. Update Schedule State
        sched.active_batch_id = batch.id
        sched.last_run_at = now
        sched.last_status = "RUNNING"
        sched.overrun_active = False
        sched.overdue_reason = None
        sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)

        # 5. Emit Lifecycle Alert
        alert = SecurityAlert(
            id=uuid.uuid4(),
            severity="INFO",
            title=f"Scheduled Scan Triggered: {sched.name}",
            message=(
                f"{'[FOLLOW-UP] ' if is_followup else ''}Assessment schedule '{sched.name}' "
                f"launched across {len(targets)} targets (Batch: {batch.id})."
            ),
            category="SCAN",
            is_read=False,
            metadata_json={
                "schedule_id": str(sched.id),
                "batch_id": str(batch.id),
                "targets_count": len(targets),
                "is_followup": is_followup,
                "missed_slots_coalesced": missed_slots,
                "triggered_at": now.isoformat(),
            },
        )
        session.add(alert)
        await session.commit()

        # 6. Dispatch Scans
        for s_id in dispatched_scan_ids:
            await dispatcher.dispatch_scan(s_id)

        logger.info(
            "Launched scheduled batch %s for schedule %s with %s scans (followup=%s)",
            batch.id,
            sched.id,
            len(dispatched_scan_ids),
            is_followup,
        )
        return batch

    async def tick(self) -> int:
        """Executes one evaluation cycle for active DailySchedule configurations with overrun coalescing."""
        now = datetime.now(timezone.utc)
        triggered_count = 0

        async with AsyncSessionLocal() as session:
            # Step A: Periodic lease reaper recovery for abandoned or expired worker leases
            try:
                reaped = await IDBDurableQueue.recover_expired_leases(session)
                if reaped > 0:
                    logger.info("Lease reaper recovered %d expired/abandoned jobs", reaped)
            except Exception as e:
                logger.error("Error running lease reaper in scheduler tick: %s", e)

            # Step B: Evaluate active schedules
            stmt = select(DailySchedule).where(DailySchedule.is_active == True)
            res = await session.execute(stmt)
            schedules = res.scalars().all()

            for sched in schedules:
                # Ensure next_run_at is computed
                if sched.next_run_at is None:
                    sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
                    await session.commit()
                    continue

                next_run = sched.next_run_at
                if next_run.tzinfo is None:
                    next_run = next_run.replace(tzinfo=timezone.utc)
                else:
                    next_run = next_run.astimezone(timezone.utc)

                # Check if there is an active batch linked
                if sched.active_batch_id:
                    batch_res = await session.execute(
                        select(ScanBatch).where(ScanBatch.id == sched.active_batch_id)
                    )
                    active_batch = batch_res.scalars().first()

                    if active_batch and active_batch.status in (
                        ScanStatus.QUEUED.value,
                        ScanStatus.RUNNING.value,
                        ScanStatus.INITIALIZING.value,
                        ScanStatus.PENDING.value,
                    ):
                        # Batch is still actively executing!
                        # Check if slot interval has elapsed (i.e. now >= next_run) -> Overrun!
                        if now >= next_run:
                            sched.overrun_active = True
                            sched.pending_followup = True  # Coalesce to at most ONE follow-up
                            sched.missed_slots_count = (sched.missed_slots_count or 0) + 1
                            sched.overdue_reason = (
                                f"Run in progress exceeding slot interval (overrun active for batch {active_batch.id}); "
                                f"follow-up queued"
                            )
                            sched.last_status = "OVERRUN_COALESCING"
                            # Advance next_run_at to the subsequent top of hour to track future missed slots
                            sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
                            await session.commit()
                            logger.warning(
                                "Schedule %s overrun detected: batch %s taking >1h. Missed slots: %d",
                                sched.name,
                                active_batch.id,
                                sched.missed_slots_count,
                            )
                        # Keep current run intact; do not launch concurrent duplicate sweep
                        continue

                    else:
                        # Batch has finished (COMPLETED, FAILED, CANCELLED)
                        sched.last_completed_at = (
                            active_batch.completed_at if active_batch else now
                        )
                        if sched.pending_followup:
                            # Immediate follow-up trigger
                            logger.info(
                                "Active batch %s completed. Triggering single follow-up for schedule %s (coalesced: %d)",
                                sched.active_batch_id,
                                sched.name,
                                sched.missed_slots_count,
                            )
                            missed_count = sched.missed_slots_count
                            sched.pending_followup = False
                            sched.overrun_active = False
                            sched.missed_slots_count = 0
                            sched.overdue_reason = None
                            await self._launch_schedule_batch(
                                session, sched, is_followup=True, missed_slots=missed_count
                            )
                            triggered_count += 1
                            continue
                        else:
                            sched.active_batch_id = None
                            sched.overrun_active = False
                            sched.overdue_reason = None
                            sched.last_status = active_batch.status if active_batch else "IDLE"
                            await session.commit()

                # If no active batch running and due time has arrived
                if now >= next_run:
                    logger.info("Triggering scheduled assessment for %s (id=%s)", sched.name, sched.id)
                    await self._launch_schedule_batch(session, sched, is_followup=False, missed_slots=0)
                    triggered_count += 1

        return triggered_count


# Global singleton
_scheduler_engine = SchedulerEngine(interval_seconds=30)


def get_scheduler_engine() -> SchedulerEngine:
    return _scheduler_engine
