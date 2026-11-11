"""Tests for Milestone M1 (Platform Core):
- Primary Root Target Seeding (https://empire.edu.vn/)
- Idempotent Seeding
- 8-Step Target Verification Pipeline (TargetVerifier)
- POST /api/v1/assets/{id}/verify Endpoint Integration
- POST /api/v1/assets/bulk-preview Ingestion & Deduplication
"""

from __future__ import annotations

import uuid
import pytest
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import AsyncSessionLocal, init_db
from backend.app.core.empire_seeder import seed_empire_ecosystem
from backend.app.core.target_verifier import get_target_verifier, TargetVerifier
from backend.app.models.asset import Asset
from backend.app.schemas.common import (
    AssetType,
    Criticality,
    EmpireModule,
    VerificationStatus,
    VerificationType,
)
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.models.base import User
from backend.app.models.user import UserRole
import pytest_asyncio


@pytest_asyncio.fixture(autouse=True)
async def authenticate_client(client: httpx.AsyncClient):
    async with AsyncSessionLocal() as session:
        user = await session.scalar(select(User).where(User.username == "admin_m1_test"))
        if not user:
            user = User(
                id=uuid.uuid4(),
                username="admin_m1_test",
                email="admin_m1_test@example.com",
                hashed_password=get_password_hash("AdminPass123!"),
                role=UserRole.ADMIN.value,
                is_superuser=True,
                is_active=True,
            )
            session.add(user)
            await session.commit()
    token = create_access_token("admin_m1_test", role=UserRole.ADMIN.value)
    client.headers["Authorization"] = f"Bearer {token}"



@pytest.mark.asyncio
async def test_primary_root_target_seeded(db_session: AsyncSession):
    """Test 1: Verify primary root target https://empire.edu.vn/ is seeded with production-safe policy."""
    res = await db_session.execute(
        select(Asset).where(Asset.target_locator.in_(("https://empire.edu.vn/", "https://empire.edu.vn")))
    )
    root_asset = res.scalars().first()
    assert root_asset is not None, "Primary root asset https://empire.edu.vn/ must be registered in database"
    assert root_asset.verification_status == VerificationStatus.VERIFIED.value
    assert root_asset.criticality == Criticality.CRITICAL.value

    policy = root_asset.assessment_policy
    assert policy.get("scope") == "*.empire.edu.vn" or policy.get("same_origin_scope") == "*.empire.edu.vn"
    assert policy.get("same_origin_only") is True
    assert policy.get("baseline_policy") == "PRODUCTION_SAFE" or policy.get("intensity") == "PRODUCTION_SAFE"


@pytest.mark.asyncio
async def test_seeder_idempotency(db_session: AsyncSession):
    """Test 2: Verify repeated execution of seeder is 100% idempotent and does not duplicate assets."""
    res1 = await db_session.execute(select(Asset))
    count1 = len(res1.scalars().all())

    # Run seeder a second time
    await seed_empire_ecosystem(db_session)

    res2 = await db_session.execute(select(Asset))
    count2 = len(res2.scalars().all())

    assert count1 == count2, f"Seeder must be idempotent: count before ({count1}) != count after ({count2})"


@pytest.mark.asyncio
async def test_target_verifier_live_probe_8_steps():
    """Test 3: Execute TargetVerifier live probe against https://empire.edu.vn/ and verify all 8 steps."""
    verifier = get_target_verifier()
    result = await verifier.verify_target("https://empire.edu.vn/")

    assert result["status"] == "VERIFIED"
    assert result["verified"] is True
    assert len(result["steps"]) == 8

    # Verify each distinct step
    step_names = [s["name"] for s in result["steps"]]
    expected_steps = [
        "Input Validation",
        "DNS Resolution",
        "TLS Verification",
        "HTTP Connectivity",
        "Redirect Inspection",
        "Web Discovery",
        "Target Fingerprint",
        "Verification Result",
    ]
    assert step_names == expected_steps

    for s in result["steps"]:
        assert s["status"] in ("PASS", "INFO"), f"Step {s['step']} ({s['name']}) should pass: {s['detail']}"

    # Verify target fingerprint
    fp = result["fingerprint"]
    assert "server" in fp
    assert "Envoy" in fp.get("reverse_proxy_waf", "") or "envoy" in fp.get("server", "").lower()
    assert "Next.js" in fp.get("framework", "") or "React" in fp.get("technologies", [])
    assert fp.get("active_security_headers_count", 0) >= 3


@pytest.mark.asyncio
async def test_target_verifier_ssrf_rejection():
    """Test 4: Verify TargetVerifier rejects malicious or private cloud metadata SSRF targets."""
    verifier = TargetVerifier(timeout=3.0)
    result = await verifier.verify_target("http://169.254.169.254/latest/meta-data/", allow_private=False)

    assert result["status"] == "FAILED"
    assert result["verified"] is False
    assert result["steps"][0]["status"] == "FAIL"
    assert "SSRF" in result["steps"][0]["detail"] or "cloud metadata" in result["steps"][0]["detail"].lower()


@pytest.mark.asyncio
async def test_api_verify_asset_endpoint(client: httpx.AsyncClient, db_session: AsyncSession):
    """Test 5: Verify POST /api/v1/assets/{id}/verify executes the 8-step probe and updates asset."""
    res = await db_session.execute(
        select(Asset).where(Asset.target_locator.in_(("https://empire.edu.vn/", "https://empire.edu.vn")))
    )
    root_asset = res.scalars().first()
    assert root_asset is not None

    resp = await client.post(f"/api/v1/assets/{root_asset.id}/verify", json={"verification_type": "ADMIN_OVERRIDE"})
    assert resp.status_code == 200
    data = resp.json()

    assert data["verified"] is True
    assert data["status"] == "VERIFIED"
    assert len(data["steps"]) == 8
    assert "fingerprint" in data
    assert data["asset_id"] == str(root_asset.id)


@pytest.mark.asyncio
async def test_bulk_preview_csv(client: httpx.AsyncClient):
    """Test 6: Verify POST /api/v1/assets/bulk-preview detects duplicates and previews new CSV targets."""
    csv_payload = {
        "import_type": "CSV",
        "raw_content": (
            "target,name,empire_module,environment\n"
            "https://id.empire.edu.vn,Empire ID Service,STUDENT_MANAGEMENT,PRODUCTION\n"  # Duplicate
            "https://empire.edu.vn/,Empire Root Platform,WEB_APPLICATION,PRODUCTION\n"  # Duplicate
            "https://new-preview-test.empire.edu.vn,New Preview Portal,STUDENT_MANAGEMENT,STAGING\n"  # New
        ),
    }
    resp = await client.post("/api/v1/assets/bulk-preview", json=csv_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 3
    assert len(data["duplicate"]) == 2
    assert len(data["new"]) == 1

    dup_locs = [d["target_locator"] for d in data["duplicate"]]
    assert any("id.empire.edu.vn" in loc for loc in dup_locs)
    assert any("empire.edu.vn" in loc for loc in dup_locs)
    assert data["new"][0]["target_locator"] == "https://new-preview-test.empire.edu.vn"
    assert data["new"][0]["is_duplicate"] is False


@pytest.mark.asyncio
async def test_bulk_preview_json_and_batch_dedup(client: httpx.AsyncClient):
    """Test 7: Verify POST /api/v1/assets/bulk-preview handles JSON array and intra-batch duplicates."""
    json_payload = {
        "import_type": "JSON",
        "raw_content": (
            '[\n'
            '  "https://id.empire.edu.vn",\n'
            '  "https://unique-sub-1.empire.edu.vn",\n'
            '  "https://unique-sub-1.empire.edu.vn"\n'
            ']'
        ),
    }
    resp = await client.post("/api/v1/assets/bulk-preview", json=json_payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 3
    assert len(data["new"]) == 1
    assert len(data["duplicate"]) == 2

    # One duplicate is from DB (id.empire.edu.vn), one duplicate is from intra-batch
    reasons = [d["reason"] for d in data["duplicate"]]
    assert any("registered in inventory" in r for r in reasons)
    assert any("within current import batch" in r for r in reasons)


@pytest.mark.asyncio
async def test_bulk_preview_openapi(client: httpx.AsyncClient):
    """Test 8: Verify POST /api/v1/assets/bulk-preview parses OpenAPI JSON servers."""
    openapi_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Empire Academic Gateway API", "version": "1.0.0"},
        "servers": [
            {"url": "https://gw.empire.edu.vn", "description": "Production Gateway API"},
            {"url": "https://api-sandbox.empire.edu.vn", "description": "Sandbox Gateway API"},
        ],
        "paths": {"/courses": {"get": {"summary": "List courses"}}},
    }
    import json
    payload = {
        "import_type": "OPENAPI",
        "raw_content": json.dumps(openapi_spec),
    }
    resp = await client.post("/api/v1/assets/bulk-preview", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 2
    # gw.empire.edu.vn is in DB (duplicate)
    assert len(data["duplicate"]) == 1
    assert "gw.empire.edu.vn" in data["duplicate"][0]["target_locator"]
    # api-sandbox.empire.edu.vn is new
    assert len(data["new"]) == 1
    assert "api-sandbox.empire.edu.vn" in data["new"][0]["target_locator"]
    assert data["new"][0]["asset_type"] == AssetType.API_ENDPOINT.value


@pytest.mark.asyncio
async def test_bulk_preview_cidr_and_ips(client: httpx.AsyncClient):
    """Test 9: Verify POST /api/v1/assets/bulk-preview handles CIDR and IP addresses."""
    payload = {
        "import_type": "TXT",
        "raw_content": (
            "160.191.101.79\n"  # Plain IP
            "10.200.0.0/24\n"   # Subnet CIDR
        ),
    }
    resp = await client.post("/api/v1/assets/bulk-preview", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total"] == 2
    types = [item["asset_type"] for item in data["new"]]
    assert all(t == AssetType.SERVER.value for t in types)

