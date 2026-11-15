import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base, GUID, TimestampMixin


class ChecklistCategory(str, enum.Enum):
    """Empire Pentest Checklist Categories (6 categories)."""
    WEB = "WEB"
    API = "API"
    FILE = "FILE"
    AUTH = "AUTH"
    INFRA = "INFRA"
    DEP = "DEP"


class ChecklistResultState(str, enum.Enum):
    """Immutable 7-state result engine states."""
    PASS = "PASS"
    FAIL = "FAIL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"
    ERROR = "ERROR"


class AutomationType(str, enum.Enum):
    """Execution automation capability."""
    AUTOMATED = "AUTOMATED"
    MANUAL = "MANUAL"
    HYBRID = "HYBRID"


class TargetEngine(str, enum.Enum):
    """Primary execution or auditing engine."""
    ZAP = "ZAP"
    NUCLEI = "NUCLEI"
    TRIVY = "TRIVY"
    EMPIRE_ENGINE = "EMPIRE_ENGINE"
    SYNTHETIC_HARNESS = "SYNTHETIC_HARNESS"
    FILE_POLICY = "FILE_POLICY"


# Set of terminal/unrun/blocked states that can NEVER transition directly to PASS
UNVERIFIED_STATES_CANNOT_PASS = {
    ChecklistResultState.NOT_RUN.value,
    ChecklistResultState.BLOCKED.value,
    ChecklistResultState.ERROR.value,
}


def validate_state_transition(current_state: str, new_state: str) -> None:
    """Enforces the invariant: Never convert unrun, blocked, or error states to PASS.
    A check must execute and produce evidence, or undergo verified remediation,
    before yielding a PASS state.
    """
    if current_state in UNVERIFIED_STATES_CANNOT_PASS and new_state == ChecklistResultState.PASS.value:
        raise ValueError(
            f"State invariant violation: cannot transition check result from '{current_state}' "
            f"directly to '{new_state}'. Check must be executed or remediated with affirmative evidence."
        )


class ChecklistDefinition(Base, TimestampMixin):
    """Versioned Pentest Checklist Check Definition.
    Contains bilingual Vietnamese/English metadata, severity, target engine,
    and remediation guidance for each of the 39 Empire checks.
    """
    __tablename__ = "checklist_definitions"

    check_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    category: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    title_vi: Mapped[str] = mapped_column(String(256), nullable=False)
    title_en: Mapped[str] = mapped_column(String(256), nullable=False)
    description_vi: Mapped[str] = mapped_column(Text, nullable=False)
    description_en: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="MEDIUM", nullable=False)
    automation_type: Mapped[str] = mapped_column(String(32), default=AutomationType.AUTOMATED.value, nullable=False)
    target_engine: Mapped[str] = mapped_column(String(64), default=TargetEngine.EMPIRE_ENGINE.value, nullable=False)
    remediation_guidance_vi: Mapped[str] = mapped_column(Text, default="", nullable=False)
    remediation_guidance_en: Mapped[str] = mapped_column(Text, default="", nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0.0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    results = relationship("ChecklistResult", back_populates="definition", cascade="all, delete-orphan")


class ChecklistAssessmentRun(Base, TimestampMixin):
    """Container for a point-in-time pentest checklist assessment execution against an asset."""
    __tablename__ = "checklist_assessment_runs"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False
    )
    batch_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("scan_batches.id", ondelete="SET NULL"), nullable=True
    )
    scan_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("scans.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_checks: Mapped[int] = mapped_column(Integer, default=39, nullable=False)
    automated_coverage_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    manual_completion_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    state_counts: Mapped[Dict[str, int]] = mapped_column(
        JSON,
        default=lambda: {
            ChecklistResultState.PASS.value: 0,
            ChecklistResultState.FAIL.value: 0,
            ChecklistResultState.NEEDS_REVIEW.value: 0,
            ChecklistResultState.NOT_APPLICABLE.value: 0,
            ChecklistResultState.BLOCKED.value: 0,
            ChecklistResultState.NOT_RUN.value: 39,
            ChecklistResultState.ERROR.value: 0,
        },
        nullable=False,
    )

    asset = relationship("Asset", lazy="selectin")
    results = relationship("ChecklistResult", back_populates="run", cascade="all, delete-orphan", lazy="selectin")

    def recompute_metrics(self) -> None:
        """Calculates honest automated coverage and manual review completion percentages
        without score fabrication.
        - automated_coverage_pct: evaluated automated checks / total automated checks
        - manual_completion_pct: completed manual reviews / total manual/hybrid checks
        """
        counts = {state.value: 0 for state in ChecklistResultState}
        automated_total = 0
        automated_evaluated = 0
        manual_total = 0
        manual_completed = 0

        for r in self.results:
            counts[r.state] = counts.get(r.state, 0) + 1
            auto_type = getattr(r.definition, "automation_type", AutomationType.AUTOMATED.value) if r.definition else AutomationType.AUTOMATED.value
            
            if auto_type in (AutomationType.AUTOMATED.value, AutomationType.HYBRID.value):
                automated_total += 1
                # Considered evaluated if it has been run (not NOT_RUN and not BLOCKED)
                if r.state not in (ChecklistResultState.NOT_RUN.value, ChecklistResultState.BLOCKED.value):
                    automated_evaluated += 1

            if auto_type in (AutomationType.MANUAL.value, AutomationType.HYBRID.value):
                manual_total += 1
                # Considered completed if reviewed or evaluated to terminal state
                if r.reviewed_by is not None or r.state not in (ChecklistResultState.NOT_RUN.value, ChecklistResultState.NEEDS_REVIEW.value):
                    manual_completed += 1

        self.state_counts = counts
        self.automated_coverage_pct = round((automated_evaluated / automated_total * 100.0), 2) if automated_total > 0 else 0.0
        self.manual_completion_pct = round((manual_completed / manual_total * 100.0), 2) if manual_total > 0 else 0.0


class ChecklistResult(Base, TimestampMixin):
    """Immutable single check execution record within an assessment run.
    Enforces 7-state result engine semantics and records forensic evidence.
    """
    __tablename__ = "checklist_results"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("checklist_assessment_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    check_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("checklist_definitions.check_id", ondelete="CASCADE"), index=True, nullable=False
    )
    state: Mapped[str] = mapped_column(
        String(32), default=ChecklistResultState.NOT_RUN.value, nullable=False
    )
    evidence_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    execution_duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    run = relationship("ChecklistAssessmentRun", back_populates="results")
    definition = relationship("ChecklistDefinition", back_populates="results", lazy="selectin")

    def transition_state(
        self,
        new_state: ChecklistResultState | str,
        reviewed_by: Optional[str] = None,
        review_notes: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Safely transitions check result state while enforcing immutable state invariants."""
        target_state = new_state.value if isinstance(new_state, ChecklistResultState) else new_state
        validate_state_transition(self.state, target_state)
        self.state = target_state
        if reviewed_by:
            self.reviewed_by = reviewed_by
        if review_notes:
            self.review_notes = review_notes
        if evidence:
            self.evidence_payload.update(evidence)
        self.evaluated_at = datetime.now(timezone.utc)


__all__ = [
    "ChecklistCategory",
    "ChecklistResultState",
    "AutomationType",
    "TargetEngine",
    "UNVERIFIED_STATES_CANNOT_PASS",
    "validate_state_transition",
    "ChecklistDefinition",
    "ChecklistAssessmentRun",
    "ChecklistResult",
]
