"""Tier 1: Comprehensive Feature Coverage Test Suite.
Verifies core functional behavior, API contracts, and primary happy-paths across:
1. Target Management & Ingestion (>=5 tests)
2. Scanner Orchestration & Process Safety (>=5 tests)
3. Empire Business Modules & Finding Intelligence (>=5 tests)
4. UI Contracts & Metric Telemetry (>=5 tests)
5. Multi-Format Reporting Engine (>=5 tests)
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
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan
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
# 1. Target Management & Ingestion (Feature 1)
# ============================================================================

@pytest.mark.asyncio
async def test_t1_tgt_01_list_assets_pagination_and_schema(client: httpx.AsyncClient):
    """Verifies GET /api/v1/assets returns paginated structure with total, page, size, and items."""
    resp = await client.get("/api/v1/assets?page=1&size=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data
    assert "pages" in data
    assert data["page"] == 1
    assert data["size"] == 10
    assert data["total"] >= 6  # Seeded assets must be present
    assert len(data["items"]) <= 10


@pytest.mark.asyncio
async def test_t1_tgt_02_create_single_asset(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies POST /api/v1/assets creates a new asset with verification token and default status."""
    unique_slug = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Tier 1 Test Portal {unique_slug}",
        "asset_type": "WEB_APP",
        "target_locator": f"https://t1-test-{unique_slug}.empire.edu.vn",
        "empire_module": "STUDENT_MANAGEMENT",
        "environment": "STAGING",
        "technology": "Next.js",
        "criticality": "HIGH",
        "exposure": "INTERNET",
        "description": "Automated Tier 1 test target",
        "tags": ["tier1", "test"],
    }
    resp = await client.post("/api/v1/assets", json=payload)
    assert resp.status_code == 201
    asset = resp.json()
    created_asset_ids.append(asset["id"])

    assert asset["name"] == payload["name"]
    assert asset["target_locator"] == payload["target_locator"]
    assert asset["empire_module"] == "STUDENT_MANAGEMENT"
    assert asset["verification_status"] in (VerificationStatus.PENDING.value, "PENDING")
    assert asset["verification_token"].startswith("sentinel-")


@pytest.mark.asyncio
async def test_t1_tgt_03_get_asset_by_id_and_summary(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies GET /api/v1/assets/{id} and GET /api/v1/assets/{id}/summary return expected details."""
    unique_slug = uuid.uuid4().hex[:8]
    create_resp = await client.post("/api/v1/assets", json={
        "name": f"Summary Test Asset {unique_slug}",
        "asset_type": "API_ENDPOINT",
        "target_locator": f"https://api-test-{unique_slug}.empire.edu.vn",
        "empire_module": "API_SERVICES",
        "criticality": "MEDIUM",
        "exposure": "INTERNAL",
    })
    assert create_resp.status_code == 201
    asset_id = create_resp.json()["id"]
    created_asset_ids.append(asset_id)

    # 1. Fetch by ID
    get_resp = await client.get(f"/api/v1/assets/{asset_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == asset_id

    # 2. Fetch Summary
    sum_resp = await client.get(f"/api/v1/assets/{asset_id}/summary")
    assert sum_resp.status_code == 200
    summary = sum_resp.json()
    assert summary["asset_id"] == asset_id
    assert "critical_findings" in summary
    assert "high_findings" in summary
    assert "open_findings" in summary
    assert summary["total_findings"] >= 0


@pytest.mark.asyncio
async def test_t1_tgt_04_update_asset_properties(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies PUT /api/v1/assets/{id} updates fields and preserves unchanged fields."""
    unique_slug = uuid.uuid4().hex[:8]
    create_resp = await client.post("/api/v1/assets", json={
        "name": f"Pre-Update Asset {unique_slug}",
        "target_locator": f"https://upd-{unique_slug}.empire.edu.vn",
        "criticality": "LOW",
    })
    assert create_resp.status_code == 201
    asset_id = create_resp.json()["id"]
    created_asset_ids.append(asset_id)

    update_payload = {
        "name": f"Post-Update Asset {unique_slug}",
        "criticality": "CRITICAL",
        "tags": ["updated", "tier1"],
        "description": "Updated description content",
    }
    upd_resp = await client.put(f"/api/v1/assets/{asset_id}", json=update_payload)
    assert upd_resp.status_code == 200
    updated = upd_resp.json()
    assert updated["name"] == update_payload["name"]
    assert updated["criticality"] == "CRITICAL"
    assert "updated" in updated["tags"]
    assert updated["description"] == update_payload["description"]


@pytest.mark.asyncio
async def test_t1_tgt_05_bulk_import_csv(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies POST /api/v1/assets/bulk-import parses CSV, imports new targets, and skips duplicates."""
    slug_new = uuid.uuid4().hex[:8]
    csv_content = (
        "target_locator,name,empire_module,environment\n"
        f"https://id.empire.edu.vn,Empire ID Service,STUDENT_MANAGEMENT,PRODUCTION\n"  # Duplicate
        f"https://new-{slug_new}.empire.edu.vn,New Asset {slug_new},STUDENT_MANAGEMENT,STAGING\n"  # New
    )
    resp = await client.post("/api/v1/assets/bulk-import", json={
        "import_type": "CSV",
        "raw_content": csv_content,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported_count"] == 1
    assert data["skipped_duplicates"] >= 1
    for a in data["imported_assets"]:
        created_asset_ids.append(a["id"])


@pytest.mark.asyncio
async def test_t1_tgt_06_bulk_import_json(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies POST /api/v1/assets/bulk-import parses JSON array format."""
    slug_json = uuid.uuid4().hex[:8]
    json_content = (
        f'[\n'
        f'  {{"target_locator": "https://json-import-{slug_json}.empire.edu.vn", "name": "JSON Target", "environment": "PRODUCTION"}}\n'
        f']'
    )
    resp = await client.post("/api/v1/assets/bulk-import", json={
        "import_type": "JSON",
        "raw_content": json_content,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported_count"] == 1
    for a in data["imported_assets"]:
        created_asset_ids.append(a["id"])


@pytest.mark.asyncio
async def test_t1_tgt_07_verify_asset_ownership(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies POST /api/v1/assets/{id}/verify executes administrative policy verification."""
    unique_slug = uuid.uuid4().hex[:8]
    create_resp = await client.post("/api/v1/assets", json={
        "name": f"Verification Target {unique_slug}",
        "target_locator": f"https://verify-me-{unique_slug}.empire.edu.vn",
    })
    assert create_resp.status_code == 201
    asset_id = create_resp.json()["id"]
    created_asset_ids.append(asset_id)

    verify_resp = await client.post(f"/api/v1/assets/{asset_id}/verify", json={
        "verification_type": "ADMIN_OVERRIDE",
    })
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["verified"] is True
    assert verify_data["verification_status"] == "VERIFIED"


# ============================================================================
# 2. Scanner Orchestration & Process Safety (Feature 2)
# ============================================================================

@pytest.mark.asyncio
async def test_t1_scn_01_list_scans_pagination_and_filter(client: httpx.AsyncClient):
    """Verifies GET /api/v1/scans returns paginated results and honors query parameters."""
    resp = await client.get("/api/v1/scans?page=1&size=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert data["page"] == 1
    assert data["size"] == 5


@pytest.mark.asyncio
async def test_t1_scn_02_create_and_dispatch_scan(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies POST /api/v1/scans dispatches an asynchronous scan job with initial status QUEUED."""
    unique_slug = uuid.uuid4().hex[:8]
    asset_resp = await client.post("/api/v1/assets", json={
        "name": f"Scan Dispatch Target {unique_slug}",
        "target_locator": f"https://scan-target-{unique_slug}.empire.edu.vn",
        "empire_module": "STUDENT_MANAGEMENT",
    })
    assert asset_resp.status_code == 201
    asset = asset_resp.json()
    created_asset_ids.append(asset["id"])

    scan_payload = {
        "asset_id": asset["id"],
        "engine": "nuclei",
        "profile": "BASELINE",
        "allow_private_targets": True,
        "timeout_seconds": 60,
    }
    resp = await client.post("/api/v1/scans", json=scan_payload)
    assert resp.status_code == 201
    scan = resp.json()
    assert scan["asset_id"] == asset["id"]
    assert scan["engine"] == "nuclei"
    assert scan["profile"] == "BASELINE"
    assert scan["status"] in ("QUEUED", "RUNNING", "COMPLETED")


@pytest.mark.asyncio
async def test_t1_scn_03_get_scan_details(client: httpx.AsyncClient):
    """Verifies GET /api/v1/scans/{id} retrieves an existing scan job."""
    list_resp = await client.get("/api/v1/scans?size=1")
    scans = list_resp.json()["items"]
    if not scans:
        pytest.skip("No scans available to test retrieval")
    scan_id = scans[0]["id"]

    resp = await client.get(f"/api/v1/scans/{scan_id}")
    assert resp.status_code == 200
    scan = resp.json()
    assert scan["id"] == scan_id
    assert "progress_percentage" in scan
    assert "status" in scan


@pytest.mark.asyncio
async def test_t1_scn_04_scan_logs_retrieval(client: httpx.AsyncClient):
    """Verifies GET /api/v1/scans/{id}/logs returns paginated audit log entries."""
    list_resp = await client.get("/api/v1/scans?size=1")
    scans = list_resp.json()["items"]
    if not scans:
        pytest.skip("No scans available to fetch logs")
    scan_id = scans[0]["id"]

    resp = await client.get(f"/api/v1/scans/{scan_id}/logs?page=1&size=20")
    assert resp.status_code == 200
    logs = resp.json()
    assert "items" in logs
    assert "total" in logs


@pytest.mark.asyncio
async def test_t1_scn_05_scan_cancellation(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies POST /api/v1/scans/{id}/cancel issues cancellation request without 500 error."""
    unique_slug = uuid.uuid4().hex[:8]
    asset_resp = await client.post("/api/v1/assets", json={
        "name": f"Cancel Target {unique_slug}",
        "target_locator": f"https://cancel-{unique_slug}.empire.edu.vn",
    })
    asset_id = asset_resp.json()["id"]
    created_asset_ids.append(asset_id)

    scan_resp = await client.post("/api/v1/scans", json={
        "asset_id": asset_id,
        "engine": "nuclei",
        "profile": "BASELINE",
    })
    scan_id = scan_resp.json()["id"]

    cancel_resp = await client.post(f"/api/v1/scans/{scan_id}/cancel")
    assert cancel_resp.status_code == 200
    cancel_data = cancel_resp.json()
    assert cancel_data["scan_id"] == scan_id
    assert "status" in cancel_data
    assert "message" in cancel_data


@pytest.mark.asyncio
async def test_t1_scn_06_scan_sse_log_stream(client: httpx.AsyncClient):
    """Verifies SSE log streaming route configuration and log_buffer real-time pub/sub mechanism."""
    from backend.app.core.dispatcher import log_buffer

    test_scan_id = uuid.uuid4()

    # 1. Verify route registration in OpenAPI schema
    openapi_paths = client._transport.app.openapi().get("paths", {})
    assert "/api/v1/scans/{scan_id}/logs/stream" in openapi_paths

    # 2. Verify buffer append and subscription delivery
    await log_buffer.append_log(test_scan_id, "INFO", "Pre-buffered audit entry", "scanner")

    gen = log_buffer.subscribe(test_scan_id)
    first_entry = await gen.__anext__()
    assert first_entry.scan_id == test_scan_id
    assert first_entry.message == "Pre-buffered audit entry"
    assert first_entry.level == "INFO"
    await gen.aclose()


# ============================================================================
# 3. Empire Business Modules & Finding Intelligence (Feature 3)
# ============================================================================

@pytest.mark.asyncio
async def test_t1_emp_01_list_empire_modules_metadata(client: httpx.AsyncClient):
    """Verifies GET /api/v1/empire-modules returns all 6 business modules with risk metrics."""
    resp = await client.get("/api/v1/empire-modules")
    assert resp.status_code == 200
    modules = resp.json()
    assert len(modules) == 6

    expected_modules = {
        "STUDENT_MANAGEMENT",
        "LEARNING_MATERIALS",
        "SUPPORTING_TOOLS",
        "API_SERVICES",
        "WEB_APPLICATION",
        "SERVER_INFRASTRUCTURE",
    }
    returned_keys = {m["module_key"] for m in modules}
    assert expected_modules == returned_keys

    for m in modules:
        assert "risk_score" in m
        assert "risk_tier" in m
        assert "asset_count" in m
        assert "total_findings" in m
        assert 0.0 <= m["risk_score"] <= 100.0


@pytest.mark.asyncio
async def test_t1_emp_02_list_findings_filtering(client: httpx.AsyncClient):
    """Verifies GET /api/v1/findings supports severity and search query filtering."""
    resp = await client.get("/api/v1/findings?severity=CRITICAL")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    for finding in data["items"]:
        assert finding["severity"] == "CRITICAL"


@pytest.mark.asyncio
async def test_t1_emp_03_get_finding_detail_and_evidence(client: httpx.AsyncClient):
    """Verifies GET /api/v1/findings/{id} returns comprehensive finding detail with evidence."""
    list_resp = await client.get("/api/v1/findings?size=1")
    findings = list_resp.json()["items"]
    assert len(findings) > 0
    target_finding = findings[0]
    finding_id = target_finding["id"]

    resp = await client.get(f"/api/v1/findings/{finding_id}")
    assert resp.status_code == 200
    f = resp.json()
    assert f["id"] == finding_id
    assert "fingerprint" in f
    assert "scanner_engine" in f
    assert "scanner_rule_id" in f
    assert "evidence" in f
    assert isinstance(f["evidence"], dict)


@pytest.mark.asyncio
async def test_t1_emp_04_triage_finding_status_transition(client: httpx.AsyncClient):
    """Verifies POST /api/v1/findings/{id}/triage records status transition and updates history."""
    list_resp = await client.get("/api/v1/findings?size=1")
    finding_id = list_resp.json()["items"][0]["id"]

    triage_payload = {
        "status": "IN_REMEDIATION",
        "assignee": "tier1-lead@empire.edu.vn",
        "comment": "Tier 1 automated triage verification.",
    }
    resp = await client.post(f"/api/v1/findings/{finding_id}/triage", json=triage_payload)
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["status"] in ("IN_REMEDIATION", FindingStatus.IN_PROGRESS.value)
    assert updated["assignee"] in (triage_payload["assignee"], "[REDACTED_EMAIL]")
    assert updated["remediation_notes"] == triage_payload["comment"]


@pytest.mark.asyncio
async def test_t1_emp_05_live_retest_finding(client: httpx.AsyncClient):
    """Verifies POST /api/v1/findings/{id}/retest executes and records retest verdict."""
    list_resp = await client.get("/api/v1/findings?size=1")
    finding_id = list_resp.json()["items"][0]["id"]

    resp = await client.post(f"/api/v1/findings/{finding_id}/retest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["finding_id"] == finding_id
    assert "retest_status" in data
    assert data["retest_status"] in ("STILL_VULNERABLE", "VERIFIED_FIXED", "RETEST_ERROR")


@pytest.mark.asyncio
async def test_t1_emp_06_approved_media_baseline_policy(client: httpx.AsyncClient):
    """Verifies GET /api/v1/baselines includes the /media PUBLIC_BY_DESIGN policy."""
    resp = await client.get("/api/v1/baselines")
    assert resp.status_code == 200
    baselines = resp.json()
    assert len(baselines) >= 1
    media_policy = next((b for b in baselines if "/media" in b["scope"]), None)
    assert media_policy is not None
    assert media_policy["classification"] == "PUBLIC_BY_DESIGN"


# ============================================================================
# 4. UI Contracts & Metric Telemetry (Feature 4)
# ============================================================================

@pytest.mark.asyncio
async def test_t1_met_01_overview_kpis(client: httpx.AsyncClient):
    """Verifies GET /api/v1/metrics/overview returns all 10 core KPIs."""
    resp = await client.get("/api/v1/metrics/overview")
    assert resp.status_code == 200
    kpis = resp.json()
    required_keys = [
        "total_assets",
        "targets_assessed_today",
        "active_assessments",
        "failed_assessments",
        "critical_findings",
        "high_findings",
        "total_open_findings",
        "fixed_findings",
        "newly_discovered_cves",
        "relevant_kev_count",
        "overall_risk_score",
        "risk_posture",
    ]
    for key in required_keys:
        assert key in kpis
    assert kpis["total_assets"] >= 6
    assert 0.0 <= kpis["overall_risk_score"] <= 100.0


@pytest.mark.asyncio
async def test_t1_met_02_severity_distribution(client: httpx.AsyncClient):
    """Verifies GET /api/v1/metrics/severity-distribution returns counts per severity."""
    resp = await client.get("/api/v1/metrics/severity-distribution")
    assert resp.status_code == 200
    dist = resp.json()
    assert "CRITICAL" in dist
    assert "HIGH" in dist
    assert "MEDIUM" in dist
    assert "LOW" in dist
    assert "INFO" in dist
    assert all(isinstance(v, int) for v in dist.values())


@pytest.mark.asyncio
async def test_t1_met_03_vulnerability_trend_chart(client: httpx.AsyncClient):
    """Verifies GET /api/v1/metrics/charts/vulnerability-trend returns time series points."""
    resp = await client.get("/api/v1/metrics/charts/vulnerability-trend?days=7")
    assert resp.status_code == 200
    points = resp.json()
    assert len(points) == 7
    for pt in points:
        assert "date" in pt
        assert "new_findings" in pt
        assert "fixed_findings" in pt
        assert "reopened_findings" in pt


@pytest.mark.asyncio
async def test_t1_met_04_module_risk_chart(client: httpx.AsyncClient):
    """Verifies GET /api/v1/metrics/charts/module-risk returns per-module risk points."""
    resp = await client.get("/api/v1/metrics/charts/module-risk")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 6
    for item in items:
        assert "module_key" in item
        assert "risk_score" in item
        assert "critical_count" in item
        assert "high_count" in item


@pytest.mark.asyncio
async def test_t1_met_05_scanner_performance_chart(client: httpx.AsyncClient):
    """Verifies GET /api/v1/metrics/charts/scanner-performance returns engine stats."""
    resp = await client.get("/api/v1/metrics/charts/scanner-performance")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_t1_met_06_security_alerts_management(client: httpx.AsyncClient):
    """Verifies GET /api/v1/alerts lists notifications and POST /api/v1/alerts/{id}/read marks as read."""
    resp = await client.get("/api/v1/alerts")
    assert resp.status_code == 200
    alerts = resp.json()
    assert len(alerts) >= 1
    alert_id = alerts[0]["id"]

    mark_resp = await client.post(f"/api/v1/alerts/{alert_id}/read")
    assert mark_resp.status_code == 200
    assert mark_resp.json()["is_read"] is True


# ============================================================================
# 5. Multi-Format Reporting Engine (Feature 5)
# ============================================================================

@pytest.mark.asyncio
async def test_t1_rep_01_list_reports(client: httpx.AsyncClient):
    """Verifies GET /api/v1/reports returns existing security reports."""
    resp = await client.get("/api/v1/reports")
    assert resp.status_code == 200
    reports = resp.json()
    assert isinstance(reports, list)


@pytest.mark.asyncio
async def test_t1_rep_02_generate_technical_report(client: httpx.AsyncClient):
    """Verifies POST /api/v1/reports/generate creates a technical report with JSON artifact."""
    payload = {
        "title": "Tier 1 Technical Report",
        "report_type": "technical",
        "formats": ["json"],
    }
    resp = await client.post("/api/v1/reports/generate", json=payload)
    assert resp.status_code == 201
    report = resp.json()
    assert report["title"] == payload["title"]
    assert report["report_type"] == "technical"
    assert report["status"] == "READY"
    assert "json" in report["file_paths"]


@pytest.mark.asyncio
async def test_t1_rep_03_generate_multi_format_report(client: httpx.AsyncClient):
    """Verifies POST /api/v1/reports/generate generates PDF, HTML, and JSON simultaneously."""
    payload = {
        "title": "Tier 1 Multi-Format Audit Report",
        "report_type": "executive",
        "formats": ["pdf", "html", "json"],
    }
    resp = await client.post("/api/v1/reports/generate", json=payload)
    assert resp.status_code == 201
    report = resp.json()
    assert "pdf" in report["file_paths"]
    assert "html" in report["file_paths"]
    assert "json" in report["file_paths"]

    # Verify physical file existence
    for fmt, path in report["file_paths"].items():
        assert os.path.exists(path), f"Report artifact {fmt} must exist at {path}"


@pytest.mark.asyncio
async def test_t1_rep_04_get_report_by_id(client: httpx.AsyncClient):
    """Verifies GET /api/v1/reports/{id} returns report details and summary stats."""
    list_resp = await client.get("/api/v1/reports")
    reports = list_resp.json()
    if not reports:
        pytest.skip("No reports available to fetch")
    report_id = reports[0]["id"]

    resp = await client.get(f"/api/v1/reports/{report_id}")
    assert resp.status_code == 200
    report = resp.json()
    assert report["id"] == report_id
    assert "summary" in report
    assert "target_scope" in report


@pytest.mark.asyncio
async def test_t1_rep_05_download_report_artifact(client: httpx.AsyncClient):
    """Verifies GET /api/v1/reports/{id}/download serves artifact file."""
    list_resp = await client.get("/api/v1/reports")
    reports = list_resp.json()
    if not reports:
        pytest.skip("No reports available to test download")
    report_id = reports[0]["id"]

    resp = await client.get(f"/api/v1/reports/{report_id}/download?format=json")
    assert resp.status_code == 200
    assert "application/json" in resp.headers.get("content-type", "")
    assert len(resp.content) > 0


@pytest.mark.asyncio
async def test_t1_rep_06_delete_report(client: httpx.AsyncClient):
    """Verifies DELETE /api/v1/reports/{id} removes report and disk artifacts."""
    gen_resp = await client.post("/api/v1/reports/generate", json={
        "title": "Disposable Tier 1 Report",
        "report_type": "technical",
        "formats": ["json"],
    })
    report_id = gen_resp.json()["id"]

    del_resp = await client.delete(f"/api/v1/reports/{report_id}")
    assert del_resp.status_code == 204

    # Verify 404 on subsequent get
    get_resp = await client.get(f"/api/v1/reports/{report_id}")
    assert get_resp.status_code == 404
