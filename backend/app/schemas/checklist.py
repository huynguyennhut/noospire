import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.checklist import (
    AutomationType,
    ChecklistCategory,
    ChecklistResultState,
    TargetEngine,
)


class ChecklistDefinitionRead(BaseModel):
    """Bilingual definition of a single pentest checklist check."""
    model_config = ConfigDict(from_attributes=True)

    check_id: str = Field(..., description="Unique check identifier, e.g. WEB-001, API-001")
    category: ChecklistCategory = Field(..., description="Checklist category (WEB, API, FILE, AUTH, INFRA, DEP)")
    title_vi: str = Field(..., description="Vietnamese check title")
    title_en: str = Field(..., description="English check title")
    description_vi: str = Field(..., description="Vietnamese comprehensive description")
    description_en: str = Field(..., description="English comprehensive description")
    severity: str = Field(default="MEDIUM", description="Default finding severity")
    automation_type: AutomationType = Field(default=AutomationType.AUTOMATED, description="AUTOMATED, MANUAL, or HYBRID")
    target_engine: str = Field(default=TargetEngine.EMPIRE_ENGINE.value, description="Target engine adapter")
    remediation_guidance_vi: str = Field(default="", description="Vietnamese remediation guidance")
    remediation_guidance_en: str = Field(default="", description="English remediation guidance")
    version: str = Field(default="1.0.0", description="Rule pack version")
    is_active: bool = Field(default=True, description="Whether check is active")


class ChecklistResultRead(BaseModel):
    """Result of a single check evaluation within a run."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    check_id: str
    state: ChecklistResultState
    evidence_payload: Dict[str, Any] = Field(default_factory=dict)
    execution_duration_ms: int = 0
    evaluated_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    review_notes: Optional[str] = None
    definition: Optional[ChecklistDefinitionRead] = None


class ChecklistAssessmentRunCreate(BaseModel):
    """Request payload to initiate a checklist assessment run."""
    asset_id: uuid.UUID = Field(..., description="Target asset ID to assess")
    mode: Optional[str] = Field(default="AUTOMATED", description="Execution mode: AUTOMATED or FULL")


class ChecklistAssessmentRunRead(BaseModel):
    """Checklist assessment execution run with coverage statistics."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    scan_id: Optional[uuid.UUID] = None
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    total_checks: int
    automated_coverage_pct: float
    manual_completion_pct: float
    state_counts: Dict[str, int]


class ChecklistReviewRequest(BaseModel):
    """Manual review submission for a specific check result."""
    state: ChecklistResultState = Field(..., description="New state: PASS, FAIL, NEEDS_REVIEW, NOT_APPLICABLE")
    review_notes: Optional[str] = Field(default=None, description="Forensic notes justifying review transition")


class ChecklistMetricsResponse(BaseModel):
    """Aggregated honest metrics for a checklist assessment run."""
    run_id: uuid.UUID
    total_checks: int
    automated_coverage_pct: float
    manual_completion_pct: float
    state_counts: Dict[str, int]
    evaluated_checks: int
    unrun_checks: int


__all__ = [
    "ChecklistDefinitionRead",
    "ChecklistResultRead",
    "ChecklistAssessmentRunCreate",
    "ChecklistAssessmentRunRead",
    "ChecklistReviewRequest",
    "ChecklistMetricsResponse",
]
