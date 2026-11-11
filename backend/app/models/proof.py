import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlalchemy import Column, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, GUID, TimestampMixin


class OwnershipProofMethod(str, Enum):
    DNS_TXT = "DNS_TXT"
    HTTP_WELL_KNOWN = "HTTP_WELL_KNOWN"
    TLS_CANARY = "TLS_CANARY"
    ADMIN_OVERRIDE = "ADMIN_OVERRIDE"


class OwnershipProofStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class AssetOwnershipProof(Base, TimestampMixin):
    """Cryptographic ownership verification challenge proof for target locators.
    Replaces reachability heuristics with verifiable challenge proofs (DNS TXT, HTTP well-known, etc.).
    """
    __tablename__ = "asset_ownership_proofs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    method: Mapped[str] = mapped_column(
        String(32), default=OwnershipProofMethod.HTTP_WELL_KNOWN.value, nullable=False
    )
    challenge_token: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=OwnershipProofStatus.PENDING.value, index=True, nullable=False
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    proof_data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    asset = relationship("Asset", back_populates="ownership_proofs", lazy="selectin")


__all__ = ["AssetOwnershipProof", "OwnershipProofMethod", "OwnershipProofStatus"]
