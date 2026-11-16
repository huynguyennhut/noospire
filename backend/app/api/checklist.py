import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.api.deps import get_db, load_scope, require_operator, require_viewer
from backend.app.core.checklist_seeder import seed_checklist_catalog
from backend.app.core.scope_gate import ScopeEnforcementError, ScopeValidator
from backend.app.models.asset import Asset
from backend.app.models.checklist import (
    ChecklistAssessmentRun,
    ChecklistCategory,
    ChecklistDefinition,
    ChecklistResult,
    ChecklistResultState,
)
from backend.app.models.user import User
from backend.app.scanners.file_policy import FilePolicyEngine
from backend.app.scanners.synthetic_harness import SyntheticTestHarness
from backend.app.schemas.checklist import (
    ChecklistAssessmentRunCreate,
    ChecklistAssessmentRunRead,
    ChecklistDefinitionRead,
    ChecklistMetricsResponse,
    ChecklistResultRead,
    ChecklistReviewRequest,
)

logger = logging.getLogger("sentinel.checklist_api")

router = APIRouter(prefix="/checklist", tags=["Empire Pentest Checklist"])


async def _scoped_run(db: AsyncSession, user: User, run_id: uuid.UUID, action: str = "READ") -> ChecklistAssessmentRun:
    run = (await db.execute(select(ChecklistAssessmentRun).where(ChecklistAssessmentRun.id == run_id))).scalars().first()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist run not found")
    (await load_scope(user, db)).require(run.asset_id, action)
    return run


@router.get("/definitions", response_model=List[ChecklistDefinitionRead])
async def list_checklist_definitions(
    category: Optional[ChecklistCategory] = None,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieves all 39 Empire Pentest check definitions with bilingual VI/EN metadata."""
    stmt = select(ChecklistDefinition).order_by(ChecklistDefinition.check_id)
    if category:
        stmt = stmt.where(ChecklistDefinition.category == category.value)

    res = await db.execute(stmt)
    definitions = list(res.scalars().all())

    # Auto-seed catalog if empty (e.g. fresh database)
    if not definitions and category is None:
        await seed_checklist_catalog(db)
        res = await db.execute(select(ChecklistDefinition).order_by(ChecklistDefinition.check_id))
        definitions = list(res.scalars().all())

    return definitions


@router.get("/runs", response_model=List[ChecklistAssessmentRunRead])
async def list_checklist_runs(
    asset_id: Optional[uuid.UUID] = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lists point-in-time checklist assessment runs with coverage statistics."""
    stmt = select(ChecklistAssessmentRun).order_by(ChecklistAssessmentRun.created_at.desc())
    scope = await load_scope(current_user, db)
    if scope.asset_ids is not None:
        stmt = stmt.where(ChecklistAssessmentRun.asset_id.in_(scope.asset_ids))
    if asset_id:
        stmt = stmt.where(ChecklistAssessmentRun.asset_id == asset_id)

    offset = (page - 1) * size
    stmt = stmt.offset(offset).limit(size)

    res = await db.execute(stmt)
    runs = list(res.scalars().all())
    return runs


@router.post("/runs", response_model=ChecklistAssessmentRunRead, status_code=status.HTTP_201_CREATED)
async def create_checklist_run(
    run_in: ChecklistAssessmentRunCreate,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Initiates a pentest checklist assessment run for an asset.
    Enforces immutable preflight scope validation, seeds all 39 checks in NOT_RUN state,
    and executes automated checks (Synthetic Test Harness and File Policy Engine).
    """
    # Object permission must pass before resolving or probing a customer target.
    (await load_scope(current_user, db)).require(run_in.asset_id, "SCAN")
    # 1. Immutable Scope Preflight Gate
    try:
        await ScopeValidator.validate_preflight(
            asset_id=run_in.asset_id,
            requested_checks=None,
            db=db,
            is_active_probe=False,
        )
    except ScopeEnforcementError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    # 2. Retrieve asset
    asset_res = await db.execute(select(Asset).where(Asset.id == run_in.asset_id))
    asset = asset_res.scalars().first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target asset not found")

    # Ensure catalog definitions exist
    def_res = await db.execute(select(ChecklistDefinition).order_by(ChecklistDefinition.check_id))
    all_defs = list(def_res.scalars().all())
    if len(all_defs) < 39:
        await seed_checklist_catalog(db)
        def_res = await db.execute(select(ChecklistDefinition).order_by(ChecklistDefinition.check_id))
        all_defs = list(def_res.scalars().all())

    # 3. Create run record
    run = ChecklistAssessmentRun(
        id=uuid.uuid4(),
        asset_id=asset.id,
        status="RUNNING",
        total_checks=len(all_defs),
        created_at=datetime.now(timezone.utc),
    )
    db.add(run)

    # 4. Populate 39 initial results with NOT_RUN state
    check_results_map: Dict[str, ChecklistResult] = {}
    for d in all_defs:
        res_record = ChecklistResult(
            id=uuid.uuid4(),
            run_id=run.id,
            check_id=d.check_id,
            state=ChecklistResultState.NOT_RUN.value,
            evidence_payload={"status": "Pending execution", "check_id": d.check_id},
        )
        db.add(res_record)
        check_results_map[d.check_id] = res_record

    await db.flush()

    # 5. Execute automated engine suites if mode is AUTOMATED or FULL
    mode = (run_in.mode or "AUTOMATED").upper()
    if mode in ("AUTOMATED", "FULL"):
        # A. Synthetic Test Harness (API-001 BOLA, API-005 BFLA)
        try:
            harness = SyntheticTestHarness()
            harness_results = await harness.run_all(asset, db)
            for hr in harness_results:
                cid = hr["check_id"]
                if cid in check_results_map:
                    cr = check_results_map[cid]
                    cr.state = hr["state"]
                    cr.evidence_payload = hr["evidence_payload"]
                    cr.execution_duration_ms = hr.get("execution_duration_ms", 0)
                    cr.evaluated_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception("Synthetic harness evaluation encountered error: %s", exc)

        # B. File Policy Engine (FILE-001 Public Media, FILE-002 Sensitive Leaks)
        try:
            file_engine = FilePolicyEngine()
            file_results = await file_engine.run_all(asset, db)
            for fr in file_results:
                cid = fr["check_id"]
                if cid in check_results_map:
                    cr = check_results_map[cid]
                    cr.state = fr["state"]
                    cr.evidence_payload = fr["evidence_payload"]
                    cr.execution_duration_ms = fr.get("execution_duration_ms", 0)
                    cr.evaluated_at = datetime.now(timezone.utc)
        except Exception as exc:
            logger.exception("File policy engine evaluation encountered error: %s", exc)

    # 6. Finalize Run
    run.status = "COMPLETED"
    run.completed_at = datetime.now(timezone.utc)
    
    # Reload results with relationships for honest metric recomputation
    run_with_results = await db.execute(
        select(ChecklistAssessmentRun)
        .options(selectinload(ChecklistAssessmentRun.results).selectinload(ChecklistResult.definition))
        .where(ChecklistAssessmentRun.id == run.id)
    )
    final_run = run_with_results.scalars().first() or run
    final_run.recompute_metrics()

    await db.commit()
    await db.refresh(final_run)
    return final_run


@router.get("/runs/{run_id}", response_model=ChecklistAssessmentRunRead)
async def get_checklist_run(
    run_id: uuid.UUID,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieves a checklist run by ID."""
    return await _scoped_run(db, current_user, run_id)


@router.get("/runs/{run_id}/results", response_model=List[ChecklistResultRead])
async def get_checklist_run_results(
    run_id: uuid.UUID,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieves all 39 check results with forensic evidence payloads for a run."""
    await _scoped_run(db, current_user, run_id)

    res = await db.execute(
        select(ChecklistResult)
        .options(selectinload(ChecklistResult.definition))
        .where(ChecklistResult.run_id == run_id)
        .order_by(ChecklistResult.check_id)
    )
    return list(res.scalars().all())


@router.get("/runs/{run_id}/metrics", response_model=ChecklistMetricsResponse)
async def get_checklist_run_metrics(
    run_id: uuid.UUID,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieves honest automated coverage and manual review completion percentages."""
    run = await _scoped_run(db, current_user, run_id)

    counts = run.state_counts or {}
    unrun_checks = counts.get(ChecklistResultState.NOT_RUN.value, 0)
    evaluated_checks = run.total_checks - unrun_checks

    return ChecklistMetricsResponse(
        run_id=run.id,
        total_checks=run.total_checks,
        automated_coverage_pct=run.automated_coverage_pct,
        manual_completion_pct=run.manual_completion_pct,
        state_counts=counts,
        evaluated_checks=evaluated_checks,
        unrun_checks=unrun_checks,
    )


@router.post("/runs/{run_id}/review/{check_id}", response_model=ChecklistResultRead)
async def review_checklist_check(
    run_id: uuid.UUID,
    check_id: str,
    review_in: ChecklistReviewRequest,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Records manual analyst review, strictly enforcing state transition invariants.
    Invariant: Never convert unrun, blocked, or error states to PASS.
    """
    await _scoped_run(db, current_user, run_id, "TRIAGE")
    res = await db.execute(
        select(ChecklistResult)
        .options(selectinload(ChecklistResult.definition))
        .where(ChecklistResult.run_id == run_id, ChecklistResult.check_id == check_id)
    )
    check_result = res.scalars().first()
    if not check_result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check result '{check_id}' not found for run '{run_id}'",
        )

    # Enforce state invariant guard
    try:
        check_result.transition_state(
            new_state=review_in.state,
            reviewed_by=current_user.username,
            review_notes=review_in.review_notes,
            evidence={
                "manual_review_at": datetime.now(timezone.utc).isoformat(),
                "reviewed_by": current_user.username,
                "notes": review_in.review_notes,
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Recompute metrics on parent run
    run_res = await db.execute(
        select(ChecklistAssessmentRun)
        .options(selectinload(ChecklistAssessmentRun.results).selectinload(ChecklistResult.definition))
        .where(ChecklistAssessmentRun.id == run_id)
    )
    run = run_res.scalars().first()
    if run:
        run.recompute_metrics()

    await db.commit()
    await db.refresh(check_result)
    return check_result


__all__ = ["router"]
