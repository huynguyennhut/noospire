"""Milestone 4 operations model: hourly monitor schedules, slot claims, run requests,
capacity settings and per-attempt resource metrics.

All timestamps are stored in UTC. Slots are aligned to the UTC epoch; because ICT is UTC+7
with no DST, an hourly slot at HH:00 UTC is also HH:00 ICT.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import GUID, Base, UTCDateTime


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MonitorSchedule(Base):
    __tablename__ = "monitor_schedules"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    selection: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {kind, asset_ids, module}
    engines: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    profile: Mapped[str] = mapped_column(String(16), default="light", nullable=False)  # light | slow
    interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    max_workers: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    start_after: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    last_slot_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    last_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    last_result_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    last_result_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    last_result_batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    last_full_success_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    pending_catchup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    missed_slots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    overdue_reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)


class ScheduleSlot(Base):
    """One claimed slot of a schedule. The unique (schedule_id, slot_at) constraint is the
    leader election: whichever scheduler commits the row first owns that slot."""
    __tablename__ = "schedule_slots"
    __table_args__ = (UniqueConstraint("schedule_id", "slot_at", name="uq_schedule_slot"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    slot_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="scheduled", nullable=False)  # scheduled | catchup
    # launched | coalesced | completed | partial | failed | no_work
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    claimed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)
    launched_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True, index=True)
    missed_before: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coalesced_slots: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    plan_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result_summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class RunRequest(Base):
    """Idempotency record for manual runs (POST /runs)."""
    __tablename__ = "run_requests"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_run_request_key"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)


class CapacitySettings(Base):
    """Singleton (id=1) estate-wide capacity limits set by the owner."""
    __tablename__ = "capacity_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    max_running_executions: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    per_host_hourly_quota: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    per_host_egress_bytes_hourly: Mapped[int] = mapped_column(Integer, default=2_000_000, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)


class ExecutionMetric(Base):
    """Resource usage for one committed attempt. CPU and RSS are sampled for the worker
    process (concurrent attempts share it); bytes and timings are exact."""
    __tablename__ = "execution_metrics"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)
    engine_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    queue_delay_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)  # engine work only
    slot_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # attempt start -> commit (slot held)
    cpu_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rss_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    input_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    output_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    egress_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False, index=True)
