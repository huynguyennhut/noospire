import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import require_owner, require_viewer
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.dispatcher import get_dispatcher, log_buffer
from backend.app.core.empire_seeder import seed_empire_ecosystem
from backend.app.models.alert import SecurityAlert
from backend.app.models.asset import Asset
from backend.app.models.base import AdminAuditLog
from backend.app.models.baseline import BaselineException
from backend.app.models.finding import NormalizedFinding
from backend.app.models.proof import AssetOwnershipProof
from backend.app.models.scan import Scan, ScanBatch, ScanLog
from backend.app.models.schedule import DailySchedule
from backend.app.models.scope import AssetAssessmentScope
from backend.app.models.synthetic_identity import SyntheticIdentity
from backend.app.models.user import User

logger = logging.getLogger("sentinel.system")

router = APIRouter(prefix="/system", tags=["System Maintenance & State Lifecycle"])


async def execute_system_reset(db: AsyncSession, actor_username: str = "administrator", actor_id: str | None = None) -> dict:
    """Resets operational state in non-production environments.

    Critical audit history (AdminAuditLog) is IMMUTABLE and stored outside the reset path (F08).
    """
    if not settings.is_development:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Destructive system reset is disabled in production environments.",
        )

    # 1. Stop all active background scans and tasks
    dispatcher = get_dispatcher()
    try:
        await dispatcher.stop_all()
    except Exception as e:
        logger.warning(f"Error stopping scans during reset: {e}")

    # 2. Clear in-memory log buffer
    await log_buffer.clear_all()

    # 3. Purge operational state tables (AdminAuditLog is strictly preserved - F08)
    await db.execute(delete(ScanLog))
    await db.execute(delete(Scan))
    await db.execute(delete(ScanBatch))
    await db.execute(delete(NormalizedFinding))
    await db.execute(delete(SecurityAlert))
    await db.execute(delete(BaselineException))
    await db.execute(delete(DailySchedule))
    await db.execute(delete(SyntheticIdentity))
    await db.execute(delete(AssetOwnershipProof))
    await db.execute(delete(AssetAssessmentScope))
    await db.execute(delete(Asset))
    # NOTE: AdminAuditLog is append-only and NEVER deleted!
    await db.commit()

    # 4. Re-seed demo fixtures only in an explicitly isolated demo environment
    reseeded = False
    if settings.SEED_DEMO_DATA:
        await seed_empire_ecosystem(db)
        reseeded = True

    # 5. Record Reset Completed Audit Log and Alert
    now = datetime.now(timezone.utc)
    reset_alert = SecurityAlert(
        id=uuid.uuid4(),
        severity="INFO",
        title="System reset: operational data purged",
        message=f"All operational scans, logs, alerts, and dynamic findings were purged by {actor_username}.",
        category="BASELINE",
        is_read=False,
        metadata_json={"reset_at": now.isoformat(), "actor": actor_username},
    )
    db.add(reset_alert)

    audit_entry = AdminAuditLog(
        user_id=actor_id,
        username=actor_username,
        action="SYSTEM_STATE_RESET",
        details=f"Purged operational data (reseeded_demo={reseeded}). Audit history preserved.",
        ip_address="server",
    )
    db.add(audit_entry)

    await db.commit()

    return {
        "status": "RESET_SUCCESSFUL",
        "timestamp": now.isoformat(),
        "preserved_audit_logs": True,
        "reseeded_demo_fixtures": reseeded,
    }


@router.post("/reset")
async def reset_system_endpoint(
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Destructive reset: development/test only, sole owner only. Audit log preserved."""
    return await execute_system_reset(db, actor_username=current_user.username, actor_id=str(current_user.id))
