import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, GUID, TimestampMixin
from backend.app.schemas.common import FindingSeverity, FindingStatus, ExposureClassification


class NormalizedFinding(Base, TimestampMixin):
    __tablename__ = "findings"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Deterministic deduplication hash
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Empire Business Module & Exposure Classification
    empire_module: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    exposure_classification: Mapped[Optional[str]] = mapped_column(
        String(64), default=None, nullable=True
    )
    is_approved_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Engine metadata
    scanner_engine: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    scanner_rule_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(
        String(32), default=FindingSeverity.INFO.value, nullable=False, index=True
    )
    original_severity: Mapped[str] = mapped_column(String(64), nullable=False)

    # Vulnerability intelligence mapping
    cve_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    cwe_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cvss_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cvss_vector: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    epss_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    epss_percentile: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_kev: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Location & Target context
    target_location: Mapped[str] = mapped_column(String(1024), nullable=False)
    target_component: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    affected_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    fixed_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Forensic evidence & Remediation
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    raw_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    remediation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    references: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Lifecycle & Deduplication stats
    status: Mapped[str] = mapped_column(
        String(32), default=FindingStatus.NEW.value, nullable=False, index=True
    )
    remediation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    assignee: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    retest_status: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    asset: Mapped["Asset"] = relationship("Asset", back_populates="findings")
    scan: Mapped["Scan"] = relationship("Scan", back_populates="findings")
