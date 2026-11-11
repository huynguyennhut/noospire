import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, GUID, TimestampMixin, User, UTCDateTime


class UserRole(str, Enum):
    OWNER = "OWNER"
    SUPER_ADMIN = "SUPER_ADMIN"
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    DEVELOPER = "DEVELOPER"
    SECURITY_LEAD = "SECURITY_LEAD"
    VIEWER = "VIEWER"
    USER = "USER"


# Dynamically attach tokens_valid_after to User if not already mapped
if not hasattr(User, "tokens_valid_after"):
    User.tokens_valid_after = mapped_column(UTCDateTime, nullable=True)


class RevokedToken(Base, TimestampMixin):
    """Durable store for revoked JWTs, session logouts, and invalidation records."""
    __tablename__ = "revoked_tokens"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    token_jti: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(256), default="USER_LOGOUT", nullable=True)


class UserAssetGrant(Base, TimestampMixin):
    """Scoped developer asset access grants (R5).
    Controls explicit asset visibility, scan execution, and triage rights.
    """
    __tablename__ = "user_asset_grants"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), index=True, nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), index=True, nullable=False
    )
    permissions: Mapped[str] = mapped_column(String(64), default="READ,SCAN", nullable=False)
    granted_by: Mapped[str] = mapped_column(String(128), nullable=False)


__all__ = ["User", "UserRole", "RevokedToken", "UserAssetGrant"]
