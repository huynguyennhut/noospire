from datetime import datetime, timezone
from typing import Any, Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_active_user, require_owner
from backend.app.core.database import get_db
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan
from backend.app.schemas.common import EmpireModule, FindingSeverity, FindingStatus

router = APIRouter(prefix="/empire-modules", tags=["Empire Modules"], dependencies=[Depends(require_owner)])  # pilot: estate aggregates are owner-only until per-grant aggregation lands


MODULE_METADATA = {
    EmpireModule.STUDENT_MANAGEMENT.value: {
        "title": "Student Management & Identity",
        "description": "Student registration, authentication, Better-Auth identity provider, profile endpoints, and role boundary enforcement.",
        "icon": "Users",
        "critical_threshold": 8.0,
    },
    EmpireModule.LEARNING_MATERIALS.value: {
        "title": "Educational Material Management",
        "description": "Curriculum PDFs, lecture videos, exam papers, MinIO object storage, and /media Approved Public Exposure Policy.",
        "icon": "BookOpen",
        "critical_threshold": 7.5,
    },
    EmpireModule.SUPPORTING_TOOLS.value: {
        "title": "Supporting Educational Tools",
        "description": "English learning utilities, vocabulary tools, educational news feed aggregator, and external learning integrations.",
        "icon": "Wrench",
        "critical_threshold": 7.0,
    },
    EmpireModule.API_SERVICES.value: {
        "title": "API Gateway & Microservices",
        "description": "Central API gateway (gw.empire.edu.vn), course & chapter APIs, social forums, and OWASP API Top 10 defenses.",
        "icon": "Cpu",
        "critical_threshold": 7.5,
    },
    EmpireModule.WEB_APPLICATION.value: {
        "title": "Web Applications & Portals",
        "description": "Student web learning portal, teacher portals, and Vite admin SPA (console.empire.io.vn) client-side RBAC.",
        "icon": "Globe",
        "critical_threshold": 7.0,
    },
    EmpireModule.SERVER_INFRASTRUCTURE.value: {
        "title": "Server & Cloud Infrastructure",
        "description": "Reverse proxies (Nginx), TLS/SSL certificates, MinIO clusters, container configs, and internet-facing port surface.",
        "icon": "Server",
        "critical_threshold": 8.5,
    },
}


@router.get("", response_model=List[Dict[str, Any]])
async def list_empire_modules(db: AsyncSession = Depends(get_db)) -> Any:
    """Returns real-time security posture, asset count, findings, and risk scores

    broken down across Empire's business modules.
    """
    modules_result = []

    for mod_key, meta in MODULE_METADATA.items():
        # 1. Asset count in module
        asset_stmt = select(func.count(Asset.id)).where(Asset.empire_module == mod_key)
        asset_count_res = await db.execute(asset_stmt)
        asset_count = asset_count_res.scalar() or 0

        # 2. Findings counts by severity & status
        finding_stmt = select(NormalizedFinding).where(NormalizedFinding.empire_module == mod_key)
        findings_res = await db.execute(finding_stmt)
        findings = findings_res.scalars().all()

        total_findings = len(findings)
        critical_count = sum(1 for f in findings if f.severity == FindingSeverity.CRITICAL.value and f.status != FindingStatus.FIXED.value)
        high_count = sum(1 for f in findings if f.severity == FindingSeverity.HIGH.value and f.status != FindingStatus.FIXED.value)
        medium_count = sum(1 for f in findings if f.severity == FindingSeverity.MEDIUM.value and f.status != FindingStatus.FIXED.value)
        low_count = sum(1 for f in findings if f.severity in (FindingSeverity.LOW.value, FindingSeverity.INFO.value) and f.status != FindingStatus.FIXED.value)

        open_remediation = sum(
            1 for f in findings if f.status in (FindingStatus.OPEN.value, FindingStatus.IN_REMEDIATION.value, FindingStatus.REOPENED.value)
        )
        fixed_count = sum(1 for f in findings if f.status == FindingStatus.FIXED.value)

        # 3. Compute Module Risk Score (0-100)
        # Weighted formula: Critical * 30 + High * 15 + Medium * 5 + Low * 1, capped at 100
        raw_risk = (critical_count * 30.0) + (high_count * 15.0) + (medium_count * 5.0) + (low_count * 1.0)
        risk_score = round(min(100.0, raw_risk), 1)

        # Risk level category
        if risk_score >= 70.0 or critical_count > 0:
            risk_tier = "CRITICAL"
        elif risk_score >= 40.0 or high_count > 0:
            risk_tier = "HIGH"
        elif risk_score >= 15.0:
            risk_tier = "MEDIUM"
        else:
            risk_tier = "LOW"

        # 4. Latest Assessment Date
        latest_scan_stmt = (
            select(Scan.completed_at)
            .join(Asset, Scan.asset_id == Asset.id)
            .where(Asset.empire_module == mod_key, Scan.completed_at.is_not(None))
            .order_by(Scan.completed_at.desc())
            .limit(1)
        )
        latest_scan_res = await db.execute(latest_scan_stmt)
        latest_scan_time = latest_scan_res.scalar_one_or_none()

        modules_result.append({
            "module_key": mod_key,
            "title": meta["title"],
            "description": meta["description"],
            "icon": meta["icon"],
            "asset_count": asset_count,
            "risk_score": risk_score,
            "risk_tier": risk_tier,
            "total_findings": total_findings,
            "critical_count": critical_count,
            "high_count": high_count,
            "medium_count": medium_count,
            "low_count": low_count,
            "open_remediation_count": open_remediation,
            "fixed_count": fixed_count,
            "latest_assessment": latest_scan_time.isoformat() if latest_scan_time else None,
            "next_scheduled_assessment": "Daily at 02:00 AM ICT",
        })

    return modules_result
