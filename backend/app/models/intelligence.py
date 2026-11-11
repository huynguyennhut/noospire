"""SQLAlchemy models for Threat Intelligence and Vulnerability Correlation.

Conforms to Noosforge Sentinel R3 & R4 specifications.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
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


class VulnerabilityIntelligence(Base):
    """Canonical vulnerability threat intelligence entity aggregating NVD, CISA KEV,

    FIRST EPSS, OSV, and GHSA metadata.
    """

    __tablename__ = "vulnerability_intelligence"

    # Canonical Identifier (e.g. 'CVE-2021-44228')
    cve_id: Mapped[str] = mapped_column(String(32), primary_key=True, index=True)

    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # CVSS Metrics
    cvss_v3_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    cvss_v3_vector: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    cvss_v3_severity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    cvss_v2_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cvss_v4_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # FIRST EPSS Metrics
    epss_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    epss_percentile: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    epss_last_updated: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # CISA KEV Metrics
    is_cisa_kev: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    cisa_kev_date_added: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    cisa_kev_due_date: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    cisa_kev_ransomware: Mapped[Optional[str]] = mapped_column(String(32), default="Unknown", nullable=True)
    cisa_action_required: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # SSVC Decisions (CISA Stakeholder-Specific Vulnerability Categorization)
    ssvc_exploitation: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    ssvc_automatable: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    ssvc_technical_impact: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Classifications and Weaknesses
    cwe_ids: Mapped[List[str]] = mapped_column(SQLITE_JSON, default=list, nullable=False)

    # Source Provenance and Tracking
    source_provenance: Mapped[dict[str, Any]] = mapped_column(SQLITE_JSON, default=dict, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_modified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Bidirectional Aliases Relationship
    aliases: Mapped[List[VulnerabilityAlias]] = relationship(
        "VulnerabilityAlias",
        back_populates="vulnerability",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to standard dictionary."""
        return {
            "cve_id": self.cve_id,
            "title": self.title,
            "summary": self.summary,
            "description": self.description,
            "cvss_v3_score": self.cvss_v3_score,
            "cvss_v3_vector": self.cvss_v3_vector,
            "cvss_v3_severity": self.cvss_v3_severity,
            "cvss_v2_score": self.cvss_v2_score,
            "cvss_v4_score": self.cvss_v4_score,
            "epss_score": self.epss_score,
            "epss_percentile": self.epss_percentile,
            "epss_last_updated": self.epss_last_updated.isoformat() if self.epss_last_updated else None,
            "is_cisa_kev": self.is_cisa_kev,
            "cisa_kev_date_added": self.cisa_kev_date_added.isoformat() if self.cisa_kev_date_added else None,
            "cisa_kev_due_date": self.cisa_kev_due_date.isoformat() if self.cisa_kev_due_date else None,
            "cisa_kev_ransomware": self.cisa_kev_ransomware,
            "cisa_action_required": self.cisa_action_required,
            "ssvc_exploitation": self.ssvc_exploitation,
            "ssvc_automatable": self.ssvc_automatable,
            "ssvc_technical_impact": self.ssvc_technical_impact,
            "cwe_ids": self.cwe_ids or [],
            "source_provenance": self.source_provenance or {},
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "last_modified_at": self.last_modified_at.isoformat() if self.last_modified_at else None,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "aliases": [a.alias_id for a in self.aliases] if self.aliases else [],
        }


class VulnerabilityAlias(Base):
    """Mapping table correlating vendor and package advisory IDs (GHSA, PYSEC,

    RUSTSEC, ALAS) to canonical CVE IDs.
    """

    __tablename__ = "vulnerability_aliases"

    alias_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    cve_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("vulnerability_intelligence.cve_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 'GHSA', 'PYSEC', 'RUSTSEC', etc.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Reverse relationship
    vulnerability: Mapped[VulnerabilityIntelligence] = relationship(
        "VulnerabilityIntelligence",
        back_populates="aliases",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert alias to dictionary."""
        return {
            "alias_id": self.alias_id,
            "cve_id": self.cve_id,
            "alias_type": self.alias_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
