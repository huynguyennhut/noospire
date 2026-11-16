import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.inventory_reconciliation import execution_block_reasons
from backend.app.core.config import settings
from backend.app.core.ssrf import SSRFProtector, SSRFValidationError
from backend.app.models.asset import Asset
from backend.app.models.scope import AssetAssessmentScope
from backend.app.schemas.common import VerificationStatus

logger = logging.getLogger("sentinel.scope_gate")


class ScopeEnforcementError(Exception):
    """Exception raised when an assessment target or scan fails scope validation."""

    def __init__(self, detail: str, status_code: int = 403, reason: str = "SCOPE_VIOLATION"):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.reason = reason


@dataclass
class ScopeValidationResult:
    """Preflight validation audit record confirming authorized scope boundaries."""

    is_allowed: bool
    asset_id: uuid.UUID
    scope_id: Optional[uuid.UUID]
    exact_origin: str
    rate_limit_rps: int
    concurrency_limit: int
    max_requests_per_run: int
    byte_budget: int
    permitted_checks: List[str] = field(default_factory=list)
    message: str = "Scope validation passed."


class ScopeValidator:
    """Immutable backend scope authorization gatekeeper.
    Guarantees that every probe, scan, or assessment run is backed by an active,
    unexpired, customer-authorized scope grant with strict boundaries.
    """

    @classmethod
    async def validate_preflight(
        cls,
        asset_id: uuid.UUID,
        requested_checks: Optional[List[str]] = None,
        db: Optional[AsyncSession] = None,
        is_active_probe: bool = False,
        target_url: Optional[str] = None,
        allow_private: Optional[bool] = None,
    ) -> ScopeValidationResult:
        """Validates that a target asset has an active authorized scope before dispatch.
        
        Enforces:
        1. Target asset exists in inventory.
        2. Customer assessment scope record is present and active.
        3. Emergency stop is NOT active.
        4. Scope authorization grant has not expired.
        5. SSRF / network egress boundaries (RFC 1918, loopbacks, cloud metadata).
        6. Active / destructive scans are strictly blocked unless target ownership is VERIFIED.
        7. Requested checks fall within permitted check boundaries.
        8. Origin and port boundaries match authorized exact_origin and ports.
        """
        if allow_private is None:
            allow_private = bool(settings.SSRF_ALLOW_PRIVATE_TARGETS or not settings.is_production)

        if db is None:
            raise ScopeEnforcementError("Database session required for scope validation", status_code=500, reason="INTERNAL_ERROR")

        # 1. Asset existence
        asset_res = await db.execute(select(Asset).where(Asset.id == asset_id))
        asset = asset_res.scalars().first()
        if not asset:
            raise ScopeEnforcementError(
                f"Target asset with ID '{asset_id}' does not exist in inventory.",
                status_code=404,
                reason="ASSET_NOT_FOUND",
            )

        inventory_blocks = await execution_block_reasons(db, [asset])
        if inventory_blocks:
            raise ScopeEnforcementError("Synthetic or unproven seeded inventory requires reconciliation.",
                                        status_code=409, reason=inventory_blocks[str(asset.id)])

        # 2. Scope record existence
        scope_res = await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == asset_id))
        scope = scope_res.scalars().first()
        if not scope:
            raise ScopeEnforcementError(
                f"Target asset '{asset.name}' ({asset.target_locator}) lacks an authorized customer scope record. "
                "Scan dispatch is blocked by immutable scope gate.",
                status_code=403,
                reason="SCOPE_MISSING",
            )

        # 3. Emergency stop active
        if scope.emergency_stop_active:
            raise ScopeEnforcementError(
                f"Scan dispatch blocked: emergency stop is active for asset '{asset.name}'.",
                status_code=403,
                reason="EMERGENCY_STOP_ACTIVE",
            )

        # 4. Scope expiration
        if scope.expires_at is not None:
            now_utc = datetime.now(timezone.utc)
            # Ensure timezone awareness
            exp_utc = scope.expires_at if scope.expires_at.tzinfo else scope.expires_at.replace(tzinfo=timezone.utc)
            if exp_utc < now_utc:
                raise ScopeEnforcementError(
                    f"Authorized assessment scope for asset '{asset.name}' expired on {scope.expires_at.isoformat()}.",
                    status_code=403,
                    reason="SCOPE_EXPIRED",
                )

        # 5. Active / Destructive scans require VERIFIED ownership
        if is_active_probe:
            if asset.verification_status != VerificationStatus.VERIFIED.value:
                raise ScopeEnforcementError(
                    f"Active/destructive scans are strictly forbidden for unverified asset '{asset.name}'. "
                    f"Current verification status: '{asset.verification_status}'. Verification required.",
                    status_code=403,
                    reason="ASSET_NOT_VERIFIED",
                )

        # 6. SSRF & Network egress boundaries
        effective_locator = target_url or asset.target_locator
        try:
            SSRFProtector.validate_target(effective_locator, allow_private=allow_private)
        except SSRFValidationError as e:
            raise ScopeEnforcementError(
                f"Target locator '{effective_locator}' violated network / SSRF egress boundaries: {str(e)}",
                status_code=403,
                reason="SSRF_VIOLATION",
            )

        # 7. Exact origin and port validation
        if target_url:
            parsed_req = urlparse(target_url)
            parsed_scope = urlparse(scope.exact_origin)
            
            # Compare scheme and host
            if parsed_scope.scheme and parsed_req.scheme:
                if parsed_scope.scheme.lower() != parsed_req.scheme.lower():
                    raise ScopeEnforcementError(
                        f"Target URL scheme '{parsed_req.scheme}' does not match authorized scope scheme '{parsed_scope.scheme}'.",
                        status_code=403,
                        reason="ORIGIN_SCHEME_MISMATCH",
                    )
            if parsed_scope.hostname and parsed_req.hostname:
                if parsed_scope.hostname.lower() != parsed_req.hostname.lower():
                    raise ScopeEnforcementError(
                        f"Target URL host '{parsed_req.hostname}' does not match authorized scope origin '{parsed_scope.hostname}'.",
                        status_code=403,
                        reason="ORIGIN_HOST_MISMATCH",
                    )
            
            req_port = parsed_req.port or (443 if parsed_req.scheme == "https" else 80)
            if scope.ports and req_port not in scope.ports:
                raise ScopeEnforcementError(
                    f"Target port '{req_port}' is not in authorized ports list {scope.ports}.",
                    status_code=403,
                    reason="PORT_NOT_PERMITTED",
                )

        # 8. Permitted checks boundary
        if requested_checks and scope.permitted_checks:
            if "*" not in scope.permitted_checks:
                disallowed = [c for c in requested_checks if c not in scope.permitted_checks]
                if disallowed:
                    raise ScopeEnforcementError(
                        f"Requested checks {disallowed} are not permitted under the authorized scope for asset '{asset.name}'. "
                        f"Permitted checks: {scope.permitted_checks}.",
                        status_code=403,
                        reason="CHECKS_NOT_PERMITTED",
                    )

        return ScopeValidationResult(
            is_allowed=True,
            asset_id=asset.id,
            scope_id=scope.id,
            exact_origin=scope.exact_origin,
            rate_limit_rps=scope.rate_limit_rps,
            concurrency_limit=scope.concurrency_limit,
            max_requests_per_run=scope.max_requests_per_run,
            byte_budget=scope.byte_budget,
            permitted_checks=scope.permitted_checks or [],
            message=f"Scope authorization validated successfully for '{asset.name}'.",
        )

    @classmethod
    async def check_rate_and_budget(
        cls,
        asset_id: uuid.UUID,
        request_count: int,
        bytes_count: int,
        db: AsyncSession,
    ) -> bool:
        """Evaluates whether current execution consumption remains within approved request & byte budgets."""
        scope_res = await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == asset_id))
        scope = scope_res.scalars().first()
        if not scope or scope.emergency_stop_active:
            return False

        if scope.expires_at is not None:
            now_utc = datetime.now(timezone.utc)
            exp_utc = scope.expires_at if scope.expires_at.tzinfo else scope.expires_at.replace(tzinfo=timezone.utc)
            if exp_utc < now_utc:
                return False

        if request_count > scope.max_requests_per_run:
            logger.warning(
                "Asset %s exceeded request budget: %d > %d",
                asset_id, request_count, scope.max_requests_per_run
            )
            return False

        if bytes_count > scope.byte_budget:
            logger.warning(
                "Asset %s exceeded byte budget: %d > %d",
                asset_id, bytes_count, scope.byte_budget
            )
            return False

        return True


__all__ = [
    "ScopeEnforcementError",
    "ScopeValidationResult",
    "ScopeValidator",
]
