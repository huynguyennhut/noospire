import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, GUID, TimestampMixin, UTCDateTime
from backend.app.schemas.common import ScanProfile, ScanQualityStatus, ScanStatus


class ScanBatch(Base, TimestampMixin):
    """Domain model tracking collective batch assessment sweeps across targets and profiles."""
    __tablename__ = "scan_batches"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ScanStatus.QUEUED.value, nullable=False, index=True
    )
    total_scans: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_scans: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_scans: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_scans: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engines: Mapped[Optional[Any]] = mapped_column(JSON, default=list, nullable=True)
    profiles: Mapped[Optional[Any]] = mapped_column(JSON, default=list, nullable=True)

    # Schedule and Coalescing Tracking
    schedule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("daily_schedules.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_followup: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    missed_slots_coalesced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)

    # Cancellation Tracking
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)

    # Relationships
    scans: Mapped[List["Scan"]] = relationship(
        "Scan", back_populates="batch", cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[List["ScanEvent"]] = relationship(
        "ScanEvent", back_populates="batch", cascade="all, delete-orphan", lazy="selectin"
    )

    def __init__(self, **kwargs):
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "status" not in kwargs:
            kwargs["status"] = ScanStatus.QUEUED.value
        if "total_scans" not in kwargs:
            kwargs["total_scans"] = 0
        if "completed_scans" not in kwargs:
            kwargs["completed_scans"] = 0
        if "failed_scans" not in kwargs:
            kwargs["failed_scans"] = 0
        if "cancelled_scans" not in kwargs:
            kwargs["cancelled_scans"] = 0
        if "progress_percentage" not in kwargs:
            kwargs["progress_percentage"] = 0
        if "target_count" not in kwargs:
            kwargs["target_count"] = 0
        if "engines" not in kwargs:
            kwargs["engines"] = ["all"]
        if "profiles" not in kwargs:
            kwargs["profiles"] = []
        if "metadata_json" not in kwargs:
            kwargs["metadata_json"] = {}
        if "is_followup" not in kwargs:
            kwargs["is_followup"] = False
        if "missed_slots_coalesced" not in kwargs:
            kwargs["missed_slots_coalesced"] = 0
        super().__init__(**kwargs)


class Scan(Base, TimestampMixin):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("scan_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    engine: Mapped[str] = mapped_column(String(64), default="all", nullable=False)
    profile: Mapped[str] = mapped_column(String(64), default=ScanProfile.BASELINE.value, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ScanStatus.PENDING.value, nullable=False, index=True
    )
    quality_status: Mapped[Optional[str]] = mapped_column(
        String(32), default=None, nullable=True, index=True
    )
    progress_percentage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_locator: Mapped[str] = mapped_column(String(1024), nullable=False)
    allow_private_targets: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Worker Lease & Fencing Columns
    leased_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    leased_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    fencing_token: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Bounded Retries & Backoff
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    available_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True, index=True)

    # Cancellation & Process Tracking
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    worker_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Idempotency
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)

    # Relationships
    asset: Mapped["Asset"] = relationship("Asset", back_populates="scans")
    batch: Mapped[Optional["ScanBatch"]] = relationship("ScanBatch", back_populates="scans")
    logs: Mapped[List["ScanLog"]] = relationship(
        "ScanLog", back_populates="scan", cascade="all, delete-orphan", lazy="selectin"
    )
    findings: Mapped[List["NormalizedFinding"]] = relationship(
        "NormalizedFinding", back_populates="scan", cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[List["ScanEvent"]] = relationship(
        "ScanEvent", back_populates="scan", cascade="all, delete-orphan", lazy="selectin"
    )
    engine_executions: Mapped[List["EngineExecution"]] = relationship(
        "EngineExecution", back_populates="scan", cascade="all, delete-orphan", lazy="selectin"
    )

    def __init__(self, **kwargs):
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "batch_id" not in kwargs:
            kwargs["batch_id"] = None
        if "engine" not in kwargs:
            kwargs["engine"] = "all"
        if "profile" not in kwargs:
            kwargs["profile"] = ScanProfile.BASELINE.value
        if "status" not in kwargs:
            kwargs["status"] = ScanStatus.PENDING.value
        if "quality_status" not in kwargs:
            kwargs["quality_status"] = None
        if "progress_percentage" not in kwargs:
            kwargs["progress_percentage"] = 0
        if "allow_private_targets" not in kwargs:
            kwargs["allow_private_targets"] = False
        if "timeout_seconds" not in kwargs:
            kwargs["timeout_seconds"] = 600
        if "fencing_token" not in kwargs:
            kwargs["fencing_token"] = 0
        if "attempts" not in kwargs:
            kwargs["attempts"] = 0
        if "max_retries" not in kwargs:
            kwargs["max_retries"] = 3
        super().__init__(**kwargs)


class EngineExecution(Base, TimestampMixin):
    """Tracks fine-grained execution per target, profile, and engine with attempt history."""
    __tablename__ = "engine_executions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("scan_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    engine: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="PLANNED", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_output_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    coverage_summary: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="engine_executions")


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(64), default="system", nullable=False)

    scan: Mapped["Scan"] = relationship("Scan", back_populates="logs")
