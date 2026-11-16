import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field

from backend.app.schemas.common import ScanProfile, ScanQualityStatus, ScanStatus


class ScanCreate(BaseModel):
    asset_id: uuid.UUID = Field(..., description="Target asset ID to assess")
    engine: str = Field(default="all", description="Scanner engine: nuclei, zap, trivy, or all")
    profile: ScanProfile = Field(default=ScanProfile.BASELINE, description="Scan depth profile")
    allow_private_targets: bool = Field(
        default=False,
        description="Explicit authorization for internal lab / private targets"
    )
    timeout_seconds: int = Field(default=600, ge=30, le=3600, description="Max execution duration in seconds")
    name: Optional[str] = Field(default=None, description="Optional scan name")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Optional scan parameters")

    model_config = ConfigDict(extra="ignore")


class ScanLogEntry(BaseModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    timestamp: datetime
    level: str
    message: str
    source: str

    model_config = ConfigDict(from_attributes=True)


class ScanResponse(BaseModel):
    id: uuid.UUID
    asset_id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
    engine: str
    profile: str
    status: ScanStatus
    quality_status: Optional[ScanQualityStatus] = None
    progress_percentage: int
    target_locator: str
    allow_private_targets: bool
    timeout_seconds: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


ScanRead = ScanResponse


class ScanCancelResponse(BaseModel):
    scan_id: uuid.UUID
    status: ScanStatus
    message: str


class ScanBatchCreate(BaseModel):
    name: Optional[str] = Field(default="Batch Security Assessment", description="Descriptive batch name")
    targets: Optional[Union[str, List[uuid.UUID]]] = Field(default="ALL", description="'ALL' or explicit list of asset UUIDs")
    profile: Optional[Union[ScanProfile, str]] = Field(default=None, description="Single assessment profile")
    profiles: Optional[List[Union[ScanProfile, str]]] = Field(default=None, description="Assessment profiles to run")
    engine: Optional[str] = Field(default=None, description="Single scanner engine")
    engines: Optional[List[str]] = Field(default=None, description="Scanning engines to run")
    concurrency_limit: Optional[int] = Field(default=None, ge=1, le=32, description="Max concurrent scans")
    allow_private_targets: bool = Field(default=False, description="Allow private / internal targets")
    timeout_seconds: int = Field(default=600, ge=30, le=3600, description="Per-scan timeout")
    description: Optional[str] = Field(default=None, description="Optional batch description")

    model_config = ConfigDict(extra="ignore")


class ScanBatchRead(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    total_scans: int
    completed_scans: int
    failed_scans: int
    cancelled_scans: int
    progress_percentage: int
    target_count: int
    engines: Any = []
    profiles: Any = []
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    metadata_json: Optional[Any] = None
    scans: Optional[List[ScanResponse]] = None

    model_config = ConfigDict(from_attributes=True)


class BatchScanResponse(BaseModel):
    batch_id: uuid.UUID
    name: str
    total_scans: int
    target_count: int
    status: str
    scans: List[ScanResponse] = []
    message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SystemResourcesInfo(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_available_mb: float
    memory_used_mb: Optional[float] = None
    cpu_count: Optional[int] = None
    is_throttled: Optional[bool] = False


class ActiveThreadInfo(BaseModel):
    thread_id: int
    scan_id: uuid.UUID
    target_locator: str
    profile: str
    engine: str
    stage: str
    progress_percentage: int
    started_at: Optional[str] = None
    elapsed_seconds: int
    last_log: str


class TrackCurrentResponse(BaseModel):
    active_workers: int
    max_concurrency: int
    queued_count: int = 0
    completed_count: int = 0
    is_throttled: bool = False
    system_resources: SystemResourcesInfo
    active_threads: List[ActiveThreadInfo] = []
    active_worker_count: Optional[int] = None
    running_scans: Optional[List[Any]] = None
    trackcurrent: Optional[Any] = None


class UltraScanCreate(BaseModel):
    idempotency_key: Optional[str] = Field(default=None, description="Client-supplied idempotency key")
    scope: Optional[Union[str, List[str]]] = Field(default="ALL", description="'ALL' registered assets or list of existing target UUIDs; fixtures are preview-only")
    profile: Optional[Union[ScanProfile, str]] = Field(default=ScanProfile.STANDARD, description="Scan profile")
    engines: Optional[List[str]] = Field(default=None, description="List of engine names (nuclei, zap, empire, trivy) or 'all'")
    initiator: Optional[str] = Field(default="sole_owner", description="Initiator of assessment")
    allow_private_targets: bool = Field(default=False, description="Allow private / internal targets")
    timeout_seconds: int = Field(default=600, ge=30, le=3600, description="Max execution timeout per target in seconds")

    model_config = ConfigDict(extra="ignore")


class UltraScanResponse(BaseModel):
    batch_id: uuid.UUID
    name: str
    status: str
    accounted_inventory_rows: int
    independent_execution_targets: int
    engine_executions_count: int
    shared_alias_count: int
    excluded_count: int
    tracker_link: str
    snapshot_time: datetime
    policy_revision: str
    idempotency_recovered: bool = False
    message: str

    model_config = ConfigDict(from_attributes=True)


class UltraScanFixtureResponse(BaseModel):
    accounted_inventory_rows: int
    independent_execution_targets: int
    engine_executions_count: int
    shared_alias_count: int
    excluded_count: int
    policy_revision: str
    items: List[Dict[str, Any]]
    shared_result_links: List[Dict[str, str]]
    explained_exclusions: List[Dict[str, str]]

    model_config = ConfigDict(from_attributes=True)

