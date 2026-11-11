import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, GUID, TimestampMixin
from backend.app.schemas.common import FindingSeverity


class SecurityAlert(Base, TimestampMixin):
    """In-app alert notification entity for Security Operations Center."""
    __tablename__ = "security_alerts"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    severity: Mapped[str] = mapped_column(String(32), default=FindingSeverity.INFO.value, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), default="ASSESSMENT", nullable=False)  # KEV, VULN, BASELINE, SCAN
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
