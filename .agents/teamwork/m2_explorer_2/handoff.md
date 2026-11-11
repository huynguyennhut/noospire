# Milestone 2 — Hourly Cron & Overrun Coalescing Architecture Report

**Agent**: `m2_explorer_2` (Hourly Cron & Overrun Coalescing Explorer)  
**Role**: Teamwork Explorer  
**Milestone**: Milestone 2 — Durable Queue, Scheduling & Eventing  
**Parent Conversation ID**: `eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb`  
**Working Directory**: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m2_explorer_2`  
**Date**: 2026-11-10T21:10:00Z  

---

## 1. Observation

### 1.1 Existing Scheduler Engine & Cron Calculation
- **File**: `backend/app/core/scheduler.py`
  - Lines 49–100: `compute_next_run(cron_expr: str, from_dt: Optional[datetime] = None, tz_str: str = "Asia/Ho_Chi_Minh") -> datetime` parses 5-part cron syntax.
    - Probing forward minute-by-minute with candidate starting at `(local_dt.replace(second=0, microsecond=0) + timedelta(minutes=1))`.
    - Tested top-of-hour cron `"0 * * * *"` from `datetime(2026, 11, 10, 20, 15, 0, tzinfo=timezone.utc)`:
      `python -c "from backend.app.core.scheduler import compute_next_run; from datetime import datetime, timezone; now = datetime(2026, 11, 10, 20, 15, 0, tzinfo=timezone.utc); print(compute_next_run('0 * * * *', now))"`
      Result: `2026-11-10 21:00:00+00:00` (exit code 0).
  - Lines 103–213: `SchedulerEngine` with `tick()` method currently running every 30 seconds.
    - Lines 167–189: When `next_run <= now`, `SchedulerEngine.tick()` iterates over targets and instantiates individual `Scan` records directly:
      ```python
      for target in targets:
          scan = Scan(
              id=uuid.uuid4(),
              asset_id=target.id,
              engine="all",
              profile=sched.profile,
              status=ScanStatus.QUEUED.value,
              progress_percentage=0,
              target_locator=target.target_locator,
              allow_private_targets=True,
              timeout_seconds=600,
          )
          session.add(scan)
          await session.flush()
          await dispatcher.dispatch_scan(scan.id)
      ```
    - Critical defect observed: Scheduled runs are **NOT** wrapped in a `ScanBatch` entity. Consequently:
      1. Child scans cannot be tracked collectively under a single batch progress bar.
      2. Events from child scans cannot be grouped under a parent batch header (violating R4 notification grouping requirements).
      3. The schedule has no way of tracking which batch is currently running or when it completes.
      4. Overrun condition cannot be detected because there is no link between active running scans and the schedule's active state.

### 1.2 Schedule Persistence Model
- **File**: `backend/app/models/schedule.py`
  - Lines 11–25: `DailySchedule` model defines:
    ```python
    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile: Mapped[str] = mapped_column(String(64), default=ScanProfile.DAILY_SECURITY.value, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(64), default="0 2 * * *", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String(32), default=None, nullable=True)
    ```
  - Deficiencies observed:
    1. Default `cron_expression` is `"0 2 * * *"` (daily at 02:00 ICT) instead of `"0 * * * *"` (top-of-hour hourly).
    2. Missing `last_completed_at` (required by R3 for displaying last completed run).
    3. Missing `active_batch_id` foreign key referencing `scan_batches.id`.
    4. Missing overrun coalescing fields: `pending_followup: bool`, `missed_slots_count: int`, `overrun_active: bool`, and `overdue_reason: str`.
    5. Columns use `DateTime(timezone=True)` rather than `UTCDateTime` (from `backend/app/models/base.py`), which creates offset-naive vs offset-aware datetime comparison issues in SQLite environments.

### 1.3 Seeder Baseline Configuration
- **File**: `backend/app/core/empire_seeder.py`
  - Lines 466–480: The default seeded schedule is configured with `cron_expression="0 2 * * *"` (02:00 AM ICT) instead of `"0 * * * *"` (Hourly top of hour).
  - Target perimeter is set to `["ALL"]`.

### 1.4 API Endpoints & Trigger Idempotency
- **File**: `backend/app/api/schedules.py`
  - Lines 95–149: `POST /schedules/{id}/trigger` executes `targets_res = await db.execute(select(Asset)...)` and immediately creates and dispatches `Scan` objects.
  - Critical defect observed: `trigger_schedule` performs **zero active work checks**. If a run is already active, triggering the endpoint launches duplicate scans across the entire perimeter, causing duplicate sweeps and resource starvation.
  - No dedicated endpoint exists for scheduler health, countdown time synchronization, or overdue diagnostic reasons.

### 1.5 Batch Model
- **File**: `backend/app/models/scan.py`
  - Lines 11–62: `ScanBatch` model lacks `schedule_id` and follow-up tracking indicators (`is_followup: bool`, `missed_slots_coalesced: int`).

### 1.6 Frontend Schedules and Dashboard
- **File**: `frontend/src/app/schedules/page.tsx`
  - Lines 228–245: Displays static cron text `sched.cron_expression (02:00 AM ICT)` and last run time, but does NOT feature a live 1-second countdown timer, overdue state with diagnostic reason, or follow-up status.
- **File**: `frontend/src/lib/types.ts`
  - Lines 159–173: `DailyScheduleItem` schema lacks fields for `last_completed_at`, `active_batch_id`, `pending_followup`, `missed_slots_count`, `overrun_active`, and `overdue_reason`.

---

## 2. Logic Chain

```
[Observation 1.1, 1.2: Hourly schedule R3 requirement & compute_next_run]
       │
       ▼
(Step 1: Top-of-hour cron in Asia/Ho_Chi_Minh)
Cron expression must be "0 * * * *" with timezone "Asia/Ho_Chi_Minh" (UTC+7).
ICT has no daylight saving time (UTC+07:00 fixed offset).
Top-of-hour in ICT (minute=0, second=0) exactly aligns with top-of-hour in UTC (minute=0, second=0).
Database persistence must strictly use UTCDateTime (UTC timezone-aware) across SQLite and PostgreSQL.
       │
       ▼
(Step 2: Linking DailySchedule to ScanBatch)
Every scheduled execution must instantiate a parent ScanBatch with `schedule_id = sched.id`.
`sched.active_batch_id` records the running batch ID.
This provides batch-level telemetry, prevents job flooding, and allows O(1) state lookups.
       │
       ▼
(Step 3: Overrun Detection & Coalescing Invariant)
When scheduler ticks at `now`:
If `sched.active_batch_id` is running and `now >= sched.next_run_at`:
  - Active run is taking >1 hour (overrun).
  - INVARIANT: Keep active run intact (never abort/cancel active work).
  - Set `sched.overrun_active = True`.
  - Set `sched.pending_followup = True` (bounded at ONE pending follow-up).
  - Increment `sched.missed_slots_count += 1`.
  - Set `sched.overdue_reason = "Run in progress exceeding slot interval (overrun); follow-up queued"`.
  - Advance `sched.next_run_at` to the subsequent top-of-hour.
When active batch completes:
  - If `sched.pending_followup == True`:
    - Dispatch follow-up batch immediately.
    - Reset `pending_followup = False`, `overrun_active = False`, `missed_slots_count = 0`.
    - Set next scheduled run to next top-of-hour.
  - If `sched.pending_followup == False`:
    - Clear `active_batch_id = None`, record `last_completed_at`.
       │
       ▼
(Step 4: Active Run Deduplication & Run Button API)
When user triggers schedule (`POST /schedules/{id}/trigger`) or manual batch (`POST /scans/batch`):
If `sched.active_batch_id` is currently running:
  - Return HTTP 200 with `status: "ACTIVE_BATCH_RUNNING"` and active batch metadata.
  - If `request_followup: true`: set `sched.pending_followup = True` (idempotent; repeated clicks reuse request).
  - If user requests non-overlapping target subset and concurrency budget allows (`active_workers < max_concurrency`):
    permit independent non-overlapping execution.
  - If overlapping: reject duplicate sweep and offer follow-up.
       │
       ▼
(Step 5: Real-Time UI 1-Second Countdown & Diagnostics)
API provides `server_time`, `next_due_instant`, `is_active`, `is_overdue`, and `overdue_reason`.
Frontend calculates clock skew delta (`Date.parse(server_time) - Date.now()`).
Runs 1-second interval to compute remaining time.
If remaining <= 0 and active batch exists: renders "OVERDUE (+Xm Ys)" with `overdue_reason` badge.
Pause/Resume toggle freezes countdown or recalculates next due instant.
```

---

## 3. Caveats

1. **Host Concurrency Limits**: Even when independent non-overlapping work is launched, global concurrency is bounded by `settings.MAX_CONCURRENT_SCANS` (default 2 to 4). If the host is resource-throttled (CPU > 90% or RAM > 95%), independent launches must be queued rather than executed simultaneously.
2. **SQLite vs PostgreSQL Concurrency**: Under SQLite (local development), concurrent writes from scheduler loop and manual API requests require SQLite WAL mode and busy timeout (already configured in `backend/app/core/database.py`).
3. **No Unbounded Backlog Guarantee**: The coalescing engine bounds missed runs strictly to 1 follow-up run. Even if an assessment runs for 8 hours (missing 8 hourly slots), exactly 1 follow-up sweep is executed upon completion, with `missed_slots_count=8` logged in metadata for transparency.
4. **Timezone Uniformity**: Stored timestamps are 100% UTC. UI components translate UTC into local browser time and display ICT equivalent for operational clarity.

---

## 4. Conclusion & Concrete Implementation Strategy

### 4.1 State Transition Model

| Current State | Trigger / Event | Condition | Next State | Actions |
|---|---|---|---|---|
| `IDLE` | Scheduler tick | `now >= next_run_at` and `is_active == True` | `RUNNING` | Create `ScanBatch(schedule_id=sched.id)`, set `sched.active_batch_id = batch.id`, set `sched.last_run_at = now`, calculate `next_run_at = next_top_of_hour`, dispatch scans. |
| `RUNNING` | Batch completes | `elapsed < 1 hour` and `pending_followup == False` | `IDLE` | Set `last_completed_at = now`, clear `active_batch_id = None`, set `last_status = "COMPLETED"`. |
| `RUNNING` | Scheduler tick | `now >= next_run_at` and `elapsed >= 1 hour` | `OVERRUN_COALESCING` | Keep active batch intact. Set `overrun_active = True`, `pending_followup = True`, `missed_slots_count = 1`, `last_status = "OVERRUN_COALESCING"`, advance `next_run_at = next_top_of_hour`. |
| `OVERRUN_COALESCING` | Scheduler tick | Subsequent `now >= next_run_at` while batch running | `OVERRUN_COALESCING` | Keep active batch intact. Increment `missed_slots_count += 1`. `pending_followup` remains `True`. Advance `next_run_at`. |
| `OVERRUN_COALESCING` | Active batch completes | `pending_followup == True` | `RUNNING` (Follow-up) | Record `last_completed_at = now`. Immediately dispatch new follow-up `ScanBatch(is_followup=True)`. Reset `pending_followup = False`, `overrun_active = False`, `missed_slots_count = 0`. Advance `next_run_at`. |
| `RUNNING` / `IDLE` | Operator clicks "Run" | Active batch running, `request_followup=False` | No state change | Return `ACTIVE_BATCH_RUNNING`, display active batch progress, offer follow-up action. |
| `RUNNING` / `IDLE` | Operator clicks "Run" | Active batch running, `request_followup=True` | `RUNNING` (Follow-up Queued) | Set `pending_followup = True` idempotently. Return `FOLLOW_UP_QUEUED`. Repeated clicks return same state. |
| Any state | Operator toggles Pause | `is_active == True` -> `False` | `PAUSED` | Set `is_active = False`. Countdown freezes. No slots evaluated. |
| `PAUSED` | Operator toggles Resume | `is_active == False` -> `True` | `IDLE` | Set `is_active = True`. Recalculate `next_run_at = compute_next_run(...)`. Countdown resumes. |

---

### 4.2 Drop-In Implementation Specifications

#### Component 1: `backend/app/models/schedule.py`
```python
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, Integer, JSON, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, GUID, TimestampMixin, UTCDateTime
from backend.app.schemas.common import ScanProfile


class DailySchedule(Base, TimestampMixin):
    """Hourly/Daily Security Assessment Schedule with Overrun Coalescing."""
    __tablename__ = "daily_schedules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    profile: Mapped[str] = mapped_column(String(64), default=ScanProfile.DAILY_SECURITY.value, nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(64), default="0 * * * *", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    target_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # ["ALL"] or list of target UUIDs
    
    # Execution Tracking Timestamps (Strict UTCDateTime)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)  # Last scheduled launch instant
    last_completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)  # Last completed run instant
    next_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)  # Next due instant
    last_status: Mapped[Optional[str]] = mapped_column(String(32), default="IDLE", nullable=True)
    
    # Overrun Protection & Active Deduplication
    active_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("scan_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pending_followup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    missed_slots_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overrun_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    overdue_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    # Relationship to batches
    active_batch: Mapped[Optional["ScanBatch"]] = relationship(
        "ScanBatch", foreign_keys=[active_batch_id], lazy="selectin"
    )
```

#### Component 2: `backend/app/models/scan.py` Additions
Add foreign key and follow-up tracking to `ScanBatch`:
```python
    schedule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("daily_schedules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_followup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    missed_slots_coalesced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
```

#### Component 3: Database Auto-Migration (`backend/app/core/database.py`)
Add SQLite alter statements inside `init_db`:
```python
        if settings.DATABASE_URL.startswith("sqlite"):
            try:
                res = await conn.execute(text("PRAGMA table_info(daily_schedules)"))
                cols = [row[1] for row in res.fetchall()]
                if cols:
                    if "last_completed_at" not in cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN last_completed_at TIMESTAMP"))
                    if "active_batch_id" not in cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN active_batch_id CHAR(36)"))
                    if "pending_followup" not in cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN pending_followup BOOLEAN DEFAULT 0"))
                    if "missed_slots_count" not in cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN missed_slots_count INTEGER DEFAULT 0"))
                    if "overrun_active" not in cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN overrun_active BOOLEAN DEFAULT 0"))
                    if "overdue_reason" not in cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN overdue_reason VARCHAR(256)"))
                    if "concurrency_limit" not in cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN concurrency_limit INTEGER DEFAULT 2"))
            except Exception:
                pass

            try:
                res = await conn.execute(text("PRAGMA table_info(scan_batches)"))
                bcols = [row[1] for row in res.fetchall()]
                if bcols:
                    if "schedule_id" not in bcols:
                        await conn.execute(text("ALTER TABLE scan_batches ADD COLUMN schedule_id CHAR(36)"))
                    if "is_followup" not in bcols:
                        await conn.execute(text("ALTER TABLE scan_batches ADD COLUMN is_followup BOOLEAN DEFAULT 0"))
                    if "missed_slots_coalesced" not in bcols:
                        await conn.execute(text("ALTER TABLE scan_batches ADD COLUMN missed_slots_coalesced INTEGER DEFAULT 0"))
            except Exception:
                pass
```

#### Component 4: Scheduler Core Engine (`backend/app/core/scheduler.py`)
```python
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional, Set
import uuid
import zoneinfo

from sqlalchemy import select
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.dispatcher import get_dispatcher
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
    """Calculates next execution datetime in UTC based on 5-part cron syntax evaluated in timezone tz_str."""
    if from_dt is None:
        from_dt = datetime.now(timezone.utc)
    elif from_dt.tzinfo is None:
        from_dt = from_dt.replace(tzinfo=timezone.utc)

    try:
        tz = zoneinfo.ZoneInfo(tz_str)
    except Exception:
        tz = timezone.utc

    local_dt = from_dt.astimezone(tz)
    
    # Fast path for standard top-of-hour cron ("0 * * * *")
    clean_expr = " ".join(cron_expr.strip().split())
    if clean_expr == "0 * * * *":
        candidate = (local_dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        return candidate.astimezone(timezone.utc)

    # General cron evaluation
    candidate = (local_dt.replace(second=0, microsecond=0) + timedelta(minutes=1))
    parts = clean_expr.split()
    if len(parts) != 5:
        return (from_dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    try:
        minutes = parse_cron_field(parts[0], 0, 59)
        hours = parse_cron_field(parts[1], 0, 23)
        days = parse_cron_field(parts[2], 1, 31)
        months = parse_cron_field(parts[3], 1, 12)
        weekdays = parse_cron_field(parts[4], 0, 7)
        if 7 in weekdays:
            weekdays.add(0)

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

    return (from_dt + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)


class SchedulerEngine:
    """Background asynchronous cron scheduling ticker with Overrun Coalescing."""

    def __init__(self, interval_seconds: int = 15) -> None:
        self.interval_seconds = interval_seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.last_tick_at: Optional[datetime] = None

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

    async def tick(self) -> int:
        """Executes one evaluation cycle for active DailySchedule configurations with Overrun Protection."""
        now = datetime.now(timezone.utc)
        self.last_tick_at = now
        triggered_count = 0

        async with AsyncSessionLocal() as session:
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

                # Check if there is an active batch running for this schedule
                active_batch: Optional[ScanBatch] = None
                if sched.active_batch_id:
                    batch_res = await session.execute(
                        select(ScanBatch).where(ScanBatch.id == sched.active_batch_id)
                    )
                    active_batch = batch_res.scalars().first()

                is_batch_still_running = (
                    active_batch is not None
                    and active_batch.status in (
                        ScanStatus.QUEUED.value,
                        ScanStatus.INITIALIZING.value,
                        ScanStatus.RUNNING.value,
                    )
                )

                if is_batch_still_running:
                    # Current batch is still actively executing
                    # Check for overrun condition: now >= next_run_at
                    if now >= next_run:
                        # OVERRUN CONDITION: Run took longer than the slot interval
                        # Keep active batch intact, record due slots, coalesce to at most ONE follow-up
                        if not sched.overrun_active:
                            sched.overrun_active = True
                            sched.missed_slots_count = 1
                            sched.last_status = "OVERRUN_COALESCING"
                            logger.warning(
                                "Schedule %s overrun detected: active batch %s still executing past slot %s. Coalescing.",
                                sched.name, sched.active_batch_id, next_run.isoformat()
                            )
                        else:
                            sched.missed_slots_count += 1

                        sched.pending_followup = True
                        sched.overdue_reason = (
                            f"Active batch in progress ({active_batch.progress_percentage}% complete); "
                            f"coalescing missed slots ({sched.missed_slots_count}). One follow-up queued."
                        )
                        # Advance next_run_at to the subsequent top of hour
                        sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
                        await session.commit()
                        continue
                    else:
                        # Still running within normal slot window
                        continue

                # Batch is NOT running (either completed, failed, cancelled, or never started)
                if active_batch and not is_batch_still_running:
                    # Active batch recently finished!
                    sched.last_completed_at = active_batch.completed_at or now
                    sched.active_batch_id = None

                    # If a follow-up was queued during an overrun, trigger it immediately!
                    if sched.pending_followup:
                        logger.info(
                            "Schedule %s: active batch finished. Launching coalesced follow-up run (missed: %s slots).",
                            sched.name, sched.missed_slots_count
                        )
                        await self._launch_scheduled_batch(
                            session, sched, now, is_followup=True, missed_coalesced=sched.missed_slots_count
                        )
                        sched.pending_followup = False
                        sched.overrun_active = False
                        sched.missed_slots_count = 0
                        sched.overdue_reason = None
                        sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
                        await session.commit()
                        triggered_count += 1
                        continue
                    else:
                        sched.overrun_active = False
                        sched.overdue_reason = None
                        sched.last_status = active_batch.status

                # Normal Trigger Evaluation: No active batch running and due time arrived
                if now >= next_run:
                    logger.info("Schedule %s triggered at top-of-hour window (%s)", sched.name, next_run.isoformat())
                    await self._launch_scheduled_batch(session, sched, now, is_followup=False)
                    sched.last_run_at = now
                    sched.last_status = "RUNNING"
                    sched.overrun_active = False
                    sched.pending_followup = False
                    sched.overdue_reason = None
                    sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
                    await session.commit()
                    triggered_count += 1

        return triggered_count

    async def _launch_scheduled_batch(
        self,
        session,
        sched: DailySchedule,
        now: datetime,
        is_followup: bool = False,
        missed_coalesced: int = 0,
    ) -> ScanBatch:
        """Atomically builds and dispatches a unified ScanBatch for the scheduled perimeter."""
        # 1. Resolve Targets
        if "ALL" in sched.target_ids:
            targets_res = await session.execute(select(Asset))
            targets = targets_res.scalars().all()
        else:
            uids = [uuid.UUID(t) for t in sched.target_ids]
            targets_res = await session.execute(select(Asset).where(Asset.id.in_(uids)))
            targets = targets_res.scalars().all()

        prefix = "Coalesced Follow-up Sweep" if is_followup else "Scheduled Hourly Sweep"
        batch_name = f"{prefix}: {sched.name} ({now.strftime('%Y-%m-%d %H:00 UTC')})"

        # 2. Create ScanBatch
        batch = ScanBatch(
            id=uuid.uuid4(),
            name=batch_name,
            status=ScanStatus.QUEUED.value,
            target_count=len(targets),
            engines=["all"],
            profiles=[sched.profile],
            metadata_json={
                "schedule_id": str(sched.id),
                "is_followup": is_followup,
                "missed_slots_coalesced": missed_coalesced,
                "triggered_by": "hourly_scheduler",
                "timezone": sched.timezone,
            },
        )
        batch.schedule_id = sched.id
        batch.is_followup = is_followup
        batch.missed_slots_coalesced = missed_coalesced
        session.add(batch)
        await session.flush()

        # 3. Create Child Scans
        dispatcher = get_dispatcher()
        dispatched_scan_ids = []

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
                allow_private_targets=True,
                timeout_seconds=600,
            )
            session.add(scan)
            dispatched_scan_ids.append(scan.id)

        batch.total_scans = len(dispatched_scan_ids)
        sched.active_batch_id = batch.id
        await session.flush()

        # 4. Dispatch to worker queue
        for sid in dispatched_scan_ids:
            await dispatcher.dispatch_scan(sid)

        # 5. Emit lifecycle alert
        alert = SecurityAlert(
            id=uuid.uuid4(),
            severity="INFO",
            title=f"Scheduled Scan Batch: {batch.name}",
            message=f"Assessment schedule '{sched.name}' launched {len(targets)} targets (Follow-up: {is_followup}).",
            category="SCAN",
            is_read=False,
            metadata_json={
                "schedule_id": str(sched.id),
                "batch_id": str(batch.id),
                "is_followup": is_followup,
                "targets_count": len(targets),
                "triggered_at": now.isoformat(),
            },
        )
        session.add(alert)
        return batch
```

#### Component 5: API Endpoints with Deduplication & Status (`backend/app/api/schedules.py`)
```python
@router.get("/{id}/status")
async def get_schedule_status(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
) -> Any:
    """Provides server time, countdown metrics, active batch status, and overdue diagnostic reasons."""
    sched = (await db.execute(select(DailySchedule).where(DailySchedule.id == id))).scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")

    now = datetime.now(timezone.utc)
    next_due = sched.next_run_at
    if next_due and next_due.tzinfo is None:
        next_due = next_due.replace(tzinfo=timezone.utc)

    is_overdue = bool(sched.is_active and next_due and now > next_due)
    overdue_by_seconds = int((now - next_due).total_seconds()) if (is_overdue and next_due) else 0

    active_batch_info = None
    if sched.active_batch_id:
        b_res = await db.execute(select(ScanBatch).where(ScanBatch.id == sched.active_batch_id))
        b = b_res.scalars().first()
        if b:
            active_batch_info = {
                "id": str(b.id),
                "name": b.name,
                "status": b.status,
                "progress_percentage": b.progress_percentage,
                "started_at": b.started_at,
                "target_count": b.target_count,
                "completed_scans": b.completed_scans,
                "total_scans": b.total_scans,
            }

    return {
        "server_time": now.isoformat(),
        "schedule_id": str(sched.id),
        "schedule_name": sched.name,
        "is_active": sched.is_active,
        "is_paused": not sched.is_active,
        "status": sched.last_status or ("PAUSED" if not sched.is_active else "IDLE"),
        "cron_expression": sched.cron_expression,
        "timezone": sched.timezone,
        "next_due_instant": next_due.isoformat() if next_due else None,
        "last_scheduled_run": sched.last_run_at.isoformat() if sched.last_run_at else None,
        "last_completed_run": sched.last_completed_at.isoformat() if sched.last_completed_at else None,
        "active_batch": active_batch_info,
        "overrun_active": sched.overrun_active,
        "pending_followup": sched.pending_followup,
        "missed_slots_count": sched.missed_slots_count,
        "is_overdue": is_overdue,
        "overdue_by_seconds": overdue_by_seconds,
        "overdue_reason": sched.overdue_reason if is_overdue else None,
        "scheduler_daemon_alive": get_scheduler_engine()._running,
    }


@router.post("/{id}/trigger")
async def trigger_schedule(
    id: uuid.UUID,
    request_followup: bool = Query(False, description="Queue at most one follow-up if batch active"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
) -> Any:
    """Manually triggers scheduled pipeline with active run deduplication & follow-up queuing."""
    sched = (await db.execute(select(DailySchedule).where(DailySchedule.id == id))).scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")

    # 1. Deduplication Check: Is a batch already active for this schedule?
    if sched.active_batch_id:
        batch = (await db.execute(select(ScanBatch).where(ScanBatch.id == sched.active_batch_id))).scalars().first()
        if batch and batch.status in (ScanStatus.QUEUED.value, ScanStatus.RUNNING.value, ScanStatus.INITIALIZING.value):
            if request_followup:
                sched.pending_followup = True
                await db.commit()
                return {
                    "status": "FOLLOW_UP_QUEUED",
                    "message": "Matching active batch is running. Exactly one follow-up has been queued.",
                    "active_batch_id": str(batch.id),
                    "active_batch_progress": batch.progress_percentage,
                    "pending_followup": True,
                }
            else:
                return {
                    "status": "ACTIVE_BATCH_RUNNING",
                    "message": f"Assessment batch '{batch.name}' is already running ({batch.progress_percentage}% completed).",
                    "active_batch_id": str(batch.id),
                    "active_batch_progress": batch.progress_percentage,
                    "pending_followup": sched.pending_followup,
                    "action_offered": "QUEUE_FOLLOWUP",
                }

    # 2. No active batch running: dispatch fresh batch
    now = datetime.now(timezone.utc)
    engine = get_scheduler_engine()
    batch = await engine._launch_scheduled_batch(db, sched, now, is_followup=False)
    sched.last_run_at = now
    sched.last_status = "RUNNING"
    sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
    await db.commit()

    return {
        "status": "DISPATCHED",
        "message": f"Assessment batch '{batch.name}' dispatched with {batch.total_scans} targets.",
        "batch_id": str(batch.id),
        "schedule_id": str(sched.id),
    }


@router.put("/{id}/toggle")
async def toggle_schedule(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
) -> Any:
    """Toggles schedule between ACTIVE and PAUSED. Resuming recalculates next top-of-hour instant."""
    sched = (await db.execute(select(DailySchedule).where(DailySchedule.id == id))).scalars().first()
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")

    sched.is_active = not sched.is_active
    now = datetime.now(timezone.utc)
    if sched.is_active:
        sched.next_run_at = compute_next_run(sched.cron_expression, now, sched.timezone)
        sched.overdue_reason = None
    else:
        sched.overdue_reason = "Schedule paused by operator"
    await db.commit()

    return {
        "id": str(sched.id),
        "is_active": sched.is_active,
        "status": "ACTIVE" if sched.is_active else "PAUSED",
        "next_run_at": sched.next_run_at.isoformat() if sched.next_run_at else None,
    }
```

#### Component 6: Frontend 1-Second Countdown Engine Hook (`frontend/src/hooks/useScheduleCountdown.ts`)
```typescript
import { useState, useEffect, useRef } from 'react';
import { api } from '@/lib/api';

export interface CountdownState {
  remainingSeconds: number;
  formattedTime: string;
  isOverdue: boolean;
  overdueBySeconds: number;
  overdueReason: string | null;
  isActive: boolean;
  isPaused: boolean;
  serverTime: string;
  nextDueInstant: string | null;
  activeBatch: any | null;
}

export function useScheduleCountdown(scheduleId: string, refreshIntervalMs = 15000) {
  const [state, setState] = useState<CountdownState>({
    remainingSeconds: 0,
    formattedTime: '--:--:--',
    isOverdue: false,
    overdueBySeconds: 0,
    overdueReason: null,
    isActive: true,
    isPaused: false,
    serverTime: '',
    nextDueInstant: null,
    activeBatch: null,
  });

  const clockSkewRef = useRef<number>(0);
  const nextDueRef = useRef<number | null>(null);

  const fetchStatus = async () => {
    try {
      const res = await api.fetchJson<any>(`/schedules/${scheduleId}/status`);
      const serverMs = Date.parse(res.server_time);
      const localMs = Date.now();
      clockSkewRef.current = serverMs - localMs;

      if (res.next_due_instant) {
        nextDueRef.current = Date.parse(res.next_due_instant);
      } else {
        nextDueRef.current = null;
      }

      updateTick(res);
    } catch (err) {
      console.error('Failed to poll schedule status:', err);
    }
  };

  const updateTick = (meta?: any) => {
    if (!nextDueRef.current) {
      setState((prev) => ({ ...prev, formattedTime: 'PAUSED', isPaused: true }));
      return;
    }

    const adjustedNow = Date.now() + clockSkewRef.current;
    const diffSeconds = Math.floor((nextDueRef.current - adjustedNow) / 1000);

    if (diffSeconds > 0) {
      const h = Math.floor(diffSeconds / 3600);
      const m = Math.floor((diffSeconds % 3600) / 60);
      const s = diffSeconds % 60;
      const formatted = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
      setState((prev) => ({
        ...prev,
        remainingSeconds: diffSeconds,
        formattedTime: formatted,
        isOverdue: false,
        overdueBySeconds: 0,
        ...(meta ? {
          isActive: meta.is_active,
          isPaused: meta.is_paused,
          nextDueInstant: meta.next_due_instant,
          activeBatch: meta.active_batch,
          overdueReason: meta.overdue_reason,
        } : {}),
      }));
    } else {
      const overdueSec = Math.abs(diffSeconds);
      const m = Math.floor(overdueSec / 60);
      const s = overdueSec % 60;
      const formatted = `+${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
      setState((prev) => ({
        ...prev,
        remainingSeconds: 0,
        formattedTime: formatted,
        isOverdue: true,
        overdueBySeconds: overdueSec,
        ...(meta ? {
          isActive: meta.is_active,
          isPaused: meta.is_paused,
          nextDueInstant: meta.next_due_instant,
          activeBatch: meta.active_batch,
          overdueReason: meta.overdue_reason,
        } : {}),
      }));
    }
  };

  useEffect(() => {
    fetchStatus();
    const tickTimer = setInterval(() => updateTick(), 1000); // 1-second countdown tick
    const pollTimer = setInterval(fetchStatus, refreshIntervalMs); // Background sync

    return () => {
      clearInterval(tickTimer);
      clearInterval(pollTimer);
    };
  }, [scheduleId]);

  return { ...state, refetch: fetchStatus };
}
```

---

## 5. Verification Method

### 5.1 Test Scenarios for Worker Implementation

1. **Top-of-Hour Calculation & Timezone Conversion**:
   - Command: `pytest tests/test_hourly_scheduler.py -k "test_top_of_hour" -v`
   - Assert: `compute_next_run("0 * * * *", from_dt=dt, tz_str="Asia/Ho_Chi_Minh")` returns exact top-of-hour UTC timestamp with second=0, microsecond=0 across day boundaries, month boundaries, and leap years.

2. **Overrun Coalescing & Intact Active Run**:
   - Create active batch taking >1 hour.
   - Advance clock by 65 minutes (`now = next_run_at + timedelta(minutes=5)`).
   - Invoke `engine.tick()`.
   - Assert:
     - Active batch remains intact (`QUEUED`/`RUNNING`, not aborted).
     - `sched.overrun_active == True`.
     - `sched.pending_followup == True`.
     - `sched.missed_slots_count == 1`.
     - `sched.next_run_at` advanced by 1 hour.
     - Zero duplicate batch was dispatched.
   - Advance clock another 60 minutes.
   - Invoke `engine.tick()`.
   - Assert:
     - `sched.missed_slots_count == 2`.
     - `sched.pending_followup == True` (remains bounded at 1).
   - Simulate active batch completion (`status="COMPLETED"`).
   - Invoke `engine.tick()`.
   - Assert:
     - Follow-up batch immediately dispatched with `is_followup=True` and `missed_slots_coalesced=2`.
     - `sched.pending_followup == False`.
     - `sched.overrun_active == False`.

3. **Active Run Deduplication on Trigger**:
   - Launch batch.
   - Trigger `POST /schedules/{id}/trigger` while batch is active.
   - Assert HTTP 200 with status `"ACTIVE_BATCH_RUNNING"` and active batch progress. Zero duplicate scans spawned.
   - Trigger `POST /schedules/{id}/trigger?request_followup=true`.
   - Assert HTTP 200 with status `"FOLLOW_UP_QUEUED"` and `pending_followup=True`. Repeated calls return same response.

4. **Countdown & Overdue Diagnostic API**:
   - Call `GET /schedules/{id}/status`.
   - Verify `server_time`, `next_due_instant`, `is_active`, `is_overdue`, and `overdue_reason`.

5. **Pause / Resume Toggle**:
   - Call `PUT /schedules/{id}/toggle`.
   - Verify `is_active=False`, `status="PAUSED"`.
   - Call `PUT /schedules/{id}/toggle` again.
   - Verify `is_active=True`, `next_run_at` recalculated to next top of hour.

### 5.2 Verification Commands
```bash
# Backend unit & enhancement tests
pytest tests/test_enhancement_suite.py -k "schedule or cron" -v
pytest tests/test_empire_e2e_opaque_box.py -k "schedule" -v

# Full test run after implementation
pytest tests/ -v
```

### 5.3 Invalidation Conditions
- Any implementation where active runs taking >1 hour are terminated or restarted.
- Any implementation where missed runs accumulate into multiple concurrent or backlogged executions rather than coalescing into at most ONE follow-up.
- Any implementation where triggering a schedule during an active run spawns a duplicate sweep across in-scope assets.
- Any implementation where countdown timers drift due to client clock skew or lack of server time synchronization.
