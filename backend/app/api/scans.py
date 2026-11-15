import asyncio
from datetime import datetime, timedelta, timezone
import json
import time
from typing import Any, List, Optional
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import (
    get_authorized_asset_ids,
    is_sole_owner,
    load_scope,
    require_admin,
    require_operator,
    require_owner,
    require_viewer,
    session_still_valid,
)
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal, get_db
from backend.app.core.dispatcher import get_dispatcher, log_buffer
from backend.app.core.event_bus import event_broadcaster
from backend.app.core.ssrf import SSRFProtector, SSRFValidationError
from backend.app.models.alert import SecurityAlert
from backend.app.models.asset import Asset
from backend.app.models.event import ScanEvent
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan, ScanBatch, ScanLog
from backend.app.models.scope import AssetAssessmentScope
from backend.app.models.user import User, UserRole
from backend.app.core.ultra_planner import ultra_planner
from backend.app.schemas.common import (
    AssetType,
    EmpireModule,
    PaginatedResponse,
    ScanProfile,
    ScanQualityStatus,
    ScanStatus,
    VerificationStatus,
)
from backend.app.schemas.scan import (
    ActiveThreadInfo,
    BatchScanResponse,
    ScanBatchCreate,
    ScanBatchRead,
    ScanCancelResponse,
    ScanCreate,
    ScanLogEntry,
    ScanRead,
    ScanResponse,
    TrackCurrentResponse,
    UltraScanCreate,
    UltraScanFixtureResponse,
    UltraScanResponse,
)

AUTH_REVOKED_FRAME = 'event: auth_revoked\ndata: {"detail": "session or grant revoked"}\n\n'


async def _scoped_scan(db: AsyncSession, user: User, scan_id: uuid.UUID, action: str = "READ") -> Scan:
    """Load a scan and enforce object scope (404 when unreadable, 403 when action missing)."""
    scan = (await db.execute(select(Scan).where(Scan.id == scan_id))).scalars().first()
    if not scan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan not found")
    (await load_scope(user, db)).require(scan.asset_id, action)
    return scan


async def _scoped_batch_filter(stmt, db: AsyncSession, user: User):
    scope = await load_scope(user, db)
    if scope.asset_ids is None:
        return stmt
    visible = select(Scan.batch_id).where(Scan.asset_id.in_(scope.asset_ids), Scan.batch_id.is_not(None))
    return stmt.where(ScanBatch.id.in_(visible))


router = APIRouter(prefix="/scans", tags=["Scan Center"])


@router.get("", response_model=PaginatedResponse[ScanResponse])
async def list_scans(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    asset_id: Optional[uuid.UUID] = None,
    status_filter: Optional[ScanStatus] = None,
    days: Optional[int] = Query(None, ge=1, le=365, description="Filter scans within past N days"),
    from_date: Optional[datetime] = Query(None, description="Start datetime (UTC/ISO)"),
    to_date: Optional[datetime] = Query(None, description="End datetime (UTC/ISO)"),
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = select(Scan)
    _scope = await load_scope(current_user, db)
    if _scope.asset_ids is not None:
        stmt = stmt.where(Scan.asset_id.in_(_scope.asset_ids))
    if asset_id:
        stmt = stmt.where(Scan.asset_id == asset_id)
    if status_filter:
        stmt = stmt.where(Scan.status == status_filter.value)
    if days is not None:
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(Scan.created_at >= threshold)
    if from_date:
        stmt = stmt.where(Scan.created_at >= from_date)
    if to_date:
        stmt = stmt.where(Scan.created_at <= to_date)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.order_by(Scan.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


@router.post("", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def create_scan(
    scan_in: ScanCreate,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    # 1. Verify target asset exists
    asset_res = await db.execute(select(Asset).where(Asset.id == scan_in.asset_id))
    asset = asset_res.scalars().first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    # Developer Scoping Enforcement (R5)
    _scope = await load_scope(current_user, db)
    if not _scope.estate_wide and not _scope.can(scan_in.asset_id, "SCAN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Missing SCAN permission for target asset {scan_in.asset_id}",
        )

    # 2. Scope and Emergency Stop Check (F13 - kill switch takes precedence)
    scope_res = await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == asset.id))
    scope = scope_res.scalars().first()
    if scope and scope.emergency_stop_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scan dispatch blocked: emergency stop is active for this target asset.",
        )

    # 3. SSRF Pre-flight Validation Gate (F11 - strict egress policy)
    target_locator = asset.target_locator.strip()
    allow_private = bool((scan_in.allow_private_targets or not settings.is_production) and settings.SSRF_ALLOW_PRIVATE_TARGETS)
    if asset.asset_type in (AssetType.WEB_APP.value, AssetType.DOMAIN.value, AssetType.API_ENDPOINT.value):
        try:
            SSRFProtector.validate_target(target_locator, allow_private=allow_private)
        except SSRFValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SSRF Validation Blocked: {str(e)}",
            )

    # 4. Active Scan Authorization Check
    if scan_in.profile == ScanProfile.DEEP_ACTIVE:
        if asset.verification_status != VerificationStatus.VERIFIED.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Active scanning (DEEP_ACTIVE) is prohibited: asset ownership is not verified.",
            )

    # 4. Create Scan Record
    scan = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        engine=scan_in.engine.lower(),
        profile=scan_in.profile.value,
        status=ScanStatus.QUEUED.value,
        progress_percentage=0,
        target_locator=target_locator,
        allow_private_targets=scan_in.allow_private_targets,
        timeout_seconds=scan_in.timeout_seconds,
    )
    db.add(scan)
    await db.commit()
    await db.refresh(scan)

    # 5. Dispatch Scan Asynchronously
    dispatcher = get_dispatcher()
    await dispatcher.dispatch_scan(scan.id)

    return scan


# ============================================================================
# BATCH SCAN & ORCHESTRATION ENDPOINTS (Preceding /{scan_id} to avoid collision)
# ============================================================================

@router.post("/batch", response_model=BatchScanResponse, status_code=status.HTTP_201_CREATED)
@router.post("/scan-all", response_model=BatchScanResponse, status_code=status.HTTP_201_CREATED)
async def create_batch_scan(
    batch_in: ScanBatchCreate,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dispatches a synchronized assessment batch across all registered targets (or selected targets),
    evaluating them across configured profiles and engines under concurrency throttling.
    """
    # 1. Resolve Target Assets
    is_estate_wide = (
        batch_in.targets == "ALL"
        or (isinstance(batch_in.targets, str) and batch_in.targets.strip().upper() == "ALL")
        or getattr(batch_in, "scan_all", False)
        or getattr(batch_in, "is_ultra_scan", False)
    )

    if is_estate_wide:
        # Enforce R5: Estate-wide scan is restricted solely to the system owner
        if not is_sole_owner(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Launching estate-wide Ultra Scan across the entire inventory is restricted solely to the system owner.",
            )
        asset_res = await db.execute(select(Asset))
        assets = asset_res.scalars().all()
    elif isinstance(batch_in.targets, list):
        if not batch_in.targets:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No target assets found: target asset list is empty (not found).",
            )
        try:
            target_uuids = [uuid.UUID(str(t)) for t in batch_in.targets]
        except (ValueError, TypeError) as ve:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid target UUID format in target list: {ve}",
            )

        asset_res = await db.execute(select(Asset).where(Asset.id.in_(target_uuids)))
        assets = asset_res.scalars().all()
        found_ids = {a.id for a in assets}
        missing_ids = [str(tid) for tid in target_uuids if tid not in found_ids]

        if not assets:
            missing_str = f": {', '.join(missing_ids)}" if missing_ids else ""
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No target assets found: requested target asset(s) not found for batch assessment{missing_str}.",
            )

        if missing_ids and not is_sole_owner(current_user):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Target asset(s) not found: {', '.join(missing_ids)}",
            )

        # Developer Scoping Enforcement (R5)
        _scope = await load_scope(current_user, db)
        if not _scope.estate_wide:
            unauthorized = [a.id for a in assets if not _scope.can(a.id, "SCAN")]
            if unauthorized:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied to target assets: {', '.join(str(u) for u in unauthorized)}",
                )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid targets parameter: '{batch_in.targets}'. Expected 'ALL' or a non-empty list of UUIDs.",
        )

    if not assets:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No target assets found for batch assessment.",
        )

    # 2. Resolve Profiles
    if batch_in.profiles:
        profile_list = batch_in.profiles
    elif batch_in.profile:
        profile_list = [batch_in.profile]
    else:
        profile_list = [ScanProfile.BASELINE, ScanProfile.DAILY_SECURITY, ScanProfile.STANDARD]

    # 3. Resolve Engines
    if batch_in.engines:
        engine_list = batch_in.engines
    elif batch_in.engine:
        engine_list = [batch_in.engine]
    else:
        engine_list = ["all"]

    engine_str = ",".join(engine_list) if engine_list else "all"

    # 4. Create ScanBatch Entity
    batch_name = batch_in.name or f"Scan All Batch ({len(assets)} targets)"
    profiles_serialized = [p.value if hasattr(p, "value") else str(p) for p in profile_list]

    batch = ScanBatch(
        id=uuid.uuid4(),
        name=batch_name,
        status=ScanStatus.QUEUED.value,
        target_count=len(assets),
        engines=engine_list,
        profiles=profiles_serialized,
        metadata_json={
            "description": batch_in.description,
            "concurrency_limit": batch_in.concurrency_limit,
            "allow_private_targets": batch_in.allow_private_targets,
        },
    )
    db.add(batch)
    await db.flush()

    # 5. Expand Target x Profile Matrix
    created_scans: List[Scan] = []
    scans_to_dispatch: List[uuid.UUID] = []
    auth_required_count = 0
    now_utc = datetime.now(timezone.utc)

    for asset in assets:
        for p in profile_list:
            p_val = p.value if hasattr(p, "value") else str(p)

            # Security gate: DEEP_ACTIVE requires asset verification
            if p_val == ScanProfile.DEEP_ACTIVE.value and asset.verification_status != VerificationStatus.VERIFIED.value:
                scan = Scan(
                    id=uuid.uuid4(),
                    asset_id=asset.id,
                    batch_id=batch.id,
                    engine=engine_str,
                    profile=p_val,
                    status=ScanStatus.FAILED.value,
                    quality_status=ScanQualityStatus.AUTH_REQUIRED.value,
                    progress_percentage=100,
                    target_locator=asset.target_locator.strip(),
                    allow_private_targets=batch_in.allow_private_targets,
                    timeout_seconds=batch_in.timeout_seconds,
                    error_message="Active scanning (DEEP_ACTIVE) is prohibited: asset ownership is not verified.",
                    started_at=now_utc,
                    completed_at=now_utc,
                )
                auth_required_count += 1
            else:
                scan = Scan(
                    id=uuid.uuid4(),
                    asset_id=asset.id,
                    batch_id=batch.id,
                    engine=engine_str,
                    profile=p_val,
                    status=ScanStatus.QUEUED.value,
                    progress_percentage=0,
                    target_locator=asset.target_locator.strip(),
                    allow_private_targets=batch_in.allow_private_targets,
                    timeout_seconds=batch_in.timeout_seconds,
                )
                scans_to_dispatch.append(scan.id)

            created_scans.append(scan)
            db.add(scan)

    batch.total_scans = len(created_scans)
    batch.failed_scans = auth_required_count
    await db.commit()
    await db.refresh(batch)

    # 6. Dispatch Queued Scans to Dispatcher
    dispatcher = get_dispatcher()
    await dispatcher.batch_dispatch_scans(scans_to_dispatch, batch_id=batch.id)

    return BatchScanResponse(
        batch_id=batch.id,
        name=batch.name,
        total_scans=batch.total_scans,
        target_count=batch.target_count,
        status=batch.status,
        scans=[ScanResponse.model_validate(s) for s in created_scans],
        message=f"Batch '{batch.name}' initiated with {len(created_scans)} scans across {len(assets)} targets.",
    )


@router.get("/ultra/fixture-379", response_model=UltraScanFixtureResponse)
async def get_ultra_scan_fixture(
    current_user: User = Depends(require_viewer),
) -> Any:
    """Returns the synthetic 379-item inventory plan and classification breakdown
    for continuous security assessment validation.
    """
    items = ultra_planner.generate_acceptance_fixture_379()
    plan = ultra_planner.plan_inventory(items)
    return UltraScanFixtureResponse(
        accounted_inventory_rows=plan.accounted_inventory_rows,
        independent_execution_targets=plan.independent_execution_targets,
        engine_executions_count=plan.engine_executions_count,
        shared_alias_count=plan.shared_alias_count,
        excluded_count=plan.excluded_count,
        policy_revision=plan.policy_revision,
        items=items,
        shared_result_links=plan.shared_result_links,
        explained_exclusions=plan.explained_exclusions,
    )


@router.post("/ultra", response_model=UltraScanResponse, status_code=status.HTTP_201_CREATED)
async def launch_ultra_scan(
    ultra_in: UltraScanCreate,
    request: Request,
    idempotency_key_header: Optional[str] = Header(None, alias="Idempotency-Key"),
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dispatches or recovers an authorized Ultra Scan batch assessment across the Empire estate.
    Adheres strictly to the hourly assessment cadence, durable batch tracking,
    complete inventory accounting, and idempotent recovery.
    """
    # 1. Resolve Idempotency Key
    idempotency_key = ultra_in.idempotency_key or idempotency_key_header
    if idempotency_key:
        idempotency_key = idempotency_key.strip()
        # Query if this batch was already created
        existing_batch_res = await db.execute(
            select(ScanBatch).where(ScanBatch.idempotency_key == idempotency_key)
        )
        existing_batch = existing_batch_res.scalars().first()
        if existing_batch:
            meta = existing_batch.metadata_json or {}
            return UltraScanResponse(
                batch_id=existing_batch.id,
                name=existing_batch.name,
                status=existing_batch.status,
                accounted_inventory_rows=meta.get("accounted_inventory_rows", existing_batch.total_scans),
                independent_execution_targets=meta.get("independent_execution_targets", existing_batch.target_count),
                engine_executions_count=existing_batch.total_scans,
                shared_alias_count=meta.get("shared_alias_count", 0),
                excluded_count=meta.get("excluded_count", 0),
                tracker_link=f"/active-assessments?batch_id={existing_batch.id}",
                snapshot_time=existing_batch.created_at,
                policy_revision=meta.get("policy_revision", "2026.11-R2"),
                idempotency_recovered=True,
                message=f"Idempotent recovery: Returning active Ultra Scan batch {existing_batch.id}",
            )

    # 2. Authorization Verification (R5: Estate-wide scan restricted solely to system owner)
    is_estate_wide = (
        ultra_in.scope == "ALL"
        or (isinstance(ultra_in.scope, str) and ultra_in.scope.upper() in ("ALL", "EMPIRE_ESTATE_379", "FIXTURE_379"))
    )
    if is_estate_wide:
        if not is_sole_owner(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Launching estate-wide Ultra Scan across the entire inventory is restricted solely to the system owner.",
            )

    # 3. Plan Inventory
    scope_str = ultra_in.scope if isinstance(ultra_in.scope, str) else ""
    if scope_str.upper() in ("FIXTURE_379", "EMPIRE_ESTATE_379"):
        inventory_items = ultra_planner.generate_acceptance_fixture_379()
    elif scope_str.upper() == "ALL":
        asset_res = await db.execute(select(Asset))
        db_assets = asset_res.scalars().all()
        if db_assets:
            inventory_items = [
                {
                    "id": str(a.id),
                    "target_locator": a.target_locator,
                    "asset_type": a.asset_type,
                    "is_out_of_scope": False,
                    "is_alias": False,
                    "environment": a.environment,
                    "tenant": "empire_edu",
                    "identity": "synthetic_scanner",
                }
                for a in db_assets
            ]
        else:
            inventory_items = ultra_planner.generate_acceptance_fixture_379()
    elif isinstance(ultra_in.scope, list):
        if not ultra_in.scope:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scope target list cannot be empty.")
        target_uuids = [uuid.UUID(str(t)) for t in ultra_in.scope]
        asset_res = await db.execute(select(Asset).where(Asset.id.in_(target_uuids)))
        db_assets = asset_res.scalars().all()
        inventory_items = [
            {
                "id": str(a.id),
                "target_locator": a.target_locator,
                "asset_type": a.asset_type,
                "is_out_of_scope": False,
                "is_alias": False,
                "environment": a.environment,
                "tenant": "empire_edu",
                "identity": "synthetic_scanner",
            }
            for a in db_assets
        ]
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid scope '{ultra_in.scope}'.")

    profile_val = ultra_in.profile.value if hasattr(ultra_in.profile, "value") else str(ultra_in.profile)
    plan_batch_id = uuid.uuid4()
    plan = ultra_planner.plan_inventory(
        inventory_items=inventory_items,
        requested_engines=ultra_in.engines,
        profile=profile_val,
        batch_id=str(plan_batch_id),
    )

    # 4. Create ScanBatch Entity
    batch = ScanBatch(
        id=plan_batch_id,
        name=f"Empire Ultra Scan Assessment ({plan.independent_execution_targets} Targets)",
        status=ScanStatus.QUEUED.value,
        target_count=plan.independent_execution_targets,
        total_scans=plan.engine_executions_count,
        engines=ultra_in.engines or ["nuclei", "zap", "empire", "trivy"],
        profiles=[profile_val],
        idempotency_key=idempotency_key,
        metadata_json={
            "initiator": ultra_in.initiator or current_user.email,
            "policy_revision": plan.policy_revision,
            "accounted_inventory_rows": plan.accounted_inventory_rows,
            "independent_execution_targets": plan.independent_execution_targets,
            "shared_alias_count": plan.shared_alias_count,
            "excluded_count": plan.excluded_count,
            "shared_result_links": plan.shared_result_links,
            "explained_exclusions": plan.explained_exclusions,
            "allow_private_targets": ultra_in.allow_private_targets,
            "timeout_seconds": ultra_in.timeout_seconds,
        },
    )
    db.add(batch)
    await db.flush()

    # 5. Populate Execution Targets (Ensure Assets and Child Scans)
    exec_target_ids = {uuid.UUID(child.target_id) for child in plan.all_executions}
    existing_assets_res = await db.execute(select(Asset.id).where(Asset.id.in_(exec_target_ids)))
    existing_asset_ids = set(existing_assets_res.scalars().all())

    locator_map = {child.target_id: child.target_locator for child in plan.all_executions}
    missing_ids = exec_target_ids - existing_asset_ids
    for mid in missing_ids:
        mid_str = str(mid)
        loc = locator_map.get(mid_str, f"https://target-{mid_str[:8]}.empire.edu.vn")
        synthetic_asset = Asset(
            id=mid,
            name=f"Asset {loc}",
            asset_type=AssetType.WEB_APP.value,
            target_locator=loc,
            empire_module=EmpireModule.WEB_APPLICATION.value,
            environment="PRODUCTION",
            technology="Empire Cloud Service",
            verification_status=VerificationStatus.VERIFIED.value,
        )
        db.add(synthetic_asset)

    if missing_ids:
        await db.flush()

    created_scans: List[Scan] = []
    scans_to_dispatch: List[uuid.UUID] = []

    for child in plan.all_executions:
        scan_id = uuid.UUID(child.execution_id)
        target_uuid = uuid.UUID(child.target_id)
        scan = Scan(
            id=scan_id,
            asset_id=target_uuid,
            batch_id=batch.id,
            engine=child.engine,
            profile=child.profile,
            status=ScanStatus.QUEUED.value,
            progress_percentage=0,
            target_locator=child.target_locator,
            allow_private_targets=ultra_in.allow_private_targets,
            timeout_seconds=ultra_in.timeout_seconds,
        )
        db.add(scan)
        created_scans.append(scan)
        scans_to_dispatch.append(scan_id)

    await db.commit()
    await db.refresh(batch)

    # 6. Dispatch Queued Child Scans to Dispatcher
    dispatcher = get_dispatcher()
    await dispatcher.batch_dispatch_scans(scans_to_dispatch, batch_id=batch.id)

    return UltraScanResponse(
        batch_id=batch.id,
        name=batch.name,
        status=batch.status,
        accounted_inventory_rows=plan.accounted_inventory_rows,
        independent_execution_targets=plan.independent_execution_targets,
        engine_executions_count=plan.engine_executions_count,
        shared_alias_count=plan.shared_alias_count,
        excluded_count=plan.excluded_count,
        tracker_link=f"/active-assessments?batch_id={batch.id}",
        snapshot_time=plan.snapshot_time,
        policy_revision=plan.policy_revision,
        idempotency_recovered=False,
        message=f"Ultra Scan batch '{batch.name}' successfully planned and dispatched with {len(created_scans)} executions.",
    )


@router.get("/batches", response_model=PaginatedResponse[ScanBatchRead])
async def list_batches(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = await _scoped_batch_filter(select(ScanBatch), db, current_user)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.order_by(ScanBatch.created_at.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


@router.get("/batch/{batch_id}", response_model=ScanBatchRead)
async def get_batch(
    batch_id: uuid.UUID,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = await _scoped_batch_filter(select(ScanBatch).where(ScanBatch.id == batch_id), db, current_user)
    batch = (await db.execute(stmt)).scalars().first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan batch not found")
    return batch


@router.post("/batch/{batch_id}/cancel")
async def cancel_batch(
    batch_id: uuid.UUID,
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await db.execute(select(ScanBatch).where(ScanBatch.id == batch_id))
    batch = result.scalars().first()
    if not batch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan batch not found")

    dispatcher = get_dispatcher()
    cancelled_count = await dispatcher.cancel_batch(batch_id)
    await db.refresh(batch)

    return {
        "batch_id": batch.id,
        "status": ScanStatus.CANCELLED.value,
        "cancelled_count": cancelled_count,
        "message": f"Scan batch {batch_id} cancelled successfully ({cancelled_count} scans halted).",
    }


@router.post("/stop-all")
async def stop_all_scans(
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Platform-wide emergency stop halting all running scans, sub-processes, and queued tasks."""
    dispatcher = get_dispatcher()
    halted_count = await dispatcher.stop_all()
    return {
        "status": "STOPPED",
        "halted_count": halted_count,
        "message": f"Platform-wide emergency stop executed: {halted_count} scans halted.",
    }


@router.get("/trackcurrent", response_model=TrackCurrentResponse)
@router.get("/telemetry", response_model=TrackCurrentResponse)
async def get_trackcurrent(
    current_user: User = Depends(require_owner),
) -> Any:
    """Provides real-time telemetry on active worker threads, queue depth, and host resources."""
    dispatcher = get_dispatcher()
    return dispatcher.get_telemetry()


# ============================================================================
# SINGLE SCAN LIFECYCLE & LOG ENDPOINTS
# ============================================================================

@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(
    scan_id: uuid.UUID,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    scan = await _scoped_scan(db, current_user, scan_id, "READ")
    return scan


@router.delete("/{scan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scan(
    scan_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    scan = await _scoped_scan(db, current_user, scan_id, "READ")

    await db.delete(scan)
    await db.commit()


@router.post("/{scan_id}/cancel", response_model=ScanCancelResponse)
async def cancel_scan(
    scan_id: uuid.UUID,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    scan = await _scoped_scan(db, current_user, scan_id, "SCAN")

    dispatcher = get_dispatcher()
    success = await dispatcher.cancel_scan(scan_id)

    if success:
        scan.status = ScanStatus.CANCELLED.value
        scan.cancelled_at = datetime.now(timezone.utc)
        await db.commit()
    await db.refresh(scan)
    return ScanCancelResponse(
        scan_id=scan.id,
        status=ScanStatus(scan.status),
        message="Scan cancelled successfully." if success else "Scan could not be cancelled or was already finished.",
    )


@router.get("/{scan_id}/logs", response_model=PaginatedResponse[ScanLogEntry])
async def get_scan_logs(
    scan_id: uuid.UUID,
    days: Optional[int] = Query(None, ge=1, le=365, description="Filter logs within past N days"),
    from_date: Optional[datetime] = Query(None, description="Start datetime (UTC/ISO)"),
    to_date: Optional[datetime] = Query(None, description="End datetime (UTC/ISO)"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    search: Optional[str] = Query(None, description="Text search in message"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=1000),
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    await _scoped_scan(db, current_user, scan_id, "READ")
    stmt = select(ScanLog).where(ScanLog.scan_id == scan_id)

    if days is not None:
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(ScanLog.timestamp >= threshold)
    if from_date:
        stmt = stmt.where(ScanLog.timestamp >= from_date)
    if to_date:
        stmt = stmt.where(ScanLog.timestamp <= to_date)
    if level:
        stmt = stmt.where(func.upper(ScanLog.level) == level.upper())
    if search:
        stmt = stmt.where(ScanLog.message.ilike(f"%{search}%"))

    stmt = stmt.order_by(ScanLog.timestamp.asc())
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()

    pages = (total + size - 1) // size if total > 0 else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


@router.delete("/{scan_id}/logs")
async def delete_scan_logs(
    scan_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Deletes all operational logs associated with a scan ID."""
    stmt = delete(ScanLog).where(ScanLog.scan_id == scan_id)
    res = await db.execute(stmt)
    await log_buffer.clear_scan(scan_id)
    await db.commit()
    purged_count = res.rowcount if hasattr(res, "rowcount") else 0
    return {
        "scan_id": str(scan_id),
        "purged_count": max(0, purged_count),
        "message": f"Successfully deleted {max(0, purged_count)} logs for scan {scan_id}",
    }


@router.get("/{scan_id}/events/stream")
@router.get("/{scan_id}/logs/stream")  # Dual route for backward compatibility
async def stream_scan_events(
    scan_id: uuid.UUID,
    request: Request,
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    cursor: Optional[int] = Query(None, description="Monotonic integer event cursor"),
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """SSE stream with Last-Event-ID replay and gap detection. Authorization is
    re-validated every heartbeat: logout, disable or grant revocation ends the stream."""
    scoped_scan = await _scoped_scan(db, current_user, scan_id, "READ")
    stream_asset_id = scoped_scan.asset_id
    start_id = 0
    if last_event_id:
        try:
            start_id = int(last_event_id.strip())
        except ValueError:
            start_id = 0
    elif cursor is not None:
        start_id = max(0, cursor)

    async def event_generator():
        last_emitted_id = start_id

        # Phase 1: Replay all historic committed events from DB where id > start_id
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ScanEvent)
                .where(ScanEvent.scan_id == scan_id)
                .where(ScanEvent.id > start_id)
                .order_by(ScanEvent.id.asc())
            )
            res = await session.execute(stmt)
            for evt in res.scalars().all():
                payload = {
                    "id": evt.id,
                    "scan_id": str(evt.scan_id) if evt.scan_id else None,
                    "timestamp": evt.occurred_at.isoformat(),
                    "level": evt.level,
                    "message": evt.message,
                    "source": evt.engine or "system",
                    "event_type": evt.event_type,
                    "details": evt.details_json or {},
                }
                yield f"id: {evt.id}\nevent: {evt.event_type}\ndata: {json.dumps(payload)}\n\n"
                last_emitted_id = max(last_emitted_id, evt.id)

        # Phase 2: Live PubSub stream with gap detection and periodic heartbeats
        live_gen = event_broadcaster.subscribe_scan(scan_id)
        try:
            while True:
                if await request.is_disconnected():
                    break
                if not await session_still_valid(request, stream_asset_id):
                    yield AUTH_REVOKED_FRAME
                    break
                try:
                    evt = await asyncio.wait_for(live_gen.__anext__(), timeout=10.0)

                    # Deduplicate against Phase 1 replay
                    if evt.id <= last_emitted_id:
                        continue

                    # Gap Detection: Check if events were committed while switching from replay to queue
                    if evt.id > last_emitted_id + 1:
                        async with AsyncSessionLocal() as gap_session:
                            gap_stmt = (
                                select(ScanEvent)
                                .where(ScanEvent.scan_id == scan_id)
                                .where(ScanEvent.id > last_emitted_id)
                                .where(ScanEvent.id < evt.id)
                                .order_by(ScanEvent.id.asc())
                            )
                            gap_res = await gap_session.execute(gap_stmt)
                            for g_evt in gap_res.scalars().all():
                                g_payload = {
                                    "id": g_evt.id,
                                    "scan_id": str(g_evt.scan_id) if g_evt.scan_id else None,
                                    "timestamp": g_evt.occurred_at.isoformat(),
                                    "level": g_evt.level,
                                    "message": g_evt.message,
                                    "source": g_evt.engine or "system",
                                    "event_type": g_evt.event_type,
                                    "details": g_evt.details_json or {},
                                }
                                yield f"id: {g_evt.id}\nevent: {g_evt.event_type}\ndata: {json.dumps(g_payload)}\n\n"
                                last_emitted_id = g_evt.id

                    # Yield live event
                    payload = {
                        "id": evt.id,
                        "scan_id": str(evt.scan_id) if evt.scan_id else None,
                        "timestamp": evt.occurred_at.isoformat(),
                        "level": evt.level,
                        "message": evt.message,
                        "source": evt.engine or "system",
                        "event_type": evt.event_type,
                        "details": evt.details_json or {},
                    }
                    yield f"id: {evt.id}\nevent: {evt.event_type}\ndata: {json.dumps(payload)}\n\n"
                    last_emitted_id = evt.id

                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                except (StopAsyncIteration, asyncio.CancelledError):
                    break
        finally:
            await live_gen.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{scan_id}/events")
async def get_scan_events(
    scan_id: uuid.UUID,
    after_id: int = Query(0, ge=0, description="Monotonic integer cursor: returns events with id > after_id"),
    limit: int = Query(200, ge=1, le=1000, description="Batch size for bounded polling"),
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Bounded incremental event polling endpoint with cursor pagination for events 101+."""
    await _scoped_scan(db, current_user, scan_id, "READ")
    stmt = (
        select(ScanEvent)
        .where(ScanEvent.scan_id == scan_id)
        .where(ScanEvent.id > after_id)
        .order_by(ScanEvent.id.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    items = result.scalars().all()

    total_stmt = select(func.count()).select_from(
        select(ScanEvent).where(ScanEvent.scan_id == scan_id).subquery()
    )
    total_res = await db.execute(total_stmt)
    total = total_res.scalar() or 0

    return {
        "items": [
            {
                "id": e.id,
                "scan_id": str(e.scan_id) if e.scan_id else None,
                "timestamp": e.occurred_at.isoformat(),
                "level": e.level,
                "message": e.message,
                "source": e.engine or "system",
                "event_type": e.event_type,
                "details": e.details_json or {},
            }
            for e in items
        ],
        "total": total,
        "page": 1,
        "size": len(items),
        "pages": 1,
    }


class LoopTestRequest(BaseModel):
    target_locator: str = Field(default="https://empire.edu.vn/")
    loops: int = Field(default=3, ge=1, le=5)
    profile: ScanProfile = Field(default=ScanProfile.QUICK)
    engines: List[str] = Field(default_factory=lambda: ["nuclei", "zap", "empire_engine", "crawler"])


class LoopPassResult(BaseModel):
    pass_number: int
    scan_id: str
    status: str
    quality_status: str
    findings_count: int
    new_findings_count: int
    duration_seconds: float
    timestamp: str


class LoopTestResponse(BaseModel):
    status: str
    target_locator: str
    loops_requested: int
    loops_completed: int
    drift_detected: bool
    total_unique_findings: int
    passes: List[LoopPassResult]
    message: str


@router.post("/loop-test", response_model=LoopTestResponse)
async def run_loop_test(
    payload: Optional[LoopTestRequest] = None,
    target_locator: Optional[str] = Query(None),
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Execute sequential multi-pass assessment on the target to track stability, finding drift, and emit lifecycle alerts."""
    effective_loc = payload.target_locator if payload and payload.target_locator else target_locator
    if not effective_loc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="target_locator is required via request body or query parameter",
        )
    target_norm = effective_loc.rstrip("/")
    stmt = select(Asset).where(
        (Asset.target_locator == effective_loc)
        | (Asset.target_locator == target_norm)
        | (Asset.target_locator == target_norm + "/")
    )
    res = await db.execute(stmt)
    asset = res.scalars().first()
    if not asset:
        # F12: Reject unknown loop-test asset with HTTP 404 (eliminate silent fallback)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target asset not found for loop test: '{effective_loc}'",
        )

    passes_results: List[LoopPassResult] = []
    seen_fingerprints = set()
    total_drift_count = 0
    dispatcher = get_dispatcher()

    loops_count = payload.loops if payload and payload.loops else 3
    chosen_profile = payload.profile.value if payload and payload.profile else ScanProfile.QUICK.value
    engine_list = payload.engines if payload and payload.engines else ["nuclei", "zap", "empire_engine", "crawler"]
    engine_str = ",".join(engine_list) if engine_list else "all"

    for pass_idx in range(1, loops_count + 1):
        pass_t0 = time.perf_counter()
        scan = Scan(
            id=uuid.uuid4(),
            asset_id=asset.id,
            engine=engine_str,
            profile=chosen_profile,
            status=ScanStatus.QUEUED.value,
            progress_percentage=0,
            target_locator=asset.target_locator,
            allow_private_targets=bool(not settings.is_production and settings.SSRF_ALLOW_PRIVATE_TARGETS),
            timeout_seconds=30,
        )
        db.add(scan)
        await db.commit()

        # Execute scan pass directly
        from backend.app.scanners.base import CancellationToken
        token = CancellationToken()
        await dispatcher._run_scan(scan.id, token, 1)

        await db.refresh(scan)

        # Inspect findings
        findings_res = await db.execute(
            select(NormalizedFinding).where(NormalizedFinding.asset_id == asset.id)
        )
        current_findings = findings_res.scalars().all()
        current_fps = {f.fingerprint for f in current_findings if f.fingerprint}

        new_in_this_pass = len(current_fps - seen_fingerprints) if seen_fingerprints else 0
        if pass_idx > 1 and new_in_this_pass > 0:
            total_drift_count += new_in_this_pass
        seen_fingerprints.update(current_fps)

        duration = round(time.perf_counter() - pass_t0, 2)
        pass_res = LoopPassResult(
            pass_number=pass_idx,
            scan_id=str(scan.id),
            status=scan.status,
            quality_status=scan.quality_status or "SCANNED_SUCCESSFULLY",
            findings_count=len(current_findings),
            new_findings_count=new_in_this_pass,
            duration_seconds=duration,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        passes_results.append(pass_res)

        # Emit notification alert for each pass
        alert = SecurityAlert(
            id=uuid.uuid4(),
            severity="INFO",
            title=f"Loop Test Pass {pass_idx}/{payload.loops} Completed",
            message=f"Sequential loop pass {pass_idx}/{payload.loops} on {asset.target_locator} completed in {duration}s. Total findings: {len(current_findings)}.",
            category="SCAN",
            is_read=False,
            metadata_json={
                "loop_pass": pass_idx,
                "total_loops": payload.loops,
                "scan_id": str(scan.id),
                "duration_seconds": duration,
                "target": asset.target_locator,
            },
        )
        db.add(alert)
        await db.commit()

    drift_detected = total_drift_count > 0
    return {
        "status": "COMPLETED",
        "target_locator": asset.target_locator,
        "loops_requested": payload.loops,
        "loops_completed": len(passes_results),
        "drift_detected": drift_detected,
        "total_unique_findings": len(seen_fingerprints),
        "passes": passes_results,
        "message": "Loop assessment successfully completed with zero regression drift." if not drift_detected else f"Loop assessment completed with {total_drift_count} drift finding(s) detected.",
    }

