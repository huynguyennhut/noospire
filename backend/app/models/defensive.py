"""Defensive engine execution records (Milestone 3).

Terminology (kept distinct in API and UI):
- Execution (`ExecutionRecord`): one logical engine run on one asset with one input.
  1:1 with the queue row (`scans`) that carries lease/fencing state.
- Attempt (`ExecutionAttempt`): one worker's try at an execution, bound to a fencing token.
- Worker (`WorkerHeartbeat`): a process that claims executions.
- Finding: a normalized issue produced by a succeeded execution (table `findings`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import GUID, Base, UTCDateTime


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Engine execution terminal/non-terminal states (lower-case contract values).
EXEC_QUEUED = "queued"
EXEC_RUNNING = "running"
EXEC_SUCCEEDED = "succeeded"
EXEC_FAILED = "failed"
EXEC_TIMED_OUT = "timed_out"
EXEC_CANCELLED = "cancelled"
EXEC_SKIPPED = "skipped"
EXEC_UNAVAILABLE = "unavailable"
TERMINAL_STATES = {EXEC_SUCCEEDED, EXEC_FAILED, EXEC_TIMED_OUT, EXEC_CANCELLED, EXEC_SKIPPED, EXEC_UNAVAILABLE}


class Artifact(Base):
    """Owner/grantee-supplied input file (SBOM, lockfile, manifest). Stored immutable by hash."""
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # sbom
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_note: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(String(64), nullable=False)  # user id
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)


class AdvisorySnapshot(Base):
    """A versioned, content-addressed advisory database (OSV format) imported by the owner."""
    __tablename__ = "advisory_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. "OSV export (Empire)"
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ecosystems: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    data_modified_max: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    imported_by: Mapped[str] = mapped_column(String(64), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)


class ExecutionRecord(Base):
    __tablename__ = "execution_records"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_execution_idem"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("scans.id", ondelete="CASCADE"),
                                               unique=True, index=True)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    engine_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # sbom | tls_health
    driver: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    driver_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    execution_mode: Mapped[str] = mapped_column(String(32), default="native", nullable=False)
    artifact_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    input_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_descriptor: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    rule_source: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    rule_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    rule_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scope_revision: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trigger: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    request_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=EXEC_QUEUED, nullable=False, index=True)
    status_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_class: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    finding_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    output_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    worker_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    queued_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    observed_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # monotonic clock
    # Milestone 4: planning / scheduling provenance
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    schedule_slot_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True, index=True)
    lane: Mapped[str] = mapped_column(String(16), default="quick", nullable=False)  # quick | long
    target_host: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    plan_note: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)


class ExecutionAttempt(Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (UniqueConstraint("execution_id", "attempt_no", name="uq_attempt_no"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("execution_records.id", ondelete="CASCADE"),
                                                    index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    fencing_token: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    phase: Mapped[str] = mapped_column(String(32), default="preflight", nullable=False)  # preflight|running|reporting
    status: Mapped[str] = mapped_column(String(32), default=EXEC_RUNNING, nullable=False)  # + abandoned
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_class: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # redacted


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hostname: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    engines: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)
    active_executions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    throttle_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
