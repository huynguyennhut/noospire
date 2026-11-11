"""tests/test_m1_challenger2_backend_boundaries.py

Empirical Challenger 2 Backend Stress Test Suite:
Adversarial validation of API boundary behaviors and scan recovery replay:
1. Target resolution with non-existent asset ID on batch scan (/api/v1/scans/batch):
   - Rejects with HTTP 404
   - Zero silent fallback to all assets
   - Mixed valid + invalid targets rejected atomically
2. Target resolution on loop test endpoint (/api/v1/scans/loop-test):
   - Rejects unknown target locator with HTTP 404 via query and body
   - Zero scan records committed
3. Single scan dispatch (/api/v1/scans):
   - Rejects non-existent asset ID with HTTP 404
4. Recovery across replay:
   - Valid scan POST commits to DB and returns authentic UUID
   - Subsequent query from independent client recovers identical job state
   - Direct database query verifies persistent state
   - Non-existent scan query returns HTTP 404 without client-side fabrication
"""

import uuid
import pytest
import pytest_asyncio
import httpx
from sqlalchemy import select, func, delete

from backend.main import app
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.models.asset import Asset
from backend.app.models.scan import Scan, ScanBatch
from backend.app.models.user import User, UserRole
from backend.app.schemas.common import AssetType, ScanProfile, VerificationStatus


@pytest_asyncio.fixture(autouse=True)
async def seed_users():
    """Seed authentic operator and viewer users into the DB for active session authentication."""
    async with AsyncSessionLocal() as session:
        users = [
            User(
                id=uuid.uuid4(),
                username="operator_test",
                email="operator_test@example.com",
                hashed_password=get_password_hash("OpPass123!"),
                role=UserRole.OPERATOR.value,
                is_active=True,
                is_superuser=False,
            ),
            User(
                id=uuid.uuid4(),
                username="viewer_test",
                email="viewer_test@example.com",
                hashed_password=get_password_hash("ViewerPass123!"),
                role=UserRole.VIEWER.value,
                is_active=True,
                is_superuser=False,
            ),
        ]
        for u in users:
            stmt = select(User).where(User.username == u.username)
            existing = (await session.execute(stmt)).scalars().first()
            if not existing:
                session.add(u)
        await session.commit()


@pytest.fixture
def operator_token() -> str:
    return create_access_token(
        subject="operator_test",
        role=UserRole.OPERATOR.value,
    )


@pytest.fixture
def operator_headers(operator_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {operator_token}"}


@pytest.fixture
def viewer_token() -> str:
    return create_access_token(
        subject="viewer_test",
        role=UserRole.VIEWER.value,
    )


@pytest.fixture
def viewer_headers(viewer_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {viewer_token}"}


@pytest_asyncio.fixture
async def test_asset():
    """Provides a verified target asset in the database for scan testing."""
    async with AsyncSessionLocal() as session:
        asset_id = uuid.uuid4()
        asset = Asset(
            id=asset_id,
            name="Empirical Challenger Verified Asset",
            target_locator="https://empire.edu.vn",
            asset_type=AssetType.WEB_APP.value,
            empire_module="STUDENT_PORTAL",
            verification_status=VerificationStatus.VERIFIED.value,
            environment="PRODUCTION",
            criticality="HIGH",
        )
        session.add(asset)
        await session.commit()
        await session.refresh(asset)
        yield asset

        # Teardown: delete any associated scans and the asset
        await session.execute(delete(Scan).where(Scan.asset_id == asset_id))
        await session.execute(delete(Asset).where(Asset.id == asset_id))
        await session.commit()


# ==============================================================================
# 1. BATCH SCAN TARGET RESOLUTION & UNKNOWN ASSETS
# ==============================================================================

@pytest.mark.asyncio
async def test_batch_scan_unknown_asset_id_rejected_404(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
):
    """Verify /api/v1/scans/batch with a non-existent asset ID returns HTTP 404

    and does NOT silently fall back to scanning all assets.
    """
    fake_asset_id = str(uuid.uuid4())
    payload = {
        "targets": [fake_asset_id],
        "name": "Adversarial Batch With Unknown Asset",
        "profile": "BASELINE",
        "engine": "nuclei",
    }

    # Count scans and batches before request
    async with AsyncSessionLocal() as session:
        scans_before = (await session.execute(select(func.count(Scan.id)))).scalar() or 0
        batches_before = (await session.execute(select(func.count(ScanBatch.id)))).scalar() or 0

    response = await client.post("/api/v1/scans/batch", json=payload, headers=operator_headers)

    assert response.status_code == 404, (
        f"Expected HTTP 404 when batch targets contain unknown asset, got {response.status_code}: {response.text}"
    )
    detail = response.json().get("detail", "")
    assert "not found" in detail.lower(), f"Expected 'not found' in detail message, got: {detail}"
    assert fake_asset_id in detail, f"Expected missing asset ID {fake_asset_id} to be named in detail, got: {detail}"

    # Verify ZERO scans and ZERO batches were created (zero fallback to all assets)
    async with AsyncSessionLocal() as session:
        scans_after = (await session.execute(select(func.count(Scan.id)))).scalar() or 0
        batches_after = (await session.execute(select(func.count(ScanBatch.id)))).scalar() or 0

    assert scans_after == scans_before, f"Scans count changed ({scans_before} -> {scans_after})! Silent execution occurred!"
    assert batches_after == batches_before, f"Batch was committed despite 404 error!"


@pytest.mark.asyncio
async def test_batch_scan_mixed_valid_and_unknown_target_rejected_404(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
    test_asset: Asset,
):
    """Verify /api/v1/scans/batch with mixed valid and non-existent targets is rejected

    atomically with HTTP 404 and does NOT dispatch partial scans.
    """
    fake_asset_id = str(uuid.uuid4())
    payload = {
        "targets": [str(test_asset.id), fake_asset_id],
        "name": "Adversarial Mixed Batch",
        "profile": "BASELINE",
        "engine": "nuclei",
    }

    async with AsyncSessionLocal() as session:
        scans_before = (await session.execute(select(func.count(Scan.id)))).scalar() or 0

    response = await client.post("/api/v1/scans/batch", json=payload, headers=operator_headers)

    assert response.status_code == 404
    assert fake_asset_id in response.json()["detail"]

    # Verify no partial scans were launched for the valid asset
    async with AsyncSessionLocal() as session:
        scans_after = (await session.execute(select(func.count(Scan.id)))).scalar() or 0

    assert scans_after == scans_before, "Partial scan dispatch occurred on mixed valid/invalid batch targets!"


@pytest.mark.asyncio
async def test_batch_scan_plural_and_singular_routes(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
):
    """Verify behavior of /api/v1/scans/batches (GET collection) vs /api/v1/scans/batch (POST action)."""
    fake_asset_id = str(uuid.uuid4())

    # GET /api/v1/scans/batches is valid collection retrieval
    get_res = await client.get("/api/v1/scans/batches", headers=operator_headers)
    assert get_res.status_code == 200

    # POST to /api/v1/scans/batch with non-existent target returns 404
    post_res = await client.post(
        "/api/v1/scans/batch",
        json={"targets": [fake_asset_id], "name": "Plurality Check"},
        headers=operator_headers,
    )
    assert post_res.status_code == 404


# ==============================================================================
# 2. LOOP-TEST TARGET RESOLUTION & UNKNOWN ASSETS
# ==============================================================================

@pytest.mark.asyncio
async def test_loop_test_unknown_asset_query_param_rejected_404(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
):
    """Verify /api/v1/scans/loop-test with non-existent target locator in query returns 404."""
    unknown_loc = f"https://nonexistent-empire-{uuid.uuid4().hex[:8]}.edu.vn"

    async with AsyncSessionLocal() as session:
        scans_before = (await session.execute(select(func.count(Scan.id)))).scalar() or 0

    response = await client.post(
        f"/api/v1/scans/loop-test?target_locator={unknown_loc}",
        headers=operator_headers,
    )

    assert response.status_code == 404, f"Expected 404, got {response.status_code}: {response.text}"
    detail = response.json().get("detail", "")
    assert "not found" in detail.lower()
    assert unknown_loc in detail

    async with AsyncSessionLocal() as session:
        scans_after = (await session.execute(select(func.count(Scan.id)))).scalar() or 0
    assert scans_after == scans_before, "Scans were created for unknown loop-test asset!"


@pytest.mark.asyncio
async def test_loop_test_unknown_asset_json_body_rejected_404(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
):
    """Verify /api/v1/scans/loop-test with non-existent target locator in JSON body returns 404."""
    unknown_loc = f"https://nonexistent-body-{uuid.uuid4().hex[:8]}.edu.vn"

    response = await client.post(
        "/api/v1/scans/loop-test",
        json={"target_locator": unknown_loc, "loops": 2, "profile": "QUICK"},
        headers=operator_headers,
    )

    assert response.status_code == 404
    detail = response.json().get("detail", "")
    assert "not found" in detail.lower()
    assert unknown_loc in detail


# ==============================================================================
# 3. SINGLE SCAN DISPATCH BOUNDARY BEHAVIOR
# ==============================================================================

@pytest.mark.asyncio
async def test_single_scan_unknown_asset_rejected_404(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
):
    """Verify POST /api/v1/scans with non-existent asset_id returns HTTP 404."""
    fake_asset_id = str(uuid.uuid4())
    payload = {
        "asset_id": fake_asset_id,
        "engine": "nuclei",
        "profile": "BASELINE",
    }

    response = await client.post("/api/v1/scans", json=payload, headers=operator_headers)
    assert response.status_code == 404
    assert "asset not found" in response.json()["detail"].lower()


# ==============================================================================
# 4. RECOVERY ACROSS REPLAY (DURABILITY & IDENTITY PRESERVATION)
# ==============================================================================

@pytest.mark.asyncio
async def test_recovery_across_replay_and_independent_sessions(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
    viewer_headers: dict[str, str],
    test_asset: Asset,
):
    """Empirical challenge: Valid scan POST must commit a real server job, return

    authentic server UUID, and subsequent query from a completely independent client
    (simulating tab close, page refresh, and 2nd browser reopen) recovers the exact
    same job without client-side fake state.
    """
    payload = {
        "asset_id": str(test_asset.id),
        "engine": "nuclei",
        "profile": "BASELINE",
        "allow_private_targets": False,
        "timeout_seconds": 60,
    }

    # Step 1: POST /api/v1/scans to launch scan
    post_res = await client.post("/api/v1/scans", json=payload, headers=operator_headers)
    assert post_res.status_code == 201, f"Failed to create scan: {post_res.text}"

    data = post_res.json()
    server_scan_id = data["id"]

    # Verify ID is a genuine UUID
    parsed_uuid = uuid.UUID(server_scan_id)
    assert str(parsed_uuid) == server_scan_id
    assert not server_scan_id.startswith("temp-")
    assert not server_scan_id.startswith("sim-")
    assert data["asset_id"] == str(test_asset.id)
    assert data["target_locator"] == test_asset.target_locator
    assert data["status"] in ("QUEUED", "RUNNING", "COMPLETED")

    # Step 2: Simulate second browser session (fresh transport & client, different user/role)
    transport2 = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport2, base_url="http://test") as client2:
        # Query GET /api/v1/scans/{scan_id}
        get_res = await client2.get(f"/api/v1/scans/{server_scan_id}", headers=viewer_headers)
        assert get_res.status_code == 200, f"Second client failed to recover scan: {get_res.text}"

        recovered_data = get_res.json()
        assert recovered_data["id"] == server_scan_id, "Recovered scan ID does not match server job ID"
        assert recovered_data["asset_id"] == str(test_asset.id), "Recovered asset ID does not match"
        assert recovered_data["target_locator"] == test_asset.target_locator, "Recovered target locator does not match"
        assert recovered_data["engine"] == "nuclei"
        assert recovered_data["profile"] == "BASELINE"

    # Step 3: Verify authentic database persistence directly (bypassing HTTP stack)
    async with AsyncSessionLocal() as session:
        stmt = select(Scan).where(Scan.id == parsed_uuid)
        db_scan = (await session.execute(stmt)).scalars().first()

        assert db_scan is not None, f"Scan {server_scan_id} was NOT committed to the database!"
        assert str(db_scan.id) == server_scan_id
        assert db_scan.asset_id == test_asset.id
        assert db_scan.target_locator == test_asset.target_locator
        assert db_scan.created_at is not None

    # Step 4: Verify querying non-existent scan ID returns HTTP 404 (zero fabrication)
    random_fake_id = str(uuid.uuid4())
    fake_res = await client.get(f"/api/v1/scans/{random_fake_id}", headers=viewer_headers)
    assert fake_res.status_code == 404
    assert "scan not found" in fake_res.json()["detail"].lower()
