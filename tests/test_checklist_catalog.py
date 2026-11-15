import uuid
from datetime import datetime, timezone
from typing import Dict

import pytest
import pytest_asyncio
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.core.checklist_seeder import EMPIRE_CHECKLIST_CATALOG, seed_checklist_catalog
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.models.asset import Asset
from backend.app.models.checklist import (
    AutomationType,
    ChecklistAssessmentRun,
    ChecklistCategory,
    ChecklistDefinition,
    ChecklistResult,
    ChecklistResultState,
    validate_state_transition,
)
from backend.app.models.scope import AssetAssessmentScope
from backend.app.models.user import User, UserRole
from backend.app.schemas.common import VerificationStatus


@pytest_asyncio.fixture
async def owner_user_and_headers(db_session: AsyncSession) -> Dict[str, str]:
    """Creates/ensures sole owner user in DB and returns valid bearer token headers."""
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
            username="owner_admin",
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
async def test_checklist_seeder_all_39_definitions(db_session: AsyncSession):
    """R1: Verify checklist catalog seeder seeds all 39 Empire check definitions across 6 categories."""
    count = await seed_checklist_catalog(db_session)
    assert count == 39

    res = await db_session.execute(select(ChecklistDefinition))
    defs = res.scalars().all()
    assert len(defs) == 39

    category_counts = {}
    for d in defs:
        category_counts[d.category] = category_counts.get(d.category, 0) + 1

    # Exact expected distribution across 6 categories
    assert category_counts[ChecklistCategory.WEB.value] == 10  # WEB-001..010
    assert category_counts[ChecklistCategory.API.value] == 10  # API-001..010
    assert category_counts[ChecklistCategory.FILE.value] == 5  # FILE-001..005
    assert category_counts[ChecklistCategory.AUTH.value] == 5  # AUTH-001..005
    assert category_counts[ChecklistCategory.INFRA.value] == 4  # INFRA-001..004
    assert category_counts[ChecklistCategory.DEP.value] == 5   # DEP-001..005


@pytest.mark.asyncio
async def test_bilingual_metadata_completeness(db_session: AsyncSession):
    """R1: Verify all 39 check definitions contain full bilingual VI/EN metadata and guidance."""
    await seed_checklist_catalog(db_session)
    res = await db_session.execute(select(ChecklistDefinition))
    defs = res.scalars().all()

    for d in defs:
        assert d.check_id.strip() != ""
        assert d.category in [c.value for c in ChecklistCategory]
        assert len(d.title_vi.strip()) > 3, f"{d.check_id} missing title_vi"
        assert len(d.title_en.strip()) > 3, f"{d.check_id} missing title_en"
        assert len(d.description_vi.strip()) > 10, f"{d.check_id} missing description_vi"
        assert len(d.description_en.strip()) > 10, f"{d.check_id} missing description_en"
        assert len(d.remediation_guidance_vi.strip()) > 5, f"{d.check_id} missing remediation_guidance_vi"
        assert len(d.remediation_guidance_en.strip()) > 5, f"{d.check_id} missing remediation_guidance_en"
        assert d.version == "1.0.0"
        assert d.is_active is True


@pytest.mark.asyncio
async def test_7_result_states_and_invariant_enforcement():
    """R1: Test strict 7-state semantics and invariant guard: never convert unrun/blocked/error to PASS."""
    # 7 valid states
    states = [s.value for s in ChecklistResultState]
    expected_states = ["PASS", "FAIL", "NEEDS_REVIEW", "NOT_APPLICABLE", "BLOCKED", "NOT_RUN", "ERROR"]
    assert set(states) == set(expected_states)

    # Invariant: Unverified states CANNOT transition directly to PASS
    with pytest.raises(ValueError, match="State invariant violation"):
        validate_state_transition("NOT_RUN", "PASS")

    with pytest.raises(ValueError, match="State invariant violation"):
        validate_state_transition("BLOCKED", "PASS")

    with pytest.raises(ValueError, match="State invariant violation"):
        validate_state_transition("ERROR", "PASS")

    # Permitted valid transitions
    validate_state_transition("NOT_RUN", "FAIL")
    validate_state_transition("NOT_RUN", "NEEDS_REVIEW")
    validate_state_transition("NOT_RUN", "BLOCKED")
    validate_state_transition("NOT_RUN", "NOT_APPLICABLE")
    validate_state_transition("NEEDS_REVIEW", "PASS")
    validate_state_transition("FAIL", "PASS")


@pytest.mark.asyncio
async def test_honest_coverage_metrics_calculation(db_session: AsyncSession):
    """R1: Test honest automated coverage % and manual review completion % formulas without score fabrication."""
    await seed_checklist_catalog(db_session)
    def_res = await db_session.execute(select(ChecklistDefinition))
    defs = list(def_res.scalars().all())

    asset = Asset(
        id=uuid.uuid4(),
        name="Test Coverage Target",
        target_locator="https://coverage.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)

    run = ChecklistAssessmentRun(
        id=uuid.uuid4(),
        asset_id=asset.id,
        status="RUNNING",
        total_checks=len(defs),
    )
    db_session.add(run)

    # Populate 39 results
    for i, d in enumerate(defs):
        state = ChecklistResultState.NOT_RUN.value
        reviewed_by = None
        # Simulate partial evaluation:
        if i < 10:
            state = ChecklistResultState.PASS.value
        elif i < 15:
            state = ChecklistResultState.FAIL.value
        elif i < 20:
            state = ChecklistResultState.NEEDS_REVIEW.value
            if i == 18:
                reviewed_by = "analyst1"

        result = ChecklistResult(
            id=uuid.uuid4(),
            run_id=run.id,
            check_id=d.check_id,
            state=state,
            reviewed_by=reviewed_by,
        )
        db_session.add(result)

    await db_session.commit()

    # Recompute metrics
    run_with_res = await db_session.execute(
        select(ChecklistAssessmentRun).where(ChecklistAssessmentRun.id == run.id)
    )
    loaded_run = run_with_res.scalars().first()
    loaded_run.recompute_metrics()

    # Ensure coverage is honestly calculated
    assert 0.0 < loaded_run.automated_coverage_pct <= 100.0
    assert loaded_run.state_counts[ChecklistResultState.PASS.value] == 10
    assert loaded_run.state_counts[ChecklistResultState.FAIL.value] == 5
    assert loaded_run.state_counts[ChecklistResultState.NEEDS_REVIEW.value] == 5
    assert loaded_run.state_counts[ChecklistResultState.NOT_RUN.value] == 19


@pytest.mark.asyncio
async def test_checklist_api_definitions_endpoint(
    client: httpx.AsyncClient, owner_user_and_headers: Dict[str, str], db_session: AsyncSession
):
    """R1: Test GET /api/v1/checklist/definitions endpoint and category filtering."""
    await seed_checklist_catalog(db_session)

    # 1. All definitions
    resp = await client.get("/api/v1/checklist/definitions", headers=owner_user_and_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 39

    # 2. Filter by category WEB
    resp_web = await client.get("/api/v1/checklist/definitions?category=WEB", headers=owner_user_and_headers)
    assert resp_web.status_code == 200
    data_web = resp_web.json()
    assert len(data_web) == 10
    assert all(item["category"] == "WEB" for item in data_web)

    # 3. Filter by category API
    resp_api = await client.get("/api/v1/checklist/definitions?category=API", headers=owner_user_and_headers)
    assert resp_api.status_code == 200
    data_api = resp_api.json()
    assert len(data_api) == 10
    assert all(item["category"] == "API" for item in data_api)


@pytest.mark.asyncio
async def test_checklist_api_run_lifecycle_and_review(
    client: httpx.AsyncClient, owner_user_and_headers: Dict[str, str], db_session: AsyncSession
):
    """R1: Test complete checklist run launch, results retrieval, honest metrics, and manual review."""
    await seed_checklist_catalog(db_session)

    # Create target asset and authorized scope
    asset = Asset(
        id=uuid.uuid4(),
        name="Empire Portal API",
        target_locator="https://api.empire.edu.vn",
        verification_status=VerificationStatus.VERIFIED.value,
    )
    db_session.add(asset)
    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset.id,
        exact_origin="https://api.empire.edu.vn",
        emergency_stop_active=False,
    )
    db_session.add(scope)
    await db_session.commit()

    # 1. Launch checklist assessment run via POST /api/v1/checklist/runs
    run_resp = await client.post(
        "/api/v1/checklist/runs",
        headers=owner_user_and_headers,
        json={"asset_id": str(asset.id), "mode": "AUTOMATED"},
    )
    assert run_resp.status_code == 201
    run_data = run_resp.json()
    run_id = run_data["id"]
    assert run_data["total_checks"] == 39
    assert run_data["status"] == "COMPLETED"

    # 2. Retrieve results via GET /api/v1/checklist/runs/{id}/results
    results_resp = await client.get(f"/api/v1/checklist/runs/{run_id}/results", headers=owner_user_and_headers)
    assert results_resp.status_code == 200
    results = results_resp.json()
    assert len(results) == 39

    # 3. Retrieve metrics via GET /api/v1/checklist/runs/{id}/metrics
    metrics_resp = await client.get(f"/api/v1/checklist/runs/{run_id}/metrics", headers=owner_user_and_headers)
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics["total_checks"] == 39
    assert "automated_coverage_pct" in metrics
    assert "manual_completion_pct" in metrics

    # 4. Attempt invalid review transition (NOT_RUN -> PASS directly): Expect HTTP 400
    bad_review_resp = await client.post(
        f"/api/v1/checklist/runs/{run_id}/review/WEB-001",
        headers=owner_user_and_headers,
        json={"state": "PASS", "review_notes": "Attempting unverified pass without evidence"},
    )
    assert bad_review_resp.status_code == 400
    assert "State invariant violation" in bad_review_resp.json()["detail"]

    # 5. Perform valid review transition (NOT_RUN -> NEEDS_REVIEW, then NEEDS_REVIEW -> PASS)
    review_resp1 = await client.post(
        f"/api/v1/checklist/runs/{run_id}/review/WEB-001",
        headers=owner_user_and_headers,
        json={"state": "NEEDS_REVIEW", "review_notes": "Flagged for manual header audit"},
    )
    assert review_resp1.status_code == 200
    assert review_resp1.json()["state"] == "NEEDS_REVIEW"

    review_resp2 = await client.post(
        f"/api/v1/checklist/runs/{run_id}/review/WEB-001",
        headers=owner_user_and_headers,
        json={"state": "PASS", "review_notes": "Manual audit verified strict HSTS and CSP headers"},
    )
    assert review_resp2.status_code == 200
    assert review_resp2.json()["state"] == "PASS"
    assert review_resp2.json()["review_notes"] == "Manual audit verified strict HSTS and CSP headers"
