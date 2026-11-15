import csv
import io
import ipaddress
import json
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from pydantic import Field
import httpx
import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_authorized_asset_ids, load_scope, require_admin, require_operator, require_viewer
from backend.app.core.database import get_db
from backend.app.core.target_verifier import get_target_verifier
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.proof import AssetOwnershipProof, OwnershipProofMethod, OwnershipProofStatus
from backend.app.models.scope import AssetAssessmentScope
from backend.app.models.scan import Scan
from backend.app.models.user import User
from backend.app.schemas.asset import (
    AssetBulkImportItem,
    AssetBulkImportRequest,
    AssetBulkImportResponse,
    AssetBulkPreviewRequest,
    AssetBulkPreviewResponse,
    AssetCreate,
    AssetResponse,
    AssetUpdate,
    AssetVerifyRequest,
    AssetVerifyResponse,
    BulkPreviewItem,
    VerificationStepResult,
)

from backend.app.schemas.common import (
    AssetType,
    Criticality,
    EmpireModule,
    Exposure,
    FindingSeverity,
    FindingStatus,
    PaginatedResponse,
    ScanStatus,
    VerificationStatus,
    VerificationType,
)

router = APIRouter(prefix="/assets", tags=["Target & Asset Management"])


async def annotate_verification(db: AsyncSession, assets) -> None:
    """Attach `verification_state` / `verification_proof` from the proof table (Milestone 6)."""
    assets = [a for a in assets if a is not None]
    if not assets:
        return
    rows = (await db.execute(select(AssetOwnershipProof).where(
        AssetOwnershipProof.asset_id.in_([a.id for a in assets]),
        AssetOwnershipProof.status == OwnershipProofStatus.VERIFIED.value)
        .order_by(AssetOwnershipProof.created_at))).scalars().all()
    latest = {r.asset_id: r for r in rows}
    for a in assets:
        proof = latest.get(a.id)
        if proof is not None and a.verification_status == VerificationStatus.VERIFIED.value:
            a.verification_state = "VERIFIED"
            a.verification_proof = {"proof_id": str(proof.id), "method": proof.method,
                                    "verified_at": proof.verified_at.isoformat() if proof.verified_at else None,
                                    "created_by": proof.created_by}
        else:
            a.verification_state = ("UNPROVEN" if a.verification_status == VerificationStatus.VERIFIED.value
                                    else a.verification_status)
            a.verification_proof = None


@router.get("", response_model=PaginatedResponse[AssetResponse])
async def list_assets(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    asset_type: Optional[AssetType] = None,
    empire_module: Optional[EmpireModule] = None,
    environment: Optional[str] = None,
    verification_status: Optional[VerificationStatus] = None,
    search: Optional[str] = None,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    stmt = select(Asset)
    allowed_ids = await get_authorized_asset_ids(current_user, db)
    if allowed_ids is not None:
        stmt = stmt.where(Asset.id.in_(allowed_ids))

    if asset_type:
        stmt = stmt.where(Asset.asset_type == asset_type.value)
    if empire_module:
        stmt = stmt.where(Asset.empire_module == empire_module.value)
    if environment:
        stmt = stmt.where(Asset.environment == environment.upper())
    if verification_status:
        stmt = stmt.where(Asset.verification_status == verification_status.value)
    if search:
        search_filter = f"%{search}%"
        stmt = stmt.where(
            or_(
                Asset.name.ilike(search_filter),
                Asset.target_locator.ilike(search_filter),
                Asset.description.ilike(search_filter),
                Asset.technology.ilike(search_filter),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    # Paginate (Module A and primary ecosystem targets ordered by creation)
    stmt = stmt.order_by(Asset.created_at.asc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    items = result.scalars().all()
    await annotate_verification(db, items)

    pages = (total + size - 1) // size if total > 0 else 1
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
    }


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def create_asset(
    asset_in: AssetCreate,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    # Check duplicate locator
    existing = await db.execute(select(Asset).where(Asset.target_locator == asset_in.target_locator.strip()))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Target locator already registered in inventory")

    token = f"sentinel-{uuid.uuid4().hex[:16]}"
    asset_id = uuid.uuid4()
    asset = Asset(
        id=asset_id,
        name=asset_in.name,
        asset_type=asset_in.asset_type.value,
        target_locator=asset_in.target_locator.strip(),
        empire_module=asset_in.empire_module.value,
        environment=asset_in.environment,
        technology=asset_in.technology,
        verification_status=VerificationStatus.PENDING.value,
        verification_type=VerificationType.HTTP_WELL_KNOWN.value,
        verification_token=token,
        criticality=asset_in.criticality.value,
        exposure=asset_in.exposure.value,
        description=asset_in.description,
        tags=asset_in.tags,
        approved_media_baseline=asset_in.approved_media_baseline,
        assessment_policy=asset_in.assessment_policy,
        auth_profile=asset_in.auth_profile,
        excluded_endpoints=asset_in.excluded_endpoints,
    )
    db.add(asset)

    # Separate facts of discovery, ownership proof, and authorized scope (F09)
    proof = AssetOwnershipProof(
        id=uuid.uuid4(),
        asset_id=asset_id,
        method=OwnershipProofMethod.HTTP_WELL_KNOWN.value,
        challenge_token=token,
        status=OwnershipProofStatus.PENDING.value,
        created_by=current_user.username,
    )
    db.add(proof)

    scope = AssetAssessmentScope(
        id=uuid.uuid4(),
        asset_id=asset_id,
        exact_origin=asset_in.target_locator.strip(),
        ports=[80, 443],
        allowed_path_patterns=["/*"],
        rate_limit_rps=1,
        concurrency_limit=1,
        byte_budget=10485760,
        max_requests_per_run=100,
        emergency_stop_active=False,
        created_by=current_user.username,
    )
    db.add(scope)

    await db.commit()
    await db.refresh(asset)
    await annotate_verification(db, [asset])
    return asset


@router.post("/bulk-import", response_model=AssetBulkImportResponse)
async def bulk_import_assets(
    payload: AssetBulkImportRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Bulk imports Empire targets with deduplication, module auto-assignment,
    and pending ownership challenge generation (F09).
    """
    imported_assets: List[Asset] = []
    skipped_duplicates = 0
    errors: List[str] = []

    # Helper function to classify module from locator
    def classify_module(loc: str) -> str:
        loc_lower = loc.lower()
        if "id." in loc_lower or "auth" in loc_lower or "student" in loc_lower:
            return EmpireModule.STUDENT_MANAGEMENT.value
        if "media" in loc_lower or "voh." in loc_lower or "mh." in loc_lower or "storage" in loc_lower:
            return EmpireModule.LEARNING_MATERIALS.value
        if "news" in loc_lower or "tool" in loc_lower or "vocab" in loc_lower:
            return EmpireModule.SUPPORTING_TOOLS.value
        if "gw." in loc_lower or "api" in loc_lower:
            return EmpireModule.API_SERVICES.value
        if "console" in loc_lower or "admin" in loc_lower or "app" in loc_lower:
            return EmpireModule.WEB_APPLICATION.value
        return EmpireModule.SERVER_INFRASTRUCTURE.value

    # Normalize candidate items
    candidates = []
    if payload.items:
        candidates = payload.items
    elif payload.raw_content:
        content = payload.raw_content.strip()
        # Try JSON
        if content.startswith("[") and content.endswith("]"):
            try:
                parsed = json.loads(content)
                for item in parsed:
                    if isinstance(item, str):
                        candidates.append(AssetBulkImportItem(target_locator=item))
                    elif isinstance(item, dict) and "target_locator" in item:
                        candidates.append(AssetBulkImportItem(**item))
            except Exception as e:
                errors.append(f"JSON parse error: {e}")
        # Try CSV
        elif "," in content and "\n" in content:
            try:
                reader = csv.DictReader(io.StringIO(content))
                for row in reader:
                    loc = row.get("target_locator") or row.get("url") or row.get("target")
                    if loc:
                        candidates.append(
                            AssetBulkImportItem(
                                target_locator=loc,
                                name=row.get("name"),
                                environment=row.get("environment", "PRODUCTION"),
                            )
                        )
            except Exception as e:
                errors.append(f"CSV parse error: {e}")
        # Plain lines of URLs/domains
        else:
            for line in content.splitlines():
                clean = line.strip()
                if clean and not clean.startswith("#"):
                    candidates.append(AssetBulkImportItem(target_locator=clean))

    for item in candidates:
        locator = item.target_locator.strip()
        if not locator:
            continue

        # Format URL scheme if missing
        if not locator.startswith("http://") and not locator.startswith("https://"):
            locator = f"https://{locator}"

        # Deduplication check
        existing = await db.execute(select(Asset).where(Asset.target_locator == locator))
        if existing.scalars().first():
            skipped_duplicates += 1
            continue

        mod = item.empire_module.value if item.empire_module else classify_module(locator)
        name = item.name or f"Empire - {urlparse(locator).netloc or locator}"
        token = f"sentinel-{uuid.uuid4().hex[:16]}"
        asset_id = uuid.uuid4()

        new_asset = Asset(
            id=asset_id,
            name=name,
            asset_type=item.asset_type.value if item.asset_type else AssetType.WEB_APP.value,
            target_locator=locator,
            empire_module=mod,
            environment=item.environment or "PRODUCTION",
            technology="Web Target",
            criticality=item.criticality.value if item.criticality else Criticality.MEDIUM.value,
            exposure=Exposure.INTERNET.value,
            verification_status=VerificationStatus.PENDING.value,
            verification_type=VerificationType.HTTP_WELL_KNOWN.value,
            verification_token=token,
            tags=["empire", mod.lower(), "imported"],
        )
        db.add(new_asset)

        # Create pending proof & scope (F09 - eliminate bulk auto-approval)
        proof = AssetOwnershipProof(
            id=uuid.uuid4(),
            asset_id=asset_id,
            method=OwnershipProofMethod.HTTP_WELL_KNOWN.value,
            challenge_token=token,
            status=OwnershipProofStatus.PENDING.value,
            created_by=current_user.username,
        )
        db.add(proof)

        scope = AssetAssessmentScope(
            id=uuid.uuid4(),
            asset_id=asset_id,
            exact_origin=locator,
            ports=[80, 443],
            allowed_path_patterns=["/*"],
            rate_limit_rps=1,
            concurrency_limit=1,
            byte_budget=10485760,
            max_requests_per_run=100,
            emergency_stop_active=False,
            created_by=current_user.username,
        )
        db.add(scope)
        imported_assets.append(new_asset)

    await db.commit()
    for a in imported_assets:
        await db.refresh(a)

    return AssetBulkImportResponse(
        imported_count=len(imported_assets),
        skipped_duplicates=skipped_duplicates,
        errors=errors,
        imported_assets=imported_assets,
    )


@router.post("/bulk-preview", response_model=AssetBulkPreviewResponse)
async def preview_bulk_assets(
    payload: AssetBulkPreviewRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Previews incoming target assets from various formats (URL, domain, IP, CIDR, OpenAPI, CSV, JSON)

    with duplicate detection against the asset inventory and within the import batch.
    """
    candidates: List[Dict[str, Any]] = []

    def classify_mod(loc: str) -> EmpireModule:
        loc_lower = loc.lower()
        if any(k in loc_lower for k in ("id.", "auth", "student", "account")):
            return EmpireModule.STUDENT_MANAGEMENT
        if any(k in loc_lower for k in ("media", "voh.", "mh.", "storage", "s3", "minio")):
            return EmpireModule.LEARNING_MATERIALS
        if any(k in loc_lower for k in ("news", "tool", "vocab", "learn")):
            return EmpireModule.SUPPORTING_TOOLS
        if any(k in loc_lower for k in ("gw.", "api", "gateway", "graphql")):
            return EmpireModule.API_SERVICES
        if any(k in loc_lower for k in ("console", "admin", "dashboard", "portal")):
            return EmpireModule.WEB_APPLICATION
        return EmpireModule.WEB_APPLICATION

    def classify_type(loc: str) -> AssetType:
        clean = loc.replace("https://", "").replace("http://", "").split("/")[0]
        # Check CIDR
        if "/" in clean and not loc.startswith("http"):
            try:
                ipaddress.ip_network(clean, strict=False)
                return AssetType.SERVER
            except ValueError:
                pass
        # Check IP
        try:
            ipaddress.ip_address(clean.split(":")[0])
            return AssetType.SERVER
        except ValueError:
            pass
        if "api" in loc.lower() or "openapi" in loc.lower():
            return AssetType.API_ENDPOINT
        if "voh." in loc.lower() or "s3" in loc.lower() or "storage" in loc.lower():
            return AssetType.OBJECT_STORAGE
        return AssetType.WEB_APP

    if payload.items:
        for item in payload.items:
            loc = item.target_locator.strip()
            if not loc.startswith("http://") and not loc.startswith("https://") and not "/" in loc:
                loc = f"https://{loc}"
            candidates.append({
                "target_locator": loc,
                "name": item.name or f"Empire - {urlparse(loc).netloc or loc}",
                "asset_type": item.asset_type or classify_type(loc),
                "empire_module": item.empire_module or classify_mod(loc),
                "environment": item.environment or "PRODUCTION",
                "criticality": item.criticality or Criticality.MEDIUM,
            })
    elif payload.raw_content:
        content = payload.raw_content.strip()
        parsed_as_structured = False

        # 1. Check OpenAPI (JSON or YAML)
        if (
            payload.import_type.upper() == "OPENAPI"
            or "openapi" in content[:300].lower()
            or "swagger" in content[:300].lower()
        ):
            try:
                spec = json.loads(content) if content.startswith("{") else yaml.safe_load(content)
                if isinstance(spec, dict) and ("openapi" in spec or "swagger" in spec):
                    parsed_as_structured = True
                    servers = spec.get("servers", [])
                    if servers:
                        for srv in servers:
                            url = srv.get("url", "").strip()
                            if url:
                                if not url.startswith("http://") and not url.startswith("https://"):
                                    url = f"https://{url}"
                                candidates.append({
                                    "target_locator": url,
                                    "name": srv.get("description") or f"OpenAPI Service ({spec.get('info', {}).get('title', 'Empire API')})",
                                    "asset_type": AssetType.API_ENDPOINT,
                                    "empire_module": classify_mod(url),
                                    "environment": "PRODUCTION",
                                    "criticality": Criticality.HIGH,
                                })
                    elif "host" in spec:
                        schemes = spec.get("schemes", ["https"])
                        scheme = schemes[0] if schemes else "https"
                        base_path = spec.get("basePath", "")
                        url = f"{scheme}://{spec['host']}{base_path}"
                        candidates.append({
                            "target_locator": url,
                            "name": f"OpenAPI Service ({spec.get('info', {}).get('title', 'Empire API')})",
                            "asset_type": AssetType.API_ENDPOINT,
                            "empire_module": classify_mod(url),
                            "environment": "PRODUCTION",
                            "criticality": Criticality.HIGH,
                        })
            except Exception:
                pass

        # 2. Check JSON List
        if not parsed_as_structured and content.startswith("[") and content.endswith("]"):
            try:
                arr = json.loads(content)
                parsed_as_structured = True
                for elem in arr:
                    if isinstance(elem, str) and elem.strip():
                        loc = elem.strip()
                        if not loc.startswith("http://") and not loc.startswith("https://"):
                            loc = f"https://{loc}"
                        candidates.append({
                            "target_locator": loc,
                            "name": f"Empire - {urlparse(loc).netloc or loc}",
                            "asset_type": classify_type(loc),
                            "empire_module": classify_mod(loc),
                            "environment": "PRODUCTION",
                            "criticality": Criticality.MEDIUM,
                        })
                    elif isinstance(elem, dict) and "target_locator" in elem:
                        loc = elem["target_locator"].strip()
                        if not loc.startswith("http://") and not loc.startswith("https://"):
                            loc = f"https://{loc}"
                        mod_val = elem.get("empire_module")
                        candidates.append({
                            "target_locator": loc,
                            "name": elem.get("name") or f"Empire - {urlparse(loc).netloc or loc}",
                            "asset_type": AssetType(elem["asset_type"]) if elem.get("asset_type") else classify_type(loc),
                            "empire_module": EmpireModule(mod_val) if mod_val else classify_mod(loc),
                            "environment": elem.get("environment", "PRODUCTION"),
                            "criticality": Criticality(elem["criticality"]) if elem.get("criticality") else Criticality.MEDIUM,
                        })
            except Exception:
                pass

        # 3. Check CSV
        if not parsed_as_structured and "," in content and "\n" in content:
            first_line = content.splitlines()[0].lower()
            if any(k in first_line for k in ("target", "url", "locator", "module", "name")):
                try:
                    reader = csv.DictReader(io.StringIO(content))
                    for row in reader:
                        loc = (
                            row.get("target_locator")
                            or row.get("target")
                            or row.get("url")
                            or row.get("locator")
                        )
                        if loc and loc.strip():
                            loc = loc.strip()
                            if not loc.startswith("http://") and not loc.startswith("https://"):
                                loc = f"https://{loc}"
                            raw_mod = row.get("empire_module") or row.get("module")
                            candidates.append({
                                "target_locator": loc,
                                "name": row.get("name") or f"Empire - {urlparse(loc).netloc or loc}",
                                "asset_type": classify_type(loc),
                                "empire_module": EmpireModule(raw_mod) if raw_mod in EmpireModule.__members__ else classify_mod(loc),
                                "environment": row.get("environment", "PRODUCTION").upper(),
                                "criticality": Criticality.MEDIUM,
                            })
                    parsed_as_structured = True
                except Exception:
                    pass

        # 4. Check Plain Lines (TXT / URLs / Domains / CIDRs / IPs)
        if not parsed_as_structured:
            for raw_line in content.splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                # Check CIDR
                if "/" in line and not line.startswith("http"):
                    try:
                        net = ipaddress.ip_network(line, strict=False)
                        if net.num_addresses <= 8:
                            for ip in net.hosts():
                                ip_url = f"https://{ip}"
                                candidates.append({
                                    "target_locator": ip_url,
                                    "name": f"Empire Host - {ip}",
                                    "asset_type": AssetType.SERVER,
                                    "empire_module": EmpireModule.SERVER_INFRASTRUCTURE,
                                    "environment": "PRODUCTION",
                                    "criticality": Criticality.MEDIUM,
                                })
                        else:
                            candidates.append({
                                "target_locator": str(net),
                                "name": f"Empire Subnet - {net}",
                                "asset_type": AssetType.SERVER,
                                "empire_module": EmpireModule.SERVER_INFRASTRUCTURE,
                                "environment": "PRODUCTION",
                                "criticality": Criticality.HIGH,
                            })
                        continue
                    except ValueError:
                        pass

                # Check plain IP
                try:
                    ipaddress.ip_address(line)
                    ip_url = f"https://{line}"
                    candidates.append({
                        "target_locator": ip_url,
                        "name": f"Empire Host - {line}",
                        "asset_type": AssetType.SERVER,
                        "empire_module": EmpireModule.SERVER_INFRASTRUCTURE,
                        "environment": "PRODUCTION",
                        "criticality": Criticality.MEDIUM,
                    })
                    continue
                except ValueError:
                    pass

                # Standard URL or Domain
                loc = line
                if not loc.startswith("http://") and not loc.startswith("https://"):
                    loc = f"https://{loc}"
                try:
                    parsed_netloc = urlparse(loc).netloc
                except Exception:
                    parsed_netloc = loc
                candidates.append({
                    "target_locator": loc,
                    "name": f"Empire - {parsed_netloc or loc}",
                    "asset_type": classify_type(loc),
                    "empire_module": classify_mod(loc),
                    "environment": "PRODUCTION",
                    "criticality": Criticality.MEDIUM,
                })

    # Deduplication analysis against database
    existing_res = await db.execute(select(Asset.id, Asset.target_locator))
    existing_rows = existing_res.all()

    def norm_key(loc: str) -> str:
        k = loc.strip().rstrip("/").lower()
        if k.startswith("https://") and ":443" in k:
            k = k.replace(":443", "")
        if k.startswith("http://") and ":80" in k:
            k = k.replace(":80", "")
        return k

    db_map = {norm_key(r[1]): str(r[0]) for r in existing_rows}
    seen_in_batch: set[str] = set()

    new_items: List[BulkPreviewItem] = []
    dup_items: List[BulkPreviewItem] = []

    for c in candidates:
        loc = c["target_locator"]
        key = norm_key(loc)

        if key in db_map:
            dup_items.append(
                BulkPreviewItem(
                    target_locator=loc,
                    name=c["name"],
                    asset_type=c["asset_type"],
                    empire_module=c["empire_module"],
                    environment=c["environment"],
                    criticality=c["criticality"],
                    is_duplicate=True,
                    existing_asset_id=db_map[key],
                    reason=f"Target locator already registered in inventory (Asset ID: {db_map[key]})",
                )
            )
        elif key in seen_in_batch:
            dup_items.append(
                BulkPreviewItem(
                    target_locator=loc,
                    name=c["name"],
                    asset_type=c["asset_type"],
                    empire_module=c["empire_module"],
                    environment=c["environment"],
                    criticality=c["criticality"],
                    is_duplicate=True,
                    existing_asset_id=None,
                    reason="Duplicate target entry detected within current import batch",
                )
            )
        else:
            seen_in_batch.add(key)
            new_items.append(
                BulkPreviewItem(
                    target_locator=loc,
                    name=c["name"],
                    asset_type=c["asset_type"],
                    empire_module=c["empire_module"],
                    environment=c["environment"],
                    criticality=c["criticality"],
                    is_duplicate=False,
                    existing_asset_id=None,
                    reason=None,
                )
            )

    return AssetBulkPreviewResponse(
        total=len(new_items) + len(dup_items),
        new=new_items,
        duplicate=dup_items,
    )



@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: uuid.UUID,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target asset not found")

    allowed_ids = await get_authorized_asset_ids(current_user, db)
    if allowed_ids is not None and asset_id not in allowed_ids:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to target asset")

    await annotate_verification(db, [asset])
    return asset


@router.get("/{asset_id}/summary")
async def get_asset_summary(
    asset_id: uuid.UUID,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    (await load_scope(current_user, db)).require(asset_id, "READ")
    asset_res = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = asset_res.scalars().first()
    if not asset:
        raise HTTPException(status_code=404, detail="Target asset not found")

    findings_res = await db.execute(select(NormalizedFinding).where(NormalizedFinding.asset_id == asset_id))
    findings = findings_res.scalars().all()

    critical_count = sum(1 for f in findings if f.severity == FindingSeverity.CRITICAL.value and f.status != FindingStatus.FIXED.value)
    high_count = sum(1 for f in findings if f.severity == FindingSeverity.HIGH.value and f.status != FindingStatus.FIXED.value)
    open_count = sum(1 for f in findings if f.status in (FindingStatus.OPEN.value, FindingStatus.NEW.value, FindingStatus.REOPENED.value))
    fixed_count = sum(1 for f in findings if f.status == FindingStatus.FIXED.value)

    last_scan_res = await db.execute(
        select(Scan).where(Scan.asset_id == asset_id, Scan.completed_at.is_not(None)).order_by(Scan.completed_at.desc()).limit(1)
    )
    last_scan = last_scan_res.scalars().first()

    return {
        "asset_id": str(asset.id),
        "name": asset.name,
        "target_locator": asset.target_locator,
        "empire_module": asset.empire_module,
        "environment": asset.environment,
        "critical_findings": critical_count,
        "high_findings": high_count,
        "open_findings": open_count,
        "fixed_findings": fixed_count,
        "total_findings": len(findings),
        "last_assessment_at": last_scan.completed_at.isoformat() if last_scan and last_scan.completed_at else None,
        "last_scan_status": last_scan.status if last_scan else None,
    }


class AssetUpdateRequest(AssetUpdate):
    target_locator: Optional[str] = Field(default=None, min_length=1, max_length=1024)


@router.put("/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: uuid.UUID,
    asset_in: AssetUpdateRequest,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target asset not found")

    old_locator = asset.target_locator
    new_locator = asset_in.target_locator.strip() if asset_in.target_locator else None
    locator_changed = new_locator is not None and new_locator != old_locator

    update_data = asset_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            if hasattr(value, "value"):
                value = value.value
            setattr(asset, field, value)

    # Invalidate associated proofs and scopes if target locator changed (F10)
    if locator_changed:
        # 1. Invalidate existing proofs
        await db.execute(
            update(AssetOwnershipProof)
            .where(AssetOwnershipProof.asset_id == asset.id)
            .values(status=OwnershipProofStatus.REVOKED.value)
        )
        # 2. Deactivate existing scopes with emergency stop
        await db.execute(
            update(AssetAssessmentScope)
            .where(AssetAssessmentScope.asset_id == asset.id)
            .values(emergency_stop_active=True)
        )
        # 3. Reset verification status
        asset.verification_status = VerificationStatus.PENDING.value
        asset.verification_type = VerificationType.HTTP_WELL_KNOWN.value
        asset.verified_at = None
        asset.verification_token = f"sentinel-{uuid.uuid4().hex[:16]}"

        # 4. Generate fresh pending proof and scope for new locator
        new_proof = AssetOwnershipProof(
            id=uuid.uuid4(),
            asset_id=asset.id,
            method=OwnershipProofMethod.HTTP_WELL_KNOWN.value,
            challenge_token=asset.verification_token,
            status=OwnershipProofStatus.PENDING.value,
            created_by=current_user.username,
        )
        db.add(new_proof)

        new_scope = AssetAssessmentScope(
            id=uuid.uuid4(),
            asset_id=asset.id,
            exact_origin=new_locator,
            ports=[80, 443],
            allowed_path_patterns=["/*"],
            rate_limit_rps=1,
            concurrency_limit=1,
            byte_budget=10485760,
            max_requests_per_run=100,
            emergency_stop_active=False,
            created_by=current_user.username,
        )
        db.add(new_scope)

    await db.commit()
    await db.refresh(asset)
    await annotate_verification(db, [asset])
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target asset not found")

    await db.delete(asset)
    await db.commit()


@router.post("/{asset_id}/verify", response_model=AssetVerifyResponse)
async def verify_asset(
    asset_id: uuid.UUID,
    verify_req: AssetVerifyRequest = AssetVerifyRequest(),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target asset not found")

    verifier = get_target_verifier()
    probe_res = await verifier.verify_target(
        asset.target_locator,
        allow_private=verify_req.allow_private,
    )

    probe_passes = probe_res["verified"]

    # F09: Separate facts of discovery, ownership proof, and scope
    proof_method = verify_req.verification_type.value
    challenge_data: dict = {}

    if verify_req.verification_type == VerificationType.ADMIN_OVERRIDE:
        # Owner attests ownership out-of-band (manual evidence). Recorded with actor ID.
        is_verified = True
        challenge_data = {"override_by_user_id": str(current_user.id), "method": "OWNER_ATTESTATION"}
    else:
        # Challenge verification (DNS TXT or HTTP well-known)
        challenge_passed, challenge_msg, challenge_data = await verifier.verify_ownership_challenge(
            asset.target_locator,
            asset.verification_token,
            method=proof_method,
            allow_private=verify_req.allow_private,
        )
        is_verified = challenge_passed and probe_passes

    now_utc = datetime.now(timezone.utc)

    # Persist genuine AssetOwnershipProof
    proof = AssetOwnershipProof(
        id=uuid.uuid4(),
        asset_id=asset.id,
        method=proof_method,
        challenge_token=asset.verification_token,
        status=OwnershipProofStatus.VERIFIED.value if is_verified else OwnershipProofStatus.FAILED.value,
        verified_at=now_utc if is_verified else None,
        proof_data=challenge_data,
        created_by=current_user.username,
    )
    db.add(proof)

    if is_verified:
        asset.verification_status = VerificationStatus.VERIFIED.value
        asset.verification_type = proof_method
        asset.verified_at = now_utc.isoformat()
        tech_list = probe_res.get("fingerprint", {}).get("technologies", [])
        if tech_list:
            asset.technology = " / ".join(tech_list)
    else:
        asset.verification_status = VerificationStatus.FAILED.value

    await db.commit()
    await db.refresh(asset)

    response_status = "VERIFIED" if is_verified else probe_res["status"]

    return AssetVerifyResponse(
        asset_id=asset.id,
        verification_status=VerificationStatus(asset.verification_status),
        verified=is_verified,
        status=response_status,
        message=probe_res["message"],
        steps=[VerificationStepResult(**s) for s in probe_res["steps"]],
        fingerprint=probe_res["fingerprint"],
    )


@router.post("/{asset_id}/emergency-stop")
async def emergency_stop_asset(
    asset_id: uuid.UUID,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Target-level emergency stop: Immediately toggles emergency_stop_active=True
    and terminates all active scanner processes for the asset in < 3s.
    """
    from backend.app.core.dispatcher import process_safety

    result = await db.execute(select(Asset).where(Asset.id == asset_id))
    asset = result.scalars().first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target asset not found")

    scope_res = await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == asset_id))
    scope = scope_res.scalars().first()
    if scope:
        scope.emergency_stop_active = True
    else:
        # Create an emergency scope record to enforce the kill-switch if not present
        scope = AssetAssessmentScope(
            asset_id=asset.id,
            exact_origin=asset.target_locator,
            emergency_stop_active=True,
            created_by=current_user.username,
        )
        db.add(scope)

    # Halt all running and queued scans for this asset
    scans_res = await db.execute(
        select(Scan).where(
            Scan.asset_id == asset_id,
            Scan.status.in_([
                ScanStatus.QUEUED.value,
                ScanStatus.INITIALIZING.value,
                ScanStatus.RUNNING.value,
                ScanStatus.PENDING.value,
            ]),
        )
    )
    active_scans = scans_res.scalars().all()
    halted_count = 0
    now_utc = datetime.now(timezone.utc)

    for scan in active_scans:
        process_safety.terminate_process_tree(scan.id)
        scan.status = ScanStatus.CANCELLED.value
        scan.cancelled_at = now_utc
        scan.completed_at = now_utc
        scan.cancellation_reason = f"Target emergency stop triggered by operator '{current_user.username}'"
        halted_count += 1

    await db.commit()

    return {
        "status": "EMERGENCY_STOP_ACTIVATED",
        "asset_id": asset.id,
        "emergency_stop_active": True,
        "halted_scans_count": halted_count,
        "message": f"Target emergency stop activated for asset '{asset.name}'. {halted_count} scanner processes terminated in < 3s.",
    }

