"""Comprehensive test suite for Canonical 10-State Finding Lifecycle, Triage Audit Trail,

Secret Redaction, and Honest Reporting (Milestone 12).
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Dict, List

import httpx
import pytest
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import create_access_token
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.lifecycle import FindingChange
from backend.app.core.config import settings
from backend.app.models.user import User, UserRole
from backend.app.reporting.generator import CoverageGapExport, ReportGenerator
from backend.app.schemas.common import AssetType, FindingSeverity, FindingStatus, VerificationStatus

OWNER_USER_ID = uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID)


@pytest.fixture(autouse=True)
async def seed_test_user():
    """Seeds the authenticated sole owner user for testing finding triage and audit trails."""
    async with AsyncSessionLocal() as session:
        user = await session.get(User, OWNER_USER_ID)
        if not user:
            user = User(
                id=OWNER_USER_ID,
                username="dangnhutnguyen0910",
                email=settings.SOLE_OWNER_EMAIL,
                hashed_password="test_hash_value",
                role=UserRole.OWNER.value,
                is_active=True,
                is_superuser=True,
            )
            session.add(user)
            await session.commit()
        else:
            user.role = UserRole.OWNER.value
            user.email = settings.SOLE_OWNER_EMAIL
            user.is_active = True
            await session.commit()


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Generates valid signed JWT bearer token for the sole owner."""
    token = create_access_token(
        subject=str(OWNER_USER_ID),
        role=UserRole.OWNER.value,
        is_superuser=True,
    )
    return {"Authorization": f"Bearer {token}"}


class TestFindingStatusCanonical10States:
    """Verifies that FindingStatus strictly implements the 10 canonical lifecycle states

    and maintains backward compatibility with legacy aliases.
    """

    def test_exact_10_canonical_states(self):
        canonical = [
            "NEW",
            "NEEDS_TRIAGE",
            "CONFIRMED",
            "FALSE_POSITIVE",
            "ACCEPTED_RISK",
            "ASSIGNED",
            "IN_PROGRESS",
            "FIXED_PENDING_RETEST",
            "RESOLVED",
            "REOPENED",
        ]
        assert len(FindingStatus) == 10
        assert FindingStatus.canonical_states() == canonical

        for name in canonical:
            status_enum = FindingStatus(name)
            assert status_enum.value == name

    def test_backward_compatibility_aliases(self):
        # Attribute alias checks
        assert FindingStatus.OPEN == FindingStatus.NEEDS_TRIAGE
        assert FindingStatus.POTENTIAL == FindingStatus.NEEDS_TRIAGE
        assert FindingStatus.IN_REMEDIATION == FindingStatus.IN_PROGRESS
        assert FindingStatus.FIXED == FindingStatus.FIXED_PENDING_RETEST
        assert FindingStatus.NOT_AFFECTED == FindingStatus.FALSE_POSITIVE
        assert FindingStatus.MUTED == FindingStatus.ACCEPTED_RISK

        # Dynamic string parsing via _missing_
        assert FindingStatus("OPEN") == FindingStatus.NEEDS_TRIAGE
        assert FindingStatus("open") == FindingStatus.NEEDS_TRIAGE
        assert FindingStatus("POTENTIAL") == FindingStatus.NEEDS_TRIAGE
        assert FindingStatus("IN_REMEDIATION") == FindingStatus.IN_PROGRESS
        assert FindingStatus("FIXED") == FindingStatus.FIXED_PENDING_RETEST
        assert FindingStatus("NOT_AFFECTED") == FindingStatus.FALSE_POSITIVE
        assert FindingStatus("MUTED") == FindingStatus.ACCEPTED_RISK


class TestFindingTriageAndAuditTrail:
    """Tests triage state transitions, audit trail logging, and secret redaction."""

    @pytest.mark.asyncio
    async def test_triage_all_canonical_states_and_audit_log(
        self,
        client: httpx.AsyncClient,
        auth_headers: Dict[str, str],
    ):
        """Creates a finding and tests triage progression through canonical states."""
        asset_id = uuid.uuid4()
        scan_id = uuid.uuid4()
        finding_id = uuid.uuid4()

        # Seed asset and finding directly
        async with AsyncSessionLocal() as session:
            asset = Asset(
                id=asset_id,
                name="Triage Test Asset",
                target_locator="https://triage.empire.edu.vn",
                asset_type=AssetType.WEB_APP.value,
                verification_status=VerificationStatus.VERIFIED.value,
            )
            session.add(asset)

            finding = NormalizedFinding(
                id=finding_id,
                asset_id=asset_id,
                scan_id=scan_id,
                fingerprint=f"fp-{uuid.uuid4().hex[:12]}",
                scanner_engine="nuclei",
                scanner_rule_id="cve-2023-test",
                title="Cross-Site Scripting in Student Portal",
                description="Reflected XSS on search query parameter.",
                severity=FindingSeverity.HIGH.value,
                original_severity="high",
                target_location="https://triage.empire.edu.vn/search",
                status=FindingStatus.NEW.value,
            )
            session.add(finding)
            await session.commit()

        # Test canonical transitions
        test_states = [
            (FindingStatus.NEEDS_TRIAGE, "Assessed by analyst: Needs triage review."),
            (FindingStatus.CONFIRMED, "Vulnerability verified reproducible."),
            (FindingStatus.ASSIGNED, "Assigned to appsec developer."),
            (FindingStatus.IN_PROGRESS, "Remediation patch currently in development."),
            (FindingStatus.FIXED_PENDING_RETEST, "Code deployed to staging, awaiting affirmative retest."),
            (FindingStatus.RESOLVED, "Defensive control verified fixed in production."),
            (FindingStatus.REOPENED, "Reoccurrence detected on subsequent regression scan."),
            (FindingStatus.ACCEPTED_RISK, "Formal risk waiver accepted by CISO."),
            (FindingStatus.FALSE_POSITIVE, "WAF synthetic anomaly rule determined non-exploitable."),
        ]

        for target_status, note in test_states:
            resp = await client.post(
                f"/api/v1/findings/{finding_id}/triage",
                headers=auth_headers,
                json={
                    "status": target_status.value,
                    "comment": note,
                    "assignee": "appsec-engineer",
                },
            )
            assert resp.status_code == 200, f"Failed transitioning to {target_status.value}: {resp.text}"
            data = resp.json()
            assert data["status"] == target_status.value
            assert data["remediation_notes"] == note
            assert data["assignee"] == "appsec-engineer"

            # Verify triage history in evidence
            triage_hist = data["evidence"].get("triage_history", [])
            assert len(triage_hist) >= 1
            latest = triage_hist[-1]
            assert latest["new_status"] == target_status.value
            assert latest["comment"] == note

        # Verify FindingChange immutable audit records in database
        async with AsyncSessionLocal() as session:
            stmt = select(FindingChange).where(FindingChange.finding_id == finding_id)
            changes = (await session.execute(stmt)).scalars().all()
            assert len(changes) >= len(test_states), "Audit changes were not recorded in FindingChange table."
            status_changes = [c for c in changes if c.field == "status"]
            assert len(status_changes) >= len(test_states)

    @pytest.mark.asyncio
    async def test_secret_redaction_in_triage(
        self,
        client: httpx.AsyncClient,
        auth_headers: Dict[str, str],
    ):
        """Verifies Bearer tokens, cookies, passwords, and JWTs are redacted from comments and evidence."""
        asset_id = uuid.uuid4()
        finding_id = uuid.uuid4()

        async with AsyncSessionLocal() as session:
            asset = Asset(
                id=asset_id,
                name="Redaction Test Asset",
                target_locator="https://redact.empire.edu.vn",
                asset_type=AssetType.WEB_APP.value,
                verification_status=VerificationStatus.VERIFIED.value,
            )
            finding = NormalizedFinding(
                id=finding_id,
                asset_id=asset_id,
                scan_id=uuid.uuid4(),
                fingerprint=f"fp-{uuid.uuid4().hex[:12]}",
                scanner_engine="zap",
                scanner_rule_id="auth-leak",
                title="Leaked Authorization Headers",
                description="Sensitive credentials leaked in HTTP header logs.",
                severity=FindingSeverity.HIGH.value,
                original_severity="high",
                target_location="https://redact.empire.edu.vn/api/user",
                status=FindingStatus.NEW.value,
                evidence={
                    "request": "GET /api/user HTTP/1.1\nAuthorization: Bearer secret_api_key_value_12345",
                    "cookie": "session_id_sensitive_value_abcde",
                },
            )
            session.add(asset)
            session.add(finding)
            await session.commit()

        # Submit comment containing sensitive credentials
        sensitive_comment = (
            "Investigated trace with password=SuperSecretPassword999! and "
            "token=ghp_PersonalAccessTokenABC123 and Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeak"
        )
        resp = await client.post(
            f"/api/v1/findings/{finding_id}/triage",
            headers=auth_headers,
            json={
                "status": "CONFIRMED",
                "comment": sensitive_comment,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify secrets are redacted in remediation_notes
        notes = data["remediation_notes"]
        assert "SuperSecretPassword999!" not in notes
        assert "[REDACTED]" in notes
        assert "doNotLeak" not in notes

        # Verify secrets in evidence history are redacted
        triage_entry = data["evidence"]["triage_history"][-1]
        assert "SuperSecretPassword999!" not in triage_entry["comment"]
        assert "[REDACTED]" in triage_entry["comment"]


class TestReportingCoverageGapsAndDualTheme:
    """Verifies that the reporting pipeline honestly discloses Coverage Gaps & Exclusions

    and renders both Obsidian Dark and Warm Light theme CSS styles.
    """

    def test_report_export_model_coverage_metrics(self):
        generator = ReportGenerator(storage_dir=Path("storage/test_reports"))
        gap_1 = CoverageGapExport(
            target="https://admin.internal.empire.edu.vn",
            target_locator="https://admin.internal.empire.edu.vn",
            engine="zap",
            status="BLOCKED",
            reason="Private IP / Intranet origin without explicit authorization waiver.",
            remediation_suggestion="Submit RFC-1918 security authorization sign-off.",
        )
        gap_2 = CoverageGapExport(
            target="https://heavy.empire.edu.vn/bulk-export",
            target_locator="https://heavy.empire.edu.vn/bulk-export",
            engine="nuclei",
            status="TIMEOUT",
            reason="Endpoint response exceeded 300s deadline limit.",
            remediation_suggestion="Increase timeout allocation or schedule dedicated maintenance window.",
        )

        export = generator.prepare_report_data(
            report_id=str(uuid.uuid4()),
            title="Integrity Audit Test",
            report_type="technical",
            target_scope="Empire Production Perimeter",
            findings=[],
            coverage_gaps=[gap_1, gap_2],
        )

        assert len(export.coverage_gaps) == 2
        assert export.coverage_gaps[0].status == "BLOCKED"
        assert export.coverage_gaps[1].status == "TIMEOUT"
        assert export.coverage_metrics["coverage_gaps_count"] == 2
        assert export.coverage_metrics["coverage_pct"] < 100.0

    def test_html_report_rendering_coverage_gaps_and_warm_light(self, tmp_path: Path):
        generator = ReportGenerator(storage_dir=tmp_path)
        gap = CoverageGapExport(
            target="https://excluded.empire.edu.vn",
            target_locator="https://excluded.empire.edu.vn",
            engine="trivy",
            status="EXCLUDED",
            reason="Container repository registry auth expired.",
            remediation_suggestion="Refresh robot account credentials.",
        )

        export = generator.prepare_report_data(
            report_id=str(uuid.uuid4()),
            title="Warm Light & Coverage Test",
            report_type="technical",
            target_scope="All Scope",
            findings=[],
            coverage_gaps=[gap],
        )

        out_html = tmp_path / "report.html"
        generator.render_html(export, out_html)
        assert out_html.exists()

        content = out_html.read_text(encoding="utf-8")
        # Verify Coverage Gaps section
        assert "3. Coverage Gaps & Exclusions" in content
        assert "https://excluded.empire.edu.vn" in content
        assert "EXCLUDED" in content
        assert "Container repository registry auth expired" in content

        # Verify Warm Light theme styling exists in CSS
        assert "--bg-primary: #FAF8F5" in content
        assert "--bg-surface: #FFFFFF" in content
        assert "--text-primary: #18181B" in content
        assert "theme-warm" in content
        assert "toggleTheme" in content

    def test_pdf_report_rendering_coverage_gaps(self, tmp_path: Path):
        generator = ReportGenerator(storage_dir=tmp_path)
        gap = CoverageGapExport(
            target="https://blocked-gateway.empire.edu.vn",
            target_locator="https://blocked-gateway.empire.edu.vn",
            engine="nuclei",
            status="AUTH_REQUIRED",
            reason="Active probe authorization verification missing.",
            remediation_suggestion="Complete DNS-TXT asset ownership verification.",
        )

        export = generator.prepare_report_data(
            report_id=str(uuid.uuid4()),
            title="PDF Vector Audit Test",
            report_type="technical",
            target_scope="Enterprise Scope",
            findings=[],
            coverage_gaps=[gap],
        )

        out_pdf = tmp_path / "report.pdf"
        generator.render_pdf(export, out_pdf)
        assert out_pdf.exists()
        assert out_pdf.stat().st_size > 1000
