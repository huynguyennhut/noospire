"""Hourly monitor scheduler (Milestone 4).

Each tick, per active schedule:
  1. finalize launched slots whose quick-lane work is done (completed | partial | failed)
  2. due slot = floor(now, interval) aligned to the UTC epoch
     - new slot -> INSERT schedule_slots(schedule_id, slot_at) in the same transaction as the
       plan + executions. The unique constraint makes the claim atomic across schedulers:
       a second scheduler's commit fails and it rolls everything back.
     - previous run still active -> slot recorded as `coalesced`, `pending_catchup` set
       (at most ONE catch-up regardless of how many slots were coalesced)
     - slots skipped while no scheduler ran (restart / outage) are counted in `missed_before`
       and covered by the single launch of the newest slot
  3. pending catch-up and nothing active -> conditional UPDATE pending_catchup true->false
     (atomic) then launch it as kind=`catchup` on the newest coalesced slot.
Also runs the lease reaper and turns exhausted leases into dead-lettered executions.
"""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.planner import NOT_APPLICABLE, Selection, build_plan, materialize
from backend.app.models.defensive import (
    EXEC_FAILED,
    EXEC_QUEUED,
    EXEC_RUNNING,
    EXEC_SUCCEEDED,
    ExecutionRecord,
)
from backend.app.models.operations import CapacitySettings, MonitorSchedule, ScheduleSlot, SchedulerHeartbeat
from backend.app.models.scan import Scan, ScanBatch

log = logging.getLogger("noospire.scheduler")
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class _OwnerScope:
    """Schedules are created by the sole owner and run over the whole estate selection."""
    asset_ids = None

    def require(self, asset_id, action="READ"):
        return None

    def can(self, asset_id, action="READ"):
        return True

    def ids_with(self, action):
        return None


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def floor_slot(now: datetime, interval_minutes: int) -> datetime:
    step = interval_minutes * 60
    secs = int((now - EPOCH).total_seconds())
    return EPOCH + timedelta(seconds=secs - secs % step)


def next_slot_after(dt: datetime, interval_minutes: int) -> datetime:
    return floor_slot(dt, interval_minutes) + timedelta(minutes=interval_minutes)


async def active_work(db, schedule_id: uuid.UUID) -> int:
    """Quick-lane executions of this schedule not yet finished (long-lane deferrals don't block)."""
    batch_ids = select(ScheduleSlot.batch_id).where(ScheduleSlot.schedule_id == schedule_id,
                                                    ScheduleSlot.batch_id.is_not(None))
    return (await db.execute(select(func.count()).select_from(ExecutionRecord).where(
        ExecutionRecord.batch_id.in_(batch_ids), ExecutionRecord.lane == "quick",
        ExecutionRecord.status.in_((EXEC_QUEUED, EXEC_RUNNING))))).scalar() or 0


def _result_of(counts: dict, plan_summary: dict) -> str:
    total = sum(counts.values())
    ok = counts.get(EXEC_SUCCEEDED, 0)
    blocking_skips = {k: v for k, v in (plan_summary.get("reasons") or {}).items()
                      if k not in NOT_APPLICABLE and k != "HOST_SPACING"}
    if total == 0:
        return "no_work" if not blocking_skips else "partial"
    if ok == total and not blocking_skips and not plan_summary.get("defer"):
        return "completed"
    if ok == 0 and counts.get(EXEC_FAILED, 0) + counts.get("timed_out", 0) == total:
        return "failed"
    return "partial"


class MonitorScheduler:
    def __init__(self, interval_seconds: float = 15.0) -> None:
        self.interval_seconds = interval_seconds
        self.scheduler_id = f"scheduler-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception:
                log.exception("scheduler tick failed")
            await asyncio.sleep(self.interval_seconds)

    # ------------------------------------------------------------------ tick
    async def tick(self, now: Optional[datetime] = None) -> dict:
        now = now or datetime.now(timezone.utc)
        report = {"launched": 0, "coalesced": 0, "catchups": 0, "finalized": 0, "dead_letters": 0, "conflicts": 0}
        report["dead_letters"] = await reap_and_dead_letter()
        try:
            report["stale_alerts"] = await notify_stale_sources(now)
        except Exception:
            log.exception("stale source check failed")
        async with AsyncSessionLocal() as db:
            ids = (await db.execute(select(MonitorSchedule.id).where(MonitorSchedule.is_active == True))  # noqa
                   ).scalars().all()
        for sid in ids:
            try:
                await self._tick_schedule(sid, now, report)
            except (IntegrityError, OperationalError) as exc:
                report["conflicts"] += 1  # another scheduler owns this slot / write lock contention
                log.info("slot claim lost for schedule %s: %s", sid, type(exc).__name__)
        # Only completed ticks advertise readiness; a live but failing loop is stale.
        async with AsyncSessionLocal() as db:
            await db.merge(SchedulerHeartbeat(scheduler_id=self.scheduler_id,
                                             last_tick_at=datetime.now(timezone.utc)))
            await db.commit()
        return report

    async def _tick_schedule(self, sid: uuid.UUID, now: datetime, report: dict) -> None:
        from backend.app.core.event_bus import emit_event

        async with AsyncSessionLocal() as db:
            report["finalized"] += await finalize_slots(db, sid, now)
            await db.commit()

        async with AsyncSessionLocal() as db:
            s = await db.get(MonitorSchedule, sid)
            if s is None or not s.is_active:
                return
            capacity = await db.get(CapacitySettings, 1)
            if capacity and capacity.emergency_stop_active:
                s.overdue_reason = "Global emergency stop is active; scheduled work is paused."
                await db.commit()
                return
            due = floor_slot(now, s.interval_minutes)
            first_allowed = next_slot_after(_utc(s.start_after), s.interval_minutes) \
                if floor_slot(_utc(s.start_after), s.interval_minutes) < _utc(s.start_after) else _utc(s.start_after)
            last = _utc(s.last_slot_at)
            busy = await active_work(db, sid)
            s.next_run_at = due + timedelta(minutes=s.interval_minutes)

            if due >= first_allowed and (last is None or due > last):
                step = timedelta(minutes=s.interval_minutes)
                missed = 0
                if last is not None:
                    missed = int((due - last) / step) - 1
                elif due > first_allowed:
                    missed = int((due - first_allowed) / step)
                corr = f"slot-{uuid.uuid4().hex[:16]}"
                slot = ScheduleSlot(schedule_id=sid, slot_at=due, claimed_by=self.scheduler_id, status="claimed",
                                    missed_before=max(0, missed), correlation_id=corr)
                db.add(slot)
                await db.flush()  # unique (schedule_id, slot_at): the claim
                res = await db.execute(update(MonitorSchedule).where(
                    MonitorSchedule.id == sid,
                    (MonitorSchedule.last_slot_at.is_(None)) | (MonitorSchedule.last_slot_at < due))
                    .values(last_slot_at=due))
                if res.rowcount != 1:
                    await db.rollback()
                    report["conflicts"] += 1
                    return
                s.missed_slots = (s.missed_slots or 0) + max(0, missed)
                if busy:
                    slot.status = "coalesced"
                    slot.reason = f"Previous run still has {busy} unfinished quick execution(s); coalesced."
                    s.pending_catchup = True
                    s.missed_slots += 1
                    s.overdue_reason = slot.reason
                    await emit_event("SCHEDULE_SLOT_COALESCED", f"{s.name}: slot {due.isoformat()} coalesced",
                                     session=db, details={"schedule_id": str(sid), "slot_id": str(slot.id),
                                                          "slot_at": due.isoformat(), "missed_slots": s.missed_slots,
                                                          "correlation_id": corr})
                    report["coalesced"] += 1
                else:
                    await self._launch(db, s, slot, now, kind="scheduled", coalesced=max(0, missed))
                    report["launched"] += 1
                await db.commit()
                return

            if s.pending_catchup and not busy:
                res = await db.execute(update(MonitorSchedule).where(MonitorSchedule.id == sid,
                                                                     MonitorSchedule.pending_catchup == True)  # noqa
                                       .values(pending_catchup=False))
                if res.rowcount != 1:
                    await db.rollback()
                    return
                slot = (await db.execute(select(ScheduleSlot).where(ScheduleSlot.schedule_id == sid,
                                                                    ScheduleSlot.status == "coalesced")
                                         .order_by(ScheduleSlot.slot_at.desc()).limit(1))).scalars().first()
                if slot is None:
                    await db.commit()
                    return
                await self._launch(db, s, slot, now, kind="catchup", coalesced=s.missed_slots)
                report["catchups"] += 1
                await db.commit()
                return
            await db.commit()

    async def _launch(self, db, s: MonitorSchedule, slot: ScheduleSlot, now: datetime, kind: str,
                      coalesced: int) -> None:
        plan = await build_plan(db, selection=Selection.parse(s.selection), engines=s.engines, profile=s.profile,
                                trigger="schedule" if kind == "scheduled" else "schedule_catchup",
                                scope=_OwnerScope(), window_seconds=s.interval_minutes * 60,
                                max_workers=s.max_workers, now=now)
        corr = slot.correlation_id or f"slot-{uuid.uuid4().hex[:16]}"
        batch = await materialize(db, plan, name=f"{'Catch-up' if kind == 'catchup' else 'Scheduled'} · {s.name} · "
                                  f"{_utc(slot.slot_at).isoformat()}", actor_id=s.created_by, correlation_id=corr,
                                  schedule_slot_id=slot.id, schedule_id=s.id)
        batch.is_followup = kind == "catchup"
        batch.missed_slots_coalesced = coalesced
        slot.kind = kind
        slot.status = "launched"
        slot.launched_at = now
        slot.batch_id = batch.id
        slot.coalesced_slots = coalesced
        slot.correlation_id = corr
        slot.plan_summary = plan.summary()
        s.last_run_at = now
        s.last_batch_id = batch.id
        s.missed_slots = 0
        s.overdue_reason = None
        if plan.summary()["defer"]:
            s.overdue_reason = (f"{plan.summary()['defer']} execution(s) deferred "
                                f"({', '.join(k for k in plan.summary()['reasons'] if k in ('HOST_QUOTA', 'EGRESS_BUDGET', 'WINDOW_OVERFLOW'))}); "
                                f"resume at {plan.summary()['deferred_resume_at']}")
        from backend.app.core.event_bus import emit_event
        await emit_event("SCHEDULE_SLOT_LAUNCHED", f"{s.name}: {kind} run for slot {_utc(slot.slot_at).isoformat()}",
                         batch_id=batch.id, session=db,
                         details={"schedule_id": str(s.id), "slot_id": str(slot.id), "kind": kind,
                                  "coalesced_slots": coalesced, "correlation_id": corr, "summary": plan.summary()})


async def finalize_slots(db, schedule_id: uuid.UUID, now: datetime) -> int:
    from backend.app.core.event_bus import emit_event

    slots = (await db.execute(select(ScheduleSlot).where(ScheduleSlot.schedule_id == schedule_id,
                                                         ScheduleSlot.status == "launched"))).scalars().all()
    done = 0
    for slot in slots:
        rows = (await db.execute(select(ExecutionRecord.status, ExecutionRecord.lane, func.count())
                                 .where(ExecutionRecord.batch_id == slot.batch_id)
                                 .group_by(ExecutionRecord.status, ExecutionRecord.lane))).all()
        if any(st in (EXEC_QUEUED, EXEC_RUNNING) and lane == "quick" for st, lane, _ in rows):
            continue
        counts: dict = {}
        long_pending = 0
        for st, lane, n in rows:
            if st in (EXEC_QUEUED, EXEC_RUNNING):
                long_pending += n
                continue
            counts[st] = counts.get(st, 0) + n
        result = _result_of(counts, slot.plan_summary or {})
        if long_pending and result == "completed":
            result = "partial"
        # An atomic finalization claim also prevents two schedulers from creating
        # separate automatic reports for the same completed slot.
        claim = await db.execute(update(ScheduleSlot).where(ScheduleSlot.id == slot.id,
            ScheduleSlot.status == "launched").values(status="finalizing"))
        if claim.rowcount != 1:
            continue
        slot.status = result
        slot.finished_at = now
        slot.result_summary = {"by_status": counts, "long_lane_pending": long_pending}
        s = await db.get(MonitorSchedule, schedule_id)
        if s is not None and "public_web" in s.engines:
            from backend.app.models.asset import Asset
            from backend.app.reporting.pilot_report import create_snapshot
            asset_ids = select(ExecutionRecord.asset_id).where(ExecutionRecord.batch_id == slot.batch_id)
            assets = list((await db.execute(select(Asset).where(Asset.id.in_(asset_ids)))).scalars().all())
            if assets:
                report = await create_snapshot(db, title=f"{s.name} · {_utc(slot.slot_at).isoformat()}",
                    assets=assets, batch_id=slot.batch_id, days=1, user_id=s.created_by, scope_kind="run")
                slot.result_summary = {**slot.result_summary, "report_id": str(report.id)}
        if s is not None and (s.last_result_at is None or _utc(s.last_result_at) <= now):
            s.last_result_status = result
            s.last_result_at = now
            s.last_result_batch_id = slot.batch_id
            if result == "completed":
                s.last_full_success_at = now
        batch = await db.get(ScanBatch, slot.batch_id) if slot.batch_id else None
        if batch is not None and batch.status in ("QUEUED", "RUNNING"):
            batch.status = "COMPLETED" if result in ("completed", "partial", "no_work") else "FAILED"
            batch.completed_at = now
        from backend.app.core import lifecycle
        from backend.app.core.config import settings as _settings
        await lifecycle.notify(db, [str(_settings.SOLE_OWNER_ACCOUNT_ID)], kind="run_finished",
                               severity="INFO" if result in ("completed", "no_work") else "MEDIUM",
                               title=f"Scheduled run {result}: {s.name if s else schedule_id}",
                               message=f"Slot {_utc(slot.slot_at).isoformat()}: " +
                                       ", ".join(f"{k} {v}" for k, v in counts.items()) +
                                       (f"; {long_pending} long-lane pending" if long_pending else ""),
                               object_type="run", object_id=str(slot.batch_id),
                               link=f"/engine-runs/?run={slot.batch_id}", dedup_key=f"slot:{slot.id}")
        await emit_event("SCHEDULE_SLOT_FINISHED", f"slot {_utc(slot.slot_at).isoformat()} {result}",
                         batch_id=slot.batch_id, session=db,
                         details={"schedule_id": str(schedule_id), "slot_id": str(slot.id), "result": result,
                                  "by_status": counts, "long_lane_pending": long_pending,
                                  "correlation_id": slot.correlation_id})
        done += 1
    return done


async def reap_and_dead_letter() -> int:
    """Requeue expired leases; executions whose queue row exhausted its retries become dead letters."""
    from backend.app.core.event_bus import emit_event
    from backend.app.core.queue import IDBDurableQueue

    async with AsyncSessionLocal() as db:
        try:
            await IDBDurableQueue.recover_expired_leases(db)
        except Exception:
            log.exception("lease reaper failed")
            await db.rollback()
        rows = (await db.execute(select(ExecutionRecord, Scan.error_message).join(Scan, Scan.id == ExecutionRecord.scan_id)
                                 .where(ExecutionRecord.status.in_((EXEC_QUEUED, EXEC_RUNNING)),
                                        Scan.status == "FAILED"))).all()
        now = datetime.now(timezone.utc)
        for rec, msg in rows:
            rec.status = EXEC_FAILED
            rec.error_class = "DEAD_LETTER"
            rec.status_reason = msg or "Queue row failed without a committed result (retry budget exhausted)."
            rec.finished_at = now
            await emit_event("EXECUTION_DEAD_LETTER", f"{rec.engine_id} dead-lettered", scan_id=rec.scan_id,
                             batch_id=rec.batch_id, target_id=rec.asset_id, engine=rec.engine_id, level="ERROR",
                             session=db, details={"execution_id": str(rec.id), "correlation_id": rec.correlation_id})
        await db.commit()
        return len(rows)


_instance: Optional[MonitorScheduler] = None


def get_monitor_scheduler() -> MonitorScheduler:
    global _instance
    if _instance is None:
        _instance = MonitorScheduler(interval_seconds=float(os.getenv("NOOSPIRE_SCHEDULER_TICK_SECONDS", "15")))
    return _instance


FEED_STALE = timedelta(days=7)
WORKER_GONE = timedelta(minutes=5)


async def notify_stale_sources(now: datetime) -> int:
    """Owner alerts (deduplicated per ICT day): advisory feed older than 7 days; queued work but
    no worker heartbeat for 5 minutes."""
    from backend.app.core import lifecycle
    from backend.app.core.config import settings
    from backend.app.models.defensive import AdvisorySnapshot, WorkerHeartbeat

    owner = [str(settings.SOLE_OWNER_ACCOUNT_ID)]
    day = now.astimezone(timezone(timedelta(hours=7))).date().isoformat()
    n = 0
    async with AsyncSessionLocal() as db:
        snap = (await db.execute(select(AdvisorySnapshot).where(AdvisorySnapshot.is_active == True))  # noqa: E712
                ).scalars().first()
        if snap is not None and now - _utc(snap.imported_at) > FEED_STALE:
            n += await lifecycle.notify(db, owner, kind="source_stale", severity="MEDIUM",
                                        title="Advisory snapshot is stale",
                                        message=f"Active snapshot {snap.version_label} imported "
                                                f"{(now - _utc(snap.imported_at)).days} days ago.",
                                        object_type="feed", object_id=str(snap.id), link="/engine-runs/",
                                        dedup_key=f"stale:feed:{day}")
        queued = (await db.execute(select(func.count()).select_from(ExecutionRecord)
                                   .where(ExecutionRecord.status == EXEC_QUEUED))).scalar() or 0
        newest = (await db.execute(select(func.max(WorkerHeartbeat.last_seen_at)))).scalar()
        if queued and (newest is None or now - _utc(newest) > WORKER_GONE):
            n += await lifecycle.notify(db, owner, kind="source_stale", severity="HIGH",
                                        title="No worker online while jobs are queued",
                                        message=f"{queued} execution(s) waiting; last worker heartbeat "
                                                f"{_utc(newest).isoformat() if newest else 'never'}.",
                                        object_type="worker", object_id=None, link="/schedules/",
                                        dedup_key=f"stale:worker:{day}")
        await db.commit()
    return n
