import uuid
from typing import List, Optional
from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, GUID, TimestampMixin
from backend.app.models.proof import AssetOwnershipProof
from backend.app.models.scope import AssetAssessmentScope
from backend.app.schemas.common import (
    AssetType,
    Criticality,
    EmpireModule,
    Exposure,
    VerificationStatus,
    VerificationType,
)


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(32), default=AssetType.WEB_APP.value, nullable=False)
    target_locator: Mapped[str] = mapped_column(String(1024), nullable=False)

    # Empire Business Module Mapping
    empire_module: Mapped[str] = mapped_column(
        String(64), default=EmpireModule.STUDENT_MANAGEMENT.value, nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(String(32), default="PRODUCTION", nullable=False)
    technology: Mapped[str] = mapped_column(String(255), default="Web Service", nullable=False)

    # Approved Public Media Policy & Target Rules
    approved_media_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    assessment_policy: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    auth_profile: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    excluded_endpoints: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Ownership verification (default to PENDING and NONE)
    verification_status: Mapped[str] = mapped_column(
        String(32), default=VerificationStatus.PENDING.value, nullable=False, index=True
    )
    verification_type: Mapped[str] = mapped_column(
        String(32), default=VerificationType.HTTP_WELL_KNOWN.value, nullable=False
    )
    verification_token: Mapped[str] = mapped_column(
        String(128), default=lambda: f"sentinel-{uuid.uuid4().hex[:16]}", nullable=False
    )
    verified_at: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Risk context
    criticality: Mapped[str] = mapped_column(String(32), default=Criticality.MEDIUM.value, nullable=False)
    exposure: Mapped[str] = mapped_column(String(32), default=Exposure.INTERNET.value, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    # Relationships
    scans: Mapped[List["Scan"]] = relationship(
        "Scan", back_populates="asset", cascade="all, delete-orphan", lazy="selectin"
    )
    findings: Mapped[List["NormalizedFinding"]] = relationship(
        "NormalizedFinding", back_populates="asset", cascade="all, delete-orphan", lazy="selectin"
    )
    ownership_proofs: Mapped[List["AssetOwnershipProof"]] = relationship(
        "AssetOwnershipProof", back_populates="asset", cascade="all, delete-orphan", lazy="selectin"
    )
    assessment_scopes: Mapped[List["AssetAssessmentScope"]] = relationship(
        "AssetAssessmentScope", back_populates="asset", cascade="all, delete-orphan", lazy="selectin"
    )

    def __init__(self, **kwargs):
        if "id" not in kwargs:
            kwargs["id"] = uuid.uuid4()
        if "asset_type" not in kwargs:
            kwargs["asset_type"] = AssetType.WEB_APP.value
        if "empire_module" not in kwargs:
            kwargs["empire_module"] = EmpireModule.STUDENT_MANAGEMENT.value
        if "environment" not in kwargs:
            kwargs["environment"] = "PRODUCTION"
        if "verification_status" not in kwargs:
            kwargs["verification_status"] = VerificationStatus.PENDING.value
        if "verification_type" not in kwargs:
            kwargs["verification_type"] = "NONE"
        if "verification_token" not in kwargs:
            kwargs["verification_token"] = f"sentinel-{uuid.uuid4().hex[:16]}"
        super().__init__(**kwargs)
