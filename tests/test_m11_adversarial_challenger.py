"""Adversarial Verification Test Suite for Milestone 11 (Empire Pentest Backend).

Challenger: teamwork_preview_challenger_m11_m13_1
Adversarial Verification Scope:
1. State Invariant Guards (attempt invalid transitions from NOT_RUN, BLOCKED, ERROR to PASS)
2. Customer Scope Authorization Gate (missing scope, expired scope, active emergency stop, unverified asset, SSRF egress)
3. Custom Synthetic Test Harness (verify BLOCKED when credentials missing or insufficient)
4. Target-Level Emergency Stop (verify speed < 3s, process termination, state update, subsequent block)
"""

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.scope_gate import ScopeEnforcementError, ScopeValidator
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.core.ssrf import SSRFProtector, SSRFValidationError
from backend.app.models.asset import Asset
from backend.app.models.checklist import (
    ChecklistAssessmentRun,
    ChecklistCategory,
    ChecklistDefinition,
    ChecklistResult,
    ChecklistResultState,
    UNVERIFIED_STATES_CANNOT_PASS,
    validate_state_transition,
)
from backend.app.models.scan import Scan
from backend.app.models.scope import AssetAssessmentScope
from backend.app.models.synthetic_identity import SyntheticIdentity
from backend.app.models.user import User, UserRole
from backend.app.scanners.synthetic_harness import SyntheticTestHarness
from backend.app.schemas.common import ScanStatus, VerificationStatus


@pytest_asyncio.fixture
async def challenger_owner_headers(db_session: AsyncSession) -> Dict[str, str]:
    """Ensures sole owner exists in database and returns valid bearer token headers."""
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
            username="owner_challenger_admin",
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


# ==============================================================================
# TASK 1: STATE INVARIANTS ADVERSARIAL PROBES
# ==============================================================================


@pytest.mark.asyncio
async def test_adversarial_state_invariants_direct():
    """Task 1: Verify validate_state_transition strictly forbids unverified states from transitioning to PASS."""
    # 1. Direct unverified transitions to PASS must raise ValueError
    for forbidden_state in UNVERIFIED_STATES_CANNOT_PASS:
        with pytest.raises(ValueError) as exc_info:
            validate_state_transition(forbidden_state, ChecklistResultState.PASS.value)
        assert "State invariant violation" in str(exc_info.value)
        assert forbidden_state in str(exc_info.value)

    # 2. Permitted valid transitions must succeed without exception
    permitted_transitions = [
        ("NOT_RUN", "FAIL"),
        ("NOT_RUN", "NEEDS_REVIEW"),
        ("NOT_RUN", "BLOCKED"),
        ("NOT_RUN", "NOT_APPLICABLE"),
        ("NEEDS_REVIEW", "PASS"),
        ("FAIL", "PASS"),
        ("NOT_APPLICABLE", "PASS"),
        ("PASS", "PASS"),
        ("BLOCKED", "NEEDS_REVIEW"),
        ("ERROR", "NEEDS_REVIEW"),
    ]
    for src, dst in permitted_transitions:
        validate_state_transition(src, dst)

    # 3. Verify transition_state method on ChecklistResult model enforces invariant
    dummy_run_id = uuid.uuid4()
    cr = ChecklistResult(
        id=uuid.uuid4(),
        run_id=dummy_run_id,
        check_id="WEB-001",
        state=ChecklistResultState.NOT_RUN.value,
    )

    with pytest.raises(ValueError, match="State invariant violation"):
        cr.transition_state(ChecklistResultState.PASS)

    cr.state = ChecklistResultState.BLOCKED.value
    with pytest.raises(ValueError, match="State invariant violation"):
        cr.transition_state(ChecklistResultState.PASS)

    cr.state = ChecklistResultState.ERROR.value
    with pytest.raises(ValueError, match="State invariant violation"):
        cr.transition_state(ChecklistResultState.PASS)

    # Legitimate transition after review
    cr.state = ChecklistResultState.NEEDS_REVIEW.value
    cr.transition_state(ChecklistResultState.PASS, reviewed_by="adversarial_challenger")
    assert cr.state == ChecklistResultState.PASS.value
    assert cr.reviewed_by == "adversarial_challenger"


@pytest.mark.asyncio
async def test_adversarial_api_review_endpoint_rejects_invalid_transitions(
    client: httpx.AsyncClient, challenger_owner_headers: Dict[str, str], db_session: AsyncSession
):
    """Task 1: Verify POST /api/v1/checklist/runs/{id}/review/{check_id} returns HTTP 400 when attempting unverified PASS."""
    # Create target asset and authorized scope
    asset = Asset(
        id=uuid.uuid4(),
        name="Adversarial Invariant Target",
        target_locator="https://invariant.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)
    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin="https://invariant.empire.edu.vn",
        emergency_stop_active=False,
    )
    db_session.add(scope)
    await db_session.commit()

    # Launch checklist run
    run_resp = await client.post(
        "/api/v1/checklist/runs",
        headers=challenger_owner_headers,
        json={"asset_id": str(asset.id), "mode": "AUTOMATED"},
    )
    assert run_resp.status_code == 201
    run_id = run_resp.json()["id"]

    # 1. Attempt invalid transition: NOT_RUN -> PASS directly (Must return HTTP 400)
    resp_not_run_to_pass = await client.post(
        f"/api/v1/checklist/runs/{run_id}/review/WEB-001",
        headers=challenger_owner_headers,
        json={"state": "PASS", "review_notes": "Attempting unverified transition to PASS from NOT_RUN"},
    )
    assert resp_not_run_to_pass.status_code == 400
    assert "State invariant violation" in resp_not_run_to_pass.json()["detail"]

    # 2. Attempt invalid transition: BLOCKED -> PASS directly (Must return HTTP 400)
    # API-001 is evaluated by synthetic harness and ends up BLOCKED when credentials missing
    resp_blocked_to_pass = await client.post(
        f"/api/v1/checklist/runs/{run_id}/review/API-001",
        headers=challenger_owner_headers,
        json={"state": "PASS", "review_notes": "Attempting unverified transition to PASS from BLOCKED"},
    )
    assert resp_blocked_to_pass.status_code == 400
    assert "State invariant violation" in resp_blocked_to_pass.json()["detail"]

    # 3. Attempt review with invalid non-enum state (Must return HTTP 422 Unprocessable Entity)
    resp_invalid_state = await client.post(
        f"/api/v1/checklist/runs/{run_id}/review/WEB-001",
        headers=challenger_owner_headers,
        json={"state": "FORGED_PASS_STATE", "review_notes": "Forged enum value"},
    )
    assert resp_invalid_state.status_code == 422

    # 4. Attempt review on non-existent check_id (Must return HTTP 404)
    resp_missing_check = await client.post(
        f"/api/v1/checklist/runs/{run_id}/review/NONEXISTENT-999",
        headers=challenger_owner_headers,
        json={"state": "NEEDS_REVIEW", "review_notes": "Bogus check"},
    )
    assert resp_missing_check.status_code == 404

    # 5. Legitimate 2-step transition: NOT_RUN -> NEEDS_REVIEW -> PASS
    step1 = await client.post(
        f"/api/v1/checklist/runs/{run_id}/review/WEB-002",
        headers=challenger_owner_headers,
        json={"state": "NEEDS_REVIEW", "review_notes": "Flagged for manual header review"},
    )
    assert step1.status_code == 200
    assert step1.json()["state"] == "NEEDS_REVIEW"

    step2 = await client.post(
        f"/api/v1/checklist/runs/{run_id}/review/WEB-002",
        headers=challenger_owner_headers,
        json={"state": "PASS", "review_notes": "Verified manual evidence: headers compliant"},
    )
    assert step2.status_code == 200
    assert step2.json()["state"] == "PASS"

    # 6. Check metrics updated honestly
    metrics_resp = await client.get(
        f"/api/v1/checklist/runs/{run_id}/metrics",
        headers=challenger_owner_headers,
    )
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics["state_counts"]["PASS"] >= 1


# ==============================================================================
# TASK 2: SCOPE GATE & SSRF ADVERSARIAL PROBES
# ==============================================================================


@pytest.mark.asyncio
async def test_adversarial_scope_gate_rejections(db_session: AsyncSession):
    """Task 2: Test preflight validation strictly rejects missing, expired, emergency stopped, unverified, and out-of-boundary assets."""
    now_utc = datetime.now(timezone.utc)

    # 1. Missing scope record -> SCOPE_MISSING (403)
    asset_no_scope = Asset(
        id=uuid.uuid4(),
        name="Scope Missing Target",
        target_locator="https://no-scope.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset_no_scope)
    await db_session.commit()

    with pytest.raises(ScopeEnforcementError) as exc_info:
        await ScopeValidator.validate_preflight(asset_no_scope.id, db=db_session)
    assert exc_info.value.status_code == 403
    assert exc_info.value.reason == "SCOPE_MISSING"

    # 2. Expired scope record -> SCOPE_EXPIRED (403)
    asset_expired = Asset(
        id=uuid.uuid4(),
        name="Expired Scope Target",
        target_locator="https://expired-scope.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset_expired)
    scope_expired = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset_expired.id,
        exact_origin="https://expired-scope.empire.edu.vn",
        expires_at=now_utc - timedelta(hours=2),
        emergency_stop_active=False,
    )
    db_session.add(scope_expired)
    await db_session.commit()

    with pytest.raises(ScopeEnforcementError) as exc_info2:
        await ScopeValidator.validate_preflight(asset_expired.id, db=db_session)
    assert exc_info2.value.status_code == 403
    assert exc_info2.value.reason == "SCOPE_EXPIRED"

    # 3. Active Emergency Stop -> EMERGENCY_STOP_ACTIVE (403)
    asset_stopped = Asset(
        id=uuid.uuid4(),
        name="Emergency Stopped Target",
        target_locator="https://stopped.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset_stopped)
    scope_stopped = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset_stopped.id,
        exact_origin="https://stopped.empire.edu.vn",
        emergency_stop_active=True,
    )
    db_session.add(scope_stopped)
    await db_session.commit()

    with pytest.raises(ScopeEnforcementError) as exc_info3:
        await ScopeValidator.validate_preflight(asset_stopped.id, db=db_session)
    assert exc_info3.value.status_code == 403
    assert exc_info3.value.reason == "EMERGENCY_STOP_ACTIVE"

    # 4. Unverified asset attempting active probe -> ASSET_NOT_VERIFIED (403)
    asset_unverified = Asset(
        id=uuid.uuid4(),
        name="Unverified Active Target",
        target_locator="https://unverified.empire.edu.vn",
        verification_status=VerificationStatus.PENDING.value,
    )
    db_session.add(asset_unverified)
    scope_unverified = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset_unverified.id,
        exact_origin="https://unverified.empire.edu.vn",
        emergency_stop_active=False,
    )
    db_session.add(scope_unverified)
    await db_session.commit()

    with pytest.raises(ScopeEnforcementError) as exc_info4:
        await ScopeValidator.validate_preflight(asset_unverified.id, is_active_probe=True, db=db_session)
    assert exc_info4.value.status_code == 403
    assert exc_info4.value.reason == "ASSET_NOT_VERIFIED"

    # 5. Non-existent asset ID -> ASSET_NOT_FOUND (404)
    fake_asset_id = uuid.uuid4()
    with pytest.raises(ScopeEnforcementError) as exc_info5:
        await ScopeValidator.validate_preflight(fake_asset_id, db=db_session)
    assert exc_info5.value.status_code == 404
    assert exc_info5.value.reason == "ASSET_NOT_FOUND"


@pytest.mark.asyncio
async def test_adversarial_ssrf_egress_protection():
    """Task 2: Test SSRFProtector against hostile cloud metadata, loopback, and private egress vectors."""
    hostile_ssrf_targets = [
        # Cloud metadata services
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
        "http://100.100.100.200/latest/meta-data/",
        "http://192.0.0.192/latest/meta-data/",
        "http://instance-data/latest/meta-data",
        # IPv4 Loopbacks
        "http://127.0.0.1:8080/",
        "http://127.0.0.2:9000/",
        # IPv6 Loopbacks
        "http://[::1]:8080/",
        # Link-local addresses
        "http://169.254.1.1/",
        "http://[fe80::1]/",
        # Zero / Unspecified network
        "http://0.0.0.0:8000/",
        # RFC 1918 Private networks (with allow_private=False)
        "http://10.0.0.1/admin",
        "http://172.16.0.1/internal",
        "http://192.168.1.1/router",
        # Decimal integer encoding
        "http://2130706433:8080/",  # 127.0.0.1 in decimal
        # Authority embedded credentials
        "http://admin:secret@empire.edu.vn/",
    ]

    for target in hostile_ssrf_targets:
        with pytest.raises(SSRFValidationError) as exc_info:
            SSRFProtector.validate_target(target, allow_private=False)
        assert exc_info.value is not None


# ==============================================================================
# TASK 3: SYNTHETIC HARNESS ADVERSARIAL PROBES
# ==============================================================================


@pytest.mark.asyncio
async def test_adversarial_synthetic_harness_blocked_when_credentials_missing(db_session: AsyncSession):
    """Task 3: Verify evaluate_bola and evaluate_bfla return BLOCKED when test accounts are absent or insufficient."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Harness Stress Target",
        target_locator="https://synthetic-stress.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    # 1. Zero identities active
    res = await db_session.execute(select(SyntheticIdentity))
    for ident in res.scalars().all():
        ident.is_active = False
    await db_session.commit()

    harness = SyntheticTestHarness()

    bola_res_zero = await harness.evaluate_bola(asset, db_session)
    assert bola_res_zero["check_id"] == "API-001"
    assert bola_res_zero["state"] == ChecklistResultState.BLOCKED.value
    assert bola_res_zero["state"] != ChecklistResultState.PASS.value
    assert bola_res_zero["state"] != ChecklistResultState.NOT_APPLICABLE.value
    assert bola_res_zero["evidence_payload"]["active_identities_found"] == 0
    assert bola_res_zero["evidence_payload"]["required_identities"] == 2

    bfla_res_zero = await harness.evaluate_bfla(asset, db_session)
    assert bfla_res_zero["check_id"] == "API-005"
    assert bfla_res_zero["state"] == ChecklistResultState.BLOCKED.value
    assert bfla_res_zero["state"] != ChecklistResultState.PASS.value
    assert bfla_res_zero["state"] != ChecklistResultState.NOT_APPLICABLE.value
    assert bfla_res_zero["evidence_payload"]["required_role"] == "STUDENT"

    # 2. Insufficient identities: Exactly 1 student identity active
    # BOLA requires at least 2 students for cross-account testing; BFLA only requires 1.
    student1 = SyntheticIdentity(
        id=uuid.uuid4(),
        identifier="adversarial_student_1",
        email="student1@test.empire.edu.vn",
        role="STUDENT",
        is_active=True,
    )
    db_session.add(student1)
    await db_session.commit()

    # BOLA with 1 student identity MUST still evaluate to BLOCKED
    bola_res_one = await harness.evaluate_bola(asset, db_session)
    assert bola_res_one["check_id"] == "API-001"
    assert bola_res_one["state"] == ChecklistResultState.BLOCKED.value
    assert bola_res_one["evidence_payload"]["active_identities_found"] == 1

    # Cleanup created student identity
    await db_session.delete(student1)
    await db_session.commit()


# ==============================================================================
# TASK 4: EMERGENCY STOP ADVERSARIAL PROBES
# ==============================================================================


@pytest.mark.asyncio
async def test_adversarial_emergency_stop_speed_and_cancellation(
    client: httpx.AsyncClient, challenger_owner_headers: Dict[str, str], db_session: AsyncSession
):
    """Task 4: Verify emergency stop terminates scans in < 3s, updates DB, and blocks future scans."""
    asset = Asset(
        id=uuid.uuid4(),
        name="Emergency Stop Stress Target",
        target_locator="https://killswitch-stress.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin="https://killswitch-stress.empire.edu.vn",
        emergency_stop_active=False,
    )
    db_session.add(scope)

    # Add simulated running and queued scans
    scan1 = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        target_locator=asset.target_locator,
        status=ScanStatus.RUNNING.value,
        profile="STANDARD",
    )
    scan2 = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        target_locator=asset.target_locator,
        status=ScanStatus.QUEUED.value,
        profile="STANDARD",
    )
    db_session.add(scan1)
    db_session.add(scan2)
    await db_session.commit()

    # Trigger emergency stop and measure execution duration
    t_start = time.perf_counter()
    resp = await client.post(
        f"/api/v1/assets/{asset.id}/emergency-stop",
        headers=challenger_owner_headers,
    )
    duration_s = time.perf_counter() - t_start

    assert resp.status_code == 200
    # Must terminate in < 3 seconds
    assert duration_s < 3.0, f"Emergency stop exceeded 3s deadline: {duration_s:.3f}s"

    data = resp.json()
    assert data["status"] == "EMERGENCY_STOP_ACTIVATED"
    assert data["emergency_stop_active"] is True
    assert data["halted_scans_count"] >= 2

    # Verify state in database
    await db_session.refresh(scope)
    await db_session.refresh(scan1)
    await db_session.refresh(scan2)

    assert scope.emergency_stop_active is True
    assert scan1.status == ScanStatus.CANCELLED.value
    assert scan2.status == ScanStatus.CANCELLED.value
    assert "emergency stop triggered" in scan1.cancellation_reason
    assert "emergency stop triggered" in scan2.cancellation_reason

    # Subsequent preflight validation MUST be rejected with EMERGENCY_STOP_ACTIVE
    with pytest.raises(ScopeEnforcementError) as exc_info:
        await ScopeValidator.validate_preflight(asset.id, db=db_session)
    assert exc_info.value.status_code == 403
    assert exc_info.value.reason == "EMERGENCY_STOP_ACTIVE"
