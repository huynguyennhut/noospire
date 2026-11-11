"""Pydantic V2 schemas for YAML Detection Rules, Schema Validation,

Test Fixture Execution, and Lifecycle Governance.
Conforms to Noosforge Sentinel R4 specifications.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RuleSeverityEnum(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class RuleStatusEnum(str, Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"


class DetectionEngineEnum(str, Enum):
    PATTERN_MATCH = "pattern_match"
    RESPONSE_EVAL = "response_eval"
    NUCLEI = "nuclei"


class MatcherPartEnum(str, Enum):
    ALL = "all"
    BODY = "body"
    HEADER = "header"
    STATUS_CODE = "status_code"
    PATH = "path"


class MatcherTypeEnum(str, Enum):
    REGEX = "regex"
    WORD = "word"
    STATUS = "status"
    BINARY = "binary"


class RuleMatcherSchema(BaseModel):
    """Schema for a single detection matcher block."""

    id: str = Field(..., pattern=r"^[a-z0-9_-]+$")
    type: MatcherTypeEnum
    part: MatcherPartEnum = MatcherPartEnum.ALL
    regex: Optional[List[str]] = None
    words: Optional[List[str]] = None
    status: Optional[List[int]] = None
    condition: Optional[str] = "or"  # "and" | "or"
    case_insensitive: bool = True
    negative: bool = False


class DetectionBlockSchema(BaseModel):
    """Schema for detection engine logic and matchers."""

    engine: DetectionEngineEnum = DetectionEngineEnum.PATTERN_MATCH
    condition: str = "any_of_matchers"  # "any_of_matchers" | "all_of_matchers"
    matchers: List[RuleMatcherSchema] = Field(..., min_length=1)


class RuleMetadataSchema(BaseModel):
    """Metadata block for CVEs, CWEs, CVSS, and taxonomy tags."""

    cve: Optional[List[str]] = Field(default_factory=list)
    cwe: Optional[List[str]] = Field(default_factory=list)
    cvss_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    tags: List[str] = Field(default_factory=list)


class RemediationBlockSchema(BaseModel):
    """Remediation guidance and vendor advisory references."""

    guidance: str
    reference_urls: List[str] = Field(default_factory=list)


class DetectionRuleBase(BaseModel):
    """Base schema for detection rule definition."""

    id: str = Field(..., pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)+$", description="Kebab-case rule ID")
    name: str = Field(..., min_length=3, max_length=256)
    description: Optional[str] = None
    version: str = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    author: str = Field(..., min_length=2, max_length=128)
    severity: RuleSeverityEnum = RuleSeverityEnum.MEDIUM
    status: RuleStatusEnum = RuleStatusEnum.DRAFT
    target_types: List[str] = Field(default_factory=lambda: ["web_application", "api_endpoint"])
    metadata: RuleMetadataSchema = Field(default_factory=RuleMetadataSchema)
    detection: DetectionBlockSchema
    remediation: RemediationBlockSchema


class DetectionRuleCreate(BaseModel):
    """Payload to create a new detection rule via YAML string or structured JSON."""

    raw_yaml: Optional[str] = None
    rule_data: Optional[DetectionRuleBase] = None
    created_by: str = "sentinel_secops"


class DetectionRuleUpdate(BaseModel):
    """Payload to update an existing detection rule."""

    raw_yaml: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[RuleSeverityEnum] = None
    metadata: Optional[RuleMetadataSchema] = None
    detection: Optional[DetectionBlockSchema] = None
    remediation: Optional[RemediationBlockSchema] = None
    updated_by: str = "sentinel_secops"


class RuleAuditLogSchema(BaseModel):
    """Audit log schema representing governance transitions."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: str
    actor: str
    action: str
    from_status: Optional[str] = None
    to_status: str
    notes: Optional[str] = None
    timestamp: datetime


class DetectionRuleResponse(BaseModel):
    """Full detection rule response model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str] = None
    version: str
    author: str
    severity: str
    status: str
    target_types: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    detection: Dict[str, Any] = Field(default_factory=dict)
    remediation: Dict[str, Any] = Field(default_factory=dict)
    raw_yaml: str
    created_by: str
    approved_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    audit_logs: List[RuleAuditLogSchema] = Field(default_factory=list)


# Test Fixture Schemas
class HttpRequestFixture(BaseModel):
    method: str = "GET"
    path: str = "/"
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[str] = ""


class HttpResponseFixture(BaseModel):
    status_code: int = 200
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[str] = ""


class TestFixtureInput(BaseModel):
    request: Optional[HttpRequestFixture] = None
    response: Optional[HttpResponseFixture] = None


class RuleTestCaseSchema(BaseModel):
    name: str
    expected_match: bool
    input: TestFixtureInput


class RuleTestFixtureRunnerRequest(BaseModel):
    """Request payload to test a rule against fixtures."""

    rule_id: Optional[str] = None
    raw_yaml: Optional[str] = None
    test_cases: Optional[List[RuleTestCaseSchema]] = None


class TestCaseResultItem(BaseModel):
    name: str
    expected_match: bool
    actual_match: bool
    passed: bool
    matched_by: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class RuleTestFixtureRunnerResponse(BaseModel):
    rule_id: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    all_passed: bool
    results: List[TestCaseResultItem]


class RuleLifecycleTransitionRequest(BaseModel):
    """Request to transition rule lifecycle state (review-gated)."""

    target_status: RuleStatusEnum
    actor: str = Field(..., min_length=2, description="Username of the operator triggering transition")
    notes: Optional[str] = None


class RuleLifecycleTransitionResponse(BaseModel):
    rule_id: str
    previous_status: str
    new_status: str
    actor: str
    success: bool
    message: str
    transition_timestamp: datetime


class RuleValidationResponse(BaseModel):
    valid: bool
    rule_id: Optional[str] = None
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class RuleValidateRequest(BaseModel):
    raw_yaml: Optional[str] = None
    rule_dict: Optional[Dict[str, Any]] = None
