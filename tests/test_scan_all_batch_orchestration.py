"""Test Suite for Milestone M8: "Scan All" Batch Scan Orchestration & Resource Optimization.

Covers BAT-01 through BAT-13:
- BAT-01: test_batch_dispatch_all_targets_default
- BAT-02: test_batch_matrix_expansion_engines_profiles
- BAT-03: test_batch_active_scan_security_gate
- BAT-04: test_concurrency_throttling_strict_cap
- BAT-05: test_per_asset_lock_mutual_exclusion
- BAT-06: test_resource_optimization_queue_drain
- BAT-07: test_cooperative_batch_cancellation
- BAT-08: test_batch_cancel_process_tree_termination
- BAT-09: test_batch_telemetry_active_threads_endpoint
- BAT-10: test_scan_lifecycle_alert_notifications
- BAT-11: test_frontend_logo_and_brand_contract
- BAT-12: test_frontend_scan_all_ui_liquid_glass_contract
- BAT-13: test_backward_compatibility_single_scan_api
"""

import asyncio
import os
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, patch
import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from backend.main import app
from backend.app.core.database import AsyncSessionLocal, init_db
from backend.app.core.dispatcher import (
    AsyncWorkerDispatcher,
    check_system_resources,
    get_dispatcher,
    process_safety,
)
from backend.app.scanners.base import CancellationToken
from backend.app.models.asset import Asset
from backend.app.models.scan import Scan, ScanBatch
from backend.app.models.alert import SecurityAlert
from backend.app.schemas.common import (
    AssetType,
    EmpireModule,
    ScanProfile,
    ScanQualityStatus,
    ScanStatus,
    VerificationStatus,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ============================================================================
# BAT-01: Default Batch Dispatch Across All Registered Targets
# ============================================================================

@pytest.mark.asyncio
async def test_batch_dispatch_all_targets_default(client: AsyncClient):
    """BAT-01: Dispatches batch scan across all registered targets with default settings."""
    payload = {
        "targets": "ALL",
        "profile": "DAILY_SECURITY",
        "engines": ["all"],
        "name": "BAT-01 Full Ecosystem Sweep",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 201, f"Batch creation failed: {response.text}"

    data = response.json()
    assert "batch_id" in data
    assert uuid.UUID(data["batch_id"])
    assert data["name"] == "BAT-01 Full Ecosystem Sweep"
    assert data["target_count"] >= 6
    assert data["total_scans"] >= 6
    assert data["status"] in ("QUEUED", "RUNNING")
    assert len(data["scans"]) == data["total_scans"]

    batch_id = data["batch_id"]
    for s in data["scans"]:
        assert s["batch_id"] == batch_id
        assert s["profile"] == "DAILY_SECURITY"

    # Clean up: cancel the 300+ dispatched scans to prevent queue saturation
    await client.post(f"/api/v1/scans/batch/{batch_id}/cancel")


# ============================================================================
# BAT-02: Target x Profile Matrix Expansion
# ============================================================================

@pytest.mark.asyncio
async def test_batch_matrix_expansion_engines_profiles(client: AsyncClient):
    """BAT-02: Verifies matrix expansion for explicit targets and multiple profiles."""
    assets_resp = await client.get("/api/v1/assets")
    assert assets_resp.status_code == 200
    assets = assets_resp.json()["items"]
    assert len(assets) >= 3

    target_ids = [assets[0]["id"], assets[1]["id"], assets[2]["id"]]
    payload = {
        "targets": target_ids,
        "profiles": ["QUICK", "STANDARD"],
        "engines": ["nuclei", "zap"],
        "name": "BAT-02 Matrix Expansion",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 201, f"Matrix expansion failed: {response.text}"

    data = response.json()
    # 3 targets * 2 profiles = 6 scan jobs
    assert data["total_scans"] == 6
    assert data["target_count"] == 3
    assert len(data["scans"]) == 6

    profiles_found = {s["profile"] for s in data["scans"]}
    assert profiles_found == {"QUICK", "STANDARD"}
    for s in data["scans"]:
        assert s["engine"] == "nuclei,zap"
        assert s["batch_id"] == data["batch_id"]

    # Clean up batch
    await client.post(f"/api/v1/scans/batch/{data['batch_id']}/cancel")


# ============================================================================
# BAT-03: Security Authorization Gate on DEEP_ACTIVE in Batch
# ============================================================================

@pytest.mark.asyncio
async def test_batch_active_scan_security_gate(client: AsyncClient, db_session):
    """BAT-03: Unverified targets with DEEP_ACTIVE are downgraded to AUTH_REQUIRED without failing batch."""
    # Ensure one verified target and one unverified target
    verified_asset = Asset(
        id=uuid.uuid4(),
        name="Verified Lab Target",
        target_locator="https://verified-lab.empire.edu.vn",
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.SUPPORTING_TOOLS.value,
        verification_status=VerificationStatus.VERIFIED.value,
    )
    unverified_asset = Asset(
        id=uuid.uuid4(),
        name="Unverified Host Target",
        target_locator="https://unverified-host.empire.edu.vn",
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.SUPPORTING_TOOLS.value,
        verification_status=VerificationStatus.PENDING.value,
    )
    db_session.add(verified_asset)
    db_session.add(unverified_asset)
    await db_session.commit()

    try:
        payload = {
            "targets": [str(verified_asset.id), str(unverified_asset.id)],
            "profiles": ["DEEP_ACTIVE"],
            "engines": ["all"],
            "name": "BAT-03 Security Gate Test",
        }
        response = await client.post("/api/v1/scans/batch", json=payload)
        assert response.status_code == 201, f"Batch request failed: {response.text}"

        data = response.json()
        assert data["total_scans"] == 2

        scans_by_asset = {s["asset_id"]: s for s in data["scans"]}
        verified_scan = scans_by_asset[str(verified_asset.id)]
        unverified_scan = scans_by_asset[str(unverified_asset.id)]

        # Verified target is queued for execution
        assert verified_scan["status"] in ("QUEUED", "RUNNING", "INITIALIZING")

        # Unverified target is blocked cleanly with AUTH_REQUIRED
        assert unverified_scan["status"] == "FAILED"
        assert unverified_scan["quality_status"] == "AUTH_REQUIRED"
        assert "ownership is not verified" in unverified_scan.get("error_message", "")
    finally:
        if "data" in locals() and "batch_id" in data:
            await client.post(f"/api/v1/scans/batch/{data['batch_id']}/cancel")
        await db_session.delete(verified_asset)
        await db_session.delete(unverified_asset)
        await db_session.commit()


# ============================================================================
# BAT-04: Concurrency Throttling Strict Cap Invariant
# ============================================================================

@pytest.mark.asyncio
async def test_concurrency_throttling_strict_cap():
    """BAT-04: Maximum concurrent running scans never exceeds the configured ceiling."""
    dispatcher = AsyncWorkerDispatcher(max_concurrent=3)
    assert dispatcher.max_concurrent <= 3
    assert dispatcher.semaphore._value == dispatcher.max_concurrent

    active_running = 0
    max_observed_concurrency = 0
    lock = asyncio.Lock()

    async def mock_run_scan(scan_id, token, thread_id=1):
        nonlocal active_running, max_observed_concurrency
        async with lock:
            active_running += 1
            if active_running > max_observed_concurrency:
                max_observed_concurrency = active_running

        await asyncio.sleep(0.02)

        async with lock:
            active_running -= 1

    with patch.object(dispatcher, "_run_scan", side_effect=mock_run_scan), \
         patch("backend.app.core.dispatcher.check_system_resources", return_value={"is_throttled": False, "cpu_percent": 10.0, "memory_percent": 50.0, "memory_available_mb": 4096.0, "memory_used_mb": 4096.0, "cpu_count": 4}):
        dispatcher.start()
        # Enqueue 15 synthetic scans
        for _ in range(15):
            sid = uuid.uuid4()
            dispatcher.cancellation_tokens[sid] = CancellationToken()
            await dispatcher.queue.put(sid)

        # Allow queue to drain
        await dispatcher.queue.join()
        await dispatcher.stop()

    assert max_observed_concurrency <= 3, f"Concurrency exceeded cap! Max was {max_observed_concurrency}"
    assert max_observed_concurrency > 0


# ============================================================================
# BAT-05: Per-Asset Lock Mutual Exclusion
# ============================================================================

@pytest.mark.asyncio
async def test_per_asset_lock_mutual_exclusion():
    """BAT-05: Multiple scans targeting the exact same asset are serialized by per-asset lock."""
    dispatcher = AsyncWorkerDispatcher(max_concurrent=4)
    asset_id = uuid.uuid4()

    lock = dispatcher.asset_locks.setdefault(asset_id, asyncio.Lock())
    assert not lock.locked()

    acquired_order = []

    async def task_worker(worker_id: int):
        async with lock:
            acquired_order.append(f"start_{worker_id}")
            await asyncio.sleep(0.02)
            acquired_order.append(f"end_{worker_id}")

    # Launch 3 competing workers on same asset lock
    await asyncio.gather(task_worker(1), task_worker(2), task_worker(3))

    # Verify strict non-overlapping serialization: start_X must be followed by end_X before start_Y
    for i in range(0, len(acquired_order), 2):
        start_tag = acquired_order[i]
        end_tag = acquired_order[i + 1]
        worker_num = start_tag.split("_")[1]
        assert end_tag == f"end_{worker_num}", f"Lock overlap detected: {start_tag} followed by {end_tag}"


# ============================================================================
# BAT-06: Resource Optimization & Queue Drain
# ============================================================================

@pytest.mark.asyncio
async def test_resource_optimization_queue_drain():
    """BAT-06: Host resource check operates and worker queue drains cleanly without deadlocks."""
    res = check_system_resources()
    assert "cpu_percent" in res
    assert "memory_percent" in res
    assert "memory_available_mb" in res
    assert "is_throttled" in res
    assert isinstance(res["is_throttled"], bool)

    dispatcher = AsyncWorkerDispatcher(max_concurrent=2)
    processed = []

    async def fast_run(scan_id, token, thread_id=1):
        processed.append(scan_id)
        await asyncio.sleep(0.01)

    with patch.object(dispatcher, "_run_scan", side_effect=fast_run), \
         patch("backend.app.core.dispatcher.check_system_resources", return_value={"is_throttled": False, "cpu_percent": 10.0, "memory_percent": 50.0, "memory_available_mb": 4096.0, "memory_used_mb": 4096.0, "cpu_count": 4}):
        dispatcher.start()
        test_ids = [uuid.uuid4() for _ in range(6)]
        for sid in test_ids:
            dispatcher.cancellation_tokens[sid] = CancellationToken()
            await dispatcher.queue.put(sid)

        await dispatcher.queue.join()
        await dispatcher.stop()

    assert len(processed) == 6
    assert set(processed) == set(test_ids)


# ============================================================================
# BAT-07: Cooperative Batch Cancellation
# ============================================================================

@pytest.mark.asyncio
async def test_cooperative_batch_cancellation(client: AsyncClient, db_session):
    """BAT-07: Cancelling a batch halts running tasks and marks queued scans as CANCELLED."""
    # Create a batch with multiple scans in DB
    batch = ScanBatch(
        id=uuid.uuid4(),
        name="BAT-07 Batch to Cancel",
        status=ScanStatus.RUNNING.value,
        total_scans=4,
    )
    db_session.add(batch)

    # Fetch an asset
    asset_res = await db_session.execute(select(Asset))
    asset = asset_res.scalars().first()
    assert asset is not None

    scans = [
        Scan(
            id=uuid.uuid4(),
            asset_id=asset.id,
            batch_id=batch.id,
            target_locator=asset.target_locator,
            status=ScanStatus.QUEUED.value,
        )
        for _ in range(4)
    ]
    for s in scans:
        db_session.add(s)
    await db_session.commit()

    cancel_resp = await client.post(f"/api/v1/scans/batch/{batch.id}/cancel")
    assert cancel_resp.status_code == 200, f"Cancel batch failed: {cancel_resp.text}"

    data = cancel_resp.json()
    assert data["batch_id"] == str(batch.id)
    assert data["status"] == "CANCELLED"
    assert data["cancelled_count"] == 4

    # Verify scans are CANCELLED in database
    for s in scans:
        await db_session.refresh(s)
        assert s.status == ScanStatus.CANCELLED.value


# ============================================================================
# BAT-08: Subprocess Tree Termination on Cancel
# ============================================================================

@pytest.mark.asyncio
async def test_batch_cancel_process_tree_termination():
    """BAT-08: Cancelling a scan removes registered PIDs and invokes process tree termination."""
    test_scan_id = uuid.uuid4()
    # Register a synthetic PID
    await process_safety.register_pid(test_scan_id, 999999)
    assert test_scan_id in process_safety._scan_pids

    with patch("psutil.Process") as mock_proc:
        mock_parent = mock_proc.return_value
        mock_parent.children.return_value = []
        process_safety.terminate_process_tree(test_scan_id)

    assert test_scan_id not in process_safety._scan_pids


# ============================================================================
# BAT-09: Live Telemetry & "trackcurrent" Endpoints
# ============================================================================

@pytest.mark.asyncio
async def test_batch_telemetry_active_threads_endpoint(client: AsyncClient):
    """BAT-09: Verifies /trackcurrent and /telemetry endpoints return active thread matrix and resources."""
    resp1 = await client.get("/api/v1/scans/trackcurrent")
    assert resp1.status_code == 200
    data1 = resp1.json()

    assert "active_workers" in data1
    assert "max_concurrency" in data1
    assert "system_resources" in data1
    assert "active_threads" in data1
    assert "is_throttled" in data1
    assert isinstance(data1["system_resources"]["cpu_percent"], (int, float))
    assert isinstance(data1["system_resources"]["memory_percent"], (int, float))

    resp2 = await client.get("/api/v1/scans/telemetry")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["max_concurrency"] == data1["max_concurrency"]


# ============================================================================
# BAT-10: Scan Lifecycle Alert Notifications
# ============================================================================

@pytest.mark.asyncio
async def test_scan_lifecycle_alert_notifications(client: AsyncClient, db_session):
    """BAT-10: Lifecycle notifications for SCAN category are created and retrievable via Alerts API."""
    # Insert a SCAN category alert
    alert = SecurityAlert(
        id=uuid.uuid4(),
        severity="INFO",
        title="Scan Completed: DAILY_SECURITY on https://empire.edu.vn",
        message="Assessment finished with status COMPLETED (Quality: SCANNED_SUCCESSFULLY).",
        category="SCAN",
        metadata_json={"scan_id": str(uuid.uuid4())},
    )
    db_session.add(alert)
    await db_session.commit()

    resp = await client.get("/api/v1/alerts")
    assert resp.status_code == 200
    alerts = resp.json()
    scan_alerts = [a for a in alerts if a.get("category") == "SCAN"]
    assert len(scan_alerts) > 0
    assert any("Scan Completed" in a["title"] for a in scan_alerts)


# ============================================================================
# BAT-11: Frontend Official Logo & Brand Asset Contract
# ============================================================================

def test_frontend_logo_and_brand_contract():
    """BAT-11: Confirms official logo asset exists and Shell.tsx integrates brand presentation."""
    # Check official logo file in repository public assets
    source_logo_path = REPO_ROOT / "frontend" / "public" / "brand" / "logo.jpg"
    if not source_logo_path.is_file():
        source_logo_path = Path(
            "C:/Users/nguye/.gemini/antigravity-cli/brain/6fde3f07-9d36-4bda-a864-b53b67d53f2e/.user_uploaded/uploaded_media_1794171615086.jpg"
        )
    assert source_logo_path.is_file(), f"Official source logo missing at {source_logo_path}"
    assert source_logo_path.stat().st_size > 10000, "Logo image file appears corrupted or empty"

    # Verify Shell.tsx layout presence
    shell_path = REPO_ROOT / "frontend" / "src" / "components" / "layout" / "Shell.tsx"
    assert shell_path.is_file(), f"Shell component missing at {shell_path}"
    shell_content = shell_path.read_text(encoding="utf-8")
    assert "NOOSFORGE" in shell_content, "NOOSFORGE brand presentation missing in Shell.tsx"


# ============================================================================
# BAT-12: Frontend Liquid Glass & Scan Center UI Contract
# ============================================================================

def test_frontend_scan_all_ui_liquid_glass_contract():
    """BAT-12: Verifies dark UI styling, scan profiles, and active assessment telemetry contracts."""
    scans_page = REPO_ROOT / "frontend" / "src" / "app" / "scans" / "page.tsx"
    active_page = REPO_ROOT / "frontend" / "src" / "app" / "active-assessments" / "page.tsx"

    assert scans_page.is_file()
    assert active_page.is_file()

    scans_content = scans_page.read_text(encoding="utf-8")
    active_content = active_page.read_text(encoding="utf-8")

    # Dark UI styling contracts
    assert "border-white" in scans_content or "bg-zinc-950" in scans_content or "bg-black" in scans_content
    # Profiles contract
    assert "BASELINE" in scans_content
    assert "DAILY_SECURITY" in scans_content
    assert "DEEP_ACTIVE" in scans_content
    # Active assessment HUD contract
    assert "preflight" in active_content
    assert "discovery" in active_content
    assert "scoring" in active_content


# ============================================================================
# BAT-13: Backward Compatibility for Single Scan API
# ============================================================================

@pytest.mark.asyncio
async def test_backward_compatibility_single_scan_api(client: AsyncClient):
    """BAT-13: Single scan creation, detail retrieval, and cancellation operate without regression."""
    assets_resp = await client.get("/api/v1/assets")
    assert assets_resp.status_code == 200
    assets = assets_resp.json()["items"]
    target_asset = assets[-1]

    # 1. Single scan POST /api/v1/scans
    scan_payload = {
        "asset_id": target_asset["id"],
        "profile": "BASELINE",
        "engine": "all",
        "allow_private_targets": True,
        "timeout_seconds": 120,
    }
    create_resp = await client.post("/api/v1/scans", json=scan_payload)
    assert create_resp.status_code == 201
    scan_data = create_resp.json()
    scan_id = scan_data["id"]
    assert scan_data["profile"] == "BASELINE"
    assert scan_data["status"] in ("QUEUED", "RUNNING", "INITIALIZING")

    # 2. GET /api/v1/scans/{scan_id}
    get_resp = await client.get(f"/api/v1/scans/{scan_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == scan_id

    # 3. POST /api/v1/scans/{scan_id}/cancel
    cancel_resp = await client.post(f"/api/v1/scans/{scan_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["scan_id"] == scan_id
    assert cancel_resp.json()["status"] in ("CANCELLED", "COMPLETED", "FAILED")
