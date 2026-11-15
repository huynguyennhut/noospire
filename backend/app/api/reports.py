"""Reports API endpoints for Noosforge Sentinel.

Handles report generation, listing, viewing, downloading (PDF, HTML, JSON),
and deletion.
"""

from __future__ import annotations

import os
import uuid
from typing import Any, List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.api.deps import require_admin, require_operator, require_viewer, load_scope
from backend.app.core.database import get_db
from backend.app.models.user import User
from backend.app.reporting.generator import Report, ReportGenerator

router = APIRouter(prefix="/reports", tags=["Reporting"])


# ============================================================================
# Schemas
# ============================================================================

class GenerateReportRequest(BaseModel):
    title: Optional[str] = Field(default=None, description="Custom report title")
    report_type: str = Field(default="technical", description="'technical' or 'executive'")
    asset_id: Optional[uuid.UUID] = Field(default=None, description="Optional target asset filter")
    scan_id: Optional[uuid.UUID] = Field(default=None, description="Optional scan job filter")
    batch_id: Optional[uuid.UUID] = Field(default=None, description="Optional assessment batch filter")
    formats: List[str] = Field(default_factory=lambda: ["pdf", "html", "json"], description="Requested formats")


class ReportResponse(BaseModel):
    id: uuid.UUID
    title: str
    report_type: str
    asset_id: Optional[uuid.UUID] = None
    scan_id: Optional[uuid.UUID] = None
    target_scope: str
    formats: List[str]
    status: str
    summary: dict
    file_paths: dict
    created_by: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ============================================================================
# Endpoints
# ============================================================================

@router.get("", response_model=List[ReportResponse])
async def list_reports(
    report_type: Optional[str] = None,
    asset_id: Optional[uuid.UUID] = None,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lists all generated security assessment and executive reports (F04, F06)."""
    stmt = select(Report).order_by(Report.created_at.desc())
    scope = await load_scope(current_user, db)
    if scope.asset_ids is not None:
        # Estate-wide reports (asset_id NULL) are visible to the owner only.
        stmt = stmt.where(Report.asset_id.in_(scope.asset_ids))
    if report_type:
        stmt = stmt.where(Report.report_type == report_type)
    if asset_id:
        stmt = stmt.where(Report.asset_id == asset_id)

    result = await db.execute(stmt)
    reports = result.scalars().all()
    return [r.to_dict() for r in reports]


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
@router.post("/generate", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def generate_report(
    req: GenerateReportRequest,
    current_user: User = Depends(require_operator),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dispatches and generates a report derived strictly from verified database findings."""
    scope = await load_scope(current_user, db)
    if req.asset_id is None and not scope.estate_wide:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Estate-wide reports are restricted to the owner.")
    if req.asset_id is not None:
        scope.require(req.asset_id, "REPORT")
    generator = ReportGenerator()
    report = await generator.generate(
        db=db,
        title=req.title,
        report_type=req.report_type,
        asset_id=req.asset_id,
        scan_id=req.scan_id,
        batch_id=req.batch_id,
        formats=req.formats,
    )
    return report.to_dict()


@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(
    report_id: uuid.UUID,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieves report metadata and summary statistics."""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    (await load_scope(current_user, db)).require(report.asset_id, "READ")
    return report.to_dict()


@router.get("/{report_id}/download")
async def download_report(
    report_id: uuid.UUID,
    format: str = Query("pdf", description="Requested format: pdf, html, or json"),
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Downloads a generated report in the requested format (PDF, HTML, JSON) with strict RBAC (F06)."""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    (await load_scope(current_user, db)).require(report.asset_id, "READ")

    fmt = format.lower().strip()
    if fmt not in ("pdf", "html", "json"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requested report format is not available")

    file_paths = report.file_paths or {}
    path_str = file_paths.get(fmt)

    # If file path not registered, check default storage
    if not path_str or not os.path.exists(path_str):
        candidate = Path(settings.STORAGE_DIR) / "reports" / f"{report_id}.{fmt}"
        if candidate.exists():
            path_str = str(candidate)

    if not path_str or not os.path.exists(path_str):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report file in '{fmt}' format is not available.",
        )

    # Path traversal protection: ensure file is within storage directory
    resolved_path = Path(path_str).resolve()
    base_storage = Path(settings.STORAGE_DIR).resolve()
    if not resolved_path.is_relative_to(base_storage):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access to path forbidden")

    media_types = {
        "pdf": "application/pdf",
        "html": "text/html",
        "json": "application/json",
    }
    media_type = media_types.get(fmt, "application/octet-stream")

    safe_title = "".join(c for c in report.title if c.isalnum() or c in ("-", "_")).rstrip()
    filename = f"{safe_title or 'Sentinel_Report'}.{fmt}"

    import hashlib
    digest = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
    return FileResponse(
        path=str(resolved_path),
        media_type=media_type,
        filename=filename,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": digest,
            "X-Content-Type-Options": "nosniff",
            "X-Template-Version": "legacy-report",
        },
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: uuid.UUID,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deletes a report record and associated artifacts from storage (Requires ADMIN role)."""
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalars().first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    # Clean up files on disk
    if report.file_paths:
        for p in report.file_paths.values():
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    await db.delete(report)
    await db.commit()
