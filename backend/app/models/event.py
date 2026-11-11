"""Durable Security Event Model for Noosforge Sentinel.

Provides monotonically ordered event records supporting Last-Event-ID cursor replay,
high-volume multi-engine audit trails, and multi-replica event bus dispatch.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, GUID, UTCDateTime


def sanitize_event_details(details: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively sanitizes event details dictionary: redacting credentials and truncating large blobs."""
    if not details:
        return {}
    sanitized: Dict[str, Any] = {}
    SENSITIVE_KEYS = {"authorization", "token", "password", "secret", "cookie", "set-cookie", "api_key", "jwt"}
    for k, v in details.items():
        k_lower = str(k).lower()
        if any(s in k_lower for s in SENSITIVE_KEYS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 4096:
            sanitized[k] = v[:4096] + "... [TRUNCATED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_event_details(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_event_details(item) if isinstance(item, dict) else item for item in v[:50]]
        else:
            sanitized[k] = v
    return sanitized


class ScanEvent(Base):
    """Durable security event entity backed by auto-incrementing monotonic integer ID."""
    __tablename__ = "scan_events"

    # Monotonic Sequence Primary Key (SQLite INTEGER / PostgreSQL BIGSERIAL)
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
        index=True,
    )

    # Scoping Identifiers
    scan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("scan_batches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    target_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(),
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Engine & Execution Details
    engine: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Actor & Origin Provenance
    actor_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    actor_type: Mapped[str] = mapped_column(String(32), default="SYSTEM", nullable=False)

    # Event Type & Severity Level
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO", nullable=False)

    # Message Description
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Strict UTC Timestamp
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )  # indexed via ix_scan_events_occurred_at in __table_args__ (one definition only)

    # Structured Sanitized Payload
    details_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        default=dict,
        nullable=True,
    )

    # Relationships
    scan: Mapped[Optional["Scan"]] = relationship("Scan", back_populates="events")
    batch: Mapped[Optional["ScanBatch"]] = relationship("ScanBatch", back_populates="events")

    # Compound Indexes for O(1) Index-Seek Cursor Queries
    __table_args__ = (
        Index("ix_scan_events_scan_cursor", "scan_id", "id"),
        Index("ix_scan_events_batch_cursor", "batch_id", "id"),
        Index("ix_scan_events_occurred_at", "occurred_at"),
        Index("ix_scan_events_type_scan", "event_type", "scan_id"),
    )
