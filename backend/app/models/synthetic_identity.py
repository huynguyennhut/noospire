import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, GUID, TimestampMixin


class SyntheticIdentity(Base, TimestampMixin):
    """Synthetic Student and Operator Identities for non-destructive access control validation."""
    __tablename__ = "synthetic_identities"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    identifier: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(64), default="STUDENT", nullable=False)  # STUDENT, TESTER, AUDITOR
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
