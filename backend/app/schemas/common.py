from enum import Enum
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class AssetType(str, Enum):
    DOMAIN = "DOMAIN"
    WEB_APP = "WEB_APP"
    API_ENDPOINT = "API_ENDPOINT"
    PROJECT_ARCHIVE = "PROJECT_ARCHIVE"
    CONTAINER_IMAGE = "CONTAINER_IMAGE"
    OBJECT_STORAGE = "OBJECT_STORAGE"
    SERVER = "SERVER"


class EmpireModule(str, Enum):
    STUDENT_MANAGEMENT = "STUDENT_MANAGEMENT"
    LEARNING_MATERIALS = "LEARNING_MATERIALS"
    SUPPORTING_TOOLS = "SUPPORTING_TOOLS"
    API_SERVICES = "API_SERVICES"
    WEB_APPLICATION = "WEB_APPLICATION"
    SERVER_INFRASTRUCTURE = "SERVER_INFRASTRUCTURE"


class VerificationStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    REVOKED = "REVOKED"


class VerificationType(str, Enum):
    NONE = "NONE"
    DNS_TXT = "DNS_TXT"
    HTTP_WELL_KNOWN = "HTTP_WELL_KNOWN"
    ADMIN_OVERRIDE = "ADMIN_OVERRIDE"


class Criticality(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Exposure(str, Enum):
    INTERNET = "INTERNET"
    INTERNAL = "INTERNAL"
    ISOLATED = "ISOLATED"


class ScanStatus(str, Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"


class ScanQualityStatus(str, Enum):
    SCANNED_SUCCESSFULLY = "SCANNED_SUCCESSFULLY"
    PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    SCANNER_FAILED = "SCANNER_FAILED"
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"


class ScanProfile(str, Enum):
    QUICK = "QUICK"
    DAILY_SECURITY = "DAILY_SECURITY"
    STANDARD = "STANDARD"
    AUTHENTICATED = "AUTHENTICATED"
    API_ASSESSMENT = "API_ASSESSMENT"
    THOROUGH = "THOROUGH"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    LIGHT_PASSIVE = "LIGHT_PASSIVE"
    BASELINE = "BASELINE"
    DEEP_ACTIVE = "DEEP_ACTIVE"
    SCA_CONTAINER = "SCA_CONTAINER"


class FindingSeverity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class FindingStatus(str, Enum):
    """Canonical 10-state lifecycle for security findings (R5)."""

    NEW = "NEW"
    NEEDS_TRIAGE = "NEEDS_TRIAGE"
    CONFIRMED = "CONFIRMED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    ACCEPTED_RISK = "ACCEPTED_RISK"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    FIXED_PENDING_RETEST = "FIXED_PENDING_RETEST"
    RESOLVED = "RESOLVED"
    REOPENED = "REOPENED"

    # Backward-compatibility aliases for legacy state names
    OPEN = "NEEDS_TRIAGE"
    POTENTIAL = "NEEDS_TRIAGE"
    IN_REMEDIATION = "IN_PROGRESS"
    FIXED = "FIXED_PENDING_RETEST"
    NOT_AFFECTED = "FALSE_POSITIVE"
    MUTED = "ACCEPTED_RISK"

    @classmethod
    def _missing_(cls, value: object):
        if isinstance(value, str):
            legacy = {
                "OPEN": cls.NEEDS_TRIAGE,
                "POTENTIAL": cls.NEEDS_TRIAGE,
                "IN_REMEDIATION": cls.IN_PROGRESS,
                "FIXED": cls.FIXED_PENDING_RETEST,
                "NOT_AFFECTED": cls.FALSE_POSITIVE,
                "MUTED": cls.ACCEPTED_RISK,
            }
            norm = value.upper()
            if norm in legacy:
                return legacy[norm]
        return None

    @classmethod
    def canonical_states(cls) -> List[str]:
        """Returns the list of 10 canonical finding lifecycle status values."""
        return [
            cls.NEW.value,
            cls.NEEDS_TRIAGE.value,
            cls.CONFIRMED.value,
            cls.FALSE_POSITIVE.value,
            cls.ACCEPTED_RISK.value,
            cls.ASSIGNED.value,
            cls.IN_PROGRESS.value,
            cls.FIXED_PENDING_RETEST.value,
            cls.RESOLVED.value,
            cls.REOPENED.value,
        ]


class ExposureClassification(str, Enum):
    PUBLIC_BY_DESIGN = "PUBLIC_BY_DESIGN"
    PUBLIC_SENSITIVE_CONTENT = "PUBLIC_SENSITIVE_CONTENT"
    UNEXPECTED_PUBLIC_FILE = "UNEXPECTED_PUBLIC_FILE"
    PRIVATE_ACCESS_CONTROL_FAILURE = "PRIVATE_ACCESS_CONTROL_FAILURE"
    MISCONFIGURED_MEDIA_STORAGE = "MISCONFIGURED_MEDIA_STORAGE"


class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int
