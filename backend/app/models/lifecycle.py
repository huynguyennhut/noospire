"""Milestone 5 lifecycle model.

- FindingObservation: one row per (finding, execution) evaluation. Every observation is kept;
  the outcome is one of new | unchanged | reopened | fixed | unavailable | changed_scope.
- FindingChange: who changed which field of a finding, when, from what to what.
- Notification: per-user inbox (read / deleted are per user; the source object stays).
- HiddenRecord: an execution or run removed from the console views. The audit log and
  the underlying evidence are kept; hiding is reversible by the owner.
- ReportSnapshot: the frozen data a report was rendered from, with template version and checksums.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import GUID, Base, UTCDateTime


def _now() -> datetime:
    return datetime.now(timezone.utc)


OUTCOMES = ("new", "unchanged", "reopened", "fixed", "unavailable", "changed_scope")


class FindingObservation(Base):
    __tablename__ = "finding_observations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True, index=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    engine_id: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status_before: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status_after: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    output_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rule_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False, index=True)


class FindingChange(Base):
    __tablename__ = "finding_changes"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    finding_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # None = system (engine)
    actor_name: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    changed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False, index=True)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "dedup_key", name="uq_notification_dedup"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # finding_new | finding_reopened | job_succeeded | job_failed | run_finished | source_stale
    severity: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)  # finding | execution | run | feed | worker
    object_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    link: Mapped[str] = mapped_column(String(512), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)


class HiddenRecord(Base):
    __tablename__ = "hidden_records"
    __table_args__ = (UniqueConstraint("object_type", "object_id", name="uq_hidden_object"),)

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)  # execution
    object_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False, index=True)
    hidden_by: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    hidden_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False)


class ReportSnapshot(Base):
    __tablename__ = "report_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # {kind, asset_ids, batch_id}
    asset_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True, index=True)
    template_version: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    files: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)  # fmt -> {path, sha256, bytes}
    execution_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    correlation_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    finding_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    previous_snapshot_id: Mapped[Optional[uuid.UUID]] = mapped_column(GUID(), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=_now, nullable=False, index=True)
