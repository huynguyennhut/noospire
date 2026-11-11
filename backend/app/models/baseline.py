import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, GUID, TimestampMixin
from backend.app.schemas.common import ExposureClassification


class BaselineException(Base, TimestampMixin):
    """Approved Public Exposure Baseline Exception Record.
    Implements Approved Public Exposure Policy for paths like `/media`.
    """
    __tablename__ = "baseline_exceptions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(512), nullable=False, index=True)  # e.g., "https://mh.empire.edu.vn/media/*"
    classification: Mapped[str] = mapped_column(
        String(64), default=ExposureClassification.PUBLIC_BY_DESIGN.value, nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(128), default="Security Operations Lead", nullable=False)
    approved_by: Mapped[str] = mapped_column(String(128), default="Chief Information Security Officer", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expiration_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    review_history: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
