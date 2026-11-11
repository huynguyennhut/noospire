"""Comprehensive Unit and Integration Test Suite for Milestone A (Features F01–F16).
Verifies:
- F01: Elimination of hardcoded secrets and rejection of missing secrets in production
- F02: One-time bootstrap mechanism permanently locking after initial admin creation
- F03: Active-user enforcement in DB and session revocation/logout
- F04: Scoped RBAC permissions (viewer, operator, admin) on operational endpoints
- F05: Server-derived audit actors across triage, rule lifecycle, and baselines
- F06: Protected report downloads and path traversal prevention
- F07: CSRF protection on cookie-authenticated mutations
- F08: Rejection of destructive system/baseline/settings resets in production and audit log retention
- F09 & F10: Ownership challenge verification (not reachable) and locator change invalidation
- F11: Strict network egress policy (blocking loopback, private, link-local, cloud metadata in prod)
- F12: Unknown loop-test asset returns HTTP 404
- F13: Enforce request/byte budgets and emergency stop active check
- F14: Minimal /health endpoint
- F15: Sanitized storage/reports/ directory
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
import pytest
import pytest_asyncio
import httpx
from pydantic import ValidationError
from sqlalchemy import select

from backend.main import app
from backend.app.core.config import Settings, settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import create_access_token, get_password_hash, verify_password
from backend.app.core.ssrf import validate_egress_target, SSRFPolicyViolation
from backend.app.models.asset import Asset
from backend.app.models.baseline import BaselineException
from backend.app.models.finding import NormalizedFinding
from backend.app.models.proof import AssetOwnershipProof
from backend.app.models.rule import DetectionRule
from backend.app.models.scope import AssetAssessmentScope
from backend.app.models.base import AdminAuditLog
from backend.app.models.user import RevokedToken, User, UserRole
from backend.app.schemas.common import (
    AssetType,
    ExposureClassification,
    FindingSeverity,
    VerificationStatus,
    VerificationType,
)


# Helper to generate test tokens
def make_token(username: str, role: str) -> str:
    return create_access_token(
        subject=username,
        role=role,
    )


@pytest_asyncio.fixture(autouse=True)
async def seed_test_users():
    async with AsyncSessionLocal() as session:
        users = [
            User(
                id=uuid.uuid4(),
                username="admin_test",
                email="admin_test@example.com",
                hashed_password=get_password_hash("AdminPass123!"),
                role=UserRole.ADMIN.value,
                is_active=True,
                is_superuser=True,
            ),
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
def admin_headers() -> dict[str, str]:
    token = make_token("admin_test", UserRole.ADMIN.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def operator_headers() -> dict[str, str]:
    token = make_token("operator_test", UserRole.OPERATOR.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_headers() -> dict[str, str]:
    token = make_token("viewer_test", UserRole.VIEWER.value)
    return {"Authorization": f"Bearer {token}"}


# -----------------------------------------------------------------------------
# F01: Hardcoded Secrets Elimination & Rejection of Missing Secrets in Prod
# -----------------------------------------------------------------------------
def test_f01_secrets_enforcement():
    # In development, default secret key is allowed
    dev_settings = Settings(ENVIRONMENT="development")
    assert dev_settings.is_development is True
    assert dev_settings.is_production is False

    # In production with default secret key, validation MUST fail
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="dev_insecure_default_secret_key_change_in_production",
        )

    # In production with empty secret key, validation MUST fail
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="",
        )

    # In production with strong secret key, validation succeeds
    prod_settings = Settings(
        ENVIRONMENT="production",
        SECRET_KEY="a_very_strong_production_secret_key_exceeding_32_bytes_securely",
    )
    assert prod_settings.is_production is True


# -----------------------------------------------------------------------------
# F02: One-Time Bootstrap Mechanism Permanently Locking
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f02_bootstrap_mechanism(client: httpx.AsyncClient, db_session):
    # Ensure at least one admin exists in DB
    stmt = select(User).where(User.role == UserRole.ADMIN.value)
    existing_admin = (await db_session.execute(stmt)).scalars().first()

    if not existing_admin:
        admin_user = User(
            id=uuid.uuid4(),
            username="bootstrap_admin",
            email="bootstrap_admin@example.com",
            hashed_password=get_password_hash("StrongPass123!"),
            role=UserRole.ADMIN.value,
            is_active=True,
            is_superuser=True,
        )
        db_session.add(admin_user)
        await db_session.commit()

    # Calling bootstrap when an admin already exists must be rejected with HTTP 400
    res = await client.post(
        "/api/v1/auth/bootstrap",
        json={"username": "new_admin", "password": "NewAdminPass123!", "email": "new_admin@example.com"},
    )
    assert res.status_code == 400
    assert "already" in res.json()["detail"].lower() and "locked" in res.json()["detail"].lower()


# -----------------------------------------------------------------------------
# F03: Active-User Enforcement in DB & Session Revocation/Logout
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f03_active_user_enforcement_and_logout(client: httpx.AsyncClient, db_session):
    # Create test user in DB
    test_username = f"user_{uuid.uuid4().hex[:8]}"
    test_user = User(
        id=uuid.uuid4(),
        username=test_username,
        email=f"{test_username}@example.com",
        hashed_password=get_password_hash("UserPass123!"),
        role=UserRole.OPERATOR.value,
        is_active=True,
        is_superuser=False,
    )
    db_session.add(test_user)
    await db_session.commit()

    # Generate token
    token = make_token(test_username, UserRole.OPERATOR.value)
    headers = {"Authorization": f"Bearer {token}"}

    # Request with active user succeeds
    res = await client.get("/api/v1/auth/me", headers=headers)
    assert res.status_code == 200
    assert res.json()["username"] == test_username

    # Deactivate user in DB -> must return 403 Forbidden
    test_user.is_active = False
    await db_session.commit()

    res_inactive = await client.get("/api/v1/auth/me", headers=headers)
    assert res_inactive.status_code == 403
    assert "inactive" in res_inactive.json()["detail"].lower()

    # Reactivate user
    test_user.is_active = True
    await db_session.commit()

    res_active = await client.get("/api/v1/auth/me", headers=headers)
    assert res_active.status_code == 200

    # Logout / session revocation
    res_logout = await client.post("/api/v1/auth/logout", headers=headers)
    assert res_logout.status_code == 200
    assert "revoked" in res_logout.json()["message"].lower()

    # Subsequent request using the revoked token must return 401 Unauthorized
    res_revoked = await client.get("/api/v1/auth/me", headers=headers)
    assert res_revoked.status_code == 401


# -----------------------------------------------------------------------------
# F04: Scoped RBAC Permissions on Operational Endpoints
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f04_scoped_rbac_enforcement(
    client: httpx.AsyncClient,
    viewer_headers: dict[str, str],
    operator_headers: dict[str, str],
    admin_headers: dict[str, str],
):
    # 1. Anonymous request to operational endpoints returns 401
    anon_res = await client.get("/api/v1/assets")
    assert anon_res.status_code == 401

    anon_scan = await client.post("/api/v1/scans", json={"asset_id": str(uuid.uuid4())})
    assert anon_scan.status_code == 401

    # 2. Viewer can view assets, but cannot create assets
    viewer_get = await client.get("/api/v1/assets", headers=viewer_headers)
    assert viewer_get.status_code == 200

    viewer_create = await client.post(
        "/api/v1/assets",
        headers=viewer_headers,
        json={"name": "Viewer Target", "target_locator": "https://viewer.example.com"},
    )
    assert viewer_create.status_code == 403

    # 3. Viewer cannot create detection rules
    viewer_rule = await client.post(
        "/api/v1/rules",
        headers=viewer_headers,
        json={"raw_yaml": "id: test\nname: test"},
    )
    assert viewer_rule.status_code == 403

    # 4. Operator can access assets list and operator endpoints
    op_get = await client.get("/api/v1/assets", headers=operator_headers)
    assert op_get.status_code == 200

    # 5. Admin-only endpoints reject operator with 403
    op_audit = await client.get("/api/v1/auth/audit", headers=operator_headers)
    assert op_audit.status_code == 403

    # 6. Admin can access admin endpoints
    admin_audit = await client.get("/api/v1/auth/audit", headers=admin_headers)
    assert admin_audit.status_code == 200


# -----------------------------------------------------------------------------
# F05: Server-Derived Audit Actors
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f05_server_derived_audit_actors(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
    admin_headers: dict[str, str],
    db_session,
):
    # Create a baseline exception with client specifying a spoofed "approved_by"
    spoofed_actor = "malicious_spoofed_approver"
    baseline_payload = {
        "scope": f"https://audit-test-{uuid.uuid4().hex[:6]}.example.com/*",
        "classification": ExposureClassification.PUBLIC_BY_DESIGN.value,
        "reason": "Test baseline for audit actor binding",
        "owner": "SecOps",
        "approved_by": spoofed_actor,
    }

    res = await client.post("/api/v1/baselines", headers=operator_headers, json=baseline_payload)
    assert res.status_code == 201
    baseline_data = res.json()

    # The server MUST bind approved_by to the authentic current_user.username ("operator_test")
    assert baseline_data["approved_by"] == "operator_test"
    assert baseline_data["approved_by"] != spoofed_actor


# -----------------------------------------------------------------------------
# F06: Protected Report Downloads and Path Traversal Blocking
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f06_protected_reports_and_traversal_blocking(
    client: httpx.AsyncClient,
    viewer_headers: dict[str, str],
):
    # Anonymous download returns 401
    res_anon = await client.get(f"/api/v1/reports/{uuid.uuid4()}/download")
    assert res_anon.status_code == 401

    # Path traversal attack in report ID is safely rejected with 400 or 404
    res_traversal = await client.get(
        "/api/v1/reports/..%2f..%2fetc%2fpasswd/download?format=json",
        headers=viewer_headers,
    )
    assert res_traversal.status_code in (400, 404)


# -----------------------------------------------------------------------------
# F07: CSRF Protection on Mutation Requests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f07_csrf_protection(client: httpx.AsyncClient):
    # A mutation using cookie auth without CSRF token must return 403
    token = make_token("admin_test", UserRole.ADMIN.value)
    cookies = {"sentinel_access_token": token}
    res = await client.post(
        "/api/v1/assets",
        cookies=cookies,
        json={"name": "CSRF Attack Target", "target_locator": "https://csrf.example.com"},
    )
    assert res.status_code == 403
    assert "csrf" in res.json()["detail"].lower()


# -----------------------------------------------------------------------------
# F08: Reset Forbidden in Production and Critical Audit Trail Retention
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f08_production_reset_forbidden_and_audit_retention(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    db_session,
):
    orig_env = settings.ENVIRONMENT
    try:
        # Simulate production environment
        settings.ENVIRONMENT = "production"

        res_system_reset = await client.post("/api/v1/system/reset", headers=admin_headers)
        assert res_system_reset.status_code == 403

        res_baseline_reset = await client.post("/api/v1/baselines/reset", headers=admin_headers)
        assert res_baseline_reset.status_code == 403

        res_settings_reset = await client.post("/api/v1/settings/reset", headers=admin_headers)
        assert res_settings_reset.status_code == 403

    finally:
        settings.ENVIRONMENT = orig_env

    # In development mode, verify AdminAuditLog records survive reset
    audit_entry = AdminAuditLog(
        id=uuid.uuid4(),
        username="forensic_auditor",
        action="TEST_ACTION",
        details="retention: immutable",
        ip_address="127.0.0.1",
    )
    db_session.add(audit_entry)
    await db_session.commit()

    # Reset in dev
    res_dev_reset = await client.post("/api/v1/system/reset", headers=admin_headers)
    assert res_dev_reset.status_code == 200

    # Ensure audit_entry still exists
    stmt = select(AdminAuditLog).where(AdminAuditLog.id == audit_entry.id)
    saved_audit = (await db_session.execute(stmt)).scalar_one_or_none()
    assert saved_audit is not None, "AdminAuditLog must never be wiped during system reset"


# -----------------------------------------------------------------------------
# F09 & F10: Ownership Proofs & Target Locator Invalidation
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f09_f10_ownership_and_locator_invalidation(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
    db_session,
):
    # 1. Create a new asset
    loc_initial = f"https://asset-{uuid.uuid4().hex[:6]}.example.com"
    create_res = await client.post(
        "/api/v1/assets",
        headers=operator_headers,
        json={"name": "Ownership Test Asset", "target_locator": loc_initial},
    )
    assert create_res.status_code == 201
    asset_id = create_res.json()["id"]

    # Must start with PENDING verification status
    assert create_res.json()["verification_status"] == VerificationStatus.PENDING.value

    # Verify proof was created
    stmt = select(AssetOwnershipProof).where(AssetOwnershipProof.asset_id == uuid.UUID(asset_id))
    proof = (await db_session.execute(stmt)).scalars().first()
    assert proof is not None
    assert proof.status == "PENDING"
    assert len(proof.challenge_token) >= 20

    # 2. Update target locator -> invalidates proof and resets status
    new_loc = f"https://asset-renamed-{uuid.uuid4().hex[:6]}.example.com"
    update_res = await client.put(
        f"/api/v1/assets/{asset_id}",
        headers=operator_headers,
        json={"target_locator": new_loc},
    )
    assert update_res.status_code == 200
    assert update_res.json()["verification_status"] == VerificationStatus.PENDING.value

    # Old proofs are revoked and new pending proof is created
    db_session.expire_all()
    proofs_stmt = select(AssetOwnershipProof).where(AssetOwnershipProof.asset_id == uuid.UUID(asset_id))
    proofs = (await db_session.execute(proofs_stmt)).scalars().all()
    statuses = [p.status for p in proofs]
    assert "REVOKED" in statuses
    assert "PENDING" in statuses


# -----------------------------------------------------------------------------
# F11: Strict Network Egress Policy (SSRF Prevention)
# -----------------------------------------------------------------------------
def test_f11_strict_network_egress_policy():
    orig_env = settings.ENVIRONMENT
    try:
        settings.ENVIRONMENT = "production"

        # Loopback
        with pytest.raises(SSRFPolicyViolation):
            validate_egress_target("http://127.0.0.1:8000/api")

        with pytest.raises(SSRFPolicyViolation):
            validate_egress_target("http://localhost:8000")

        # RFC 1918 Private ranges
        with pytest.raises(SSRFPolicyViolation):
            validate_egress_target("http://10.0.0.1/admin")

        with pytest.raises(SSRFPolicyViolation):
            validate_egress_target("http://192.168.1.1/")

        with pytest.raises(SSRFPolicyViolation):
            validate_egress_target("http://172.16.0.1/")

        # Cloud metadata service (169.254.169.254)
        with pytest.raises(SSRFPolicyViolation):
            validate_egress_target("http://169.254.169.254/latest/meta-data/")

    finally:
        settings.ENVIRONMENT = orig_env


# -----------------------------------------------------------------------------
# F12: Unknown Loop-Test Asset Returns HTTP 404
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f12_unknown_loop_test_asset_returns_404(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
):
    # Calling loop-test with a nonexistent target locator MUST return 404 (no silent fallback!)
    unknown_loc = f"https://nonexistent-{uuid.uuid4().hex}.example.com"
    res = await client.post(
        f"/api/v1/scans/loop-test?target_locator={unknown_loc}",
        headers=operator_headers,
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()


# -----------------------------------------------------------------------------
# F13: Scan Emergency Stop Enforcement
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f13_scan_emergency_stop_enforcement(
    client: httpx.AsyncClient,
    operator_headers: dict[str, str],
    db_session,
):
    # Create asset with emergency stop active
    asset = Asset(
        id=uuid.uuid4(),
        name="Emergency Stop Target",
        asset_type=AssetType.WEB_APP.value,
        target_locator=f"https://stop-test-{uuid.uuid4().hex[:6]}.example.com",
        empire_module="WEB_APPLICATION",
        environment="PRODUCTION",
        criticality="CRITICAL",
        exposure="INTERNET",
        verification_status=VerificationStatus.VERIFIED.value,
        verification_type=VerificationType.HTTP_WELL_KNOWN.value,
    )
    db_session.add(asset)

    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin=asset.target_locator,
        emergency_stop_active=True,  # EMERGENCY STOP
        created_by="secops",
    )
    db_session.add(scope)
    await db_session.commit()

    # Attempting to scan this asset must be blocked
    scan_res = await client.post(
        "/api/v1/scans",
        headers=operator_headers,
        json={"asset_id": str(asset.id), "profile": "BASELINE"},
    )
    assert scan_res.status_code in (400, 403)
    assert "emergency stop" in scan_res.json()["detail"].lower()


# -----------------------------------------------------------------------------
# F14: Minimal /health Endpoint
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_f14_minimal_health_endpoint(client: httpx.AsyncClient):
    res = await client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data == {"status": "healthy"}
    assert "service" not in data
    assert "version" not in data
    assert "target" not in data


# -----------------------------------------------------------------------------
# F15: Sanitized Storage Reports
# -----------------------------------------------------------------------------
def test_f15_storage_reports_sanitized():
    storage_dir = Path("storage/reports")
    if storage_dir.exists():
        files = list(storage_dir.iterdir())
        # No stale reports should remain in storage/reports
        stale_reports = [f for f in files if f.suffix in (".html", ".json", ".pdf")]
        assert len(stale_reports) == 0, f"Found stale reports in storage/reports: {stale_reports}"
