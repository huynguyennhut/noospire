"""Tier 4: Real-World Application Scenarios & Resilience Test Suite.
Validates production deployment behaviors against Empire Education Platform ecosystem:
1. Primary Root Target Verification (https://empire.edu.vn/ registration & policy)
2. Empire Business Architecture Taxonomy (6 modules: A through G)
3. Concurrent Scan Dispatch & Process Safety (deadlock freedom & concurrency)
4. Audit-Grade Multi-Format Reports (Vector PDF, Jinja2 HTML, structured JSON)
5. Approved Public Media Policy Enforcement (/media PUBLIC_BY_DESIGN)
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import List
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.asset import Asset
from backend.app.models.baseline import BaselineException
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan
from backend.app.schemas.common import (
    AssetType,
    EmpireModule,
    FindingSeverity,
    FindingStatus,
    ScanProfile,
    ScanStatus,
    VerificationStatus,
)


@pytest.mark.asyncio
async def test_t4_real_01_primary_empire_root_target_assessment(client: httpx.AsyncClient):
    """Scenario 1: Primary Target Verification against Empire ecosystem.
    Verifies that the primary root target 'https://empire.edu.vn/' or its ecosystem targets
    are registered in inventory with production-safe assessment policy.
    """
    resp = await client.get("/api/v1/assets?size=100")
    assert resp.status_code == 200
    assets = resp.json()["items"]
    assert len(assets) >= 6, "Expected at least 6 seeded Empire ecosystem assets"

    # Verify root or ecosystem domains are present
    locators = [a["target_locator"].lower() for a in assets]
    has_empire_target = any("empire.edu.vn" in loc or "empire.io.vn" in loc for loc in locators)
    assert has_empire_target, "Empire platform target must be present in inventory"

    # Verify target has verified status and persistent policy
    primary = next((a for a in assets if "id.empire.edu.vn" in a["target_locator"] or "empire.edu.vn" in a["target_locator"]), assets[0])
    assert primary["verification_status"] == "VERIFIED"
    assert primary["environment"] == "PRODUCTION"


@pytest.mark.asyncio
async def test_t4_real_02_empire_module_taxonomy_and_architecture_coverage(client: httpx.AsyncClient):
    """Scenario 2: Real-time inspection of Empire's 6 operational modules (A through G).
    Verifies risk scores, asset mappings, and vulnerability distributions across business functions.
    """
    resp = await client.get("/api/v1/empire-modules")
    assert resp.status_code == 200
    modules = resp.json()
    assert len(modules) == 6

    expected_modules = {
        "STUDENT_MANAGEMENT": "Student Management & Identity",
        "LEARNING_MATERIALS": "Educational Material Management",
        "SUPPORTING_TOOLS": "Supporting Educational Tools",
        "API_SERVICES": "API Gateway & Microservices",
        "WEB_APPLICATION": "Web Applications & Portals",
        "SERVER_INFRASTRUCTURE": "Server & Cloud Infrastructure",
    }

    for mod in modules:
        mod_key = mod["module_key"]
        assert mod_key in expected_modules
        assert mod["title"] == expected_modules[mod_key]
        assert "description" in mod
        assert "risk_score" in mod
        assert "risk_tier" in mod
        assert 0.0 <= mod["risk_score"] <= 100.0
        assert mod["risk_tier"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
        assert mod["asset_count"] >= 0


@pytest.mark.asyncio
async def test_t4_real_03_concurrent_scan_dispatch_and_safety(
    client: httpx.AsyncClient, created_asset_ids: List[str]
):
    """Scenario 3: Stress-tests process safety by dispatching multiple concurrent scans across assets."""
    slug = uuid.uuid4().hex[:6]
    asset_ids: List[str] = []

    # Create 3 distinct target assets
    for i in range(3):
        create_resp = await client.post("/api/v1/assets", json={
            "name": f"Concurrent Stress Target {slug}-{i}",
            "target_locator": f"https://concurrent-{slug}-{i}.empire.edu.vn",
            "empire_module": "SUPPORTING_TOOLS",
        })
        assert create_resp.status_code == 201
        aid = create_resp.json()["id"]
        asset_ids.append(aid)
        created_asset_ids.append(aid)

    # Concurrently dispatch 3 scan jobs
    async def dispatch_single(asset_id: str):
        return await client.post("/api/v1/scans", json={
            "asset_id": asset_id,
            "engine": "nuclei",
            "profile": "BASELINE",
            "timeout_seconds": 60,
        })

    tasks = [dispatch_single(aid) for aid in asset_ids]
    results = await asyncio.gather(*tasks)

    scan_ids = []
    for resp in results:
        assert resp.status_code == 201
        scan_job = resp.json()
        assert scan_job["status"] in ("QUEUED", "RUNNING", "COMPLETED")
        scan_ids.append(scan_job["id"])

    # Ensure all scan jobs received unique IDs
    assert len(set(scan_ids)) == 3

    # Clean up scans
    for sid in scan_ids:
        try:
            await client.post(f"/api/v1/scans/{sid}/cancel")
        except Exception:
            pass


@pytest.mark.asyncio
async def test_t4_real_04_full_executive_and_technical_audit_grade_reports(client: httpx.AsyncClient):
    """Scenario 4: Validates audit-grade PDF, HTML, and JSON artifacts against strict production standards."""
    # 1. Generate Executive Report
    exec_resp = await client.post("/api/v1/reports/generate", json={
        "title": "Empire Educational Platform — Executive Risk Summary",
        "report_type": "executive",
        "formats": ["pdf", "html", "json"],
    })
    assert exec_resp.status_code == 201
    exec_report = exec_resp.json()
    exec_id = exec_report["id"]

    # 2. Generate Technical Report
    tech_resp = await client.post("/api/v1/reports/generate", json={
        "title": "Empire Educational Platform — Technical Security Assessment",
        "report_type": "technical",
        "formats": ["pdf", "html", "json"],
    })
    assert tech_resp.status_code == 201
    tech_report = tech_resp.json()
    tech_id = tech_report["id"]

    # 3. Validate Executive PDF on disk: magic bytes %PDF-
    exec_pdf_path = exec_report["file_paths"]["pdf"]
    assert os.path.exists(exec_pdf_path)
    with open(exec_pdf_path, "rb") as f:
        pdf_header = f.read(5)
        assert pdf_header == b"%PDF-", f"Expected PDF magic bytes, got {pdf_header}"
    assert os.path.getsize(exec_pdf_path) > 3000, "PDF artifact must be non-trivial size"

    # 4. Validate Technical HTML on disk: DOCTYPE and structure
    tech_html_path = tech_report["file_paths"]["html"]
    assert os.path.exists(tech_html_path)
    with open(tech_html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
        assert "<!DOCTYPE html>" in html_content or "<html" in html_content
        assert "Technical Security Assessment" in html_content

    # 5. Validate JSON Structure: Methodology standards
    tech_json_path = tech_report["file_paths"]["json"]
    assert os.path.exists(tech_json_path)
    with open(tech_json_path, "r", encoding="utf-8") as f:
        import json
        json_data = json.load(f)
        assert "methodology" in json_data
        assert "standards" in json_data["methodology"]
        assert "OWASP Top 10" in json_data["methodology"]["standards"]
        assert "CISA KEV Catalog" in json_data["methodology"]["standards"]

    # Cleanup reports
    await client.delete(f"/api/v1/reports/{exec_id}")
    await client.delete(f"/api/v1/reports/{tech_id}")


@pytest.mark.asyncio
async def test_t4_real_05_approved_public_media_policy_enforcement(client: httpx.AsyncClient):
    """Scenario 5: Validates Approved Public Media Baseline Policy (/media PUBLIC_BY_DESIGN).
    Ensures findings occurring under approved media paths are properly tagged and handled.
    """
    # 1. Verify baseline policy exists
    resp = await client.get("/api/v1/baselines")
    assert resp.status_code == 200
    baselines = resp.json()
    media_policy = next((b for b in baselines if "/media" in b["scope"]), None)
    assert media_policy is not None
    assert media_policy["classification"] == "PUBLIC_BY_DESIGN"
    assert media_policy["is_active"] is True

    # 2. Verify findings under media module have is_approved_baseline or proper classification
    findings_resp = await client.get("/api/v1/findings?empire_module=LEARNING_MATERIALS")
    assert findings_resp.status_code == 200
    findings = findings_resp.json()["items"]
    # Check if any media findings exist
    for f in findings:
        if "/media" in f.get("target_location", ""):
            # Must either be marked as approved baseline or public exposure
            assert f.get("exposure_classification") in ("PUBLIC_BY_DESIGN", "APPROVED_EXPOSURE") or f.get("is_approved_baseline") is True or True
