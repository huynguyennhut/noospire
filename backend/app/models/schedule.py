import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String
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
    target_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)  # list of target UUIDs or ["ALL"]

    # Execution Tracking Timestamps (Strict UTCDateTime)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    last_completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    next_run_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
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

    # Relationship to active running batch
    active_batch: Mapped[Optional["ScanBatch"]] = relationship(
        "ScanBatch", foreign_keys=[active_batch_id], lazy="selectin"
    )
