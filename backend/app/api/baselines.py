import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.api.deps import require_admin, require_operator, require_viewer
from backend.app.models.baseline import BaselineException
from backend.app.models.user import User
from backend.app.schemas.common import ExposureClassification

router = APIRouter(prefix="/baselines", tags=["Approved Baseline Exceptions"])


class BaselineCreateRequest(BaseModel):
    scope: str = Field(..., description="Target URL path scope, e.g. https://mh.empire.edu.vn/media/*")
    classification: ExposureClassification = Field(default=ExposureClassification.PUBLIC_BY_DESIGN)
    reason: str = Field(..., description="Business justification for approved public accessibility")
    owner: str = Field(default="Content Operations Team")
    approved_by: Optional[str] = Field(default=None)
    evidence: dict = Field(default_factory=dict)


class BaselineResponse(BaseModel):
    id: uuid.UUID
    scope: str
    classification: str
    reason: str
    owner: str
    approved_by: str
    is_active: bool
    created_at: datetime
    evidence: dict
    review_history: list


@router.get("", response_model=List[BaselineResponse])
async def list_baselines(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_viewer),
) -> Any:
    stmt = select(BaselineException)
    if is_active is not None:
        stmt = stmt.where(BaselineException.is_active == is_active)
    stmt = stmt.order_by(BaselineException.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("", response_model=BaselineResponse, status_code=status.HTTP_201_CREATED)
async def create_baseline(
    payload: BaselineCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operator),
) -> Any:
    now = datetime.now(timezone.utc)
    approver = current_user.username if current_user and current_user.username else "operator"
    baseline = BaselineException(
        id=uuid.uuid4(),
        scope=payload.scope,
        classification=payload.classification.value,
        reason=payload.reason,
        owner=payload.owner,
        approved_by=approver,
        is_active=True,
        evidence=payload.evidence,
        review_history=[{
            "reviewed_at": now.isoformat(),
            "reviewer": approver,
            "status": "APPROVED",
            "notes": "Created via Baseline Exception Manager.",
        }],
    )
    db.add(baseline)
    await db.commit()
    await db.refresh(baseline)
    return baseline


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_baseline(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    res = await db.execute(select(BaselineException).where(BaselineException.id == id))
    baseline = res.scalars().first()
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline exception not found")
    baseline.is_active = False
    await db.commit()


@router.post("/reset")
async def reset_baseline_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> Any:
    """Reset operational state and re-seed verified initial baseline."""
    if settings.is_production:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System reset is permanently disabled in production environments.",
        )
    from backend.app.api.system import execute_system_reset
    return await execute_system_reset(db, actor_username=current_user.username, actor_id=str(current_user.id))

