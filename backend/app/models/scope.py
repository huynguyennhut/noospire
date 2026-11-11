import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, GUID, TimestampMixin


class AssetAssessmentScope(Base, TimestampMixin):
    """Authorized continuous security assessment scope grant.
    Enforces exact origin matching, allowed path patterns, port boundaries,
    rate limit RPS, byte budgets, and emergency kill switches.
    """
    __tablename__ = "asset_assessment_scopes"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    exact_origin: Mapped[str] = mapped_column(String(512), nullable=False)
    ports: Mapped[list] = mapped_column(JSON, default=lambda: [80, 443], nullable=False)
    allowed_path_patterns: Mapped[list] = mapped_column(JSON, default=lambda: ["/*"], nullable=False)
    permitted_checks: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    rate_limit_rps: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    concurrency_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    byte_budget: Mapped[int] = mapped_column(Integer, default=10485760, nullable=False)  # 10MB
    max_requests_per_run: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    emergency_stop_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    time_window_start: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    time_window_end: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    asset = relationship("Asset", back_populates="assessment_scopes", lazy="selectin")


__all__ = ["AssetAssessmentScope"]
