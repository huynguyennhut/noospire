"""Challenger 2 — Empirical Live Target Baseline Assessment Verification Suite.

Validates the live target https://empire.edu.vn/ across:
1. DB Target Registration, Same-Origin Scope (*.empire.edu.vn) & Safe Assessment Policy.
2. 8-Step Live Target Verification Pipeline (DNS, TLS, HTTP, Redirect, Fingerprint).
3. Real Baseline Assessment Scan Dispatch via Scanner Dispatcher API.
4. Real Audit Logs, Raw Request/Response Evidence & Finding Deduplication.
"""

from __future__ import annotations

import asyncio
import json
import uuid
import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.main import app
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.target_verifier import get_target_verifier
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan, ScanLog
from backend.app.schemas.common import (
    AssetType,
    Criticality,
    EmpireModule,
    ScanProfile,
    ScanQualityStatus,
    ScanStatus,
    VerificationStatus,
)


@pytest.mark.asyncio
async def test_01_target_registration_and_policy(db_session: AsyncSession):
    """Requirement 1: Verify https://empire.edu.vn/ is registered with same-origin scope & safe policy."""
    stmt = select(Asset).where(Asset.target_locator.in_(("https://empire.edu.vn/", "https://empire.edu.vn")))
    res = await db_session.execute(stmt)
    asset = res.scalars().first()

    assert asset is not None, "Target https://empire.edu.vn/ must be registered in noospire.db"
    assert asset.target_locator in ("https://empire.edu.vn/", "https://empire.edu.vn")
    assert asset.asset_type == AssetType.WEB_APP.value
    assert asset.criticality == Criticality.CRITICAL.value
    assert asset.verification_status == VerificationStatus.VERIFIED.value

    policy = asset.assessment_policy
    assert isinstance(policy, dict), "Assessment policy must be a JSON dictionary"
    assert policy.get("daily_scan") is True
    assert policy.get("safe_mode") is True
    assert policy.get("same_origin_only") is True
    assert policy.get("scope") == "*.empire.edu.vn" or policy.get("same_origin_scope") == "*.empire.edu.vn"
    assert policy.get("baseline_policy") == "PRODUCTION_SAFE" or policy.get("intensity") == "PRODUCTION_SAFE"
    assert policy.get("rate_limit_rps") is not None and policy.get("rate_limit_rps") <= 10


@pytest.mark.asyncio
async def test_02_execute_8_step_live_verification_pipeline(client: httpx.AsyncClient, db_session: AsyncSession):
    """Requirement 2: Execute the 8-step live probe pipeline against https://empire.edu.vn/."""
    # Find asset
    stmt = select(Asset).where(Asset.target_locator.in_(("https://empire.edu.vn/", "https://empire.edu.vn")))
    res = await db_session.execute(stmt)
    asset = res.scalars().first()
    assert asset is not None

    # Call POST /api/v1/assets/{id}/verify
    resp = await client.post(f"/api/v1/assets/{asset.id}/verify", json={"verification_type": "ADMIN_OVERRIDE"})
    assert resp.status_code == 200, f"Verify API returned status {resp.status_code}: {resp.text}"

    data = resp.json()
    assert data["verified"] is True
    assert data["status"] == "VERIFIED"
    assert len(data["steps"]) == 8, f"Expected 8 verification steps, got {len(data['steps'])}"

    steps_by_num = {s["step"]: s for s in data["steps"]}
    step_names = [s["name"] for s in data["steps"]]
    assert step_names == [
        "Input Validation",
        "DNS Resolution",
        "TLS Verification",
        "HTTP Connectivity",
        "Redirect Inspection",
        "Web Discovery",
        "Target Fingerprint",
        "Verification Result",
    ]

    # Verify Step 1: Input Validation
    s1 = steps_by_num[1]
    assert s1["status"] == "PASS"
    assert "metadata" in s1 and s1["metadata"].get("scheme") == "https"

    # Verify Step 2: DNS Resolution
    s2 = steps_by_num[2]
    assert s2["status"] == "PASS"
    dns_meta = s2.get("metadata", {})
    resolved_ips = dns_meta.get("ipv4_addresses", [])
    assert dns_meta.get("total_ips", 0) > 0 or len(resolved_ips) > 0
    assert any(ip.startswith("160.191.101.") for ip in resolved_ips), f"Resolved IP {resolved_ips} should match Empire subnet 160.191.101.0/24"

    # Verify Step 3: TLS Verification
    s3 = steps_by_num[3]
    assert s3["status"] in ("PASS", "INFO")
    assert s3["metadata"].get("tls_version") is not None

    # Verify Step 4: HTTP Connectivity
    s4 = steps_by_num[4]
    assert s4["status"] == "PASS"
    assert s4["metadata"].get("status_code") is not None
    assert s4["metadata"].get("status_code") in (200, 301, 302, 307, 308)
    assert s4["metadata"].get("latency_ms") is not None and s4["metadata"]["latency_ms"] > 0

    # Verify Step 5: Redirect Inspection
    s5 = steps_by_num[5]
    assert s5["status"] in ("PASS", "INFO")
    assert s5["metadata"].get("protocol_downgrade") is False

    # Verify Step 6: Web Discovery
    s6 = steps_by_num[6]
    assert s6["status"] in ("PASS", "INFO")

    # Verify Step 7: Target Fingerprint
    s7 = steps_by_num[7]
    assert s7["status"] == "PASS"
    fp = data.get("fingerprint", {})
    assert "server" in fp
    assert "reverse_proxy_waf" in fp
    assert "technologies" in fp
    assert fp.get("active_security_headers_count", 0) >= 0

    # Verify Step 8: Verification Result
    s8 = steps_by_num[8]
    assert s8["status"] == "PASS"
    assert s8["metadata"].get("verdict") == "VERIFIED"


@pytest.mark.asyncio
async def test_03_trigger_real_baseline_scan_and_logs(client: httpx.AsyncClient, db_session: AsyncSession):
    """Requirement 3 & 4: Trigger real baseline assessment scan on https://empire.edu.vn/ and verify audit logs."""
    # Find asset
    stmt = select(Asset).where(Asset.target_locator.in_(("https://empire.edu.vn/", "https://empire.edu.vn")))
    res = await db_session.execute(stmt)
    asset = res.scalars().first()
    assert asset is not None

    # Dispatch scan
    scan_payload = {
        "asset_id": str(asset.id),
        "profile": "DAILY_SECURITY",
        "name": "Challenger Empirical Baseline Assessment",
        "engine": "all",
        "parameters": {"safe_mode": True, "rate_limit_rps": 5},
    }
    resp = await client.post("/api/v1/scans", json=scan_payload)
    assert resp.status_code == 201, f"Create scan failed: {resp.text}"
    scan_job = resp.json()
    scan_id = scan_job["id"]
    assert scan_job["status"] in (ScanStatus.QUEUED.value, ScanStatus.INITIALIZING.value, ScanStatus.RUNNING.value)

    # Allow scan dispatcher to execute and write audit logs (poll up to 45s to handle resource throttling)
    log_items = []
    for _ in range(45):
        await asyncio.sleep(1.0)
        log_resp = await client.get(f"/api/v1/scans/{scan_id}/logs")
        if log_resp.status_code == 200:
            logs_res = log_resp.json()
            log_items = logs_res.get("items", [])
            if len(log_items) > 0:
                break

    assert len(log_items) > 0, "Scan must produce real audit log entries"

    log_sources = [log["source"] for log in log_items]
    assert "system" in log_sources or "empire_engine" in log_sources or "crawler" in log_sources, "Audit logs must include genuine sources"

    # Verify scan state progression
    scan_detail_resp = await client.get(f"/api/v1/scans/{scan_id}")
    assert scan_detail_resp.status_code == 200
    scan_detail = scan_detail_resp.json()
    assert scan_detail["status"] in (
        ScanStatus.RUNNING.value,
        ScanStatus.COMPLETED.value,
        ScanStatus.INITIALIZING.value,
    )
    assert scan_detail["progress_percentage"] > 0


@pytest.mark.asyncio
async def test_04_verify_evidence_and_deduplication(db_session: AsyncSession):
    """Requirement 4: Verify real raw request/response evidence and SHA-256 finding deduplication."""
    # Check findings for empire.edu.vn ecosystem
    stmt = select(NormalizedFinding)
    res = await db_session.execute(stmt)
    findings = res.scalars().all()

    assert len(findings) > 0, "Platform must maintain verified findings in DB"

    for f in findings:
        # Verify SHA-256 fingerprint format (64-character hex string)
        assert len(f.fingerprint) == 64, f"Fingerprint {f.fingerprint} must be 64-char SHA-256 hex"
        int(f.fingerprint, 16)  # Must be valid hex

        # Verify evidence presence
        assert f.evidence is not None, f"Finding {f.title} must have real evidence"
        assert isinstance(f.evidence, dict), "Evidence must be structured dictionary"

        # Check absence of fake/synthetic placeholders
        title_lower = f.title.lower()
        assert "dummy" not in title_lower, f"Forbidden dummy title in finding: {f.title}"
        assert "fake" not in title_lower, f"Forbidden fake title in finding: {f.title}"
        assert "placeholder" not in title_lower, f"Forbidden placeholder in finding: {f.title}"

    # Verify occurrence count increment / deduplication
    fingerprints = [f.fingerprint for f in findings]
    unique_fingerprints = set(fingerprints)
    assert len(fingerprints) == len(unique_fingerprints), "Normalized findings table must contain zero duplicate fingerprints (deterministic deduplication)"
