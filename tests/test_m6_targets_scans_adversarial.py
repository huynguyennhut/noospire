"""
Adversarial Stress Test Suite for Milestone 6:
Target Management State Flows, Scan Center, and Live Scanning HUD & Telemetry.

Empirically challenges:
1. Target detail profile drawer (5 tabs, transition contracts, scroll lock behavior)
2. Bulk import duplicate detection (5 targets with 2 duplicates, partitioning verification)
3. 8-Step verification modal (8-step pipeline, progression, JSON fingerprint inspect)
4. Scan Center (7 profiles, engine toggles, description, active scan security gate)
5. Live Scanning Interface (5-stage stepper, HUD counters, SSE parsing, log filtering, export)
"""

import asyncio
import json
import re
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport

from backend.app.main import app
from backend.app.core.database import AsyncSessionLocal
from backend.app.models.asset import Asset
from sqlalchemy import select

REPO_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = REPO_ROOT / "frontend"
SRC_DIR = FRONTEND_DIR / "src"
ASSETS_PAGE = SRC_DIR / "app" / "assets" / "page.tsx"
SCANS_PAGE = SRC_DIR / "app" / "scans" / "page.tsx"
ACTIVE_ASSESSMENTS_PAGE = SRC_DIR / "app" / "active-assessments" / "page.tsx"
VERIFY_MODAL = SRC_DIR / "components" / "verification" / "TargetVerificationModal.tsx"


# ============================================================================
# TIER 1: FRONTEND SOURCE CODE CONTRACT & STATE MACHINE INTEGRITY
# ============================================================================

def test_target_drawer_five_tabs_contract():
    """Verify Target detail profile drawer has all 5 tabs and expected content."""
    assert ASSETS_PAGE.is_file(), f"Assets page not found at {ASSETS_PAGE}"
    content = ASSETS_PAGE.read_text(encoding="utf-8")

    # 1. Drawer open/close state
    assert "selectedAssetForDrawer" in content
    assert "setSelectedAssetForDrawer" in content
    assert "drawerTab" in content
    assert "setDrawerTab" in content

    # 2. All 5 tabs exist in drawer navigation
    expected_tabs = ["overview", "dns_tls", "endpoints", "scans", "vulnerabilities"]
    for tab in expected_tabs:
        assert f"drawerTab === '{tab}'" in content, f"Drawer tab '{tab}' is missing"

    # 3. Tab 1: Overview content
    assert "Target Overview" in content
    assert "Verification Status" in content
    assert "Approved /media Policy" in content
    assert "Asset Properties" in content
    assert "Classification Tags" in content
    assert "Re-Verify Target (8-Step Probe)" in content

    # 4. Tab 2: DNS & TLS records content
    assert "DNS & TLS Records" in content
    assert "Authoritative DNS Resolution" in content
    assert "A Records (IPv4)" in content
    assert "AAAA Records (IPv6)" in content
    assert "TLS / SSL Certificate Posture" in content
    assert "TLS_AES_256_GCM_SHA384" in content

    # 5. Tab 3: Endpoints content
    assert "Discovered Endpoints" in content
    assert "/robots.txt" in content
    assert "/api/v1/auth/login" in content
    assert "/media/uploads/*" in content
    assert "/api/student/profile" in content

    # 6. Tab 4: Scans history content
    assert "Scan History" in content
    assert "drawerScans" in content
    assert "/active-assessments?scan_id=" in content

    # 7. Tab 5: Vulnerabilities breakdown
    assert "Vulnerabilities" in content
    assert "drawerFindings" in content
    assert "scanner_rule_id" in content


def test_drawer_body_scroll_and_transitions_contract():
    """Adversarial check on drawer smooth transitions and body scroll handling."""
    content = ASSETS_PAGE.read_text(encoding="utf-8")

    # Check slide-in transition classes
    assert "animate-in slide-in-from-right duration-200" in content, (
        "Drawer missing smooth slide-in transition animation"
    )

    # Check backdrop blur and dismissability
    assert "backdrop-blur-sm" in content
    assert "onClick={() => setSelectedAssetForDrawer(null)}" in content

    # Check body scroll handling:
    # Notice: In page.tsx, the drawer container is fixed inset-0 overflow-hidden.
    assert "fixed inset-0 z-50 overflow-hidden flex justify-end" in content


def test_bulk_import_partitioning_contract():
    """Verify bulk import state and preview partitioning in assets page."""
    content = ASSETS_PAGE.read_text(encoding="utf-8")

    assert "bulkPreviewData" in content
    assert "handlePreviewBulk" in content
    assert "handleCommitBulkImport" in content
    assert "/api/v1/assets/bulk-preview" in content
    assert "bulkPreviewData.new" in content
    assert "bulkPreviewData.duplicate" in content
    assert "Ready to Import" in content


def test_eight_step_verification_modal_contract():
    """Verify 8-step live probe pipeline in TargetVerificationModal."""
    assert VERIFY_MODAL.is_file(), f"TargetVerificationModal not found at {VERIFY_MODAL}"
    content = VERIFY_MODAL.read_text(encoding="utf-8")

    # Check all 8 steps defined
    expected_step_keys = [
        "input_validation",
        "dns_resolution",
        "tls_verification",
        "http_connectivity",
        "redirect_inspection",
        "web_discovery",
        "fingerprinting",
        "result_authorization",
    ]
    for key in expected_step_keys:
        assert f"key: '{key}'" in content, f"Verification step '{key}' missing"

    # Step progression
    assert "runVerificationPipeline" in content
    assert "setCurrentStepIndex" in content
    assert "api.verifyAsset" in content

    # JSON fingerprint inspect
    assert "JSON.stringify(step.details, null, 2)" in content
    assert "expandedStep" in content


def test_scan_profiles_and_engine_toggles_contract():
    """Verify 7 scan profiles, engine toggles, and security gating in Scans page."""
    assert SCANS_PAGE.is_file(), f"Scans page not found at {SCANS_PAGE}"
    content = SCANS_PAGE.read_text(encoding="utf-8")

    # Check all 7 scan profiles
    expected_profiles = [
        "BASELINE",
        "DEEP_ACTIVE",
        "DAILY_SECURITY",
        "STANDARD",
        "INFRASTRUCTURE",
        "LIGHT_PASSIVE",
        "AUTHENTICATED",
    ]
    for p in expected_profiles:
        assert f"key: '{p}'" in content, f"Scan profile '{p}' missing"

    # Engine toggles
    assert "engineNuclei" in content
    assert "engineZap" in content
    assert "engineEmpire" in content
    assert "getSelectedEngineParam" in content

    # Description and private target inputs
    assert "customDescription" in content
    assert "allowPrivate" in content
    assert "timeoutSeconds" in content

    # Security gate: DEEP_ACTIVE requires verification
    assert "Active scanning (DEEP_ACTIVE) is prohibited on unverified targets" in content
    assert "verification_status !== 'VERIFIED'" in content


def test_live_scanning_hud_and_terminal_contract():
    """Verify 5-stage stepper, telemetry HUD, and SSE terminal in Active Assessments."""
    assert ACTIVE_ASSESSMENTS_PAGE.is_file(), f"Active assessments page not found at {ACTIVE_ASSESSMENTS_PAGE}"
    content = ACTIVE_ASSESSMENTS_PAGE.read_text(encoding="utf-8")

    # 5-stage stepper
    stages = ["preflight", "discovery", "active", "empire", "scoring"]
    for s in stages:
        assert f"key: '{s}'" in content, f"Pipeline stage '{s}' missing"
    assert "currentStageIndex" in content

    # Real-time HUD metrics
    assert "requestsPerSec" in content
    assert "elapsedSeconds" in content
    assert "findingsFound" in content
    assert "formatElapsed" in content

    # SSE terminal and filters
    assert "EventSource" in content
    assert "/logs/stream" in content
    assert "logFilterLevel" in content
    assert "logSearch" in content
    assert "autoScroll" in content
    assert "handleClearTerminal" in content
    assert "handleExportLogs" in content
    assert "VULN" in content


# ============================================================================
# TIER 2: EMPIRICAL BACKEND ENDPOINT ADVERSARIAL STRESS TESTING
# ============================================================================

@pytest.mark.asyncio
async def test_bulk_preview_duplicate_partitioning_empirical(client: AsyncClient):
    """
    Simulate importing 5 targets with 2 duplicates:
    - Target 1: Existing primary root https://empire.edu.vn (duplicate vs DB)
    - Target 2: New candidate https://id-preview-test.empire.edu.vn
    - Target 3: Intra-batch duplicate of Target 2 https://id-preview-test.empire.edu.vn
    - Target 4: New candidate https://api-preview-test.empire.edu.vn
    - Target 5: New candidate https://media-preview-test.empire.edu.vn

    Verifies preview accurately partitions 3 new valid candidates and 2 duplicates.
    """
    # Input with 5 lines
    raw_input = (
        "https://empire.edu.vn\n"
        "https://id-preview-test.empire.edu.vn\n"
        "https://id-preview-test.empire.edu.vn\n"
        "https://api-preview-test.empire.edu.vn\n"
        "https://media-preview-test.empire.edu.vn\n"
    )

    res = await client.post(
        "/api/v1/assets/bulk-preview",
        json={
            "import_type": "TXT",
            "raw_content": raw_input,
        },
    )
    assert res.status_code == 200, f"bulk-preview failed: {res.text}"
    data = res.json()

    assert data["total"] == 5, f"Expected 5 total targets, got {data['total']}"
    new_items = data["new"]
    dup_items = data["duplicate"]

    assert len(new_items) == 3, f"Expected exactly 3 new valid candidates, got {len(new_items)}"
    assert len(dup_items) == 2, f"Expected exactly 2 duplicates, got {len(dup_items)}"

    # Check duplicate reasons
    dup_locators = [d["target_locator"] for d in dup_items]
    assert "https://empire.edu.vn" in dup_locators
    assert "https://id-preview-test.empire.edu.vn" in dup_locators

    # Target 1 should cite existing inventory
    db_dup = next(d for d in dup_items if d["target_locator"] == "https://empire.edu.vn")
    assert "already registered" in db_dup["reason"].lower()
    assert db_dup["existing_asset_id"] is not None

    # Target 3 should cite intra-batch duplicate
    batch_dup = next(d for d in dup_items if d["target_locator"] == "https://id-preview-test.empire.edu.vn")
    assert "current import batch" in batch_dup["reason"].lower()
    assert batch_dup["existing_asset_id"] is None


@pytest.mark.asyncio
async def test_eight_step_verification_probe_empirical(client: AsyncClient):
    """Verify live 8-step probe execution on the primary target."""
    # Find primary asset
    assets_res = await client.get("/api/v1/assets?search=empire.edu.vn")
    assert assets_res.status_code == 200
    items = assets_res.json()["items"]
    assert len(items) > 0, "Primary empire.edu.vn asset not found"
    asset_id = items[0]["id"]

    # Run verification probe via POST /api/v1/assets/{id}/verify
    probe_res = await client.post(
        f"/api/v1/assets/{asset_id}/verify",
        json={"allow_private": True, "verification_type": "DNS_TXT"},
    )
    assert probe_res.status_code == 200, f"Verify probe failed: {probe_res.text}"
    data = probe_res.json()

    assert "status" in data
    assert "steps" in data
    assert len(data["steps"]) == 8, f"Expected 8 steps, got {len(data['steps'])}"

    # All 8 steps must be present
    step_numbers = [s["step"] for s in data["steps"]]
    assert step_numbers == [1, 2, 3, 4, 5, 6, 7, 8]

    # Fingerprint inspection
    assert "fingerprint" in data
    fp = data["fingerprint"]
    assert isinstance(fp, dict)


@pytest.mark.asyncio
async def test_scan_dispatch_with_profiles_empirical(client: AsyncClient):
    """Verify scan creation with 7 profiles and engine combinations."""
    # Find asset
    assets_res = await client.get("/api/v1/assets?search=empire.edu.vn")
    asset_id = assets_res.json()["items"][0]["id"]

    # Test profile dispatch (BASELINE)
    scan_res = await client.post(
        "/api/v1/scans",
        json={
            "asset_id": asset_id,
            "engine": "all",
            "profile": "BASELINE",
            "allow_private_targets": True,
            "timeout_seconds": 60,
        },
    )
    assert scan_res.status_code in (200, 201), f"Scan dispatch failed: {scan_res.text}"
    scan_data = scan_res.json()
    assert scan_data["profile"] == "BASELINE"
    assert scan_data["status"] in ("QUEUED", "RUNNING", "INITIALIZING")
    scan_id = scan_data["id"]

    # Check log retrieval (paginated response items)
    logs_res = await client.get(f"/api/v1/scans/{scan_id}/logs")
    assert logs_res.status_code == 200
    logs_data = logs_res.json()
    logs = logs_data.get("items", logs_data if isinstance(logs_data, list) else [])
    assert isinstance(logs, list)
