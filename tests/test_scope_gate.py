import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict

import pytest
import pytest_asyncio
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.scope_gate import ScopeEnforcementError, ScopeValidator
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.models.asset import Asset
from backend.app.models.baseline import BaselineException
from backend.app.models.checklist import ChecklistResultState
from backend.app.models.scan import Scan
from backend.app.models.scope import AssetAssessmentScope
from backend.app.models.synthetic_identity import SyntheticIdentity
from backend.app.models.user import User, UserRole
from backend.app.scanners.file_policy import FilePolicyEngine
from backend.app.scanners.synthetic_harness import SyntheticTestHarness
from backend.app.schemas.common import ExposureClassification, ScanStatus, VerificationStatus


@pytest_asyncio.fixture
async def owner_headers(db_session: AsyncSession) -> Dict[str, str]:
    """Ensures sole owner in DB and returns valid bearer token headers."""
    owner_id = uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID)
    res = await db_session.execute(
        select(User).where(
            (User.id == owner_id) | (User.email == settings.SOLE_OWNER_EMAIL)
        )
    )
    user = res.scalars().first()
    if not user:
        user = User(
            id=owner_id,
            username="owner_scope_admin",
            email=settings.SOLE_OWNER_EMAIL,
            hashed_password=get_password_hash("ValidOwnerPassword123!"),
            role=UserRole.OWNER.value,
            is_active=True,
            is_superuser=True,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
    else:
        user.role = UserRole.OWNER.value
        user.is_active = True
        user.is_superuser = True
        await db_session.commit()

    token = create_access_token(
        subject=str(user.id),
        role=UserRole.OWNER.value,
        is_superuser=True,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_scope_validator_rejects_missing_scope(db_session: AsyncSession):
    """R2: Target asset without an authorized scope record is blocked by immutable scope gate."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Ungranted Asset",
        target_locator="https://ungranted.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)
    await db_session.commit()

    with pytest.raises(ScopeEnforcementError) as exc_info:
        await ScopeValidator.validate_preflight(asset.id, db=db_session)

    assert exc_info.value.status_code == 403
    assert exc_info.value.reason == "SCOPE_MISSING"
    assert "lacks an authorized customer scope record" in exc_info.value.detail


@pytest.mark.asyncio
async def test_scope_validator_rejects_expired_scope(db_session: AsyncSession):
    """R2: Target asset with an expired scope grant is blocked."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Expired Scope Asset",
        target_locator="https://expired.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    expired_scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin="https://expired.empire.edu.vn",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        emergency_stop_active=False,
    )
    db_session.add(expired_scope)
    await db_session.commit()

    with pytest.raises(ScopeEnforcementError) as exc_info:
        await ScopeValidator.validate_preflight(asset.id, db=db_session)

    assert exc_info.value.status_code == 403
    assert exc_info.value.reason == "SCOPE_EXPIRED"
    assert "expired" in exc_info.value.detail


@pytest.mark.asyncio
async def test_scope_validator_blocks_emergency_stop_active(db_session: AsyncSession):
    """R2: Scope with emergency_stop_active=True blocks all probe dispatch."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Emergency Stopped Asset",
        target_locator="https://stopped.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin="https://stopped.empire.edu.vn",
        emergency_stop_active=True,
    )
    db_session.add(scope)
    await db_session.commit()

    with pytest.raises(ScopeEnforcementError) as exc_info:
        await ScopeValidator.validate_preflight(asset.id, db=db_session)

    assert exc_info.value.status_code == 403
    assert exc_info.value.reason == "EMERGENCY_STOP_ACTIVE"
    assert "emergency stop is active" in exc_info.value.detail


@pytest.mark.asyncio
async def test_scope_validator_blocks_active_scans_on_unverified_target(db_session: AsyncSession):
    """R2: Active and destructive scans are blocked on unverified assets."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Unproven Target",
        target_locator="https://unproven.empire.edu.vn",
        verification_status=VerificationStatus.PENDING.value,
    )
    db_session.add(asset)

    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin="https://unproven.empire.edu.vn",
        emergency_stop_active=False,
    )
    db_session.add(scope)
    await db_session.commit()

    # Active probe on unverified asset MUST be blocked
    with pytest.raises(ScopeEnforcementError) as exc_info:
        await ScopeValidator.validate_preflight(asset.id, is_active_probe=True, db=db_session)

    assert exc_info.value.status_code == 403
    assert exc_info.value.reason == "ASSET_NOT_VERIFIED"
    assert "Active/destructive scans are strictly forbidden" in exc_info.value.detail


@pytest.mark.asyncio
async def test_scope_validator_blocks_ssrf_and_cloud_metadata(db_session: AsyncSession):
    """R2: SSRF boundaries reject cloud metadata, loopbacks, and private subnets."""
    # 1. Cloud metadata host
    asset_meta = Asset(
        id=uuid.uuid4(),
        name="Cloud Metadata Target",
        target_locator="http://169.254.169.254/latest/meta-data",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset_meta)
    scope_meta = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset_meta.id,
        exact_origin="http://169.254.169.254",
        emergency_stop_active=False,
    )
    db_session.add(scope_meta)
    await db_session.commit()

    with pytest.raises(ScopeEnforcementError) as exc_info:
        await ScopeValidator.validate_preflight(asset_meta.id, allow_private=False, db=db_session)

    assert exc_info.value.status_code == 403
    assert exc_info.value.reason == "SSRF_VIOLATION"

    # 2. Private IP subnet without allow_private
    asset_priv = Asset(
        id=uuid.uuid4(),
        name="Private RFC1918 Target",
        target_locator="http://192.168.1.100/admin",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset_priv)
    scope_priv = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset_priv.id,
        exact_origin="http://192.168.1.100",
        emergency_stop_active=False,
    )
    db_session.add(scope_priv)
    await db_session.commit()

    with pytest.raises(ScopeEnforcementError) as exc_info2:
        await ScopeValidator.validate_preflight(asset_priv.id, allow_private=False, db=db_session)

    assert exc_info2.value.status_code == 403
    assert exc_info2.value.reason == "SSRF_VIOLATION"


@pytest.mark.asyncio
async def test_scope_validator_origin_and_permitted_checks(db_session: AsyncSession):
    """R2: Scope validator enforces origin scheme/host and permitted checks boundary."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Scope Boundaries Asset",
        target_locator="https://boundary.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin="https://boundary.empire.edu.vn",
        permitted_checks=["WEB-001", "WEB-002", "API-001"],
        emergency_stop_active=False,
    )
    db_session.add(scope)
    await db_session.commit()

    # Disallowed check requested
    with pytest.raises(ScopeEnforcementError) as exc_info:
        await ScopeValidator.validate_preflight(
            asset.id,
            requested_checks=["WEB-001", "DEP-004"],
            db=db_session,
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.reason == "CHECKS_NOT_PERMITTED"

    # Origin scheme mismatch
    with pytest.raises(ScopeEnforcementError) as exc_info2:
        await ScopeValidator.validate_preflight(
            asset.id,
            target_url="http://boundary.empire.edu.vn/test",
            db=db_session,
        )
    assert exc_info2.value.status_code == 403
    assert exc_info2.value.reason == "ORIGIN_SCHEME_MISMATCH"


@pytest.mark.asyncio
async def test_budget_and_rate_limits(db_session: AsyncSession):
    """R2: Tests request budget and byte budget tracking."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Budget Target",
        target_locator="https://budget.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin="https://budget.empire.edu.vn",
        max_requests_per_run=50,
        byte_budget=1024 * 1024,  # 1MB
        emergency_stop_active=False,
    )
    db_session.add(scope)
    await db_session.commit()

    # Within budget
    assert await ScopeValidator.check_rate_and_budget(asset.id, request_count=20, bytes_count=50000, db=db_session) is True

    # Exceeds request count
    assert await ScopeValidator.check_rate_and_budget(asset.id, request_count=51, bytes_count=50000, db=db_session) is False

    # Exceeds byte budget
    assert await ScopeValidator.check_rate_and_budget(asset.id, request_count=20, bytes_count=2 * 1024 * 1024, db=db_session) is False


@pytest.mark.asyncio
async def test_target_emergency_stop_endpoint(
    client: httpx.AsyncClient, owner_headers: Dict[str, str], db_session: AsyncSession
):
    """R2: Target emergency stop POST /api/v1/assets/{id}/emergency-stop terminates scans and processes in < 3s."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Kill Switch Target",
        target_locator="https://killswitch.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin="https://killswitch.empire.edu.vn",
        emergency_stop_active=False,
    )
    db_session.add(scope)

    # Simulate an active running scan for this asset
    running_scan = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        target_locator=asset.target_locator,
        status=ScanStatus.RUNNING.value,
        profile="STANDARD",
    )
    db_session.add(running_scan)
    await db_session.commit()

    # Trigger emergency stop
    start_time = datetime.now(timezone.utc)
    resp = await client.post(f"/api/v1/assets/{asset.id}/emergency-stop", headers=owner_headers)
    duration_s = (datetime.now(timezone.utc) - start_time).total_seconds()

    assert resp.status_code == 200
    assert duration_s < 3.0  # Must terminate in < 3s
    data = resp.json()
    assert data["status"] == "EMERGENCY_STOP_ACTIVATED"
    assert data["emergency_stop_active"] is True
    assert data["halted_scans_count"] >= 1

    # Verify scope and scan status in DB
    await db_session.refresh(scope)
    await db_session.refresh(running_scan)
    assert scope.emergency_stop_active is True
    assert running_scan.status == ScanStatus.CANCELLED.value
    assert "emergency stop triggered" in (running_scan.cancellation_reason or "")


@pytest.mark.asyncio
async def test_synthetic_harness_marks_blocked_when_credentials_missing(db_session: AsyncSession):
    """R4: Custom synthetic test harness marks checks BLOCKED when accounts/credentials are missing."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Harness Target",
        target_locator="https://harness.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    # Deactivate all student identities to simulate missing test accounts
    res = await db_session.execute(select(SyntheticIdentity))
    for ident in res.scalars().all():
        ident.is_active = False
    await db_session.commit()

    harness = SyntheticTestHarness()

    # 1. BOLA (API-001) evaluation with missing credentials MUST be BLOCKED (never PASS)
    bola_res = await harness.evaluate_bola(asset, db_session)
    assert bola_res["check_id"] == "API-001"
    assert bola_res["state"] == ChecklistResultState.BLOCKED.value
    assert "Missing required synthetic student identities" in bola_res["evidence_payload"]["reason"]

    # 2. BFLA (API-005) evaluation with missing credentials MUST be BLOCKED (never PASS)
    bfla_res = await harness.evaluate_bfla(asset, db_session)
    assert bfla_res["check_id"] == "API-005"
    assert bfla_res["state"] == ChecklistResultState.BLOCKED.value
    assert "Missing synthetic student identity" in bfla_res["evidence_payload"]["reason"]


@pytest.mark.asyncio
async def test_file_policy_approved_media_and_sensitive_leaks(db_session: AsyncSession):
    """R4: File policy engine evaluates educational media to PASS under PUBLIC_BY_DESIGN and sensitive leaks to FAIL."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Media Policy Target",
        target_locator="https://mh.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    # Ensure baseline exception for PUBLIC_BY_DESIGN exists
    base_res = await db_session.execute(
        select(BaselineException).where(
            BaselineException.scope.like("%/media/%"),
            BaselineException.classification == ExposureClassification.PUBLIC_BY_DESIGN.value,
        )
    )
    existing_base = base_res.scalars().first()
    if not existing_base:
        existing_base = BaselineException(
            id=uuid.uuid4(),
            scope="https://mh.empire.edu.vn/media/*",
            classification=ExposureClassification.PUBLIC_BY_DESIGN.value,
            reason="Approved open-access educational course materials and syllabus PDFs",
            is_active=True,
        )
        db_session.add(existing_base)
        await db_session.commit()

    engine = FilePolicyEngine()

    # 1. FILE-001: Approved media evaluated against PUBLIC_BY_DESIGN yields PASS
    file_001_res = await engine.evaluate_approved_media(asset, db_session)
    assert file_001_res["check_id"] == "FILE-001"
    assert file_001_res["state"] == ChecklistResultState.PASS.value
    assert file_001_res["evidence_payload"]["policy"] == "PUBLIC_BY_DESIGN"

    # 2. FILE-002: Probing sensitive leaks
    file_002_res = await engine.evaluate_sensitive_file_leaks(asset, db_session)
    assert file_002_res["check_id"] == "FILE-002"
    # Either PASS (if denied/unreachable) or FAIL (if sensitive content found)
    assert file_002_res["state"] in (ChecklistResultState.PASS.value, ChecklistResultState.FAIL.value)
