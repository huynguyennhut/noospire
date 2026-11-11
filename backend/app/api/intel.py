"""FastAPI Router for Threat Intelligence and Vulnerability Synchronization.

Endpoints:
- GET /api/v1/threat-intel/summary
- POST /api/v1/threat-intel/sync
- GET /api/v1/threat-intel/cve/{cve_id}
- GET /api/v1/threat-intel/cves
- GET /api/v1/threat-intel/kev
- POST /api/v1/threat-intel/epss/batch
Conforms to Noosforge Sentinel R3 specifications.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.intel.sync_manager import ThreatIntelSyncManager
from backend.app.models.intelligence import VulnerabilityAlias, VulnerabilityIntelligence
from backend.app.schemas.intelligence import (
    EPSSBatchQueryRequest,
    EPSSBatchQueryResponse,
    EPSSScoreItem,
    ThreatIntelSummaryResponse,
    ThreatIntelSyncRequest,
    ThreatIntelSyncResponse,
    VulnerabilityIntelligenceResponse,
)

from backend.app.api.deps import get_current_active_user, require_operator
from backend.app.core.database import get_db
from backend.app.models.user import User

router = APIRouter(prefix="/threat-intel", tags=["Threat Intelligence"], dependencies=[Depends(get_current_active_user)])
sync_manager = ThreatIntelSyncManager()


@router.get("/summary", response_model=ThreatIntelSummaryResponse)
async def get_threat_intel_summary(session: AsyncSession = Depends(get_db)) -> ThreatIntelSummaryResponse:
    """Retrieve executive telemetry and aggregated metrics across all intelligence feeds."""
    return await sync_manager.get_summary(session)


@router.post("/sync", response_model=ThreatIntelSyncResponse)
async def trigger_threat_intel_sync(
    request: ThreatIntelSyncRequest,
    current_user: User = Depends(require_operator),
    session: AsyncSession = Depends(get_db),
) -> ThreatIntelSyncResponse:
    """Manually dispatch scheduled or incremental threat intelligence synchronization."""
    job_id = f"sync-{uuid.uuid4().hex[:8]}"

    if request.force_offline_fixtures:
        from backend.app.core.config import settings
        if settings.is_production:
            raise HTTPException(status_code=403, detail="Offline (synthetic) threat-intel fixtures are disabled in production.")
        results = await sync_manager.seed_from_offline_fixtures(session)
    else:
        results = await sync_manager.sync_all(
            session=session,
            sources=request.sources,
            force_offline=False,
        )

    all_success = all(r.success for r in results)
    status_str = "completed" if all_success else ("partial" if any(r.success for r in results) else "failed")

    return ThreatIntelSyncResponse(
        job_id=job_id,
        status=status_str,
        timestamp=datetime.now(timezone.utc),
        results=results,
    )


@router.get("/cve/{cve_id}", response_model=VulnerabilityIntelligenceResponse)
async def get_cve_details(
    cve_id: str,
    session: AsyncSession = Depends(get_db),
) -> VulnerabilityIntelligenceResponse:
    """Retrieve enriched threat intelligence and correlation aliases for a specific CVE or GHSA ID."""
    clean_id = cve_id.strip()

    # If identifier is not CVE (e.g. GHSA-...), resolve via alias graph
    resolved_cve = sync_manager.alias_graph.resolve_to_cve(clean_id) or clean_id

    stmt = select(VulnerabilityIntelligence).where(VulnerabilityIntelligence.cve_id == resolved_cve)
    result = await session.execute(stmt)
    vuln = result.scalar_one_or_none()

    if not vuln:
        # Check alias table directly in DB if not in in-memory graph
        alias_stmt = select(VulnerabilityAlias.cve_id).where(VulnerabilityAlias.alias_id == clean_id)
        alias_cve = (await session.execute(alias_stmt)).scalar_one_or_none()
        if alias_cve:
            stmt = select(VulnerabilityIntelligence).where(VulnerabilityIntelligence.cve_id == alias_cve)
            vuln = (await session.execute(stmt)).scalar_one_or_none()

    if not vuln:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vulnerability '{cve_id}' (resolved: '{resolved_cve}') not found in threat intelligence store.",
        )

    return VulnerabilityIntelligenceResponse.model_validate(vuln.to_dict())


@router.get("/cves", response_model=List[VulnerabilityIntelligenceResponse])
async def list_cves(
    search: Optional[str] = None,
    is_kev: Optional[bool] = None,
    min_epss: Optional[float] = Query(None, ge=0.0, le=1.0),
    min_cvss: Optional[float] = Query(None, ge=0.0, le=10.0),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> List[VulnerabilityIntelligenceResponse]:
    """Search and paginate enriched vulnerabilities with multi-criteria filtering."""
    stmt = select(VulnerabilityIntelligence)

    if search:
        search_filter = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                VulnerabilityIntelligence.cve_id.ilike(search_filter),
                VulnerabilityIntelligence.title.ilike(search_filter),
                VulnerabilityIntelligence.summary.ilike(search_filter),
            )
        )

    if is_kev is not None:
        stmt = stmt.where(VulnerabilityIntelligence.is_cisa_kev == is_kev)

    if min_epss is not None:
        stmt = stmt.where(VulnerabilityIntelligence.epss_score >= min_epss)

    if min_cvss is not None:
        stmt = stmt.where(VulnerabilityIntelligence.cvss_v3_score >= min_cvss)

    stmt = stmt.order_by(VulnerabilityIntelligence.cvss_v3_score.desc().nullslast()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    records = result.scalars().all()

    return [VulnerabilityIntelligenceResponse.model_validate(r.to_dict()) for r in records]


@router.get("/kev", response_model=List[VulnerabilityIntelligenceResponse])
async def list_cisa_kev_catalog(
    ransomware_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
) -> List[VulnerabilityIntelligenceResponse]:
    """Retrieve actively exploited vulnerabilities from the CISA KEV catalog."""
    stmt = select(VulnerabilityIntelligence).where(VulnerabilityIntelligence.is_cisa_kev.is_(True))

    if ransomware_only:
        stmt = stmt.where(VulnerabilityIntelligence.cisa_kev_ransomware == "Known")

    stmt = stmt.order_by(VulnerabilityIntelligence.cisa_kev_date_added.desc().nullslast()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    records = result.scalars().all()

    return [VulnerabilityIntelligenceResponse.model_validate(r.to_dict()) for r in records]


@router.post("/epss/batch", response_model=EPSSBatchQueryResponse)
async def query_epss_batch(
    request: EPSSBatchQueryRequest,
    session: AsyncSession = Depends(get_db),
) -> EPSSBatchQueryResponse:
    """Retrieve EPSS exploitation probabilities and percentile ranks for multiple CVEs."""
    scores_dict = await sync_manager.epss.get_scores_batch(request.cve_ids)

    score_items: dict[str, EPSSScoreItem] = {}
    for cve, data in scores_dict.items():
        score_items[cve] = EPSSScoreItem(
            cve=cve,
            epss=data.get("epss_score", 0.0001),
            percentile=data.get("epss_percentile", 0.0),
            date=data.get("source_provenance", {}).get("date"),
        )

    return EPSSBatchQueryResponse(count=len(score_items), scores=score_items)
