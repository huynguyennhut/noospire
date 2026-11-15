import hashlib
import logging
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.scheduler import compute_next_run
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan
from backend.app.models.baseline import BaselineException
from backend.app.models.schedule import DailySchedule
from backend.app.models.alert import SecurityAlert
from backend.app.models.synthetic_identity import SyntheticIdentity
from backend.app.models.proof import AssetOwnershipProof
from backend.app.models.scope import AssetAssessmentScope
from backend.app.schemas.common import (
    AssetType,
    Criticality,
    EmpireModule,
    Exposure,
    ExposureClassification,
    FindingSeverity,
    FindingStatus,
    ScanProfile,
    ScanStatus,
    VerificationStatus,
    VerificationType,
)

logger = logging.getLogger("sentinel.empire_seeder")


async def seed_empire_ecosystem(session: AsyncSession) -> None:
    """Seeds the Empire Educational Ecosystem targets, historical audit findings,

    Approved Public Media baseline policies, and continuous daily scheduler.
    """
    logger.info("Initializing Empire Security Intelligence baseline seeder...")

    # -------------------------------------------------------------------------
    # 1. REGISTER THE CORE EMPIRE TARGETS (INCLUDING PRIMARY ROOT TARGET)
    # -------------------------------------------------------------------------
    existing_res = await session.execute(select(Asset))
    existing_assets = existing_res.scalars().all()
    assets_map = {a.target_locator: a for a in existing_assets}
    norm_map = {a.target_locator.rstrip("/"): a for a in existing_assets}

    now = datetime.now(timezone.utc)

    targets_data = [
        {
            "name": "Empire Educational Platform (Primary Root)",
            "locator": "https://empire.edu.vn/",
            "type": AssetType.WEB_APP.value,
            "module": EmpireModule.WEB_APPLICATION.value,
            "tech": "Next.js / Envoy / React",
            "crit": Criticality.CRITICAL.value,
            "desc": "Primary root educational portal and main landing platform for Empire Education. Governed by same-origin assessment scope (*.empire.edu.vn) and production-safe baseline policy.",
            "approved_media": False,
            "assessment_policy": {
                "daily_scan": True,
                "intensity": "PRODUCTION_SAFE",
                "baseline_policy": "PRODUCTION_SAFE",
                "allow_active": True,
                "scope": "*.empire.edu.vn",
                "same_origin_scope": "*.empire.edu.vn",
                "same_origin_only": True,
                "rate_limit_rps": 5,
                "safe_mode": True,
            },
            "tags": ["empire", "root", "primary", "production", "web_application"],
        },
        {
            "name": "Empire Identity & Student Management",
            "locator": "https://id.empire.edu.vn",
            "type": AssetType.WEB_APP.value,
            "module": EmpireModule.STUDENT_MANAGEMENT.value,
            "tech": "Better-Auth / TypeScript / Next.js",
            "crit": Criticality.CRITICAL.value,
            "desc": "Primary authentication and student account management system. Handles student sign-in, registration, password resets, and session tokens.",
            "approved_media": False,
        },
        {
            "name": "Empire Central API Gateway",
            "locator": "https://gw.empire.edu.vn",
            "type": AssetType.API_ENDPOINT.value,
            "module": EmpireModule.API_SERVICES.value,
            "tech": "FastAPI / Node.js Reverse Proxy / Courses & Social API",
            "crit": Criticality.HIGH.value,
            "desc": "Central API gateway routing traffic to courses, chapters, lessons, exams, and community social services.",
            "approved_media": False,
        },
        {
            "name": "Empire Educational Media Host (/media)",
            "locator": "https://mh.empire.edu.vn/media",
            "type": AssetType.WEB_APP.value,
            "module": EmpireModule.LEARNING_MATERIALS.value,
            "tech": "Nginx / MinIO S3 Object Storage / Static Media",
            "crit": Criticality.HIGH.value,
            "desc": "Publicly accessible media host for authorized educational content, course lecture PDFs, and video streams. Governed by Approved Public Exposure Policy.",
            "approved_media": True,
        },
        {
            "name": "Empire Object Storage (MinIO)",
            "locator": "https://voh.empire.edu.vn",
            "type": AssetType.OBJECT_STORAGE.value,
            "module": EmpireModule.LEARNING_MATERIALS.value,
            "tech": "MinIO S3-Compatible Cloud Storage",
            "crit": Criticality.CRITICAL.value,
            "desc": "Primary backend S3-compatible bucket storage cluster holding all curriculum documents, raw exams, and audio resources.",
            "approved_media": False,
        },
        {
            "name": "Empire Admin Management Console",
            "locator": "https://console.empire.io.vn",
            "type": AssetType.WEB_APP.value,
            "module": EmpireModule.WEB_APPLICATION.value,
            "tech": "Vite / React SPA / Client-Side RBAC",
            "crit": Criticality.HIGH.value,
            "desc": "Administrative dashboard interface for instructors, teaching assistants, and administrative staff.",
            "approved_media": False,
        },
        {
            "name": "Empire News & Supporting Educational Services",
            "locator": "https://gw.empire.edu.vn/news",
            "type": AssetType.WEB_APP.value,
            "module": EmpireModule.SUPPORTING_TOOLS.value,
            "tech": "News Aggregator / English Vocabulary Services",
            "crit": Criticality.MEDIUM.value,
            "desc": "Supporting educational tool suite providing English language learning tools, news feed aggregation, and vocabulary practice.",
            "approved_media": False,
        },
    ]

    added_count = 0
    for t in targets_data:
        loc = t["locator"]
        norm_loc = loc.rstrip("/")
        if loc in assets_map or norm_loc in norm_map:
            continue

        is_prod = settings.is_production
        asset_obj = Asset(
            id=uuid.uuid4(),
            name=t["name"],
            asset_type=t["type"],
            target_locator=loc,
            empire_module=t["module"],
            environment="PRODUCTION",
            technology=t["tech"],
            criticality=t["crit"],
            exposure=Exposure.INTERNET.value,
            description=t["desc"],
            approved_media_baseline=t["approved_media"],
            verification_status=VerificationStatus.PENDING.value if is_prod else VerificationStatus.VERIFIED.value,
            verification_type="NONE" if is_prod else VerificationType.ADMIN_OVERRIDE.value,
            verified_at=None if is_prod else now.isoformat(),
            assessment_policy=t.get("assessment_policy", {"daily_scan": True, "intensity": "STANDARD", "allow_active": True}),
            tags=t.get("tags", ["empire", t["module"].lower(), "production"]),
        )
        session.add(asset_obj)

        challenge_token = secrets.token_urlsafe(32)
        initial_proof = AssetOwnershipProof(
            id=uuid.uuid4(),
            asset_id=asset_obj.id,
            method="HTTP_WELL_KNOWN",
            challenge_token=challenge_token,
            status="PENDING" if is_prod else "VERIFIED",
            verified_at=None if is_prod else now,
            proof_data={"initial_seed": True},
            created_by="system",
        )
        session.add(initial_proof)

        initial_scope = AssetAssessmentScope(
            id=uuid.uuid4(),
            asset_id=asset_obj.id,
            exact_origin=loc.rstrip("/"),
            allowed_path_patterns=["/*"],
            rate_limit_rps=5,
            emergency_stop_active=False,
            created_by="system",
        )
        session.add(initial_scope)

        assets_map[loc] = asset_obj
        norm_map[norm_loc] = asset_obj
        added_count += 1

    await session.flush()
    if added_count > 0:
        logger.info(f"Seeded {added_count} new Empire target(s) into asset inventory (Total: {len(assets_map)}).")
    else:
        logger.info(f"All {len(assets_map)} Empire targets already present in inventory.")


    # -------------------------------------------------------------------------
    # 2. SEED INITIAL HISTORICAL AUDIT SCAN & THE 6 VERIFIED VULNERABILITIES
    # -------------------------------------------------------------------------
    findings_check = await session.execute(select(NormalizedFinding).limit(1))
    if not settings.is_production and findings_check.scalars().first() is None and "https://id.empire.edu.vn" in assets_map:
        initial_scan = Scan(
            id=uuid.uuid4(),
            asset_id=assets_map["https://id.empire.edu.vn"].id,
            engine="empire_consolidated_suite",
            profile=ScanProfile.THOROUGH.value,
            status=ScanStatus.COMPLETED.value,
            progress_percentage=100,
            target_locator="https://*.empire.edu.vn",
            allow_private_targets=True,
            timeout_seconds=1200,
            started_at=now,
            completed_at=now,
        )
        session.add(initial_scan)
        await session.flush()

        findings_data = [
            {
                "asset": assets_map["https://voh.empire.edu.vn"],
                "rule_id": "VULN-01",
                "title": "Public Anonymous Access to Object Storage (MinIO Bucket Exposure)",
                "severity": FindingSeverity.CRITICAL,
                "orig_sev": "critical",
                "module": EmpireModule.LEARNING_MATERIALS.value,
                "exp_class": ExposureClassification.MISCONFIGURED_MEDIA_STORAGE.value,
                "cvss": 9.8,
                "cwe": "CWE-284",
                "loc": "https://voh.empire.edu.vn",
                "comp": "MinIO S3 Bucket (voh.empire.edu.vn / mh.empire.edu.vn)",
                "desc": (
                    "The MinIO object storage cluster hosting educational materials and curriculum assets permits unauthenticated anonymous read "
                    "access to root bucket listings and sensitive exams. Over 68/69 official exam answer keys and PDFs were accessible without credentials."
                ),
                "remediation": "Disable anonymous public ListObjects policy in MinIO and enforce presigned URL expiration tokens for private materials.",
                "evidence": {
                    "audit_report_ref": "NOOSFORGE-BCONS-002 Chapter 4",
                    "affected_hosts": ["voh.empire.edu.vn", "mh.empire.edu.vn"],
                    "downloaded_assets": "68/69 Official Exam PDFs & Answer keys (180.89 MB)",
                    "bucket_listing_allowed": True,
                },
            },
            {
                "asset": assets_map["https://console.empire.io.vn"],
                "rule_id": "VULN-02",
                "title": "Client-Side RBAC Enforcement Flaw & Privilege Verification Failure",
                "severity": FindingSeverity.HIGH,
                "orig_sev": "high",
                "module": EmpireModule.WEB_APPLICATION.value,
                "exp_class": None,
                "cvss": 8.8,
                "cwe": "CWE-602",
                "loc": "https://console.empire.io.vn",
                "comp": "Vite Admin SPA (console.empire.io.vn)",
                "desc": (
                    "Role-based access control (RBAC) was enforced primarily on the client-side JavaScript layer within Vite Admin SPA. "
                    "By inspecting client state or manipulating local storage permission claims, administrative navigation menus and buttons become unhidden."
                ),
                "remediation": "Implement strict backend authorization checks on all API endpoints; never rely on frontend UI hiding for security boundaries.",
                "evidence": {
                    "audit_report_ref": "NOOSFORGE-BCONS-002 Chapter 5",
                    "exploit_proof": "empire_admin_unhider.js DOM manipulation unlocks admin portal UI",
                    "master_admin_id": "bbb30e49379347e3a37a84c851fb7fa4",
                },
            },
            {
                "asset": assets_map["https://id.empire.edu.vn"],
                "rule_id": "VULN-03",
                "title": "Unauthenticated User Enumeration & Targeted Credential Spraying",
                "severity": FindingSeverity.HIGH,
                "orig_sev": "high",
                "module": EmpireModule.STUDENT_MANAGEMENT.value,
                "exp_class": None,
                "cvss": 8.2,
                "cwe": "CWE-307",
                "loc": "https://id.empire.edu.vn",
                "comp": "Better-Auth Gateway (id.empire.edu.vn / gw.empire.edu.vn)",
                "desc": (
                    "Discrepancies in response time, status codes, and JSON error messaging on Better-Auth endpoints allow attackers to enumerate "
                    "valid student and staff emails. Combined with weak default initial student passwords, multiple accounts were successfully compromised."
                ),
                "remediation": "Unify authentication error messages ('Invalid email or password'), enforce progressive delay, and mandate password changes upon initial enrollment.",
                "evidence": {
                    "audit_report_ref": "NOOSFORGE-BCONS-002 Chapter 6",
                    "enumerated_profiles": "40 Developer, Technical & Admin profiles uncovered",
                    "weak_default_passwords_identified": "07 VIP Accounts compromised (197,000,000 VND curriculum value)",
                },
            },
            {
                "asset": assets_map["https://gw.empire.edu.vn"],
                "rule_id": "VULN-04",
                "title": "Unauthenticated Social Intelligence & User Activity Harvesting",
                "severity": FindingSeverity.HIGH,
                "orig_sev": "high",
                "module": EmpireModule.STUDENT_MANAGEMENT.value,
                "exp_class": None,
                "cvss": 7.5,
                "cwe": "CWE-200",
                "loc": "https://gw.empire.edu.vn/social/v2/*",
                "comp": "Social Community API (gw.empire.edu.vn/social/v2/*)",
                "desc": (
                    "The community groups and discussion forum endpoints expose member lists, full names, avatars, and internal group memberships without requiring session credentials. "
                    "Over 207,000 student and staff memberships across 13 groups were harvestable."
                ),
                "remediation": "Enforce authentication on /social/v2/* group member queries and paginate public member lists with strict rate limiting.",
                "evidence": {
                    "audit_report_ref": "NOOSFORGE-BCONS-002 Chapter 7",
                    "groups_harvested": "13 Community Groups (>207,000 members)",
                    "internal_dev_group_exposed": "NhA3m dev web (38 members)",
                },
            },
            {
                "asset": assets_map["https://gw.empire.edu.vn"],
                "rule_id": "VULN-05",
                "title": "Proprietary Course Curriculum, Video HLS & Document Leakage",
                "severity": FindingSeverity.HIGH,
                "orig_sev": "high",
                "module": EmpireModule.LEARNING_MATERIALS.value,
                "exp_class": ExposureClassification.PRIVATE_ACCESS_CONTROL_FAILURE.value,
                "cvss": 7.5,
                "cwe": "CWE-285",
                "loc": "https://gw.empire.edu.vn/courses/*",
                "comp": "Courses API (gw.empire.edu.vn/courses/*)",
                "desc": (
                    "Proprietary course structures, chapter outlines, video HLS streaming URLs, and companion PDFs were returned to unauthenticated users "
                    "calling the public gateway courses routes. 10 core courses and 512 lessons were accessible without an active enrollment purchase."
                ),
                "remediation": "Restrict course content detail payloads to users with verified active enrollment claims.",
                "evidence": {
                    "audit_report_ref": "NOOSFORGE-BCONS-002 Chapter 8",
                    "extracted_content": "10 Core Courses, 120 Chapters, 512 Lessons, 2,223 Videos, 2,195 PDFs",
                },
            },
            {
                "asset": assets_map["https://console.empire.io.vn"],
                "rule_id": "VULN-06",
                "title": "Client-Side Hardcoded Secrets, Environment Variables & API Routing Leakage",
                "severity": FindingSeverity.MEDIUM,
                "orig_sev": "medium",
                "module": EmpireModule.API_SERVICES.value,
                "exp_class": None,
                "cvss": 6.5,
                "cwe": "CWE-798",
                "loc": "https://console.empire.io.vn/assets/index.js",
                "comp": "Compiled JavaScript Bundle (empire_index-DuvG8e9o.js)",
                "desc": (
                    "Production frontend JavaScript bundles contained un-obfuscated internal API routes, staging subdomains, third-party API keys, "
                    "and environment configuration objects revealing internal infrastructure architecture."
                ),
                "remediation": "Purge internal secrets from frontend builds and implement automated secret scanning in the CI/CD pipeline.",
                "evidence": {
                    "audit_report_ref": "NOOSFORGE-BCONS-002 Chapter 9",
                    "source_file": "harvested_assets/empire_index-DuvG8e9o.js",
                },
            },
        ]

        for f in findings_data:
            raw_key = f"{f['asset'].id}:empire_audit:{f['rule_id']}:{f['loc']}:{f['comp']}"
            fp = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

            finding = NormalizedFinding(
                id=uuid.uuid4(),
                scan_id=initial_scan.id,
                asset_id=f["asset"].id,
                fingerprint=fp,
                empire_module=f["module"],
                exposure_classification=f.get("exp_class"),
                is_approved_baseline=False,
                scanner_engine="empire_audit_harvester",
                scanner_rule_id=f["rule_id"],
                title=f["title"],
                description=f["desc"],
                severity=f["severity"].value,
                original_severity=f["orig_sev"],
                cwe_id=f["cwe"],
                cvss_score=f["cvss"],
                target_location=f["loc"],
                target_component=f["comp"],
                evidence=f["evidence"],
                remediation=f["remediation"],
                status=FindingStatus.OPEN.value,
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
            )
            session.add(finding)

    # -------------------------------------------------------------------------
    # 3. SEED APPROVED PUBLIC MEDIA BASELINE POLICY
    # -------------------------------------------------------------------------
    baseline_check = await session.execute(select(BaselineException).limit(1))
    if baseline_check.scalars().first() is None:
        media_baseline = BaselineException(
            id=uuid.uuid4(),
            scope="https://mh.empire.edu.vn/media/*",
            classification=ExposureClassification.PUBLIC_BY_DESIGN.value,
            reason=(
                "The /media directory is intentionally configured to allow anonymous public access for designated educational materials "
                "(lesson summaries, sample audio, publicly distributed textbook previews) as per Empire Platform Business Policy."
            ),
            owner="Empire Academic Content Delivery Team",
            approved_by="Security Operations Lead (Nhut)",
            is_active=True,
            evidence={
                "policy_document": "EMPIRE-MEDIA-POLICY-2026-V1",
                "allowed_extensions": [".pdf", ".mp4", ".mp3", ".jpg", ".png", ".webp"],
                "forbidden_patterns": ["*student*", "*.env*", "*backup*", "*password*"],
            },
            review_history=[
                {
                    "reviewed_at": now.isoformat(),
                    "reviewer": "Security Operations Lead (Nhut)",
                    "status": "APPROVED",
                    "notes": "Verified public educational media requirements. Baseline exception active.",
                }
            ],
        )
        session.add(media_baseline)

    # -------------------------------------------------------------------------
    # 4. SEED SYNTHETIC IDENTITIES FOR NON-DESTRUCTIVE TESTING
    # -------------------------------------------------------------------------
    ident_check = await session.execute(select(SyntheticIdentity).limit(1))
    if ident_check.scalars().first() is None:
        synthetic_identities = [
            SyntheticIdentity(
                id=uuid.uuid4(),
                identifier="studenttu1",
                role="STUDENT",
                email="studenttu1@empire.local",
                description="Historical internal student test account identified during security audit",
                is_active=True,
            ),
            SyntheticIdentity(
                id=uuid.uuid4(),
                identifier="test_student_a",
                role="STUDENT",
                email="student_alpha_audit@empire.local",
                description="Synthetic student persona for BOLA/IDOR cross-account authorization testing",
                is_active=True,
            ),
            SyntheticIdentity(
                id=uuid.uuid4(),
                identifier="test_student_b",
                role="STUDENT",
                email="student_bravo_audit@empire.local",
                description="Synthetic student persona for BOLA/IDOR receiver validation",
                is_active=True,
            ),
        ]
        for ident in synthetic_identities:
            session.add(ident)

    # -------------------------------------------------------------------------
    # 5. SEED CONTINUOUS DAILY ASSESSMENT SCHEDULE (Asia/Ho_Chi_Minh)
    # -------------------------------------------------------------------------
    sched_check = await session.execute(select(DailySchedule).limit(1))
    if sched_check.scalars().first() is None:
        daily_schedule = DailySchedule(
            id=uuid.uuid4(),
            name="Empire Enterprise Daily Security Assessment Pipeline",
            profile=ScanProfile.DAILY_SECURITY.value,
            cron_expression="0 * * * *",  # Top of each hour ICT
            timezone="Asia/Ho_Chi_Minh",
            is_active=False if settings.is_production else True,
            target_ids=["ALL"],
            last_status="IDLE" if settings.is_production else "SUCCESS",
            last_run_at=None if settings.is_production else now,
            next_run_at=compute_next_run("0 * * * *", now, "Asia/Ho_Chi_Minh"),
        )
        session.add(daily_schedule)

    from backend.app.models.operations import MonitorSchedule
    mon_check = await session.execute(select(MonitorSchedule).limit(1))
    if mon_check.scalars().first() is None:
        mon_schedule = MonitorSchedule(
            id=uuid.uuid4(),
            name="Empire Hourly Security Assessment Pipeline",
            selection={"kind": "all"},
            engines=["sbom", "tls_health"],
            profile="light",
            interval_minutes=60,
            max_workers=2,
            is_active=True,
            start_after=now,
            next_run_at=now,
            created_by=settings.SOLE_OWNER_ACCOUNT_ID,
        )
        session.add(mon_schedule)

    # -------------------------------------------------------------------------
    # 6. SEED INITIAL SOC ALERTS
    # -------------------------------------------------------------------------
    alert_check = await session.execute(select(SecurityAlert).limit(1))
    if alert_check.scalars().first() is None:
        alerts = [
            SecurityAlert(
                id=uuid.uuid4(),
                severity=FindingSeverity.CRITICAL.value,
                title="Critical Storage Exposure: MinIO Bucket Anonymous Access",
                message="Target voh.empire.edu.vn permits anonymous access to curriculum exams and answer keys.",
                category="VULN",
                metadata_json={"rule_id": "VULN-01", "target": "https://voh.empire.edu.vn"},
            ),
            SecurityAlert(
                id=uuid.uuid4(),
                severity=FindingSeverity.HIGH.value,
                title="User Enumeration & Weak Passwords Discovered",
                message="Better-Auth endpoint on id.empire.edu.vn allows unauthenticated user enumeration and spraying.",
                category="VULN",
                metadata_json={"rule_id": "VULN-03", "target": "https://id.empire.edu.vn"},
            ),
            SecurityAlert(
                id=uuid.uuid4(),
                severity=FindingSeverity.INFO.value,
                title="Approved Public Media Baseline Activated",
                message="Path https://mh.empire.edu.vn/media/* registered as PUBLIC_BY_DESIGN baseline exception.",
                category="BASELINE",
                metadata_json={"scope": "https://mh.empire.edu.vn/media/*"},
            ),
        ]
        for alert in alerts:
            session.add(alert)

    await session.commit()
    logger.info("Successfully seeded Empire targets, historical findings, approved media baseline, and daily schedule.")

