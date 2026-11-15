import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.common import FindingSeverity, FindingStatus, ExposureClassification


class FindingEvidence(BaseModel):
    request: Optional[str] = None
    response: Optional[str] = None
    matched_content: Optional[str] = None
    curl_command: Optional[str] = None
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    parameter: Optional[str] = None
    raw_payload: Optional[str] = None


class NormalizedFindingCreate(BaseModel):
    asset_id: uuid.UUID
    scan_id: uuid.UUID
    scanner_engine: str
    scanner_rule_id: str
    title: str
    description: str
    severity: FindingSeverity
    original_severity: str
    empire_module: Optional[str] = None
    exposure_classification: Optional[str] = None
    is_approved_baseline: bool = False
    cve_id: Optional[str] = None
    cwe_id: Optional[str] = None
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    epss_score: Optional[float] = None
    epss_percentile: Optional[float] = None
    is_kev: bool = False
    target_location: str
    target_component: Optional[str] = None
    affected_version: Optional[str] = None
    fixed_version: Optional[str] = None
    evidence: Dict[str, Any] = Field(default_factory=dict)
    raw_payload: Optional[str] = None
    remediation: Optional[str] = None
    references: List[str] = Field(default_factory=list)


class FindingResponse(BaseModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    asset_id: uuid.UUID
    fingerprint: str
    scanner_engine: str
    scanner_rule_id: str
    title: str
    description: str
    severity: FindingSeverity
    original_severity: str
    empire_module: Optional[str] = None
    exposure_classification: Optional[str] = None
    is_approved_baseline: bool = False
    cve_id: Optional[str] = None
    cwe_id: Optional[str] = None
    cvss_score: Optional[float] = None
    cvss_vector: Optional[str] = None
    epss_score: Optional[float] = None
    epss_percentile: Optional[float] = None
    is_kev: bool = False
    target_location: str
    target_component: Optional[str] = None
    affected_version: Optional[str] = None
    fixed_version: Optional[str] = None
    evidence: Dict[str, Any]
    raw_payload: Optional[str] = None
    remediation: Optional[str] = None
    references: List[str]
    status: FindingStatus
    remediation_notes: Optional[str] = None
    assignee: Optional[str] = None
    retest_status: Optional[str] = None
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FindingTriageRequest(BaseModel):
    status: FindingStatus = Field(
        ...,
        description="Target lifecycle state: NEW, NEEDS_TRIAGE, CONFIRMED, FALSE_POSITIVE, ACCEPTED_RISK, ASSIGNED, IN_PROGRESS, FIXED_PENDING_RETEST, RESOLVED, REOPENED"
    )
    comment: Optional[str] = Field(default=None, description="Triage rationale or verification notes")
    assignee: Optional[str] = Field(default=None, description="Engineer assigned to remediation")
    retest_status: Optional[str] = Field(default=None, description="Retest status after fix")
