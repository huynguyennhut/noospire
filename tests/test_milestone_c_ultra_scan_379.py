"""Comprehensive Test Suite for Milestone 3: Ultra Scan Inventory Accounting & Scanner Intelligence.

Covers:
1. Exact Numerical Accounting of 379 Inventory Items:
   - 379 Accounted Inventory Rows
   - 368 Independent Execution Targets (350 Web, 10 API, 8 Artifacts)
   - 728 Total Engine Executions (350x2 Web, 10x2 API, 8x1 Artifact)
   - 6 Equivalent Shared Result Links (Aliases)
   - 5 Explained Exclusions (Out of Scope, 0 requests)
2. Post-Snapshot Inventory Addition (380th Target Isolation & Immutability).
3. Ultra Scan Fixture REST Endpoint (GET /api/v1/scans/ultra/fixture-379).
4. Ultra Scan Dispatch, DB Persistence & Idempotency Key Recovery.
5. Strict Sole-Owner Authorization Enforcement on Estate-Wide Ultra Scan.
6. Empire Scanner False-Positive Defenses:
   - Catch-all 200 HTML responses produce 0 BOLA, 0 BFLA, and 0 media leaks.
   - 5 consecutive 404 responses produce 0 brute force / auth lockout findings.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import uuid
import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from backend.main import app
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal, init_db
from backend.app.core.security import create_access_token
from backend.app.core.ultra_planner import (
    InventoryRowClassification,
    UltraScanPlanner,
    ultra_planner,
)
from backend.app.models.asset import Asset
from backend.app.models.scan import Scan, ScanBatch
from backend.app.models.user import User, UserRole
from backend.app.scanners.empire_engine import EmpireAssessmentEngine
from backend.app.schemas.common import (
    AssetType,
    EmpireModule,
    ScanProfile,
    ScanStatus,
    VerificationStatus,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()


async def get_test_token(db, role: str, email: str = None) -> str:
    user_email = email or f"{role.lower()}_{uuid.uuid4().hex[:8]}@empire.local"
    res = await db.execute(select(User).where(User.email == user_email))
    user = res.scalars().first()
    if not user:
        user = User(
            id=uuid.uuid4(),
            username=user_email,
            email=user_email,
            hashed_password="test_hashed_password",
            role=role,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return create_access_token(subject=user.username, role=user.role)


@pytest.mark.asyncio
async def test_numerical_379_inventory_accounting():
    """Validates the exact 379-item inventory breakdown:
    - 379 Accounted Inventory Rows
    - 368 Independent Execution Targets
    - 728 Engine Executions
    - 6 Shared Result Links
    - 5 Explained Exclusions generating 0 requests
    """
    planner = UltraScanPlanner()
    items = planner.generate_acceptance_fixture_379()
    assert len(items) == 379

    plan = planner.plan_inventory(items)

    assert plan.accounted_inventory_rows == 379
    assert plan.independent_execution_targets == 368
    assert plan.engine_executions_count == 728
    assert plan.shared_alias_count == 6
    assert plan.excluded_count == 5

    assert len(plan.shared_result_links) == 6
    assert len(plan.explained_exclusions) == 5

    # Check breakdown of classifications
    web_targets = [r for r in plan.inventory_entries if r.asset_type == "WEB_APP" and r.classification == InventoryRowClassification.EXECUTION_TARGET]
    api_targets = [r for r in plan.inventory_entries if r.asset_type == "API_ENDPOINT" and r.classification == InventoryRowClassification.EXECUTION_TARGET]
    art_targets = [r for r in plan.inventory_entries if r.asset_type == "CONTAINER_IMAGE" and r.classification == InventoryRowClassification.EXECUTION_TARGET]

    assert len(web_targets) == 350
    assert len(api_targets) == 10
    assert len(art_targets) == 8

    # Check engine allocation
    for row in web_targets:
        assert set(row.planned_engines) == {"nuclei", "zap"}
        assert len(row.child_executions) == 2

    for row in api_targets:
        assert set(row.planned_engines) == {"nuclei", "empire"}
        assert len(row.child_executions) == 2

    for row in art_targets:
        assert set(row.planned_engines) == {"trivy"}
        assert len(row.child_executions) == 1

    # Total engine executions: (350 * 2) + (10 * 2) + (8 * 1) = 700 + 20 + 8 = 728
    total_execs = sum(len(r.child_executions) for r in plan.inventory_entries)
    assert total_execs == 728
    assert len(plan.all_executions) == 728

    # Excluded items must have 0 planned engines and 0 executions
    excluded_rows = [r for r in plan.inventory_entries if r.classification == InventoryRowClassification.EXCLUDED]
    assert len(excluded_rows) == 5
    for excl in excluded_rows:
        assert len(excl.planned_engines) == 0
        assert len(excl.child_executions) == 0
        assert excl.exclusion_reason is not None

    # Alias items must link to alias targets and have 0 independent executions
    alias_rows = [r for r in plan.inventory_entries if r.classification == InventoryRowClassification.ALIAS]
    assert len(alias_rows) == 6
    for alias in alias_rows:
        assert len(alias.planned_engines) == 0
        assert len(alias.child_executions) == 0
        assert alias.alias_of_target_id is not None


@pytest.mark.asyncio
async def test_post_snapshot_inventory_addition_does_not_mutate_batch():
    """Verify snapshot immutability: adding a 380th asset after plan snapshot creation
    does not alter the existing batch. The 380th item appears on the subsequent run.
    """
    planner = UltraScanPlanner()
    items = planner.generate_acceptance_fixture_379()
    batch_1_plan = planner.plan_inventory(items, batch_id="batch-001")

    assert batch_1_plan.accounted_inventory_rows == 379
    assert batch_1_plan.independent_execution_targets == 368
    assert batch_1_plan.engine_executions_count == 728

    # Add 380th asset to inventory items
    items_with_380 = list(items)
    items_with_380.append({
        "id": str(uuid.uuid4()),
        "target_locator": "https://newly-deployed-module.empire.edu.vn",
        "asset_type": "WEB_APP",
        "is_out_of_scope": False,
        "is_alias": False,
        "environment": "PRODUCTION",
    })
    assert len(items_with_380) == 380

    # Ensure previous snapshot batch_1_plan remains untouched
    assert batch_1_plan.accounted_inventory_rows == 379
    assert batch_1_plan.engine_executions_count == 728

    # Subsequent run incorporates the 380th target
    batch_2_plan = planner.plan_inventory(items_with_380, batch_id="batch-002")
    assert batch_2_plan.accounted_inventory_rows == 380
    assert batch_2_plan.independent_execution_targets == 369
    assert batch_2_plan.engine_executions_count == 730  # 728 + 2 (nuclei + zap for web app)


@pytest.mark.asyncio
async def test_ultra_scan_fixture_endpoint():
    """Verifies GET /api/v1/scans/ultra/fixture-379 returns correct numerical structure."""
    async with AsyncSessionLocal() as db:
        token = await get_test_token(db, role=UserRole.VIEWER.value)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(
            "/api/v1/scans/ultra/fixture-379",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["accounted_inventory_rows"] == 379
        assert data["independent_execution_targets"] == 368
        assert data["engine_executions_count"] == 728
        assert data["shared_alias_count"] == 6
        assert data["excluded_count"] == 5
        assert len(data["items"]) == 379
        assert len(data["shared_result_links"]) == 6
        assert len(data["explained_exclusions"]) == 5


@pytest.mark.asyncio
async def test_ultra_scan_dispatch_and_idempotency_recovery():
    """Verifies POST /api/v1/scans/ultra dispatches a durable batch and supports
    idempotent recovery via Idempotency-Key.
    """
    async with AsyncSessionLocal() as db:
        owner_email = settings.SOLE_OWNER_EMAIL
        token = await get_test_token(db, role=UserRole.OWNER.value, email=owner_email)

    idemp_key = f"ultra-test-{uuid.uuid4().hex[:12]}"
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Initial Dispatch
        resp1 = await client.post(
            "/api/v1/scans/ultra",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idemp_key,
            },
            json={
                "scope": "FIXTURE_379",
                "profile": "STANDARD",
                "engines": ["nuclei", "zap"],
            },
        )
        assert resp1.status_code == 201, resp1.text
        data1 = resp1.json()
        batch_id = data1["batch_id"]
        assert data1["idempotency_recovered"] is False
        assert data1["accounted_inventory_rows"] == 379
        assert "/active-assessments?batch_id=" in data1["tracker_link"]

        # 2. Idempotent Retry with identical key
        resp2 = await client.post(
            "/api/v1/scans/ultra",
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": idemp_key,
            },
            json={
                "scope": "FIXTURE_379",
                "profile": "STANDARD",
                "engines": ["nuclei", "zap"],
            },
        )
        assert resp2.status_code == 201, resp2.text
        data2 = resp2.json()
        assert data2["batch_id"] == batch_id
        assert data2["idempotency_recovered"] is True
        assert "Idempotent recovery" in data2["message"]

    # Verify DB persistence of batch and child scans
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(ScanBatch).where(ScanBatch.id == uuid.UUID(batch_id)))
        batch = res.scalars().first()
        assert batch is not None
        assert batch.idempotency_key == idemp_key
        assert batch.target_count == 368


@pytest.mark.asyncio
async def test_ultra_scan_owner_rbac_enforcement():
    """Estate-wide Ultra Scan is strictly restricted to the sole system owner."""
    async with AsyncSessionLocal() as db:
        # Standard operator who is NOT the sole owner
        operator_token = await get_test_token(db, role=UserRole.OPERATOR.value, email="regular_op@empire.local")
        # Sole owner
        owner_token = await get_test_token(db, role=UserRole.OWNER.value, email=settings.SOLE_OWNER_EMAIL)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Non-owner operator gets 403 Forbidden
        resp_forbidden = await client.post(
            "/api/v1/scans/ultra",
            headers={"Authorization": f"Bearer {operator_token}"},
            json={"scope": "ALL"},
        )
        assert resp_forbidden.status_code == 403
        assert "restricted solely to the system owner" in resp_forbidden.text

        # Sole owner succeeds
        resp_success = await client.post(
            "/api/v1/scans/ultra",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"scope": "FIXTURE_379"},
        )
        assert resp_success.status_code == 201


@pytest.mark.asyncio
async def test_empire_scanner_false_positive_defenses():
    """Verifies that:
    1. Catch-all HTML 200 responses produce 0 BOLA, 0 BFLA, and 0 media leaks.
    2. 5 consecutive 404 responses produce 0 brute force / auth lockout findings.
    """
    engine = EmpireAssessmentEngine()
    asset_id = uuid.uuid4()
    scan_id = uuid.uuid4()

    # Case 1: Target returns generic SPA / Catch-all HTML 200
    catch_all_html = """<!DOCTYPE html>
    <html lang="en">
    <head><title>Empire Learning Portal</title></head>
    <body>
        <div id="root">
            <h1>Page Not Found or Generic Application Shell</h1>
            <p>Welcome to Empire Education. Please log in or navigate back.</p>
        </div>
    </body>
    </html>"""

    def mock_catch_all_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=catch_all_html, headers={"Content-Type": "text/html; charset=utf-8"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_catch_all_handler))

    async def dummy_log_cb(src: str, msg: str, lvl: str = "INFO"):
        pass

    findings_catch_all = await engine.execute_empire_assessment(
        asset_id=asset_id,
        scan_id=scan_id,
        target_locator="https://gw.empire.edu.vn",
        empire_module="ALL",
        profile=ScanProfile.DAILY_SECURITY.value,
        log_cb=dummy_log_cb,
        http_client=mock_client,
    )
    # Must produce 0 BOLA, 0 BFLA, 0 media leak findings
    leak_titles = [f.title for f in findings_catch_all if any(kw in f.title.lower() for kw in ["bola", "bfla", "media leak", "unauthorized"])]
    assert len(leak_titles) == 0, f"Expected 0 leak findings from catch-all HTML, found: {leak_titles}"

    # Case 2: Target returns 404 Not Found on 5 consecutive login probes
    def mock_404_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found", "status": 404})

    mock_404_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_404_handler))

    findings_404 = await engine.execute_empire_assessment(
        asset_id=asset_id,
        scan_id=scan_id,
        target_locator="https://id.empire.edu.vn",
        empire_module=EmpireModule.STUDENT_MANAGEMENT.value,
        profile=ScanProfile.DAILY_SECURITY.value,
        log_cb=dummy_log_cb,
        http_client=mock_404_client,
    )
    # Must produce 0 brute force findings
    brute_findings = [f.title for f in findings_404 if "brute" in f.title.lower() or "lockout" in f.title.lower()]
    assert len(brute_findings) == 0, f"Expected 0 brute-force findings from 404 responses, got: {brute_findings}"
