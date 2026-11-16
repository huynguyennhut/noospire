"""Metrics & Telemetry API endpoints for NOOSFORGE Security Intelligence.
Provides aggregated KPIs, Empire module risk distributions, vulnerability lifecycle trends,
and scanner performance for the Security Overview Dashboard.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_active_user, require_owner
from backend.app.core.database import get_db
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan
from backend.app.models.intelligence import VulnerabilityIntelligence
from backend.app.models.rule import DetectionRule, RuleStatus
from backend.app.schemas.common import OPEN_FINDING_STATES, RESOLVED_FINDING_STATES, EmpireModule, FindingSeverity, FindingStatus, ScanStatus, VerificationStatus

Rule = DetectionRule

router = APIRouter(prefix="/metrics", tags=["Metrics & Dashboard Telemetry"], dependencies=[Depends(require_owner)])  # pilot: estate aggregates are owner-only until per-grant aggregation lands


class MetricsOverviewResponse(BaseModel):
    total_assets: int
    targets_assessed_today: int
    active_assessments: int
    failed_assessments: int
    critical_findings: int
    high_findings: int
    total_open_findings: int
    fixed_findings: int
    newly_discovered_cves: int
    relevant_kev_count: int
    overall_risk_score: float
    risk_posture: str


@router.get("/overview", response_model=MetricsOverviewResponse)
async def get_overview_metrics(
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Computes the 10 core KPIs required by the Security Overview Dashboard."""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Total targets
    total_assets_res = await db.execute(select(func.count(Asset.id)))
    total_assets = total_assets_res.scalar() or 0

    # 2. Targets assessed today
    assessed_today_stmt = select(func.count(func.distinct(Scan.asset_id))).where(
        Scan.completed_at >= today_start
    )
    assessed_today_res = await db.execute(assessed_today_stmt)
    targets_assessed_today = assessed_today_res.scalar() or 0

    # 3. Active assessments
    active_statuses = [ScanStatus.RUNNING.value, ScanStatus.QUEUED.value, ScanStatus.INITIALIZING.value]
    active_scans_res = await db.execute(
        select(func.count(Scan.id)).where(Scan.status.in_(active_statuses))
    )
    active_assessments = active_scans_res.scalar() or 0

    # 4. Failed assessments
    failed_res = await db.execute(select(func.count(Scan.id)).where(Scan.status == ScanStatus.FAILED.value))
    failed_assessments = failed_res.scalar() or 0

    # 5. Findings stats
    findings_res = await db.execute(select(NormalizedFinding))
    findings = findings_res.scalars().all()

    critical = sum(1 for f in findings if f.severity.upper() == "CRITICAL" and f.status not in RESOLVED_FINDING_STATES)
    high = sum(1 for f in findings if f.severity.upper() == "HIGH" and f.status not in RESOLVED_FINDING_STATES)
    open_findings = sum(
        1 for f in findings if f.status in OPEN_FINDING_STATES
    )
    fixed_findings = sum(1 for f in findings if f.status in RESOLVED_FINDING_STATES)

    # 6. Intelligence stats
    cves_res = await db.execute(select(func.count(VulnerabilityIntelligence.cve_id)))
    newly_discovered_cves = cves_res.scalar() or 0

    kev_res = await db.execute(
        select(func.count(VulnerabilityIntelligence.cve_id)).where(VulnerabilityIntelligence.is_cisa_kev == True)
    )
    relevant_kev = kev_res.scalar() or 0

    # Composite Risk Score (0-100)
    raw_score = (critical * 30.0) + (high * 15.0) + (relevant_kev * 5.0)
    overall_score = min(100.0, round(raw_score, 1))

    if overall_score >= 75.0 or critical > 0:
        posture = "CRITICAL"
    elif overall_score >= 50.0 or high > 0:
        posture = "ELEVATED"
    elif overall_score >= 25.0:
        posture = "MODERATE"
    else:
        posture = "OPTIMAL"

    return {
        "total_assets": total_assets,
        "targets_assessed_today": targets_assessed_today,
        "active_assessments": active_assessments,
        "failed_assessments": failed_assessments,
        "critical_findings": critical,
        "high_findings": high,
        "total_open_findings": open_findings,
        "fixed_findings": fixed_findings,
        "newly_discovered_cves": newly_discovered_cves,
        "relevant_kev_count": relevant_kev,
        "overall_risk_score": overall_score,
        "risk_posture": posture,
    }


# -----------------------------------------------------------------------------
# CHART 1: Findings by Severity
# -----------------------------------------------------------------------------
@router.get("/severity-distribution")
async def get_severity_distribution(db: AsyncSession = Depends(get_db)) -> Any:
    findings_res = await db.execute(select(NormalizedFinding))
    findings = findings_res.scalars().all()
    dist = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    for f in findings:
        sev = f.severity.upper() if f.severity else "INFO"
        if sev in dist:
            dist[sev] += 1
        else:
            dist["INFO"] += 1
    return dist


# -----------------------------------------------------------------------------
# CHART 2: Vulnerability Trend (New, Fixed, Reopened)
# -----------------------------------------------------------------------------
@router.get("/charts/vulnerability-trend")
async def get_vulnerability_trend(days: int = Query(default=7, ge=0, le=90), db: AsyncSession = Depends(get_db)) -> Any:
    findings_res = await db.execute(select(NormalizedFinding))
    findings = findings_res.scalars().all()
    today = datetime.now(timezone.utc).date()

    trend = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.strftime("%b %d")

        # Newly detected up to this date
        new_count = sum(1 for f in findings if f.created_at and f.created_at.date() <= d)
        # Fixed count
        fixed_count = sum(1 for f in findings if f.status in RESOLVED_FINDING_STATES and f.updated_at and f.updated_at.date() <= d)
        # Reopened
        reopened_count = sum(1 for f in findings if f.status == FindingStatus.REOPENED.value and f.updated_at and f.updated_at.date() <= d)

        trend.append({
            "date": d_str,
            "new_findings": new_count,
            "fixed_findings": fixed_count,
            "reopened_findings": reopened_count,
        })
    return trend


# -----------------------------------------------------------------------------
# CHART 3: Security Risk by Empire Module
# -----------------------------------------------------------------------------
@router.get("/charts/module-risk")
async def get_module_risk_chart(db: AsyncSession = Depends(get_db)) -> Any:
    findings_res = await db.execute(select(NormalizedFinding))
    findings = findings_res.scalars().all()

    module_names = {
        EmpireModule.STUDENT_MANAGEMENT.value: "Student Management",
        EmpireModule.LEARNING_MATERIALS.value: "Learning Materials",
        EmpireModule.SUPPORTING_TOOLS.value: "Supporting Tools",
        EmpireModule.API_SERVICES.value: "API Services",
        EmpireModule.WEB_APPLICATION.value: "Web Application",
        EmpireModule.SERVER_INFRASTRUCTURE.value: "Infrastructure",
    }

    result = []
    for mod_key, label in module_names.items():
        mod_findings = [f for f in findings if f.empire_module == mod_key]
        crit = sum(1 for f in mod_findings if f.severity.upper() == "CRITICAL" and f.status not in RESOLVED_FINDING_STATES)
        high = sum(1 for f in mod_findings if f.severity.upper() == "HIGH" and f.status not in RESOLVED_FINDING_STATES)
        med = sum(1 for f in mod_findings if f.severity.upper() == "MEDIUM" and f.status not in RESOLVED_FINDING_STATES)
        risk = min(100.0, round((crit * 35.0) + (high * 20.0) + (med * 5.0), 1))

        result.append({
            "module_key": mod_key,
            "module_name": label,
            "risk_score": risk,
            "critical_count": crit,
            "high_count": high,
            "medium_count": med,
            "total_findings": len(mod_findings),
        })
    return result


# -----------------------------------------------------------------------------
# CHART 4: Assessment Coverage
# -----------------------------------------------------------------------------
@router.get("/charts/coverage")
async def get_coverage_chart(db: AsyncSession = Depends(get_db)) -> Any:
    total_assets_res = await db.execute(select(func.count(Asset.id)))
    total_assets = total_assets_res.scalar() or 0

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    assessed_res = await db.execute(
        select(func.count(func.distinct(Scan.asset_id))).where(Scan.completed_at >= today_start)
    )
    assessed_count = assessed_res.scalar() or 0

    coverage_pct = round((assessed_count / total_assets * 100.0) if total_assets > 0 else 0.0, 1)

    return {
        "total_targets": total_assets,
        "assessed_today": assessed_count,
        "pending_assessment": max(0, total_assets - assessed_count),
        "coverage_percentage": coverage_pct,
    }


# -----------------------------------------------------------------------------
# CHART 5: Risk Score Trend
# -----------------------------------------------------------------------------
@router.get("/charts/risk-trend")
async def get_risk_score_trend(days: int = Query(default=7, ge=1, le=90), db: AsyncSession = Depends(get_db)) -> Any:
    findings_res = await db.execute(select(NormalizedFinding))
    findings = findings_res.scalars().all()
    today = datetime.now(timezone.utc).date()

    trend = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        d_str = d.strftime("%b %d")

        active_f = [f for f in findings if f.created_at and f.created_at.date() <= d and f.status not in RESOLVED_FINDING_STATES]
        crit = sum(1 for f in active_f if f.severity.upper() == "CRITICAL")
        high = sum(1 for f in active_f if f.severity.upper() == "HIGH")
        risk = min(100.0, round((crit * 25.0) + (high * 15.0) + len(active_f) * 2.0, 1))

        trend.append({
            "date": d_str,
            "risk_score": risk,
            "active_findings": len(active_f),
        })
    return trend


# -----------------------------------------------------------------------------
# CHART 6: Scanner Performance
# -----------------------------------------------------------------------------
@router.get("/charts/scanner-performance")
async def get_scanner_performance(db: AsyncSession = Depends(get_db)) -> Any:
    scans_res = await db.execute(select(Scan))
    scans = scans_res.scalars().all()

    # Dynamic query on completed scans for average duration
    overall_db_avg: Optional[float] = None
    if hasattr(Scan, "duration_seconds"):
        try:
            avg_duration_stmt = select(func.avg(getattr(Scan, "duration_seconds"))).where(
                Scan.status == ScanStatus.COMPLETED.value,
                getattr(Scan, "duration_seconds").isnot(None),
            )
            avg_duration_res = await db.execute(avg_duration_stmt)
            overall_db_avg = avg_duration_res.scalar()
        except Exception:
            overall_db_avg = None

    # Gracefully calculate from completed scans in database if no direct column recorded
    if overall_db_avg is None:
        completed_durations: List[float] = []
        for s in scans:
            if s.status == ScanStatus.COMPLETED.value:
                if hasattr(s, "duration_seconds") and getattr(s, "duration_seconds") is not None:
                    completed_durations.append(float(getattr(s, "duration_seconds")))
                elif s.completed_at and s.started_at:
                    dur = (s.completed_at - s.started_at).total_seconds()
                    if dur >= 0:
                        completed_durations.append(dur)
        if completed_durations:
            overall_db_avg = sum(completed_durations) / len(completed_durations)

    engines = ["empire_consolidated_suite", "nuclei", "zap", "trivy"]
    stats = []

    for eng in engines:
        matching = [s for s in scans if eng in (s.engine or "").lower()]
        completed_scans = [s for s in matching if s.status == ScanStatus.COMPLETED.value]
        completed = len(completed_scans)
        failed = sum(1 for s in matching if s.status == ScanStatus.FAILED.value)
        total = len(matching) or 1
        rate = round((completed / total * 100.0), 1)

        eng_durations: List[float] = []
        for s in completed_scans:
            if hasattr(s, "duration_seconds") and getattr(s, "duration_seconds") is not None:
                eng_durations.append(float(getattr(s, "duration_seconds")))
            elif s.completed_at and s.started_at:
                dur = (s.completed_at - s.started_at).total_seconds()
                if dur >= 0:
                    eng_durations.append(dur)

        if eng_durations:
            avg_duration_seconds = round(sum(eng_durations) / len(eng_durations), 1)
        elif overall_db_avg is not None:
            avg_duration_seconds = round(float(overall_db_avg), 1)
        else:
            avg_duration_seconds = 0.0

        stats.append({
            "engine": eng.replace("_", " ").title(),
            "total_executions": len(matching),
            "completed": completed,
            "failed": failed,
            "success_rate": rate,
            "avg_duration_seconds": avg_duration_seconds,
        })
    return stats


# -----------------------------------------------------------------------------
# CHART 7: Intelligence Activity
# -----------------------------------------------------------------------------
@router.get("/charts/intelligence-activity")
async def get_intelligence_activity(db: AsyncSession = Depends(get_db)) -> Any:
    cves_res = await db.execute(select(VulnerabilityIntelligence))
    cves = cves_res.scalars().all()

    kev_count = sum(1 for c in cves if c.is_cisa_kev)
    high_epss = sum(1 for c in cves if (c.epss_score or 0) >= 0.5)

    # Dynamic count of active detection rules in the database
    if hasattr(DetectionRule, "is_active"):
        rule_stmt = select(func.count(DetectionRule.id)).where(getattr(DetectionRule, "is_active") == True)
    else:
        rule_stmt = select(func.count(DetectionRule.id)).where(
            (DetectionRule.status == RuleStatus.ACTIVE.value) | (DetectionRule.status == "active")
        )
    active_rules_res = await db.execute(rule_stmt)
    detection_rules_active = active_rules_res.scalar() or 0

    return {
        "total_cves_indexed": len(cves),
        "cisa_kev_active": kev_count,
        "high_epss_exploitable": high_epss,
        "detection_rules_active": detection_rules_active,
        "last_sync": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


# -----------------------------------------------------------------------------
# CHART 8: Remediation Progress
# -----------------------------------------------------------------------------
@router.get("/charts/remediation-progress")
async def get_remediation_progress(db: AsyncSession = Depends(get_db)) -> Any:
    findings_res = await db.execute(select(NormalizedFinding))
    findings = findings_res.scalars().all()

    states = {
        "OPEN": sum(1 for f in findings if f.status in ("NEW", "NEEDS_TRIAGE", "CONFIRMED", "ASSIGNED", "OPEN", "POTENTIAL")),
        "IN_REMEDIATION": sum(1 for f in findings if f.status in ("IN_PROGRESS", "IN_REMEDIATION", "FIXED_PENDING_RETEST")),
        "FIXED": sum(1 for f in findings if f.status in RESOLVED_FINDING_STATES),
        "REOPENED": sum(1 for f in findings if f.status == FindingStatus.REOPENED.value),
        "ACCEPTED_RISK": sum(1 for f in findings if f.status == FindingStatus.ACCEPTED_RISK.value),
        "FALSE_POSITIVE": sum(1 for f in findings if f.status == FindingStatus.FALSE_POSITIVE.value),
    }
    return states
