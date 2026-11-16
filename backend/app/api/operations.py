"""Milestone 4 operations API.

  POST /plans/preview                plan without writing (scope count, expected impact)
  POST /runs        (Idempotency-Key) same planner as the hourly schedule -> 202 + batch id
  GET  /runs/{batch_id}              run progress (scoped)
  GET/POST /monitor-schedules, PATCH /monitor-schedules/{id}, GET /monitor-schedules/{id}/slots
  GET/PUT  /operations/capacity      estate-wide limits (owner)
  GET  /operations/overview          schedules, countdown basis, backlog, staleness, workers, overdue
  GET  /operations/metrics           per-engine p50/p95, queue delay, cpu/ram/bytes, host egress budget
  GET  /events?after=&limit=         cursor polling fallback
  GET  /events/stream                SSE: id = event cursor, Last-Event-ID replay, heartbeat, retry hint

SSE contract
  retry: 3000                       client reconnect hint (ms); clients add jittered backoff
  event: hello      data {server_time, cursor}           sent once on connect
  event: execution | run | schedule | scan  (id: N)     data {id, type, message, occurred_at, ...}
  event: heartbeat  data {server_time, cursor}           every HEARTBEAT_SECONDS, session re-checked
  event: reset      data {reason}                       cursor no longer replayable -> refetch snapshot
  event: auth_revoked                                    session ended -> stream closes
The stream closes after `max_seconds` (default 300); clients reconnect with Last-Event-ID.
A viewer disconnecting never touches jobs: the stream only reads.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_active_user, is_sole_owner, load_scope, require_owner, session_still_valid
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal, get_db
from backend.app.core.monitor_scheduler import floor_slot
from backend.app.core.planner import (
    ENGINES,
    PROFILES,
    Selection,
    build_plan,
    capacity_settings,
    engine_estimates,
    materialize,
    request_hash,
)
from backend.app.models.base import AdminAuditLog
from backend.app.models.defensive import (
    EXEC_QUEUED,
    EXEC_RUNNING,
    EXEC_SUCCEEDED,
    TERMINAL_STATES,
    AdvisorySnapshot,
    ExecutionRecord,
    WorkerHeartbeat,
)
from backend.app.models.event import ScanEvent
from backend.app.models.operations import (
    CapacitySettings,
    ExecutionMetric,
    MonitorSchedule,
    RunRequest,
    ScheduleSlot,
)
from backend.app.models.scan import Scan, ScanBatch
from backend.app.models.user import User

router = APIRouter(tags=["Operations"])

HEARTBEAT_SECONDS = 15.0
POLL_SECONDS = 1.0
WORKER_STALE_SECONDS = 30
OVERDUE_QUEUE_SECONDS = 600


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _audit(db, user: User, action: str, details: str, request: Request) -> None:
    db.add(AdminAuditLog(user_id=str(user.id), username=user.username, action=action, details=details[:1024],
                         ip_address=request.client.host if request.client else "unknown"))


def _pct(values: List[float], q: float) -> Optional[float]:
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(round(q * (len(v) - 1))))], 3)


# --------------------------------------------------------------------------- plans & runs

class RunCreate(BaseModel):
    selection: Dict[str, Any] = Field(default_factory=lambda: {"kind": "all"})
    engines: List[Literal["sbom", "tls_health", "public_web"]] = Field(default_factory=lambda: list(ENGINES))
    profile: Literal["light", "slow"] = "light"


async def _plan_for(db: AsyncSession, user: User, payload: RunCreate, trigger: str):
    scope = await load_scope(user, db)
    sel = Selection.parse(payload.selection)
    return await build_plan(db, selection=sel, engines=payload.engines, profile=payload.profile,
                            trigger=trigger, scope=scope)


@router.post("/plans/preview")
async def preview_plan(payload: RunCreate, current_user: User = Depends(get_current_active_user),
                       db: AsyncSession = Depends(get_db)) -> Any:
    plan = await _plan_for(db, current_user, payload, "preview")
    await db.rollback()  # capacity_settings() may have created the singleton; preview writes nothing
    return plan.to_dict()


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def launch_run(payload: RunCreate, request: Request,
                     idempotency_key: Optional[str] = Header(default=None, max_length=128),
                     current_user: User = Depends(get_current_active_user),
                     db: AsyncSession = Depends(get_db)) -> Any:
    """'Run whole system' (selection.kind=all) or a selected asset/module, through the same planner
    the hourly schedule uses. Scope is applied before the idempotency lookup."""
    plan = await _plan_for(db, current_user, payload, "manual")
    rh = request_hash(payload.model_dump(mode="json"))
    key = f"{current_user.id}:{idempotency_key}" if idempotency_key else None
    if key:
        prior = (await db.execute(select(RunRequest).where(RunRequest.idempotency_key == key))).scalars().first()
        if prior is not None:
            if prior.request_hash != rh:
                raise HTTPException(status_code=409, detail="Idempotency-Key reused with a different request body")
            # build_plan only reads (plus the capacity singleton), so nothing needs discarding.
            return JSONResponse(status_code=200, content=await _run_out(db, current_user, prior.batch_id, replayed=True))
    corr = getattr(request.state, "request_id", None) or f"run-{uuid.uuid4().hex[:16]}"
    sel_desc = payload.selection.get("kind", "all")
    batch = await materialize(db, plan, name=f"Manual run · {sel_desc} · {plan.profile}", actor_id=str(current_user.id),
                              correlation_id=corr)
    if key:
        db.add(RunRequest(idempotency_key=key, user_id=str(current_user.id), request_hash=rh, batch_id=batch.id))
    _audit(db, current_user, "RUN_LAUNCH",
           f"batch_id={batch.id} selection={sel_desc} engines={','.join(plan.engines)} profile={plan.profile} "
           f"queue={plan.summary()['queue']} defer={plan.summary()['defer']} skip={plan.summary()['skip']}", request)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if key:
            prior = (await db.execute(select(RunRequest).where(RunRequest.idempotency_key == key))).scalars().first()
            if prior is not None and prior.request_hash == rh:
                return JSONResponse(status_code=200,
                                    content=await _run_out(db, current_user, prior.batch_id, replayed=True))
        raise
    out = await _run_out(db, current_user, batch.id, replayed=False)
    out["plan"] = plan.to_dict()
    return out


async def _run_out(db: AsyncSession, user: User, batch_id: uuid.UUID, replayed: bool = False) -> dict:
    batch = await db.get(ScanBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Run not found")
    scope = await load_scope(user, db)
    stmt = select(ExecutionRecord).where(ExecutionRecord.batch_id == batch_id)
    if scope.asset_ids is not None:
        stmt = stmt.where(ExecutionRecord.asset_id.in_(scope.ids_with("READ") or [uuid.uuid4()]))
    recs = (await db.execute(stmt.order_by(ExecutionRecord.queued_at))).scalars().all()
    meta = batch.metadata_json or {}
    if scope.asset_ids is not None and not recs and meta.get("actor_id") != str(user.id):
        raise HTTPException(status_code=404, detail="Run not found")
    counts: Dict[str, int] = {}
    for r in recs:
        counts[r.status] = counts.get(r.status, 0) + 1
    finished = all(r.status in TERMINAL_STATES for r in recs)
    return {
        "batch_id": str(batch.id), "name": batch.name, "accepted_at": _iso(batch.created_at),
        "trigger": meta.get("trigger"), "correlation_id": meta.get("correlation_id"),
        "schedule_id": meta.get("schedule_id"), "schedule_slot_id": meta.get("schedule_slot_id"),
        "plan_summary": meta.get("plan_summary"), "by_status": counts, "finished": finished,
        "executions": [{"execution_id": str(r.id), "asset_id": str(r.asset_id), "engine_id": r.engine_id,
                        "status": r.status, "lane": r.lane, "status_reason": r.status_reason,
                        "plan_note": r.plan_note, "finding_count": r.finding_count,
                        "queued_at": _iso(r.queued_at), "finished_at": _iso(r.finished_at)} for r in recs],
        "tracker": f"/engine-runs/?run={batch.id}", "replayed": replayed,
        "display_timezone": settings.DEFAULT_TIMEZONE,
    }


@router.get("/runs/{batch_id}")
async def get_run(batch_id: uuid.UUID, current_user: User = Depends(get_current_active_user),
                  db: AsyncSession = Depends(get_db)) -> Any:
    return await _run_out(db, current_user, batch_id)


# --------------------------------------------------------------------------- schedules (owner)

class ScheduleIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    selection: Dict[str, Any] = Field(default_factory=lambda: {"kind": "all"})
    engines: List[Literal["sbom", "tls_health", "public_web"]] = Field(default_factory=lambda: list(ENGINES))
    profile: Literal["light", "slow"] = "light"
    interval_minutes: int = Field(60, ge=15, le=1440)
    max_workers: int = Field(2, ge=1, le=32)
    is_active: bool = True


class SchedulePatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    selection: Optional[Dict[str, Any]] = None
    engines: Optional[List[Literal["sbom", "tls_health", "public_web"]]] = None
    profile: Optional[Literal["light", "slow"]] = None
    interval_minutes: Optional[int] = Field(None, ge=15, le=1440)
    max_workers: Optional[int] = Field(None, ge=1, le=32)
    is_active: Optional[bool] = None
    expected_revision: Optional[int] = None


def _check_interval(m: int) -> None:
    if (24 * 60) % m != 0:
        raise HTTPException(status_code=422, detail="interval_minutes must divide 1440 (e.g. 15, 30, 60, 120)")


async def _schedule_out(db: AsyncSession, s: MonitorSchedule, now: datetime) -> dict:
    from backend.app.core.monitor_scheduler import active_work
    busy = await active_work(db, s.id)
    nxt = _utc(s.next_run_at) or (floor_slot(now, s.interval_minutes) + timedelta(minutes=s.interval_minutes))
    backlog = (await db.execute(select(func.count()).select_from(ExecutionRecord)
                                .join(ScheduleSlot, ScheduleSlot.id == ExecutionRecord.schedule_slot_id)
                                .where(ScheduleSlot.schedule_id == s.id,
                                       ExecutionRecord.status.in_((EXEC_QUEUED, EXEC_RUNNING))))).scalar() or 0
    est = await engine_estimates(db)
    cs = await capacity_settings(db)
    slots = max(1, min(cs.max_running_executions, s.max_workers, PROFILES[s.profile]["max_workers"] or 999))
    avg = statistics.mean([est[e]["p50"] for e in s.engines]) if s.engines else 1.0
    eta = now + timedelta(seconds=backlog * avg / slots) if backlog else None
    return {
        "id": str(s.id), "name": s.name, "selection": s.selection, "engines": s.engines, "profile": s.profile,
        "interval_minutes": s.interval_minutes, "max_workers": s.max_workers, "is_active": s.is_active,
        "revision": s.revision, "next_run_at": _iso(nxt), "last_slot_at": _iso(s.last_slot_at),
        "last_run_at": _iso(s.last_run_at), "last_batch_id": str(s.last_batch_id) if s.last_batch_id else None,
        "last_full_success_at": _iso(s.last_full_success_at),
        "latest_result": {"status": s.last_result_status, "at": _iso(s.last_result_at),
                          "batch_id": str(s.last_result_batch_id) if s.last_result_batch_id else None},
        "running": busy > 0, "pending_catchup": s.pending_catchup, "missed_slots": s.missed_slots,
        "backlog": backlog, "estimated_drain_at": _iso(eta), "overdue_reason": s.overdue_reason,
        "theoretical_hourly_capacity": int(3600 * slots / max(avg, 0.001)),
        "created_at": _iso(s.created_at), "updated_at": _iso(s.updated_at),
    }


@router.get("/monitor-schedules")
async def list_monitor_schedules(current_user: User = Depends(require_owner), db: AsyncSession = Depends(get_db)) -> Any:
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(MonitorSchedule).order_by(MonitorSchedule.created_at))).scalars().all()
    out = [await _schedule_out(db, s, now) for s in rows]
    await db.rollback()
    return {"server_time": now.isoformat(), "display_timezone": settings.DEFAULT_TIMEZONE, "items": out}


@router.post("/monitor-schedules", status_code=status.HTTP_201_CREATED)
async def create_monitor_schedule(payload: ScheduleIn, request: Request, current_user: User = Depends(require_owner),
                                  db: AsyncSession = Depends(get_db)) -> Any:
    _check_interval(payload.interval_minutes)
    Selection.parse(payload.selection)
    now = datetime.now(timezone.utc)
    s = MonitorSchedule(name=payload.name, selection=payload.selection, engines=list(payload.engines),
                        profile=payload.profile, interval_minutes=payload.interval_minutes,
                        max_workers=payload.max_workers, is_active=payload.is_active, created_by=str(current_user.id),
                        start_after=now,
                        next_run_at=floor_slot(now, payload.interval_minutes) + timedelta(minutes=payload.interval_minutes))
    db.add(s)
    await db.flush()
    _audit(db, current_user, "SCHEDULE_CREATE", f"schedule_id={s.id} interval={s.interval_minutes} "
           f"profile={s.profile} engines={','.join(s.engines)}", request)
    await db.commit()
    return await _schedule_out(db, s, now)


@router.patch("/monitor-schedules/{schedule_id}")
async def update_monitor_schedule(schedule_id: uuid.UUID, payload: SchedulePatch, request: Request,
                                  current_user: User = Depends(require_owner), db: AsyncSession = Depends(get_db)) -> Any:
    s = await db.get(MonitorSchedule, schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if payload.expected_revision is not None and payload.expected_revision != s.revision:
        raise HTTPException(status_code=409, detail=f"Schedule changed (revision {s.revision}); reload and retry")
    data = payload.model_dump(exclude_unset=True, exclude={"expected_revision"})
    if "interval_minutes" in data:
        _check_interval(data["interval_minutes"])
    if "selection" in data:
        Selection.parse(data["selection"])
    now = datetime.now(timezone.utc)
    for k, v in data.items():
        setattr(s, k, list(v) if k == "engines" else v)
    if "interval_minutes" in data or data.get("is_active"):
        s.next_run_at = floor_slot(now, s.interval_minutes) + timedelta(minutes=s.interval_minutes)
        if data.get("is_active"):
            s.start_after = now  # re-enabling does not back-fill slots missed while paused
            s.missed_slots = 0
    s.revision += 1
    s.updated_at = now
    _audit(db, current_user, "SCHEDULE_UPDATE", f"schedule_id={s.id} fields={','.join(sorted(data))} "
           f"revision={s.revision}", request)
    await db.commit()
    return await _schedule_out(db, s, now)


@router.get("/monitor-schedules/{schedule_id}/slots")
async def list_schedule_slots(schedule_id: uuid.UUID, limit: int = Query(48, ge=1, le=500),
                              current_user: User = Depends(require_owner), db: AsyncSession = Depends(get_db)) -> Any:
    rows = (await db.execute(select(ScheduleSlot).where(ScheduleSlot.schedule_id == schedule_id)
                             .order_by(ScheduleSlot.slot_at.desc()).limit(limit))).scalars().all()
    return [{"id": str(x.id), "slot_at": _iso(x.slot_at), "kind": x.kind, "status": x.status,
             "claimed_by": x.claimed_by, "claimed_at": _iso(x.claimed_at), "launched_at": _iso(x.launched_at),
             "finished_at": _iso(x.finished_at), "batch_id": str(x.batch_id) if x.batch_id else None,
             "missed_before": x.missed_before, "coalesced_slots": x.coalesced_slots, "reason": x.reason,
             "plan_summary": x.plan_summary, "result_summary": x.result_summary,
             "correlation_id": x.correlation_id} for x in rows]


# --------------------------------------------------------------------------- capacity

class CapacityIn(BaseModel):
    max_running_executions: int = Field(..., ge=1, le=64)
    per_host_hourly_quota: int = Field(..., ge=1, le=3600)
    per_host_egress_bytes_hourly: int = Field(2_000_000, ge=10_000, le=1_000_000_000)


def _cap_out(cs: CapacitySettings) -> dict:
    return {"max_running_executions": cs.max_running_executions, "per_host_hourly_quota": cs.per_host_hourly_quota,
            "per_host_egress_bytes_hourly": cs.per_host_egress_bytes_hourly,
            "emergency_stop_active": cs.emergency_stop_active, "updated_by": cs.updated_by,
            "updated_at": _iso(cs.updated_at)}


@router.get("/operations/capacity")
async def get_capacity(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> Any:
    cs = await capacity_settings(db)
    await db.commit()
    return _cap_out(cs)


class EmergencyStopIn(BaseModel):
    active: bool


@router.put("/operations/emergency-stop")
async def set_emergency_stop(payload: EmergencyStopIn, request: Request,
                             current_user: User = Depends(require_owner),
                             db: AsyncSession = Depends(get_db)) -> Any:
    """Persistent stop read by worker claims and in-flight public-web observations."""
    cs = await capacity_settings(db)
    cs.emergency_stop_active = payload.active
    cs.updated_by = str(current_user.id)
    cs.updated_at = datetime.now(timezone.utc)
    _audit(db, current_user, "GLOBAL_EMERGENCY_STOP" if payload.active else "GLOBAL_EMERGENCY_RESUME",
           json.dumps({"active": payload.active}), request)
    await db.commit()
    return _cap_out(cs)


@router.put("/operations/capacity")
async def put_capacity(payload: CapacityIn, request: Request, current_user: User = Depends(require_owner),
                       db: AsyncSession = Depends(get_db)) -> Any:
    cs = await capacity_settings(db)
    cs.max_running_executions = payload.max_running_executions
    cs.per_host_hourly_quota = payload.per_host_hourly_quota
    cs.per_host_egress_bytes_hourly = payload.per_host_egress_bytes_hourly
    cs.updated_by = str(current_user.id)
    cs.updated_at = datetime.now(timezone.utc)
    _audit(db, current_user, "CAPACITY_UPDATE", json.dumps(payload.model_dump()), request)
    await db.commit()
    return _cap_out(cs)


# --------------------------------------------------------------------------- overview & metrics

@router.get("/operations/overview")
async def operations_overview(current_user: User = Depends(get_current_active_user),
                              db: AsyncSession = Depends(get_db)) -> Any:
    now = datetime.now(timezone.utc)
    owner = is_sole_owner(current_user)
    scope = await load_scope(current_user, db)
    visible = None if scope.asset_ids is None else (scope.ids_with("READ") or [uuid.uuid4()])

    def scoped(stmt):
        return stmt if visible is None else stmt.where(ExecutionRecord.asset_id.in_(visible))

    schedules = []
    stale_threshold = timedelta(minutes=120)
    if owner:
        rows = (await db.execute(select(MonitorSchedule).order_by(MonitorSchedule.created_at))).scalars().all()
        schedules = [await _schedule_out(db, s, now) for s in rows]
        active_intervals = [s.interval_minutes for s in rows if s.is_active]
        if active_intervals:
            stale_threshold = timedelta(minutes=2 * min(active_intervals))

    engines = {}
    for eng in ENGINES:
        last_ok = (await db.execute(scoped(select(func.max(ExecutionRecord.finished_at)).where(
            ExecutionRecord.engine_id == eng, ExecutionRecord.status == EXEC_SUCCEEDED)))).scalar()
        last_any = (await db.execute(scoped(select(ExecutionRecord).where(ExecutionRecord.engine_id == eng,
                                                                            ExecutionRecord.finished_at.is_not(None))
                                            .order_by(ExecutionRecord.finished_at.desc()).limit(1)))).scalars().first()
        oldest_q = (await db.execute(scoped(select(func.min(ExecutionRecord.queued_at))
                                            .join(Scan, Scan.id == ExecutionRecord.scan_id)
                                            .where(ExecutionRecord.engine_id == eng, ExecutionRecord.status == EXEC_QUEUED,
                                                   (Scan.available_at.is_(None)) | (Scan.available_at <= now))))).scalar()
        queued = (await db.execute(scoped(select(func.count()).select_from(ExecutionRecord).where(
            ExecutionRecord.engine_id == eng, ExecutionRecord.status == EXEC_QUEUED)))).scalar() or 0
        running = (await db.execute(scoped(select(func.count()).select_from(ExecutionRecord).where(
            ExecutionRecord.engine_id == eng, ExecutionRecord.status == EXEC_RUNNING)))).scalar() or 0
        age = (now - _utc(last_ok)).total_seconds() if last_ok else None
        engines[eng] = {
            "last_success_at": _iso(last_ok),
            "latest_result": ({"status": last_any.status, "at": _iso(last_any.finished_at),
                               "execution_id": str(last_any.id)} if last_any else None),
            "staleness_seconds": round(age, 1) if age is not None else None,
            "stale": age is None or age > stale_threshold.total_seconds(),
            "queued": queued, "running": running,
            "queue_age_seconds": round((now - _utc(oldest_q)).total_seconds(), 1) if oldest_q else 0.0,
        }

    overdue_q = (await db.execute(scoped(select(func.count()).select_from(ExecutionRecord)
                                         .join(Scan, Scan.id == ExecutionRecord.scan_id)
                                         .where(ExecutionRecord.status == EXEC_QUEUED,
                                                func.coalesce(Scan.available_at, ExecutionRecord.queued_at)
                                                < now - timedelta(seconds=OVERDUE_QUEUE_SECONDS))))).scalar() or 0
    expired = (await db.execute(scoped(select(func.count()).select_from(ExecutionRecord)
                                       .join(Scan, Scan.id == ExecutionRecord.scan_id)
                                       .where(ExecutionRecord.status == EXEC_RUNNING,
                                              Scan.lease_expires_at < now)))).scalar() or 0
    day = now - timedelta(hours=24)
    parse_err = (await db.execute(scoped(select(func.count()).select_from(ExecutionRecord).where(
        ExecutionRecord.error_class == "INPUT_PARSE_ERROR", ExecutionRecord.finished_at >= day)))).scalar() or 0
    dead = (await db.execute(scoped(select(func.count()).select_from(ExecutionRecord).where(
        ExecutionRecord.error_class == "DEAD_LETTER", ExecutionRecord.finished_at >= day)))).scalar() or 0
    newest_obs = (await db.execute(scoped(select(func.max(ExecutionRecord.observed_at)).where(
        ExecutionRecord.status == EXEC_SUCCEEDED)))).scalar()

    workers = []
    for w in (await db.execute(select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()))).scalars():
        a = (now - _utc(w.last_seen_at)).total_seconds()
        workers.append({"worker_id": w.worker_id, "last_seen_at": _iso(w.last_seen_at), "age_seconds": round(a, 1),
                        "state": "online" if a <= WORKER_STALE_SECONDS else "stale",
                        "active_executions": w.active_executions, "throttle_reason": w.throttle_reason})
    snap = (await db.execute(select(AdvisorySnapshot).where(AdvisorySnapshot.is_active == True))).scalars().first()  # noqa
    cursor = (await db.execute(select(func.max(ScanEvent.id)))).scalar() or 0
    cs = await capacity_settings(db)
    await db.commit()
    return {
        "server_time": now.isoformat(), "as_of": now.isoformat(), "display_timezone": settings.DEFAULT_TIMEZONE,
        "event_cursor": cursor, "schedules": schedules, "schedules_visible": owner,
        "engines": engines, "stale_threshold_seconds": stale_threshold.total_seconds(),
        "overdue": {"queued_over_10m": overdue_q, "running_lease_expired": expired},
        "errors_24h": {"parse_errors": parse_err, "dead_letters": dead},
        "evidence": {"newest_observation_at": _iso(newest_obs),
                     "age_seconds": round((now - _utc(newest_obs)).total_seconds(), 1) if newest_obs else None},
        "feed": ({"source": snap.source, "version": snap.version_label, "digest": snap.digest,
                  "imported_at": _iso(snap.imported_at), "data_modified_max": snap.data_modified_max,
                  "age_hours": round((now - _utc(snap.imported_at)).total_seconds() / 3600, 2)}
                 if snap else None),
        "workers": workers, "workers_online": sum(1 for w in workers if w["state"] == "online"),
        "capacity": _cap_out(cs),
    }


@router.get("/operations/metrics")
async def operations_metrics(hours: int = Query(24, ge=1, le=720), current_user: User = Depends(require_owner),
                             db: AsyncSession = Depends(get_db)) -> Any:
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    rows = (await db.execute(select(ExecutionMetric).where(ExecutionMetric.recorded_at >= since))).scalars().all()
    cs = await capacity_settings(db)
    per: Dict[str, dict] = {}
    for eng in ENGINES:
        ms = [m for m in rows if m.engine_id == eng]
        dur = [m.duration_ms / 1000 for m in ms]
        slot = [m.slot_ms / 1000 for m in ms if m.slot_ms is not None]
        qd = [m.queue_delay_ms / 1000 for m in ms if m.queue_delay_ms is not None]
        by_status: Dict[str, int] = {}
        for m in ms:
            by_status[m.status] = by_status.get(m.status, 0) + 1
        avg = statistics.mean(slot) if slot else None
        per[eng] = {
            "attempts": len(ms), "by_status": by_status, "retries": sum(1 for m in ms if m.attempt_no > 1),
            "duration_p50_s": _pct(dur, 0.5), "duration_p95_s": _pct(dur, 0.95),
            "slot_p50_s": _pct(slot, 0.5), "slot_p95_s": _pct(slot, 0.95),
            "queue_delay_p50_s": _pct(qd, 0.5), "queue_delay_p95_s": _pct(qd, 0.95),
            "cpu_ms_avg": round(statistics.mean([m.cpu_ms for m in ms if m.cpu_ms is not None]), 2)
            if any(m.cpu_ms is not None for m in ms) else None,
            "rss_bytes_max": max((m.rss_bytes or 0 for m in ms), default=None) or None,
            "input_bytes": sum(m.input_bytes or 0 for m in ms), "output_bytes": sum(m.output_bytes or 0 for m in ms),
            "egress_bytes": sum(m.egress_bytes or 0 for m in ms),
            "theoretical_hourly_capacity": int(3600 * cs.max_running_executions / avg) if avg else None,
        }
    hour = now - timedelta(hours=1)
    hosts: Dict[str, dict] = {}
    for m in rows:
        if m.target_host and _utc(m.recorded_at) >= hour:
            h = hosts.setdefault(m.target_host, {"requests": 0, "egress_bytes": 0})
            h["requests"] += 1
            h["egress_bytes"] += m.egress_bytes or 0
    for h in hosts.values():
        h["quota"] = cs.per_host_hourly_quota
        h["egress_budget_bytes"] = cs.per_host_egress_bytes_hourly
        h["over_budget"] = h["requests"] >= cs.per_host_hourly_quota or h["egress_bytes"] >= cs.per_host_egress_bytes_hourly
    await db.commit()
    return {"as_of": now.isoformat(), "window_hours": hours, "engines": per, "hosts_last_hour": hosts,
            "capacity_formula": "3600 x max_running_executions / mean slot seconds per execution "
                                "(slot = attempt start to commit; excludes claim polling and queue wait)",
            "cpu_rss_note": "cpu_ms and rss_bytes are sampled for the whole worker process; concurrent attempts share them"}


# --------------------------------------------------------------------------- events

def _sse_name(event_type: str) -> str:
    t = event_type.upper()
    if t.startswith("EXECUTION_"):
        return "execution"
    if t.startswith("SCHEDULE_"):
        return "schedule"
    if t.startswith("RUN_"):
        return "run"
    return "scan"


def _event_out(e: ScanEvent) -> dict:
    d = e.details_json or {}
    return {"id": e.id, "type": e.event_type, "level": e.level, "message": e.message,
            "occurred_at": _iso(e.occurred_at), "scan_id": str(e.scan_id) if e.scan_id else None,
            "batch_id": str(e.batch_id) if e.batch_id else None,
            "asset_id": str(e.target_id) if e.target_id else None, "engine": e.engine,
            "correlation_id": d.get("correlation_id"), "details": d}


async def _events_after(db: AsyncSession, user: User, after: int, limit: int) -> List[ScanEvent]:
    stmt = select(ScanEvent).where(ScanEvent.id > after)
    if not is_sole_owner(user):
        scope = await load_scope(user, db)
        stmt = stmt.where(ScanEvent.target_id.in_(scope.ids_with("READ") or [uuid.uuid4()]))
    return list((await db.execute(stmt.order_by(ScanEvent.id).limit(limit))).scalars().all())


@router.get("/events")
async def poll_events(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                      current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> Any:
    rows = await _events_after(db, current_user, after, limit)
    cursor = rows[-1].id if rows else after
    head = (await db.execute(select(func.max(ScanEvent.id)))).scalar() or 0
    return {"items": [_event_out(e) for e in rows], "cursor": cursor, "has_more": len(rows) == limit,
            "head": head, "server_time": datetime.now(timezone.utc).isoformat(), "poll_after_seconds": 10}


def _frame(event: str, data: dict, eid: Optional[int] = None) -> str:
    head = f"id: {eid}\n" if eid is not None else ""
    return f"{head}event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


@router.get("/events/stream")
async def stream_events(request: Request, after: Optional[int] = Query(None, ge=0),
                        max_seconds: float = Query(300, ge=1, le=3600),
                        last_event_id: Optional[str] = Header(default=None),
                        current_user: User = Depends(get_current_active_user)) -> Any:
    cursor = after or 0
    if last_event_id and last_event_id.strip().isdigit():
        cursor = int(last_event_id.strip())  # Last-Event-ID wins over ?after
    user_id = current_user.id

    async def gen():
        nonlocal cursor
        loop = asyncio.get_running_loop()
        started = loop.time()
        last_hb = started
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            oldest = (await db.execute(select(func.min(ScanEvent.id)))).scalar()
            head = (await db.execute(select(func.max(ScanEvent.id)))).scalar() or 0
        yield "retry: 3000\n\n"
        if cursor and oldest is not None and cursor < oldest - 1:
            yield _frame("reset", {"reason": "cursor older than retained events; refetch the snapshot",
                                   "oldest": oldest, "head": head})
            cursor = oldest - 1
        if cursor > head:
            yield _frame("reset", {"reason": "cursor ahead of server head", "head": head})
            cursor = head
        yield _frame("hello", {"server_time": datetime.now(timezone.utc).isoformat(), "cursor": cursor, "head": head})
        while loop.time() - started < max_seconds:
            if await request.is_disconnected():
                return
            async with AsyncSessionLocal() as db:
                rows = await _events_after(db, user, cursor, 200)
            for e in rows:
                cursor = e.id
                yield _frame(_sse_name(e.event_type), _event_out(e), e.id)
            if loop.time() - last_hb >= HEARTBEAT_SECONDS:
                last_hb = loop.time()
                if not await session_still_valid(request):
                    yield _frame("auth_revoked", {"reason": "session ended"})
                    return
                yield _frame("heartbeat", {"server_time": datetime.now(timezone.utc).isoformat(), "cursor": cursor})
            if not rows:
                await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


# --------------------------------------------------------------------------- legacy /schedules

legacy_schedules_router = APIRouter(prefix="/schedules", tags=["Deprecated"])
_GONE = {"detail": "The DailySchedule API was replaced by /api/v1/monitor-schedules (Milestone 4). "
                   "Legacy schedules never launch defensive executions.",
         "replacement": "/api/v1/monitor-schedules"}


@legacy_schedules_router.api_route("", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
@legacy_schedules_router.api_route("/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                                   include_in_schema=False)
async def legacy_schedules_gone(request: Request, rest: str = "",
                                current_user: User = Depends(get_current_active_user)) -> Any:
    return JSONResponse(status_code=410, content={**_GONE, "code": "GONE",
                                                  "request_id": getattr(request.state, "request_id", None)})
