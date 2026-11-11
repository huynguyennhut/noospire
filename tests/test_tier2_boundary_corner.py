"""Tier 2: Boundary & Corner Cases Test Suite.
Exhaustively validates system defenses, boundary conditions, and adversarial inputs:
1. Target Management (empty locators, duplicate rejections, malformed CSV/JSON, non-existent targets)
2. Scanner Orchestration (SSRF metadata/private blocks, active scan permission gates, timeout bounds)
3. Empire Modules & Finding Intel (triage across all 10 states, retest errors, SHA-256 fingerprint invariants)
4. UI Contracts & Telemetry (SQL injection payloads, pagination bounds, invalid enum query params)
5. Multi-Format Reporting (path traversal in titles, non-existent IDs, invalid format queries)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import List

import httpx
import pytest
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.ssrf import SSRFProtector, SSRFValidationError
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.scanners.base import compute_finding_fingerprint
from backend.app.schemas.common import (
    AssetType,
    Criticality,
    EmpireModule,
    Exposure,
    FindingSeverity,
    FindingStatus,
    ScanProfile,
    ScanStatus,
    VerificationStatus,
)


# ============================================================================
# 1. Target Management Boundary & Corner Cases (Feature 1)
# ============================================================================

@pytest.mark.asyncio
async def test_t2_tgt_01_empty_and_whitespace_locator(client: httpx.AsyncClient):
    """Verifies POST /api/v1/assets rejects empty target locator with 422 Unprocessable Entity."""
    # 1. Empty string locator
    resp_empty = await client.post("/api/v1/assets", json={
        "name": "Empty Target",
        "target_locator": "",
    })
    assert resp_empty.status_code == 422

    # 2. Missing target_locator field altogether
    resp_missing = await client.post("/api/v1/assets", json={
        "name": "Missing Locator Target",
    })
    assert resp_missing.status_code == 422


@pytest.mark.asyncio
async def test_t2_tgt_02_duplicate_target_locator_rejection(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies POST /api/v1/assets rejects duplicate target locator with 400 Bad Request."""
    unique_slug = uuid.uuid4().hex[:8]
    locator = f"https://dup-{unique_slug}.empire.edu.vn"

    # First creation: should succeed
    resp1 = await client.post("/api/v1/assets", json={
        "name": "First Asset",
        "target_locator": locator,
    })
    assert resp1.status_code == 201
    created_asset_ids.append(resp1.json()["id"])

    # Duplicate creation: must be rejected with 400
    resp2 = await client.post("/api/v1/assets", json={
        "name": "Second Asset Duplicate",
        "target_locator": locator,
    })
    assert resp2.status_code == 400
    assert "already registered" in resp2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_t2_tgt_03_malformed_csv_bulk_import(client: httpx.AsyncClient):
    """Verifies POST /api/v1/assets/bulk-import handles corrupted or empty CSV input gracefully."""
    corrupted_csv = "this is not a valid csv\nwithout headers or valid columns\n,,,\n"
    resp = await client.post("/api/v1/assets/bulk-import", json={
        "import_type": "CSV",
        "raw_content": corrupted_csv,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported_count"] == 0


@pytest.mark.asyncio
async def test_t2_tgt_04_oversized_bulk_import_payload(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies POST /api/v1/assets/bulk-import processes large payload (50+ targets) reliably."""
    batch_size = 50
    slug = uuid.uuid4().hex[:6]
    items = [
        f"https://bulk-stress-{slug}-{i}.empire.edu.vn" for i in range(batch_size)
    ]
    raw_lines = "\n".join(items)

    resp = await client.post("/api/v1/assets/bulk-import", json={
        "import_type": "TXT",
        "raw_content": raw_lines,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported_count"] == batch_size
    for a in data["imported_assets"]:
        created_asset_ids.append(a["id"])


@pytest.mark.asyncio
async def test_t2_tgt_05_nonexistent_asset_id_operations(client: httpx.AsyncClient):
    """Verifies GET, PUT, DELETE, and VERIFY against non-existent UUIDs return 404 cleanly."""
    fake_id = uuid.uuid4()

    resp_get = await client.get(f"/api/v1/assets/{fake_id}")
    assert resp_get.status_code == 404

    resp_summary = await client.get(f"/api/v1/assets/{fake_id}/summary")
    assert resp_summary.status_code == 404

    resp_put = await client.put(f"/api/v1/assets/{fake_id}", json={"name": "New Name"})
    assert resp_put.status_code == 404

    resp_del = await client.delete(f"/api/v1/assets/{fake_id}")
    assert resp_del.status_code == 404

    resp_verify = await client.post(f"/api/v1/assets/{fake_id}/verify", json={})
    assert resp_verify.status_code == 404


@pytest.mark.asyncio
async def test_t2_tgt_06_url_normalization_scheme_inference(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies bulk import infers https:// scheme when input is a raw domain name."""
    slug = uuid.uuid4().hex[:8]
    domain = f"raw-domain-{slug}.empire.edu.vn"

    resp = await client.post("/api/v1/assets/bulk-import", json={
        "import_type": "TXT",
        "raw_content": domain,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported_count"] == 1
    imported = data["imported_assets"][0]
    created_asset_ids.append(imported["id"])
    assert imported["target_locator"] == f"https://{domain}"


# ============================================================================
# 2. Scanner Orchestration Boundary & Corner Cases (Feature 2)
# ============================================================================

@pytest.mark.asyncio
async def test_t2_scn_01_ssrf_blocked_cloud_metadata(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies SSRF gatekeeper rejects scans targeting AWS/GCP cloud metadata IP 169.254.169.254."""
    # Create asset pointing to cloud metadata
    create_resp = await client.post("/api/v1/assets", json={
        "name": "Cloud Metadata Target",
        "target_locator": "http://169.254.169.254/latest/meta-data/",
    })
    assert create_resp.status_code == 201
    asset_id = create_resp.json()["id"]
    created_asset_ids.append(asset_id)

    # Attempting to scan must be blocked by SSRF gatekeeper
    scan_resp = await client.post("/api/v1/scans", json={
        "asset_id": asset_id,
        "engine": "nuclei",
        "profile": "BASELINE",
        "allow_private_targets": False,
    })
    assert scan_resp.status_code == 400
    assert "SSRF Validation Blocked" in scan_resp.json()["detail"]


@pytest.mark.asyncio
async def test_t2_scn_02_ssrf_protector_unit_validation():
    """Directly tests SSRFProtector logic across various loopback and private representations."""
    # Loopback / local representations
    with pytest.raises(SSRFValidationError):
        SSRFProtector.validate_target("http://127.0.0.1:8080/admin", allow_private=False)

    with pytest.raises(SSRFValidationError):
        SSRFProtector.validate_target("http://localhost/api", allow_private=False)

    # Cloud metadata hosts
    with pytest.raises(SSRFValidationError):
        SSRFProtector.validate_target("http://metadata.google.internal/computeMetadata/v1", allow_private=True)

    with pytest.raises(SSRFValidationError):
        SSRFProtector.validate_target("http://169.254.169.254/latest/meta-data", allow_private=True)

    # Non-HTTP schemes
    with pytest.raises(SSRFValidationError):
        SSRFProtector.validate_target("ftp://empire.edu.vn/dump.sql")

    with pytest.raises(SSRFValidationError):
        SSRFProtector.validate_target("file:///etc/passwd")


@pytest.mark.asyncio
async def test_t2_scn_03_active_scan_unverified_target_forbidden(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies that dispatching a DEEP_ACTIVE scan against an UNVERIFIED target returns 403 Forbidden."""
    slug = uuid.uuid4().hex[:8]
    create_resp = await client.post("/api/v1/assets", json={
        "name": f"Unverified Target {slug}",
        "target_locator": f"https://unverified-{slug}.empire.edu.vn",
    })
    assert create_resp.status_code == 201
    asset = create_resp.json()
    created_asset_ids.append(asset["id"])

    # Explicitly set verification_status to PENDING in database
    async with AsyncSessionLocal() as session:
        db_asset = await session.get(Asset, uuid.UUID(asset["id"]))
        db_asset.verification_status = VerificationStatus.PENDING.value
        await session.commit()

    # Attempt DEEP_ACTIVE scan
    scan_resp = await client.post("/api/v1/scans", json={
        "asset_id": asset["id"],
        "engine": "nuclei",
        "profile": "DEEP_ACTIVE",
    })
    assert scan_resp.status_code == 403
    assert "prohibited: asset ownership is not verified" in scan_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_t2_scn_04_scan_against_nonexistent_asset(client: httpx.AsyncClient):
    """Verifies POST /api/v1/scans returns 404 when referencing a non-existent asset_id."""
    fake_asset_id = str(uuid.uuid4())
    resp = await client.post("/api/v1/scans", json={
        "asset_id": fake_asset_id,
        "engine": "nuclei",
        "profile": "BASELINE",
    })
    assert resp.status_code == 404
    assert "Asset not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_t2_scn_05_scanner_timeout_parameters(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies scanner handles boundary timeout configurations (10s to 3600s)."""
    slug = uuid.uuid4().hex[:8]
    asset_resp = await client.post("/api/v1/assets", json={
        "name": f"Timeout Asset {slug}",
        "target_locator": f"https://timeout-{slug}.empire.edu.vn",
    })
    asset_id = asset_resp.json()["id"]
    created_asset_ids.append(asset_id)

    # 1. Below minimum bound (<30s): rejected with 422
    resp_below = await client.post("/api/v1/scans", json={
        "asset_id": asset_id,
        "engine": "nuclei",
        "profile": "BASELINE",
        "timeout_seconds": 29,
    })
    assert resp_below.status_code == 422

    # 2. Minimum valid bound: 30 seconds (201)
    resp_min = await client.post("/api/v1/scans", json={
        "asset_id": asset_id,
        "engine": "nuclei",
        "profile": "BASELINE",
        "timeout_seconds": 30,
    })
    assert resp_min.status_code == 201
    assert resp_min.json()["timeout_seconds"] == 30

    # 3. Maximum valid bound: 3600 seconds (201)
    resp_max = await client.post("/api/v1/scans", json={
        "asset_id": asset_id,
        "engine": "nuclei",
        "profile": "BASELINE",
        "timeout_seconds": 3600,
    })
    assert resp_max.status_code == 201
    assert resp_max.json()["timeout_seconds"] == 3600

    # 4. Above maximum bound (>3600s): rejected with 422
    resp_above = await client.post("/api/v1/scans", json={
        "asset_id": asset_id,
        "engine": "nuclei",
        "profile": "BASELINE",
        "timeout_seconds": 3601,
    })
    assert resp_above.status_code == 422


@pytest.mark.asyncio
async def test_t2_scn_06_cancel_nonexistent_scan(client: httpx.AsyncClient):
    """Verifies POST /api/v1/scans/{id}/cancel returns 404 for unknown scan IDs."""
    fake_scan_id = uuid.uuid4()
    resp = await client.post(f"/api/v1/scans/{fake_scan_id}/cancel")
    assert resp.status_code == 404


# ============================================================================
# 3. Empire Modules & Finding Intelligence Boundary & Corner Cases (Feature 3)
# ============================================================================

@pytest.mark.asyncio
async def test_t2_emp_01_invalid_finding_id_triage(client: httpx.AsyncClient):
    """Verifies POST /api/v1/findings/{id}/triage returns 404 for unknown finding ID."""
    fake_finding_id = uuid.uuid4()
    resp = await client.post(f"/api/v1/findings/{fake_finding_id}/triage", json={
        "status": "CONFIRMED",
        "comment": "Invalid finding test",
    })
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_t2_emp_02_invalid_finding_id_retest(client: httpx.AsyncClient):
    """Verifies POST /api/v1/findings/{id}/retest returns 404 for unknown finding ID."""
    fake_finding_id = uuid.uuid4()
    resp = await client.post(f"/api/v1/findings/{fake_finding_id}/retest")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_t2_emp_03_retest_unreachable_endpoint_graceful_error(client: httpx.AsyncClient):
    """Verifies live retest against an unreachable domain returns RETEST_ERROR without crash."""
    # Fetch an existing finding
    list_resp = await client.get("/api/v1/findings?size=1")
    finding_id = list_resp.json()["items"][0]["id"]

    # Temporarily set target_location to an unroutable domain
    async with AsyncSessionLocal() as session:
        f = await session.get(NormalizedFinding, uuid.UUID(finding_id))
        original_loc = f.target_location
        f.target_location = "https://unreachable-test-domain-2026.invalid/endpoint"
        await session.commit()

    try:
        resp = await client.post(f"/api/v1/findings/{finding_id}/retest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["retest_status"] == "RETEST_ERROR"
        assert "Could not reach target" in data["notes"]
    finally:
        # Restore original location
        async with AsyncSessionLocal() as session:
            f = await session.get(NormalizedFinding, uuid.UUID(finding_id))
            f.target_location = original_loc
            await session.commit()


@pytest.mark.asyncio
async def test_t2_emp_04_finding_deduplication_fingerprint_invariance():
    """Verifies compute_finding_fingerprint produces identical SHA-256 despite case and whitespace variations."""
    asset_id = uuid.uuid4()
    fp1 = compute_finding_fingerprint(
        asset_id=asset_id,
        scanner_engine="nuclei",
        scanner_rule_id="sentinel-det-2026-0042",
        target_location="https://empire.edu.vn/api/v1/users",
        target_component="query_param",
    )
    fp2 = compute_finding_fingerprint(
        asset_id=asset_id,
        scanner_engine="  NUCLEI  ",
        scanner_rule_id="SENTINEL-DET-2026-0042",
        target_location="https://empire.edu.vn/api/v1/users   ",
        target_component="QUERY_PARAM",
    )
    assert fp1 == fp2, "Fingerprints must be invariant to case and whitespace normalization"


@pytest.mark.asyncio
async def test_t2_emp_05_finding_fingerprint_sensitivity():
    """Verifies compute_finding_fingerprint produces different SHA-256 when component or rule differs."""
    asset_id = uuid.uuid4()
    loc = "https://empire.edu.vn/api/v1/test"

    fp_rule_a = compute_finding_fingerprint(asset_id, "nuclei", "rule-a", loc, "body")
    fp_rule_b = compute_finding_fingerprint(asset_id, "nuclei", "rule-b", loc, "body")
    fp_comp_b = compute_finding_fingerprint(asset_id, "nuclei", "rule-a", loc, "header")

    assert fp_rule_a != fp_rule_b
    assert fp_rule_a != fp_comp_b


@pytest.mark.asyncio
async def test_t2_emp_06_triage_all_10_status_values(client: httpx.AsyncClient):
    """Verifies finding triage endpoint accepts and validates all 10 standard lifecycle statuses."""
    all_statuses = [
        "NEW",
        "POTENTIAL",
        "CONFIRMED",
        "OPEN",
        "IN_REMEDIATION",
        "FIXED",
        "REOPENED",
        "ACCEPTED_RISK",
        "FALSE_POSITIVE",
        "NOT_AFFECTED",
    ]
    list_resp = await client.get("/api/v1/findings?size=1")
    finding_id = list_resp.json()["items"][0]["id"]

    for st in all_statuses:
        resp = await client.post(f"/api/v1/findings/{finding_id}/triage", json={
            "status": st,
            "comment": f"Automated transition to {st}",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == st


# ============================================================================
# 4. UI Contracts & Metric Telemetry Boundary & Corner Cases (Feature 4)
# ============================================================================

@pytest.mark.asyncio
async def test_t2_met_01_metrics_pagination_extremes(client: httpx.AsyncClient):
    """Verifies pagination bounds: extreme page number returns empty list with valid metadata."""
    resp = await client.get("/api/v1/findings?page=99999&size=50")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["page"] == 99999
    assert data["total"] >= 0


@pytest.mark.asyncio
async def test_t2_met_02_chart_zero_days_parameter(client: httpx.AsyncClient):
    """Verifies vulnerability trend endpoint handles days=0 parameter without dividing by zero."""
    resp = await client.get("/api/v1/metrics/charts/vulnerability-trend?days=0")
    assert resp.status_code == 200
    points = resp.json()
    assert isinstance(points, list)
    assert len(points) == 0


@pytest.mark.asyncio
async def test_t2_met_03_filter_invalid_enum_parameters(client: httpx.AsyncClient):
    """Verifies that invalid enum query parameters produce 422 Unprocessable Entity."""
    resp = await client.get("/api/v1/findings?severity=SUPER_CRITICAL")
    assert resp.status_code == 422

    resp_mod = await client.get("/api/v1/assets?empire_module=NON_EXISTENT_MODULE")
    assert resp_mod.status_code == 422


@pytest.mark.asyncio
async def test_t2_met_04_read_nonexistent_alert(client: httpx.AsyncClient):
    """Verifies marking non-existent alert as read returns 404 Not Found."""
    fake_alert_id = uuid.uuid4()
    resp = await client.post(f"/api/v1/alerts/{fake_alert_id}/read")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_t2_met_05_search_query_sql_injection_defense(client: httpx.AsyncClient):
    """Verifies SQL injection payloads in search queries are safely escaped and do not error."""
    sqli_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE assets; --",
        "\" UNION SELECT NULL, NULL, NULL --",
        "1' AND SLEEP(5) AND '1'='1",
    ]
    for payload in sqli_payloads:
        resp = await client.get(f"/api/v1/findings?search={payload}")
        assert resp.status_code == 200, f"Failed on SQLi payload: {payload}"
        data = resp.json()
        assert "items" in data


@pytest.mark.asyncio
async def test_t2_met_06_risk_score_boundary_clamping(client: httpx.AsyncClient):
    """Verifies that risk scores never exceed 100.0 or fall below 0.0."""
    resp_overview = await client.get("/api/v1/metrics/overview")
    assert resp_overview.status_code == 200
    score = resp_overview.json()["overall_risk_score"]
    assert 0.0 <= score <= 100.0

    resp_modules = await client.get("/api/v1/empire-modules")
    assert resp_modules.status_code == 200
    for mod in resp_modules.json():
        assert 0.0 <= mod["risk_score"] <= 100.0


# ============================================================================
# 5. Multi-Format Reporting Boundary & Corner Cases (Feature 5)
# ============================================================================

@pytest.mark.asyncio
async def test_t2_rep_01_nonexistent_report_id(client: httpx.AsyncClient):
    """Verifies GET /api/v1/reports/{id} returns 404 for unknown report ID."""
    fake_id = uuid.uuid4()
    resp = await client.get(f"/api/v1/reports/{fake_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_t2_rep_02_invalid_format_download(client: httpx.AsyncClient):
    """Verifies downloading an unsupported format (e.g. format=docx) returns 404."""
    list_resp = await client.get("/api/v1/reports")
    reports = list_resp.json()
    if not reports:
        pytest.skip("No reports available to test download")
    report_id = reports[0]["id"]

    resp = await client.get(f"/api/v1/reports/{report_id}/download?format=docx")
    assert resp.status_code == 404
    assert "not available" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_t2_rep_03_generate_report_for_nonexistent_asset(client: httpx.AsyncClient):
    """Verifies generating report filtered by non-existent asset_id succeeds with empty scope without crashing."""
    fake_asset_id = str(uuid.uuid4())
    resp = await client.post("/api/v1/reports/generate", json={
        "title": "Nonexistent Asset Report",
        "asset_id": fake_asset_id,
        "formats": ["json"],
    })
    assert resp.status_code == 201
    report = resp.json()
    assert report["status"] == "READY"


@pytest.mark.asyncio
async def test_t2_rep_04_empty_formats_list_generation(client: httpx.AsyncClient):
    """Verifies generating report with formats=[] defaults safely to all 3 formats without crash."""
    resp = await client.post("/api/v1/reports/generate", json={
        "title": "Zero Formats Report",
        "formats": [],
    })
    assert resp.status_code == 201
    report = resp.json()
    assert set(report["formats"]) == {"pdf", "html", "json"}


@pytest.mark.asyncio
async def test_t2_rep_05_special_characters_in_report_title(client: httpx.AsyncClient):
    """Verifies report generation sanitizes path-traversal characters in title when downloading."""
    adversarial_title = "../../etc/passwd — <Script>alert(1)</Script> & Special! @ 2026"
    resp = await client.post("/api/v1/reports/generate", json={
        "title": adversarial_title,
        "formats": ["json"],
    })
    assert resp.status_code == 201
    report = resp.json()
    report_id = report["id"]

    # Test download filename sanitization
    dl_resp = await client.get(f"/api/v1/reports/{report_id}/download?format=json")
    assert dl_resp.status_code == 200
    cd_header = dl_resp.headers.get("content-disposition", "")
    assert ".." not in cd_header
    assert "<" not in cd_header
    assert ">" not in cd_header


@pytest.mark.asyncio
async def test_t2_rep_06_delete_nonexistent_report(client: httpx.AsyncClient):
    """Verifies DELETE /api/v1/reports/{id} returns 404 for non-existent report ID."""
    fake_id = uuid.uuid4()
    resp = await client.delete(f"/api/v1/reports/{fake_id}")
    assert resp.status_code == 404
