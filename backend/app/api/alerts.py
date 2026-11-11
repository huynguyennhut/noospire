import uuid
from datetime import datetime
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_active_user, require_admin, require_operator
from backend.app.core.database import get_db
from backend.app.models.alert import SecurityAlert
from backend.app.models.user import User

router = APIRouter(prefix="/alerts", tags=["Security Alerts & Notifications"], dependencies=[Depends(get_current_active_user)])


class AlertResponse(BaseModel):
    id: uuid.UUID
    severity: str
    title: str
    message: str
    category: str
    is_read: bool
    created_at: datetime
    metadata_json: dict


@router.get("", response_model=List[AlertResponse])
async def list_alerts(
    is_read: Optional[bool] = None,
    category: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = select(SecurityAlert)
    if is_read is not None:
        stmt = stmt.where(SecurityAlert.is_read == is_read)
    if category:
        stmt = stmt.where(SecurityAlert.category == category)
    if severity:
        stmt = stmt.where(func.upper(SecurityAlert.severity) == severity.upper())
    stmt = stmt.order_by(SecurityAlert.created_at.desc()).limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/unread-count")
async def get_unread_alerts_count(db: AsyncSession = Depends(get_db)) -> Any:
    """Returns the total number of unread alerts."""
    stmt = select(func.count()).select_from(SecurityAlert).where(SecurityAlert.is_read == False)
    res = await db.execute(stmt)
    count = res.scalar() or 0
    return {"unread_count": count}


@router.post("/{id}/read")
async def mark_alert_read(
    id: uuid.UUID,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    res = await db.execute(select(SecurityAlert).where(SecurityAlert.id == id))
    alert = res.scalars().first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_read = True
    await db.commit()
    return {"id": str(alert.id), "is_read": True}


@router.post("/read-all")
async def mark_all_alerts_read(
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    res = await db.execute(select(SecurityAlert).where(SecurityAlert.is_read == False))
    alerts = res.scalars().all()
    for a in alerts:
        a.is_read = True
    await db.commit()
    return {"marked_read": len(alerts)}


@router.delete("/{id}")
async def delete_alert(
    id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Delete a single alert notification by ID."""
    res = await db.execute(select(SecurityAlert).where(SecurityAlert.id == id))
    alert = res.scalars().first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    await db.commit()
    return {"id": str(id), "message": "Alert deleted successfully"}


@router.delete("")
async def delete_all_alerts(
    is_read: Optional[bool] = Query(None, description="If specified, delete only read/unread alerts"),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Purge alerts notification list."""
    stmt = delete(SecurityAlert)
    if is_read is not None:
        stmt = stmt.where(SecurityAlert.is_read == is_read)
    res = await db.execute(stmt)
    await db.commit()
    deleted_count = res.rowcount if hasattr(res, "rowcount") else 0
    return {"deleted_count": max(0, deleted_count), "message": f"Successfully deleted {max(0, deleted_count)} alerts."}
