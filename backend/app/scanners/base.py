import hashlib
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.app.schemas.common import AssetType, FindingSeverity
from backend.app.schemas.finding import NormalizedFindingCreate


class CancellationToken:
    """Cooperative cancellation token for scan executions."""
    def __init__(self) -> None:
        self._cancelled: bool = False

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled


@dataclass
class ScanExecutionRequest:
    scan_id: uuid.UUID
    asset_id: uuid.UUID
    asset_type: AssetType
    target_locator: str
    profile: str  # "LIGHT_PASSIVE", "BASELINE", "DEEP_ACTIVE", "SCA_CONTAINER"
    timeout_seconds: int = 300
    custom_config: Dict[str, Any] = field(default_factory=dict)
    allow_private_targets: bool = False


@dataclass
class ScannerExecutionResult:
    engine_name: str
    execution_mode: str  # "binary_cli" | "daemon_api" | "lab_engine"
    success: bool
    exit_code: int
    raw_output: str
    error_message: Optional[str]
    duration_seconds: float
    findings: List[NormalizedFindingCreate]


def compute_finding_fingerprint(
    asset_id: uuid.UUID,
    scanner_engine: str,
    scanner_rule_id: str,
    target_location: str,
    target_component: Optional[str] = None,
) -> str:
    """Computes a deterministic SHA-256 fingerprint for deduplicating findings."""
    norm_location = (target_location or "").strip().lower()
    norm_component = (target_component or "").strip().lower()
    norm_rule = (scanner_rule_id or "").strip().lower()
    norm_engine = (scanner_engine or "").strip().lower()

    raw_key = f"{asset_id}:{norm_engine}:{norm_rule}:{norm_location}:{norm_component}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


class BaseScannerAdapter(ABC):
    """Abstract interface implemented by all scanner adapters (Nuclei, ZAP, Trivy)."""

    @property
    @abstractmethod
    def engine_name(self) -> str:
        """Scanner identifier: 'nuclei', 'zap', 'trivy'."""
        pass

    @property
    @abstractmethod
    def supported_asset_types(self) -> List[AssetType]:
        """List of asset types supported by this adapter."""
        pass

    @abstractmethod
    def is_available(self) -> tuple[bool, str]:
        """Detects whether native CLI/daemon is available on the system."""
        pass

    @abstractmethod
    async def execute(
        self,
        request: ScanExecutionRequest,
        cancel_token: CancellationToken,
        log_callback: Callable[[str, str], Awaitable[None]],
    ) -> ScannerExecutionResult:
        """Executes the scan and returns normalized findings."""
        pass

    @abstractmethod
    def parse_findings(
        self, raw_output: str, request: ScanExecutionRequest
    ) -> List[NormalizedFindingCreate]:
        """Parses raw scanner output into normalized findings schema."""
        pass
