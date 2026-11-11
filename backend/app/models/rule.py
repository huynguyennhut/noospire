"""SQLAlchemy models for Detection Rules, Test Fixtures, and Review Lifecycle Auditing.

Conforms to Noosforge Sentinel R4 specifications.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from backend.app.models.base import Base
except ImportError:
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):  # type: ignore[no-redef]
        pass


def utc_now() -> datetime:
    """Return current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


class RuleSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RuleStatus(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class DetectionRule(Base):
    """Declarative YAML detection rule conforming to Sentinel Rule Spec v1."""

    __tablename__ = "detection_rules"

    # Unique Kebab-case Identifier (e.g. 'sentinel-det-2026-0042')
    id: Mapped[str] = mapped_column(String(128), primary_key=True, index=True)

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    author: Mapped[str] = mapped_column(String(128), nullable=False)

    severity: Mapped[str] = mapped_column(String(16), default=RuleSeverity.MEDIUM.value, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=RuleStatus.DRAFT.value, nullable=False, index=True)

    # Scopes: list of target types (e.g. ['web_application', 'api_endpoint'])
    target_types: Mapped[List[str]] = mapped_column(SQLITE_JSON, default=list, nullable=False)

    # Metadata: cve list, cwe list, cvss_score, tags list
    metadata_json: Mapped[dict[str, Any]] = mapped_column(SQLITE_JSON, default=dict, nullable=False)

    # Detection logic: engine, condition, matchers list
    detection_json: Mapped[dict[str, Any]] = mapped_column(SQLITE_JSON, default=dict, nullable=False)

    # Remediation guidance and reference URLs
    remediation_json: Mapped[dict[str, Any]] = mapped_column(SQLITE_JSON, default=dict, nullable=False)

    # Original YAML definition for full reproducibility
    raw_yaml: Mapped[str] = mapped_column(Text, nullable=False)

    # Authorship & Governance
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    audit_logs: Mapped[List[RuleAuditLog]] = relationship(
        "RuleAuditLog",
        back_populates="rule",
        cascade="all, delete-orphan",
        order_by="RuleAuditLog.timestamp.desc()",
        lazy="selectin",
    )

    test_fixtures: Mapped[List[RuleTestFixtureRecord]] = relationship(
        "RuleTestFixtureRecord",
        back_populates="rule",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert rule to dictionary representation."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "severity": self.severity,
            "status": self.status,
            "target_types": self.target_types or [],
            "metadata": self.metadata_json or {},
            "detection": self.detection_json or {},
            "remediation": self.remediation_json or {},
            "raw_yaml": self.raw_yaml,
            "created_by": self.created_by,
            "approved_by": self.approved_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "audit_logs": [log.to_dict() for log in self.audit_logs] if self.audit_logs else [],
            "test_fixtures": [tf.to_dict() for tf in self.test_fixtures] if self.test_fixtures else [],
        }


class RuleAuditLog(Base):
    """Immutable audit trail for detection rule lifecycle transitions and peer reviews."""

    __tablename__ = "rule_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("detection_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. "created", "submitted_review", "approved"
    from_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Reverse relationship
    rule: Mapped[DetectionRule] = relationship("DetectionRule", back_populates="audit_logs")

    def to_dict(self) -> dict[str, Any]:
        """Convert audit log to dictionary."""
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "actor": self.actor,
            "action": self.action,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "notes": self.notes,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class RuleTestFixtureRecord(Base):
    """Test fixture record associated with a detection rule for regression verification."""

    __tablename__ = "rule_test_fixtures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("detection_rules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    expected_match: Mapped[bool] = mapped_column(Boolean, nullable=False)
    input_payload: Mapped[dict[str, Any]] = mapped_column(SQLITE_JSON, nullable=False)
    last_run_success: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    last_run_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    rule: Mapped[DetectionRule] = relationship("DetectionRule", back_populates="test_fixtures")

    def to_dict(self) -> dict[str, Any]:
        """Convert test fixture record to dictionary."""
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "name": self.name,
            "expected_match": self.expected_match,
            "input_payload": self.input_payload,
            "last_run_success": self.last_run_success,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "error_message": self.error_message,
        }
