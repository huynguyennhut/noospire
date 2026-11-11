import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.dispatcher import get_dispatcher
from backend.app.core.scheduler import compute_next_run
from backend.app.api.deps import require_admin, require_operator, require_viewer
from backend.app.models.asset import Asset
from backend.app.models.scan import Scan, ScanBatch
from backend.app.models.schedule import DailySchedule
from backend.app.models.user import User
from backend.app.schemas.common import ScanProfile, ScanStatus

router = APIRouter(prefix="/schedules", tags=["Continuous Daily Schedules"])


class ScheduleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    profile: ScanProfile = Field(default=ScanProfile.DAILY_SECURITY)
    cron_expression: str = Field(default="0 * * * *")
    timezone: str = Field(default="Asia/Ho_Chi_Minh")
    target_ids: List[str] = Field(default_factory=lambda: ["ALL"])
    is_active: bool = Field(default=True)


class ScheduleResponse(BaseModel):
    id: uuid.UUID
    name: str
    profile: str
    cron_expression: str
    timezone: str
    is_active: bool
    target_ids: list
    last_run_at: Optional[datetime] = None
    last_completed_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    active_batch_id: Optional[uuid.UUID] = None
    pending_followup: bool = False
    missed_slots_count: int = 0
    overrun_active: bool = False
    overdue_reason: Optional[str] = None
    created_at: datetime


@router.get("", response_model=List[ScheduleResponse])
async def list_schedules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
) -> Any:
    stmt = select(DailySchedule).order_by(DailySchedule.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/{id}/status")
async def get_schedule_status(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
) -> Any:
    """Returns server time, next due instant, countdown metrics, active batch status, and overdue diagnostic reason."""
    res = await db.execute(select(DailySchedule).where(DailySchedule.id == id))
    sched = res.scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")

    now = datetime.now(timezone.utc)
    remaining_seconds = 0
    is_overdue = False

    if sched.next_run_at:
        next_run = sched.next_run_at if sched.next_run_at.tzinfo else sched.next_run_at.replace(tzinfo=timezone.utc)
        delta = (next_run - now).total_seconds()
        remaining_seconds = int(max(0, delta))
        if delta < 0:
            is_overdue = True

    active_batch_data = None
    if sched.active_batch_id:
        b_res = await db.execute(select(ScanBatch).where(ScanBatch.id == sched.active_batch_id))
        b = b_res.scalars().first()
        if b:
            active_batch_data = {
                "id": str(b.id),
                "name": b.name,
                "status": b.status,
                "progress_percentage": b.progress_percentage,
                "completed_scans": b.completed_scans,
                "total_scans": b.total_scans,
                "started_at": b.started_at.isoformat() if b.started_at else None,
            }

    return {
        "server_time": now.isoformat(),
        "schedule_id": str(sched.id),
        "name": sched.name,
        "cron_expression": sched.cron_expression,
        "timezone": sched.timezone,
        "is_active": sched.is_active,
        "last_run_at": sched.last_run_at.isoformat() if sched.last_run_at else None,
        "last_completed_at": sched.last_completed_at.isoformat() if sched.last_completed_at else None,
        "next_run_at": sched.next_run_at.isoformat() if sched.next_run_at else None,
        "remaining_seconds": remaining_seconds,
        "is_overdue": is_overdue,
        "overrun_active": sched.overrun_active,
        "pending_followup": sched.pending_followup,
        "missed_slots_count": sched.missed_slots_count,
        "overdue_reason": sched.overdue_reason,
        "active_batch": active_batch_data,
    }


@router.get("/{id}", response_model=ScheduleResponse)
async def get_schedule(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
) -> Any:
    res = await db.execute(select(DailySchedule).where(DailySchedule.id == id))
    sched = res.scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return sched


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    payload: ScheduleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    now = datetime.now(timezone.utc)
    next_run = compute_next_run(payload.cron_expression, now, payload.timezone)

    sched = DailySchedule(
        id=uuid.uuid4(),
        name=payload.name,
        profile=payload.profile.value,
        cron_expression=payload.cron_expression,
        timezone=payload.timezone,
        is_active=payload.is_active,
        target_ids=payload.target_ids,
        last_status="IDLE",
        next_run_at=next_run,
    )
    db.add(sched)
    await db.commit()
    await db.refresh(sched)
    return sched


@router.post("/{id}/trigger")
async def trigger_schedule(
    id: uuid.UUID,
    request_followup: bool = Query(True, description="Queue follow-up if batch currently running"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """Manually triggers or deduplicates the assessment pipeline for scheduled targets."""
    res = await db.execute(select(DailySchedule).where(DailySchedule.id == id))
    sched = res.scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")

    now = datetime.now(timezone.utc)

    # Check if there is an active batch currently executing
    if sched.active_batch_id:
        b_res = await db.execute(select(ScanBatch).where(ScanBatch.id == sched.active_batch_id))
        active_b = b_res.scalars().first()
        if active_b and active_b.status in (
            ScanStatus.QUEUED.value,
            ScanStatus.RUNNING.value,
            ScanStatus.INITIALIZING.value,
            ScanStatus.PENDING.value,
        ):
            # Active work in progress: deduplicate and offer/queue single follow-up
            if request_followup:
                sched.pending_followup = True
                await db.commit()

            return {
                "status": "ACTIVE_BATCH_RUNNING",
                "message": f"An assessment batch is currently running for this schedule (Batch: {active_b.id}). Duplicate sweep prevented.",
                "active_batch_id": str(active_b.id),
                "pending_followup": sched.pending_followup,
                "schedule_id": str(sched.id),
                "batch_status": active_b.status,
                "progress_percentage": active_b.progress_percentage,
            }

    # Fetch targets
    if "ALL" in sched.target_ids:
        targets_res = await db.execute(select(Asset))
        targets = targets_res.scalars().all()
    else:
        uids = [uuid.UUID(t) if isinstance(t, str) else t for t in sched.target_ids]
        targets_res = await db.execute(select(Asset).where(Asset.id.in_(uids)))
        targets = targets_res.scalars().all()

    if not targets:
        raise HTTPException(status_code=400, detail="No targets configured for this schedule.")

    batch = ScanBatch(
        id=uuid.uuid4(),
        name=f"Manual Trigger — {sched.name}",
        schedule_id=sched.id,
        status=ScanStatus.QUEUED.value,
        target_count=len(targets),
        engines=["all"],
        profiles=[sched.profile],
        metadata_json={
            "schedule_id": str(sched.id),
            "manually_triggered_by": current_user.username,
            "triggered_at": now.isoformat(),
        },
    )
    db.add(batch)
    await db.flush()

    dispatcher = get_dispatcher()
    dispatched_scans = []
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
        db.add(scan)
        dispatched_scans.append(str(scan.id))

    batch.total_scans = len(dispatched_scans)
    sched.active_batch_id = batch.id
    sched.last_run_at = now
    sched.last_status = "RUNNING"
    sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
    await db.commit()

    for s_id in dispatched_scans:
        await dispatcher.dispatch_scan(uuid.UUID(s_id))

    return {
        "status": "DISPATCHED",
        "message": f"Daily assessment pipeline triggered for {len(targets)} targets.",
        "batch_id": str(batch.id),
        "dispatched_scans": dispatched_scans,
        "schedule_id": str(sched.id),
    }


@router.put("/{id}/toggle")
async def toggle_schedule(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    res = await db.execute(select(DailySchedule).where(DailySchedule.id == id))
    sched = res.scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")

    now = datetime.now(timezone.utc)
    sched.is_active = not sched.is_active
    if sched.is_active:
        sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
        sched.overdue_reason = None
    await db.commit()
    return {
        "id": str(sched.id),
        "is_active": sched.is_active,
        "next_run_at": sched.next_run_at.isoformat() if sched.next_run_at else None,
    }


@router.delete("/{id}")
async def delete_schedule(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """Delete a continuous assessment schedule."""
    res = await db.execute(select(DailySchedule).where(DailySchedule.id == id))
    sched = res.scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    await db.delete(sched)
    await db.commit()
    return {"id": str(id), "message": "Schedule deleted successfully"}
