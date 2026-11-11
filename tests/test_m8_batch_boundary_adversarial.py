"""Empirical Adversarial Challenge Suite for Milestone M8.

Specifically tests API boundary conditions, corner inputs, and contract robustness:
1. Target resolution boundaries:
   - Non-existent target UUIDs (404)
   - Malformed/invalid UUID string in target list (422)
   - Empty target list (404)
   - Mixed existing and non-existent UUIDs (processes found assets)
   - Case-insensitive target strings ("all" / "ALL")
2. Boundary input validation on concurrency_limit and timeout_seconds:
   - Zero, negative, and excessive concurrency_limit (422)
   - Valid boundary bounds: concurrency_limit 1 and 32 (201)
   - Zero, negative, sub-30s, and excessive timeout_seconds (422)
   - Valid boundary bounds: timeout_seconds 30 and 3600 (201)
3. Mixed verified/unverified targets under DEEP_ACTIVE:
   - Verified target queued/dispatched
   - Multiple unverified targets marked FAILED with AUTH_REQUIRED without failing batch
4. Telemetry and TrackCurrent schema compliance:
   - Schema adherence for /trackcurrent and /telemetry
   - Active thread and system resource field contract checks
5. Backward compatibility:
   - Single scan creation (POST /api/v1/scans)
   - Single scan cancellation (POST /api/v1/scans/{id}/cancel)
   - Single scan DEEP_ACTIVE 403 gate
   - Single scan parameter boundary enforcement
"""

import os
from pathlib import Path
from typing import List
from unittest.mock import patch
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.core.dispatcher import (
    AsyncWorkerDispatcher,
    check_system_resources,
    get_dispatcher,
)
from backend.app.models.asset import Asset
from backend.app.models.scan import Scan, ScanBatch
from backend.app.schemas.common import (
    AssetType,
    EmpireModule,
    ScanProfile,
    ScanQualityStatus,
    ScanStatus,
    VerificationStatus,
)
from backend.app.schemas.scan import (
    ActiveThreadInfo,
    BatchScanResponse,
    ScanCancelResponse,
    ScanResponse,
    TrackCurrentResponse,
)


# ============================================================================
# 1. TARGET RESOLUTION BOUNDARY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_batch_invalid_uuid_format_rejected_422(client: AsyncClient):
    """Challenge: Malformed UUID string in targets list must trigger HTTP 422 Unprocessable Entity."""
    payload = {
        "targets": ["not-a-valid-uuid-format"],
        "profile": "BASELINE",
        "name": "Adversarial Invalid UUID Format",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 422, f"Expected 422 for malformed UUID, got {response.status_code}: {response.text}"
    data = response.json()
    assert "detail" in data
    # Ensure Pydantic points to targets
    err_locs = [tuple(err.get("loc", [])) for err in data["detail"]]
    assert any("targets" in loc for loc in err_locs)


@pytest.mark.asyncio
async def test_batch_non_existent_target_uuids_404(client: AsyncClient):
    """Challenge: Target UUIDs that do not exist in the database must trigger HTTP 404 Not Found."""
    fake_uuid_1 = str(uuid.uuid4())
    fake_uuid_2 = str(uuid.uuid4())
    payload = {
        "targets": [fake_uuid_1, fake_uuid_2],
        "profile": "BASELINE",
        "name": "Adversarial Non-Existent Target UUIDs",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 404, f"Expected 404 for missing targets, got {response.status_code}: {response.text}"
    data = response.json()
    assert "No target assets found" in data["detail"]


@pytest.mark.asyncio
async def test_batch_empty_targets_list_404(client: AsyncClient):
    """Challenge: Empty targets list `[]` must result in HTTP 404 Not Found."""
    payload = {
        "targets": [],
        "profile": "BASELINE",
        "name": "Adversarial Empty Targets List",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 404, f"Expected 404 for empty targets, got {response.status_code}: {response.text}"
    data = response.json()
    assert "No target assets found" in data["detail"]


@pytest.mark.asyncio
async def test_batch_mixed_existing_and_non_existent_uuids(client: AsyncClient, db_session):
    """Challenge: When provided with a mix of valid and non-existent UUIDs, batch should resolve valid ones."""
    # Create one test asset
    real_asset = Asset(
        id=uuid.uuid4(),
        name="Real Test Asset",
        target_locator="https://real-boundary-test.empire.edu.vn",
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.STUDENT_MANAGEMENT.value,
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(real_asset)
    await db_session.commit()

    non_existent_uuid = str(uuid.uuid4())
    payload = {
        "targets": [str(real_asset.id), non_existent_uuid],
        "profile": "BASELINE",
        "name": "Adversarial Mixed Existing and Non-Existent",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
    data = response.json()
    # Batch must successfully schedule scan for the existing asset only
    assert data["target_count"] == 1
    assert data["total_scans"] == 1
    assert data["scans"][0]["asset_id"] == str(real_asset.id)


@pytest.mark.asyncio
async def test_batch_string_targets_case_insensitivity(client: AsyncClient):
    """Challenge: Target string 'all', 'ALL', and 'All' should correctly match all targets."""
    for variant in ["ALL", "all", " All "]:
        payload = {
            "targets": variant,
            "profile": "QUICK",
            "name": f"Adversarial Target String {variant}",
        }
        response = await client.post("/api/v1/scans/batch", json=payload)
        assert response.status_code == 201, f"Failed for variant '{variant}': {response.text}"
        data = response.json()
        assert data["target_count"] >= 6
        assert data["total_scans"] >= 6


# ============================================================================
# 2. CONCURRENCY & TIMEOUT BOUNDARY REJECTION TESTS
# ============================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_limit", [0, -1, -50, 33, 100, 1000])
async def test_batch_concurrency_limit_boundary_rejection_422(client: AsyncClient, invalid_limit: int):
    """Challenge: Concurrency limits outside [1, 32] must be rejected with 422."""
    payload = {
        "targets": "ALL",
        "profile": "BASELINE",
        "concurrency_limit": invalid_limit,
        "name": f"Adversarial Concurrency {invalid_limit}",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 422, f"Expected 422 for concurrency_limit={invalid_limit}, got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("valid_limit", [1, 2, 16, 32])
async def test_batch_concurrency_limit_valid_bounds(client: AsyncClient, valid_limit: int):
    """Challenge: Concurrency limits at exact boundary extremes (1 and 32) must be accepted with 201."""
    payload = {
        "targets": "ALL",
        "profile": "BASELINE",
        "concurrency_limit": valid_limit,
        "name": f"Adversarial Valid Concurrency {valid_limit}",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 201, f"Expected 201 for concurrency_limit={valid_limit}, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_timeout", [0, -1, -600, 10, 29, 3601, 100000])
async def test_batch_timeout_seconds_boundary_rejection_422(client: AsyncClient, invalid_timeout: int):
    """Challenge: Timeout seconds outside [30, 3600] must be rejected with 422."""
    payload = {
        "targets": "ALL",
        "profile": "BASELINE",
        "timeout_seconds": invalid_timeout,
        "name": f"Adversarial Timeout {invalid_timeout}",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 422, f"Expected 422 for timeout_seconds={invalid_timeout}, got {response.status_code}"


@pytest.mark.asyncio
@pytest.mark.parametrize("valid_timeout", [30, 60, 1800, 3600])
async def test_batch_timeout_seconds_valid_bounds(client: AsyncClient, valid_timeout: int):
    """Challenge: Timeout seconds at exact boundary extremes (30 and 3600) must be accepted with 201."""
    payload = {
        "targets": "ALL",
        "profile": "BASELINE",
        "timeout_seconds": valid_timeout,
        "name": f"Adversarial Valid Timeout {valid_timeout}",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 201, f"Expected 201 for timeout_seconds={valid_timeout}, got {response.status_code}: {response.text}"


# ============================================================================
# 3. MIXED VERIFIED & UNVERIFIED TARGETS UNDER DEEP_ACTIVE
# ============================================================================

@pytest.mark.asyncio
async def test_batch_deep_active_mixed_verified_and_multiple_unverified(client: AsyncClient, db_session):
    """Challenge: Mixed verified and unverified targets under DEEP_ACTIVE:
    - Verified asset: Dispatched with QUEUED status
    - Unverified PENDING asset: Marked FAILED with AUTH_REQUIRED quality status
    - Unverified FAILED asset: Marked FAILED with AUTH_REQUIRED quality status
    - Batch overall returns HTTP 201 with accurate failed_scans and total_scans
    """
    v_asset = Asset(
        id=uuid.uuid4(),
        name="Verified Target For Active Scan",
        target_locator="https://verified-active-test.empire.edu.vn",
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.API_SERVICES.value,
        verification_status=VerificationStatus.VERIFIED.value,
    )
    u_pending = Asset(
        id=uuid.uuid4(),
        name="Pending Target For Active Scan",
        target_locator="https://pending-active-test.empire.edu.vn",
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.WEB_APPLICATION.value,
        verification_status=VerificationStatus.PENDING.value,
    )
    u_failed = Asset(
        id=uuid.uuid4(),
        name="Failed Verification Target For Active Scan",
        target_locator="https://failed-active-test.empire.edu.vn",
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.LEARNING_MATERIALS.value,
        verification_status=VerificationStatus.FAILED.value,
    )
    db_session.add_all([v_asset, u_pending, u_failed])
    await db_session.commit()

    payload = {
        "targets": [str(v_asset.id), str(u_pending.id), str(u_failed.id)],
        "profile": "DEEP_ACTIVE",
        "name": "Adversarial Mixed DEEP_ACTIVE Suite",
    }
    response = await client.post("/api/v1/scans/batch", json=payload)
    assert response.status_code == 201, f"Batch creation failed: {response.text}"

    data = response.json()
    assert data["target_count"] == 3
    assert data["total_scans"] == 3

    # Check batch record in DB
    batch_res = await db_session.execute(select(ScanBatch).where(ScanBatch.id == uuid.UUID(data["batch_id"])))
    batch_db = batch_res.scalars().first()
    assert batch_db is not None
    assert batch_db.total_scans == 3
    assert batch_db.failed_scans == 2  # The two unverified targets

    scans_by_asset = {s["asset_id"]: s for s in data["scans"]}

    # Verified asset scan check
    v_scan = scans_by_asset[str(v_asset.id)]
    assert v_scan["status"] in ("QUEUED", "RUNNING", "COMPLETED")
    assert v_scan["quality_status"] is None or v_scan["quality_status"] != "AUTH_REQUIRED"
    assert v_scan["error_message"] is None

    # Unverified pending asset scan check
    pending_scan = scans_by_asset[str(u_pending.id)]
    assert pending_scan["status"] == "FAILED"
    assert pending_scan["quality_status"] == "AUTH_REQUIRED"
    assert pending_scan["progress_percentage"] == 100
    assert "Active scanning (DEEP_ACTIVE) is prohibited" in pending_scan["error_message"]

    # Unverified failed asset scan check
    failed_scan = scans_by_asset[str(u_failed.id)]
    assert failed_scan["status"] == "FAILED"
    assert failed_scan["quality_status"] == "AUTH_REQUIRED"
    assert failed_scan["progress_percentage"] == 100
    assert "Active scanning (DEEP_ACTIVE) is prohibited" in failed_scan["error_message"]


# ============================================================================
# 4. TELEMETRY & TRACKCURRENT SCHEMA CONFORMANCE
# ============================================================================

@pytest.mark.asyncio
async def test_telemetry_and_trackcurrent_endpoints_schema_contract(client: AsyncClient):
    """Challenge: Both /trackcurrent and /telemetry must return compliant TrackCurrentResponse schema:
    - active_workers: int >= 0
    - max_concurrency: int >= 1
    - system_resources: valid SystemResourcesInfo (cpu_percent, memory_percent, memory_available_mb)
    - active_threads: list of valid ActiveThreadInfo
    """
    for endpoint in ["/api/v1/scans/trackcurrent", "/api/v1/scans/telemetry"]:
        resp = await client.get(endpoint)
        assert resp.status_code == 200, f"Endpoint {endpoint} failed: {resp.text}"

        data = resp.json()
        validated = TrackCurrentResponse.model_validate(data)
        assert validated.active_workers >= 0
        assert validated.max_concurrency >= 1
        assert validated.system_resources.cpu_percent >= 0.0
        assert validated.system_resources.memory_percent >= 0.0
        assert validated.system_resources.memory_available_mb >= 0.0
        assert isinstance(validated.is_throttled, bool)
        assert isinstance(validated.active_threads, list)


@pytest.mark.asyncio
async def test_telemetry_active_threads_live_structure(client: AsyncClient):
    """Challenge: When active threads exist in dispatcher, verify full ActiveThreadInfo fields."""
    dispatcher = get_dispatcher()
    dummy_scan_id = uuid.uuid4()
    dispatcher._active_threads[dummy_scan_id] = {
        "thread_id": 99,
        "scan_id": dummy_scan_id,
        "target_locator": "https://test-telemetry.empire.edu.vn",
        "profile": "STANDARD",
        "engine": "nuclei",
        "stage": "active",
        "progress_percentage": 50,
        "started_at": "2026-11-09T01:00:00Z",
        "elapsed_seconds": 15,
        "last_log": "Testing active parameter fuzzing",
    }

    try:
        resp = await client.get("/api/v1/scans/trackcurrent")
        assert resp.status_code == 200
        data = resp.json()
        validated = TrackCurrentResponse.model_validate(data)
        assert validated.active_workers >= 1

        thread = next((t for t in validated.active_threads if t.scan_id == dummy_scan_id), None)
        assert thread is not None
        assert thread.thread_id == 99
        assert thread.target_locator == "https://test-telemetry.empire.edu.vn"
        assert thread.stage == "active"
        assert thread.progress_percentage == 50
        assert thread.last_log == "Testing active parameter fuzzing"
    finally:
        dispatcher._active_threads.pop(dummy_scan_id, None)


# ============================================================================
# 5. BACKWARD COMPATIBILITY: SINGLE SCAN API & CANCELLATION
# ============================================================================

@pytest.mark.asyncio
async def test_backward_compatibility_single_scan_lifecycle(client: AsyncClient, db_session):
    """Challenge: Single scan creation (POST /api/v1/scans), get, cancel, and logs work 100%."""
    # Create target asset
    asset = Asset(
        id=uuid.uuid4(),
        name="Single Scan Asset",
        target_locator="https://single-scan-test.empire.edu.vn",
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.STUDENT_MANAGEMENT.value,
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)
    await db_session.commit()

    # 1. Create single scan
    scan_create_payload = {
        "asset_id": str(asset.id),
        "engine": "nuclei",
        "profile": "BASELINE",
        "allow_private_targets": True,
        "timeout_seconds": 300,
    }
    create_resp = await client.post("/api/v1/scans", json=scan_create_payload)
    assert create_resp.status_code == 201, f"Single scan creation failed: {create_resp.text}"
    scan_data = create_resp.json()
    validated_scan = ScanResponse.model_validate(scan_data)
    assert validated_scan.asset_id == asset.id
    assert validated_scan.batch_id is None
    assert validated_scan.engine == "nuclei"
    assert validated_scan.profile == "BASELINE"

    scan_id = validated_scan.id

    # 2. Get scan detail
    get_resp = await client.get(f"/api/v1/scans/{scan_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == str(scan_id)

    # 3. Cancel single scan
    cancel_resp = await client.post(f"/api/v1/scans/{scan_id}/cancel")
    assert cancel_resp.status_code == 200, f"Cancel single scan failed: {cancel_resp.text}"
    cancel_data = cancel_resp.json()
    validated_cancel = ScanCancelResponse.model_validate(cancel_data)
    assert validated_cancel.scan_id == scan_id
    assert validated_cancel.status == ScanStatus.CANCELLED

    # 4. Get scan logs
    logs_resp = await client.get(f"/api/v1/scans/{scan_id}/logs")
    assert logs_resp.status_code == 200
    assert "items" in logs_resp.json()


@pytest.mark.asyncio
async def test_backward_compatibility_single_scan_deep_active_gate(client: AsyncClient, db_session):
    """Challenge: Single scan DEEP_ACTIVE on unverified asset MUST return HTTP 403 Forbidden."""
    unverified = Asset(
        id=uuid.uuid4(),
        name="Unverified Single Scan Target",
        target_locator="https://unverified-single.empire.edu.vn",
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.API_SERVICES.value,
        verification_status=VerificationStatus.PENDING.value,
    )
    db_session.add(unverified)
    await db_session.commit()

    payload = {
        "asset_id": str(unverified.id),
        "engine": "zap",
        "profile": "DEEP_ACTIVE",
        "allow_private_targets": True,
    }
    resp = await client.post("/api/v1/scans", json=payload)
    assert resp.status_code == 403, f"Expected 403 Forbidden for DEEP_ACTIVE on unverified, got {resp.status_code}: {resp.text}"
    assert "Active scanning (DEEP_ACTIVE) is prohibited" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_single_scan_parameter_boundary_enforcement(client: AsyncClient, db_session):
    """Challenge: Single scan creation enforces timeout_seconds in [30, 3600] and validates asset_id."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Valid Asset for Boundary Check",
        target_locator="https://boundary-param.empire.edu.vn",
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.SUPPORTING_TOOLS.value,
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)
    await db_session.commit()

    # Timeout too small
    resp = await client.post("/api/v1/scans", json={
        "asset_id": str(asset.id),
        "timeout_seconds": 15,
    })
    assert resp.status_code == 422

    # Timeout too large
    resp = await client.post("/api/v1/scans", json={
        "asset_id": str(asset.id),
        "timeout_seconds": 5000,
    })
    assert resp.status_code == 422

    # Non-existent asset ID
    resp = await client.post("/api/v1/scans", json={
        "asset_id": str(uuid.uuid4()),
        "timeout_seconds": 300,
    })
    assert resp.status_code == 404
    assert "Asset not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_batch_non_existent_id_operations_404(client: AsyncClient):
    """Challenge: Non-existent batch IDs on GET /batch/{id} and POST /batch/{id}/cancel return 404."""
    random_batch_id = uuid.uuid4()
    
    # GET non-existent batch
    get_resp = await client.get(f"/api/v1/scans/batch/{random_batch_id}")
    assert get_resp.status_code == 404
    assert "Scan batch not found" in get_resp.json()["detail"]

    # Cancel non-existent batch
    cancel_resp = await client.post(f"/api/v1/scans/batch/{random_batch_id}/cancel")
    assert cancel_resp.status_code == 404
    assert "Scan batch not found" in cancel_resp.json()["detail"]


@pytest.mark.asyncio
async def test_emergency_stop_all_endpoint(client: AsyncClient):
    """Challenge: Emergency stop endpoint POST /stop-all halts all active tasks cleanly."""
    resp = await client.post("/api/v1/scans/stop-all")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "STOPPED"
    assert isinstance(data["halted_count"], int)
    assert "Platform-wide emergency stop executed" in data["message"]


@pytest.mark.asyncio
async def test_batches_pagination_contract(client: AsyncClient):
    """Challenge: GET /api/v1/scans/batches honors pagination parameters."""
    resp = await client.get("/api/v1/scans/batches?page=1&size=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "size" in data
    assert data["page"] == 1
    assert data["size"] == 5
    assert isinstance(data["items"], list)

