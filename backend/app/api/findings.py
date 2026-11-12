from datetime import date, datetime, timezone
import uuid
from typing import Any, Optional
from fastapi import Request, APIRouter, Depends, HTTPException, Query, status
import httpx
from sqlalchemy import func, or_, select
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import AccessScope, load_scope, require_operator, require_viewer
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.ssrf import SSRFProtector, SSRFValidationError
from backend.app.models.finding import NormalizedFinding
from backend.app.models.alert import SecurityAlert
from backend.app.models.user import User
from backend.app.schemas.common import (
    EmpireModule,
    ExposureClassification,
    FindingSeverity,
    FindingStatus,
    PaginatedResponse,
)
from backend.app.schemas.finding import FindingResponse, FindingTriageRequest

router = APIRouter(prefix="/findings", tags=["Findings Explorer & Remediation"])


@router.get("", response_model=PaginatedResponse[FindingResponse])
async def list_findings(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    asset_id: Optional[uuid.UUID] = None,
    scan_id: Optional[uuid.UUID] = None,
    empire_module: Optional[EmpireModule] = None,
    exposure_classification: Optional[ExposureClassification] = None,
    severity: Optional[FindingSeverity] = None,
    status_filter: Optional[FindingStatus] = None,
    scanner_engine: Optional[str] = None,
    cve_id: Optional[str] = None,
    search: Optional[str] = None,
    status_group: Optional[str] = Query(None, pattern="^(open|closed)$"),
    outcome: Optional[str] = Query(None, pattern="^(new|unchanged|reopened|fixed|unavailable|changed_scope)$"),
    day: Optional[date] = Query(None, description="ICT day for `outcome` (observation-based)"),
    execution_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = select(NormalizedFinding)
    scope = await load_scope(current_user, db)
    if scope.asset_ids is not None:
        stmt = stmt.where(NormalizedFinding.asset_id.in_(scope.asset_ids))

    if asset_id:
        stmt = stmt.where(NormalizedFinding.asset_id == asset_id)
    if scan_id:
        stmt = stmt.where(NormalizedFinding.scan_id == scan_id)
    if empire_module:
        stmt = stmt.where(NormalizedFinding.empire_module == empire_module.value)
    if exposure_classification:
        stmt = stmt.where(NormalizedFinding.exposure_classification == exposure_classification.value)
    if severity:
        stmt = stmt.where(NormalizedFinding.severity == severity.value)
    if status_filter:
        stmt = stmt.where(NormalizedFinding.status == status_filter.value)
    if scanner_engine:
        stmt = stmt.where(NormalizedFinding.scanner_engine == scanner_engine.lower())
    if cve_id:
        stmt = stmt.where(NormalizedFinding.cve_id == cve_id)
    open_states = ("NEW", "OPEN", "CONFIRMED", "IN_REMEDIATION", "REOPENED")
    if status_group == "open":
        stmt = stmt.where(NormalizedFinding.status.in_(open_states))
    elif status_group == "closed":
        stmt = stmt.where(NormalizedFinding.status.not_in(open_states))
    if outcome or day or execution_id:
        from backend.app.api.console import ict_day_bounds
        from backend.app.models.lifecycle import FindingObservation
        obs = select(FindingObservation.finding_id)
        if outcome:
            obs = obs.where(FindingObservation.outcome == outcome)
        if day:
            lo, hi = ict_day_bounds(day)
            obs = obs.where(FindingObservation.observed_at >= lo, FindingObservation.observed_at < hi)
        if execution_id:
            obs = obs.where(FindingObservation.execution_id == execution_id)
        stmt = stmt.where(NormalizedFinding.id.in_(obs))
    if search:
        search_filter = f"%{search}%"
        stmt = stmt.where(
            or_(
                NormalizedFinding.title.ilike(search_filter),
                NormalizedFinding.description.ilike(search_filter),
                NormalizedFinding.target_location.ilike(search_filter),
                NormalizedFinding.cve_id.ilike(search_filter),
                NormalizedFinding.scanner_rule_id.ilike(search_filter),
            )
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.order_by(NormalizedFinding.first_seen_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


@router.get("/{finding_id}", response_model=FindingResponse)
async def get_finding(
    finding_id: uuid.UUID,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await db.execute(select(NormalizedFinding).where(NormalizedFinding.id == finding_id))
    finding = result.scalars().first()
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    (await load_scope(current_user, db)).require(finding.asset_id, "READ")
    return finding


@router.post("/{finding_id}/triage", response_model=FindingResponse)
async def triage_finding(
    finding_id: uuid.UUID,
    triage_req: FindingTriageRequest,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Updates finding lifecycle status across the 10 supported states:

    NEW, POTENTIAL, CONFIRMED, OPEN, IN_REMEDIATION, FIXED, REOPENED,
    ACCEPTED_RISK, FALSE_POSITIVE, NOT_AFFECTED.
    """
    result = await db.execute(select(NormalizedFinding).where(NormalizedFinding.id == finding_id))
    finding = result.scalars().first()
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    (await load_scope(current_user, db)).require(finding.asset_id, "TRIAGE")

    old_status = finding.status
    old_assignee = finding.assignee
    old_notes = finding.remediation_notes
    old_retest = finding.retest_status
    finding.status = triage_req.status.value

    # Assignee & notes
    if triage_req.assignee:
        finding.assignee = triage_req.assignee
    else:
        finding.assignee = current_user.username

    if triage_req.comment:
        finding.remediation_notes = triage_req.comment
    if triage_req.retest_status:
        finding.retest_status = triage_req.retest_status

    # Server-derived audit actor (F05)
    evidence = dict(finding.evidence or {})
    triage_history = evidence.get("triage_history", [])
    triage_history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "old_status": old_status,
        "new_status": triage_req.status.value,
        "comment": triage_req.comment,
        "actor": current_user.username,
        "assignee": finding.assignee,
    })
    evidence["triage_history"] = triage_history
    finding.evidence = evidence
    flag_modified(finding, "evidence")

    from backend.app.core.lifecycle import record_change
    for field, old, new in (("status", old_status, finding.status), ("assignee", old_assignee, finding.assignee),
                            ("remediation_notes", old_notes, finding.remediation_notes),
                            ("retest_status", old_retest, finding.retest_status)):
        record_change(db, finding.id, field, old, new, actor_id=str(current_user.id),
                      actor_name=current_user.username, reason=triage_req.comment)

    # Record alert if vulnerability marked FIXED or REOPENED
    if triage_req.status == FindingStatus.FIXED:
        alert = SecurityAlert(
            id=uuid.uuid4(),
            severity=FindingSeverity.LOW.value,
            title=f"Finding Resolved: {finding.title}",
            message=f"Finding '{finding.title}' has been verified and marked as FIXED by {current_user.username}.",
            category="REMEDIATION",
            metadata_json={"finding_id": str(finding.id), "actor": current_user.username},
        )
        db.add(alert)
    elif triage_req.status == FindingStatus.REOPENED:
        alert = SecurityAlert(
            id=uuid.uuid4(),
            severity=finding.severity,
            title=f"Finding REOPENED: {finding.title}",
            message=f"Finding '{finding.title}' has been REOPENED and requires remediation (by {current_user.username}).",
            category="REMEDIATION",
            metadata_json={"finding_id": str(finding.id), "actor": current_user.username},
        )
        db.add(alert)

    await db.commit()
    await db.refresh(finding)
    return finding


@router.post("/{finding_id}/retest", deprecated=True)
async def retest_finding(
    finding_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Deprecated alias of POST /findings/{id}/recheck (Milestone 5).

    The former implementation sent a live GET to the finding location and marked the finding
    FIXED on 401/403/404, which is neither an approved defensive control nor equivalent evidence.
    It now queues the same defensive control that produced the finding.
    """
    from backend.app.api.console import recheck_finding_impl

    return await recheck_finding_impl(db, current_user, finding_id, request, None)
