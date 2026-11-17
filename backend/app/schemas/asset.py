import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.common import (
    AssetType,
    Criticality,
    EmpireModule,
    Exposure,
    VerificationStatus,
    VerificationType,
)


class AssetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable asset name")
    asset_type: AssetType = Field(default=AssetType.WEB_APP, description="Target asset category")
    target_locator: str = Field(..., min_length=1, max_length=1024, description="URL, domain, or path")
    empire_module: EmpireModule = Field(
        default=EmpireModule.STUDENT_MANAGEMENT, description="Empire business module"
    )
    environment: str = Field(default="PRODUCTION", description="Target environment (PRODUCTION, STAGING, DEV)")
    technology: str = Field(default="Web Service", description="Detected or declared technology profile")
    criticality: Criticality = Field(default=Criticality.MEDIUM, description="Business criticality tier")
    exposure: Exposure = Field(default=Exposure.INTERNET, description="Network exposure boundary")
    description: Optional[str] = Field(default=None, description="Optional asset context or ownership notes")
    tags: List[str] = Field(default_factory=list, description="Asset classification tags")
    approved_media_baseline: bool = Field(
        default=False, description="Flag indicating approved anonymous public access for /media policy"
    )
    assessment_policy: Dict[str, Any] = Field(default_factory=dict, description="Persistent assessment rules")
    auth_profile: Dict[str, Any] = Field(default_factory=dict, description="Configured authentication profile")
    excluded_endpoints: List[str] = Field(default_factory=list, description="Endpoints excluded from testing")


class AssetCreate(AssetBase):
    pass


class AssetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    empire_module: Optional[EmpireModule] = None
    environment: Optional[str] = None
    technology: Optional[str] = None
    criticality: Optional[Criticality] = None
    exposure: Optional[Exposure] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    approved_media_baseline: Optional[bool] = None
    assessment_policy: Optional[Dict[str, Any]] = None
    auth_profile: Optional[Dict[str, Any]] = None
    excluded_endpoints: Optional[List[str]] = None


class AssetResponse(AssetBase):
    id: uuid.UUID
    verification_status: VerificationStatus
    verification_type: VerificationType
    verification_token: str
    verified_at: Optional[str] = None
    # Milestone 6: derived from asset_ownership_proofs, not from the stored flag alone.
    # VERIFIED = a VERIFIED proof row exists · UNPROVEN = flag says VERIFIED but no proof row
    # (e.g. imported fixtures) · otherwise mirrors PENDING / FAILED / REVOKED.
    verification_state: str = "UNPROVEN"
    verification_proof: Optional[Dict[str, Any]] = None
    # Derived execution eligibility; stored VERIFIED alone cannot enable scanning.
    assessment_eligible: bool = False
    artifact_analysis_eligible: bool = False
    assessment_block_reason: Optional[str] = "OWNERSHIP_NOT_VERIFIED"
    inventory_classification: str = "UNKNOWN_OR_UNVERIFIED"
    inventory_provenance: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VerificationStepResult(BaseModel):
    step: int = Field(..., description="1-8 step sequence number")
    name: str = Field(..., description="Diagnostic step name")
    status: str = Field(..., description="PASS, FAIL, or INFO")
    detail: str = Field(..., description="Human-readable result summary")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostic evidence metadata")


class AssetVerifyRequest(BaseModel):
    verification_type: VerificationType = Field(
        default=VerificationType.ADMIN_OVERRIDE,
        description="Verification method: DNS_TXT, HTTP_WELL_KNOWN, or ADMIN_OVERRIDE"
    )
    allow_private: bool = Field(
        default=True,
        description="Permit private/loopback IP verification for staging or lab environments"
    )


class AssetVerifyResponse(BaseModel):
    asset_id: uuid.UUID
    verification_status: VerificationStatus
    verified: bool
    status: str = Field(default="VERIFIED", description="VERIFIED or FAILED")
    message: str
    steps: List[VerificationStepResult] = Field(default_factory=list, description="8-step pipeline execution breakdown")
    fingerprint: Dict[str, Any] = Field(default_factory=dict, description="Target technology and infrastructure fingerprint")


class AssetBulkImportItem(BaseModel):
    name: Optional[str] = None
    target_locator: str
    asset_type: Optional[AssetType] = AssetType.WEB_APP
    empire_module: Optional[EmpireModule] = EmpireModule.STUDENT_MANAGEMENT
    environment: Optional[str] = "PRODUCTION"
    criticality: Optional[Criticality] = Criticality.MEDIUM


class AssetBulkImportRequest(BaseModel):
    import_type: str = Field(default="AUTO", description="AUTO, CSV, JSON, TXT, OPENAPI")
    raw_content: Optional[str] = None
    items: Optional[List[AssetBulkImportItem]] = None


class AssetBulkImportResponse(BaseModel):
    imported_count: int
    skipped_duplicates: int
    errors: List[str] = Field(default_factory=list)
    imported_assets: List[AssetResponse] = Field(default_factory=list)


class BulkPreviewItem(BaseModel):
    target_locator: str
    name: str
    asset_type: AssetType = AssetType.WEB_APP
    empire_module: EmpireModule = EmpireModule.STUDENT_MANAGEMENT
    environment: str = "PRODUCTION"
    criticality: Criticality = Criticality.MEDIUM
    is_duplicate: bool = False
    existing_asset_id: Optional[str] = None
    reason: Optional[str] = None


class AssetBulkPreviewRequest(BaseModel):
    import_type: str = Field(default="AUTO", description="AUTO, CSV, JSON, TXT, OPENAPI, CIDR, IP, URL")
    raw_content: Optional[str] = None
    items: Optional[List[AssetBulkImportItem]] = None


class AssetBulkPreviewResponse(BaseModel):
    total: int
    new: List[BulkPreviewItem] = Field(default_factory=list)
    duplicate: List[BulkPreviewItem] = Field(default_factory=list)

