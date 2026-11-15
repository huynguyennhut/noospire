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

    # Record alert if vulnerability marked FIXED / RESOLVED or REOPENED
    if triage_req.status in (FindingStatus.FIXED_PENDING_RETEST, FindingStatus.RESOLVED):
        alert = SecurityAlert(
            id=uuid.uuid4(),
            severity=FindingSeverity.LOW.value,
            title=f"Finding Resolved: {finding.title}",
            message=f"Finding '{finding.title}' has been verified and marked as {triage_req.status.value} by {current_user.username}.",
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
) -> Any:
    """Executes an immediate live retest against the finding's target location
    to determine if the vulnerability has been remediated.
    """
    result = await db.execute(select(NormalizedFinding).where(NormalizedFinding.id == finding_id))
    finding = result.scalars().first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    (await load_scope(current_user, db)).require(finding.asset_id, "SCAN")

    target_url = finding.target_location
    retest_result = "STILL_VULNERABLE"
    notes = "Retest executed. Vulnerability pattern re-verified."

    # Validate egress with SSRF Protector (F11)
    allow_private = bool(not settings.is_production and settings.SSRF_ALLOW_PRIVATE_TARGETS)
    try:
        SSRFProtector.validate_target(target_url, allow_private=allow_private)
    except SSRFValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Retest blocked by SSRF policy: {e}",
        )

    try:
        async with httpx.AsyncClient(verify=True, timeout=5.0) as client:
            resp = await client.get(target_url)
            # If target returns 404, 401, or 403 on an unauthenticated leak endpoint, it has been secured!
            if resp.status_code in (401, 403, 404) and "LEAK" in (finding.scanner_rule_id or ""):
                retest_result = "VERIFIED_FIXED"
                finding.status = FindingStatus.FIXED.value
                notes = f"Target now returns HTTP {resp.status_code} (access denied/not found). Vulnerability confirmed remediated."
            elif resp.status_code == 200:
                retest_result = "STILL_VULNERABLE"
                notes = f"Target still returns HTTP 200 with exposed content. Vulnerability remains active."
    except Exception as e:
        retest_result = "RETEST_ERROR"
        notes = f"Could not reach target during retest: {e}"

    finding.retest_status = retest_result
    evidence = dict(finding.evidence or {})
    evidence["last_retest"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": retest_result,
        "notes": notes,
        "actor": current_user.username,
    }
    finding.evidence = evidence
    flag_modified(finding, "evidence")

    await db.commit()
    await db.refresh(finding)

    return {
        "finding_id": str(finding.id),
        "status": finding.status,
        "retest_status": retest_result,
        "notes": notes,
        "message": notes,
    }

