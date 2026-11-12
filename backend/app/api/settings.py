from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import require_admin, require_viewer
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.ssrf import SSRFProtector
from backend.app.models.user import User

router = APIRouter(prefix="/settings", tags=["System Settings"])


class SettingsResponse(BaseModel):
    project_name: str
    version: str
    dispatcher_mode: str
    max_concurrent_scans: int
    default_scan_timeout: int
    ssrf_allow_private_targets: bool
    cors_origins: List[str]


class SettingsUpdateRequest(BaseModel):
    max_concurrent_scans: int | None = None
    default_scan_timeout: int | None = None
    ssrf_allow_private_targets: bool | None = None


class SSRFConfigResponse(BaseModel):
    blocked_networks_count: int
    cloud_metadata_hosts: List[str]
    allow_private_targets_globally: bool


class SSRFConfigUpdateRequest(BaseModel):
    allow_private_targets_globally: bool


@router.get("", response_model=SettingsResponse)
async def get_settings(
    current_user: User = Depends(require_admin),
) -> Any:
    return {
        "project_name": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "dispatcher_mode": settings.DISPATCHER_MODE,
        "max_concurrent_scans": settings.MAX_CONCURRENT_SCANS,
        "default_scan_timeout": settings.DEFAULT_SCAN_TIMEOUT,
        "ssrf_allow_private_targets": settings.SSRF_ALLOW_PRIVATE_TARGETS,
        "cors_origins": settings.CORS_ORIGINS,
    }


@router.put("", response_model=SettingsResponse)
async def update_settings(
    update_req: SettingsUpdateRequest,
    current_user: User = Depends(require_admin),
) -> Any:
    if update_req.max_concurrent_scans is not None:
        settings.MAX_CONCURRENT_SCANS = update_req.max_concurrent_scans
    if update_req.default_scan_timeout is not None:
        settings.DEFAULT_SCAN_TIMEOUT = update_req.default_scan_timeout
    if update_req.ssrf_allow_private_targets is not None:
        if settings.is_production and update_req.ssrf_allow_private_targets:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot enable private target scanning in production environment.",
            )
        settings.SSRF_ALLOW_PRIVATE_TARGETS = update_req.ssrf_allow_private_targets

    return await get_settings(current_user=current_user)


@router.get("/ssrf-config", response_model=SSRFConfigResponse)
async def get_ssrf_config(
    current_user: User = Depends(require_admin),
) -> Any:
    return {
        "blocked_networks_count": len(SSRFProtector.BLOCKED_NETWORKS),
        "cloud_metadata_hosts": list(SSRFProtector.CLOUD_METADATA_HOSTS),
        "allow_private_targets_globally": settings.SSRF_ALLOW_PRIVATE_TARGETS,
    }


@router.put("/ssrf-config", response_model=SSRFConfigResponse)
async def update_ssrf_config(
    update_req: SSRFConfigUpdateRequest,
    current_user: User = Depends(require_admin),
) -> Any:
    if settings.is_production and update_req.allow_private_targets_globally:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot enable private target scanning in production environment.",
        )
    settings.SSRF_ALLOW_PRIVATE_TARGETS = update_req.allow_private_targets_globally
    return await get_ssrf_config(current_user=current_user)


@router.post("/reset-baseline")
async def reset_baseline_endpoint(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Reset system state and re-seed clean baseline (Forbidden in production - F08)."""
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Destructive reset is disabled in production environments.",
        )
    from backend.app.api.system import execute_system_reset
    return await execute_system_reset(db, actor_username=current_user.username, actor_id=str(current_user.id))


@router.post("/reset")
async def reset_endpoint(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Alias for resetting system state (Forbidden in production - F08)."""
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Destructive reset is disabled in production environments.",
        )
    from backend.app.api.system import execute_system_reset
    return await execute_system_reset(db, actor_username=current_user.username, actor_id=str(current_user.id))
