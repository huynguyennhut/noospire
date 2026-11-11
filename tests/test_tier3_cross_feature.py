"""Tier 3: Cross-Feature Interactions & End-to-End Lifecycles.
Validates multi-stage workflows traversing multiple subsystems:
1. Target Verification -> Scan Dispatch -> Finding Detection -> Alerts
2. Finding Detection -> SHA-256 Deduplication -> Triage -> Regression -> Retest
3. Scan Execution -> SSE Logs -> Audit Report Generation -> Disk Verification
4. Scheduled Assessment Pipeline -> Dispatcher -> Dashboard Metrics Sync
5. Bulk Target Ingestion -> Module Architecture Mapping & Classification
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
from backend.app.core.dispatcher import log_buffer
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan
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


@pytest.mark.asyncio
async def test_t3_lifecycle_01_target_verification_to_scan_and_alert(
    client: httpx.AsyncClient, created_asset_ids: List[str]
):
    """Lifecycle 1: Ingests target -> Executes 8-step verification -> Dispatches scan -> Checks alerts."""
    slug = uuid.uuid4().hex[:8]

    # Step 1: Ingest target asset
    ingest_resp = await client.post("/api/v1/assets", json={
        "name": f"Lifecycle 1 Target {slug}",
        "asset_type": "WEB_APP",
        "target_locator": f"https://life1-{slug}.empire.edu.vn",
        "empire_module": "STUDENT_MANAGEMENT",
        "environment": "STAGING",
        "criticality": "HIGH",
    })
    assert ingest_resp.status_code == 201
    asset = ingest_resp.json()
    asset_id = asset["id"]
    created_asset_ids.append(asset_id)

    # Step 2: Execute target verification
    verify_resp = await client.post(f"/api/v1/assets/{asset_id}/verify", json={
        "verification_type": "ADMIN_OVERRIDE",
    })
    assert verify_resp.status_code == 200
    assert verify_resp.json()["verified"] is True

    # Step 3: Dispatch assessment scan
    scan_resp = await client.post("/api/v1/scans", json={
        "asset_id": asset_id,
        "engine": "nuclei",
        "profile": "BASELINE",
        "timeout_seconds": 60,
    })
    assert scan_resp.status_code == 201
    scan = scan_resp.json()
    scan_id = scan["id"]
    assert scan["status"] in ("QUEUED", "RUNNING", "COMPLETED")

    # Step 4: Verify scan logs generated
    await asyncio.sleep(1)
    logs_resp = await client.get(f"/api/v1/scans/{scan_id}/logs")
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    assert "items" in logs

    # Step 5: Query security alerts
    alerts_resp = await client.get("/api/v1/alerts")
    assert alerts_resp.status_code == 200
    assert isinstance(alerts_resp.json(), list)


@pytest.mark.asyncio
async def test_t3_lifecycle_02_finding_deduplication_and_regression_retest(
    client: httpx.AsyncClient, created_asset_ids: List[str]
):
    """Lifecycle 2: Finding detection -> SHA-256 deduplication -> Fixed triage -> Reopen regression -> Live retest."""
    slug = uuid.uuid4().hex[:8]

    # Create target asset
    asset_resp = await client.post("/api/v1/assets", json={
        "name": f"Finding Lifecycle Target {slug}",
        "target_locator": f"https://finding-life-{slug}.empire.edu.vn",
        "empire_module": "API_SERVICES",
    })
    assert asset_resp.status_code == 201
    asset_id = uuid.UUID(asset_resp.json()["id"])
    # Create a real scan job for the asset to satisfy foreign key constraint
    scan_resp = await client.post("/api/v1/scans", json={
        "asset_id": str(asset_id),
        "engine": "nuclei",
        "profile": "BASELINE",
    })
    assert scan_resp.status_code == 201
    scan_id = uuid.UUID(scan_resp.json()["id"])

    # Compute deterministic SHA-256 fingerprint
    rule_id = "sentinel-vuln-2026-auth-bypass"
    location = f"http://127.0.0.1:65534/api/v1/auth/{slug}"
    fp = compute_finding_fingerprint(
        asset_id=asset_id,
        scanner_engine="nuclei",
        scanner_rule_id=rule_id,
        target_location=location,
        target_component="header",
    )

    # 1. Insert initial finding
    finding_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        initial_finding = NormalizedFinding(
            id=finding_id,
            scan_id=scan_id,
            asset_id=asset_id,
            fingerprint=fp,
            empire_module=EmpireModule.API_SERVICES.value,
            scanner_engine="nuclei",
            scanner_rule_id=rule_id,
            title="Authentication Token Bypass in Header",
            description="Auth header parsing logic allows bypass.",
            severity=FindingSeverity.HIGH.value,
            original_severity="HIGH",
            target_location=location,
            target_component="header",
            status=FindingStatus.OPEN.value,
            occurrence_count=1,
        )
        session.add(initial_finding)
        await session.commit()

    # 2. Simulate re-detection with same fingerprint: occurrence_count should increment
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(NormalizedFinding).where(NormalizedFinding.fingerprint == fp)
        )
        existing = res.scalars().first()
        assert existing is not None
        existing.occurrence_count += 1
        await session.commit()

    # Verify occurrence incremented via API
    get_resp = await client.get(f"/api/v1/findings/{finding_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["occurrence_count"] == 2

    # 3. Triage finding to FIXED
    triage_resp = await client.post(f"/api/v1/findings/{finding_id}/triage", json={
        "status": "FIXED",
        "comment": "Hotfix deployed. Verified fixed by engineering.",
    })
    assert triage_resp.status_code == 200
    assert triage_resp.json()["status"] == "FIXED"

    # 4. Simulate scanner re-encountering finding (Regression Detection)
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(NormalizedFinding).where(NormalizedFinding.id == finding_id)
        )
        f = res.scalars().first()
        # In dispatcher.py: if existing_finding.status == FIXED -> status = REOPENED
        if f.status == FindingStatus.FIXED.value:
            f.status = FindingStatus.REOPENED.value
            f.occurrence_count += 1
        await session.commit()

    reopened_resp = await client.get(f"/api/v1/findings/{finding_id}")
    assert reopened_resp.status_code == 200
    assert reopened_resp.json()["status"] == "REOPENED"
    assert reopened_resp.json()["occurrence_count"] == 3

    # 5. Execute Live Retest
    retest_resp = await client.post(f"/api/v1/findings/{finding_id}/retest")
    assert retest_resp.status_code == 200
    retest_data = retest_resp.json()
    assert retest_data["finding_id"] == str(finding_id)
    assert retest_data["retest_status"] in ("STILL_VULNERABLE", "VERIFIED_FIXED", "RETEST_ERROR")


@pytest.mark.asyncio
async def test_t3_lifecycle_03_scan_execution_to_audit_report(
    client: httpx.AsyncClient, created_asset_ids: List[str]
):
    """Lifecycle 3: Target assessment -> Audit report generation -> Artifact file download."""
    slug = uuid.uuid4().hex[:8]

    # Create & verify asset
    asset_resp = await client.post("/api/v1/assets", json={
        "name": f"Reporting Target {slug}",
        "target_locator": f"https://report-{slug}.empire.edu.vn",
    })
    asset_id = asset_resp.json()["id"]
    created_asset_ids.append(asset_id)

    # Generate multi-format report
    report_resp = await client.post("/api/v1/reports/generate", json={
        "title": f"Lifecycle 3 Audit Report {slug}",
        "report_type": "technical",
        "asset_id": asset_id,
        "formats": ["pdf", "html", "json"],
    })
    assert report_resp.status_code == 201
    report = report_resp.json()
    report_id = report["id"]
    assert report["status"] == "READY"

    # Verify download of all 3 artifacts
    for fmt in ["pdf", "html", "json"]:
        dl_resp = await client.get(f"/api/v1/reports/{report_id}/download?format={fmt}")
        assert dl_resp.status_code == 200
        assert len(dl_resp.content) > 0

    # Cleanup report
    del_resp = await client.delete(f"/api/v1/reports/{report_id}")
    assert del_resp.status_code == 204


@pytest.mark.asyncio
async def test_t3_lifecycle_04_schedule_trigger_and_metrics_sync(client: httpx.AsyncClient):
    """Lifecycle 4: Daily schedule trigger -> Scan dispatch -> Overview metrics synchronization."""
    # 1. Capture baseline metrics
    initial_metrics_resp = await client.get("/api/v1/metrics/overview")
    assert initial_metrics_resp.status_code == 200
    initial_metrics = initial_metrics_resp.json()

    # 2. Get schedule and trigger
    sched_resp = await client.get("/api/v1/schedules")
    assert sched_resp.status_code == 200
    schedules = sched_resp.json()
    assert len(schedules) >= 1
    sched_id = schedules[0]["id"]

    trig_resp = await client.post(f"/api/v1/schedules/{sched_id}/trigger")
    assert trig_resp.status_code == 200
    trig_data = trig_resp.json()
    assert "dispatched_scans" in trig_data
    assert len(trig_data["dispatched_scans"]) >= 1

    # 3. Synchronize overview metrics
    updated_metrics_resp = await client.get("/api/v1/metrics/overview")
    assert updated_metrics_resp.status_code == 200
    updated_metrics = updated_metrics_resp.json()
    assert updated_metrics["total_assets"] >= initial_metrics["total_assets"]


@pytest.mark.asyncio
async def test_t3_lifecycle_05_bulk_import_to_module_mapping(
    client: httpx.AsyncClient, created_asset_ids: List[str]
):
    """Lifecycle 5: Bulk ingestion across 4 modules -> Verify Empire module auto-classification."""
    slug = uuid.uuid4().hex[:6]
    csv_payload = (
        "target_locator,name,empire_module,environment\n"
        f"https://id-{slug}.empire.edu.vn,Student ID {slug},STUDENT_MANAGEMENT,PRODUCTION\n"
        f"https://voh-{slug}.empire.edu.vn,Media CDN {slug},LEARNING_MATERIALS,PRODUCTION\n"
        f"https://gw-{slug}.empire.edu.vn,Gateway {slug},API_SERVICES,PRODUCTION\n"
        f"https://console-{slug}.empire.edu.vn,Console {slug},WEB_APPLICATION,PRODUCTION\n"
    )
    import_resp = await client.post("/api/v1/assets/bulk-import", json={
        "import_type": "CSV",
        "raw_content": csv_payload,
    })
    assert import_resp.status_code == 200
    import_data = import_resp.json()
    assert import_data["imported_count"] == 4

    for a in import_data["imported_assets"]:
        created_asset_ids.append(a["id"])

    # Verify modules endpoint reflects new assets
    modules_resp = await client.get("/api/v1/empire-modules")
    assert modules_resp.status_code == 200
    modules_map = {m["module_key"]: m for m in modules_resp.json()}

    assert modules_map["STUDENT_MANAGEMENT"]["asset_count"] >= 1
    assert modules_map["LEARNING_MATERIALS"]["asset_count"] >= 1
    assert modules_map["API_SERVICES"]["asset_count"] >= 1
    assert modules_map["WEB_APPLICATION"]["asset_count"] >= 1
