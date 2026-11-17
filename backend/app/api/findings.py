from datetime import date, datetime, timezone
import uuid
from typing import Any, Optional
from fastapi import Request, APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import AccessScope, load_scope, require_operator, require_viewer
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.finding import NormalizedFinding
from backend.app.models.alert import SecurityAlert
from backend.app.models.user import User
from backend.app.schemas.common import (
    EmpireModule,
    ExposureClassification,
    FindingSeverity,
    FindingStatus,
    OPEN_FINDING_STATES,
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
    observation_group: Optional[str] = Query(None, pattern="^detected$"),
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
        from backend.app.models.defensive import ExecutionRecord
        from backend.app.models.lifecycle import FindingObservation
        detected = select(FindingObservation.finding_id).join(
            ExecutionRecord, ExecutionRecord.id == FindingObservation.execution_id).where(
            ExecutionRecord.scan_id == scan_id,
            FindingObservation.outcome.in_(("new", "unchanged", "reopened")))
        stmt = stmt.where(or_(NormalizedFinding.scan_id == scan_id, NormalizedFinding.id.in_(detected)))
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
    open_states = OPEN_FINDING_STATES
    if status_group == "open":
        stmt = stmt.where(NormalizedFinding.status.in_(open_states))
    elif status_group == "closed":
        stmt = stmt.where(NormalizedFinding.status.not_in(open_states))
    if outcome or day or execution_id or observation_group:
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
        if observation_group == "detected":
            obs = obs.where(FindingObservation.outcome.in_(("new", "unchanged", "reopened")))
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


def redact_secrets(val: Any) -> Any:
    """Recursively redacts sensitive authentication tokens, cookies, passwords, and JWTs."""
    if val is None:
        return None
    if isinstance(val, str):
        import re
        patterns = [
            (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
            (re.compile(r"(?i)((?:token|password|passwd|secret|api[_-]?key|cookie)=)[^&\s]+"), r"\1[REDACTED]"),
            (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"), "[REDACTED_JWT]"),
            (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
        ]
        out = val
        for pat, rep in patterns:
            out = pat.sub(rep, out)
        return out
    elif isinstance(val, dict):
        sanitized = {}
        for k, v in val.items():
            if str(k).lower() in {"authorization", "token", "password", "secret", "cookie", "set-cookie", "api_key", "jwt"}:
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = redact_secrets(v)
        return sanitized
    elif isinstance(val, list):
        return [redact_secrets(item) for item in val]
    return val


@router.post("/{finding_id}/triage", response_model=FindingResponse)
async def triage_finding(
    finding_id: uuid.UUID,
    triage_req: FindingTriageRequest,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Updates finding lifecycle status across the 10 canonical supported states:

    NEW, NEEDS_TRIAGE, CONFIRMED, FALSE_POSITIVE, ACCEPTED_RISK,
    ASSIGNED, IN_PROGRESS, FIXED_PENDING_RETEST, RESOLVED, REOPENED.
    """
    result = await db.execute(select(NormalizedFinding).where(NormalizedFinding.id == finding_id))
    finding = result.scalars().first()
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found")
    (await load_scope(current_user, db)).require(finding.asset_id, "TRIAGE")

    if triage_req.status == FindingStatus.RESOLVED and finding.status != "RESOLVED":
        raise HTTPException(status_code=409, detail="Resolution requires an equivalent successful engine recheck. Claim FIXED_PENDING_RETEST, then recheck.")
    if triage_req.status in (FindingStatus.FALSE_POSITIVE, FindingStatus.ACCEPTED_RISK) and len((triage_req.comment or "").strip()) < 8:
        raise HTTPException(status_code=422, detail="False positives and accepted risks require a reason of at least 8 characters.")

    old_status = finding.status
    old_assignee = finding.assignee
    old_notes = finding.remediation_notes
    old_retest = finding.retest_status
    finding.status = triage_req.status.value

    # Assignee & notes with secret redaction
    if triage_req.assignee:
        finding.assignee = redact_secrets(triage_req.assignee)
    else:
        finding.assignee = current_user.username

    sanitized_comment = redact_secrets(triage_req.comment)
    if sanitized_comment:
        finding.remediation_notes = sanitized_comment
    if triage_req.retest_status:
        finding.retest_status = redact_secrets(triage_req.retest_status)

    # Server-derived audit actor (F05) with evidence redaction
    evidence = dict(finding.evidence or {})
    triage_history = evidence.get("triage_history", [])
    triage_history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "old_status": old_status,
        "new_status": triage_req.status.value,
        "comment": sanitized_comment,
        "actor": current_user.username,
        "assignee": finding.assignee,
    })
    evidence["triage_history"] = triage_history
    finding.evidence = redact_secrets(evidence)
    flag_modified(finding, "evidence")

    from backend.app.core.lifecycle import record_change
    for field, old, new in (("status", old_status, finding.status), ("assignee", old_assignee, finding.assignee),
                            ("remediation_notes", old_notes, finding.remediation_notes),
                            ("retest_status", old_retest, finding.retest_status)):
        record_change(db, finding.id, field, old, new, actor_id=str(current_user.id),
                      actor_name=current_user.username, reason=sanitized_comment)

    # A claimed fix is distinct from a completed verification.
    if triage_req.status in (FindingStatus.FIXED_PENDING_RETEST, FindingStatus.RESOLVED):
        alert = SecurityAlert(
            id=uuid.uuid4(),
            severity=FindingSeverity.LOW.value,
            title=f"Finding {'Awaiting Retest' if triage_req.status == FindingStatus.FIXED_PENDING_RETEST else 'Resolved'}: {finding.title}",
            message=f"Finding '{finding.title}' marked as {triage_req.status.value} by {current_user.username}.",
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


@router.post("/{finding_id}/retest")
async def retest_finding(
    finding_id: uuid.UUID,
    request: Request,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> Any:
    """Compatibility alias for a durable recheck; never infer a fix from an HTTP status."""
    from backend.app.api.console import recheck_finding_impl

    return await recheck_finding_impl(db, current_user, finding_id, request, idempotency_key)
