import csv
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_active_user, require_admin
from backend.app.core.database import get_db
from backend.app.core.dispatcher import log_buffer
from backend.app.models.scan import ScanLog
from backend.app.models.user import User

router = APIRouter(prefix="/logs", tags=["Operational Logs Management"], dependencies=[Depends(get_current_active_user)])


class LogItemResponse(BaseModel):
    id: uuid.UUID
    scan_id: uuid.UUID
    timestamp: datetime
    level: str
    message: str
    source: str


class PaginatedLogsResponse(BaseModel):
    items: List[LogItemResponse]
    total: int
    page: int
    size: int
    pages: int


class PurgeLogsRequest(BaseModel):
    days: Optional[int] = Field(None, description="Purge logs older than N days")
    scan_id: Optional[uuid.UUID] = Field(None, description="Purge logs for a specific scan ID")
    purge_all: bool = Field(False, description="Purge all operational scan logs")


@router.get("", response_model=PaginatedLogsResponse)
async def list_logs(
    scan_id: Optional[uuid.UUID] = None,
    days: Optional[int] = Query(None, ge=1, le=365, description="Filter logs within past N days"),
    from_date: Optional[datetime] = Query(None, description="Start datetime (UTC/ISO)"),
    to_date: Optional[datetime] = Query(None, description="End datetime (UTC/ISO)"),
    level: Optional[str] = Query(None, description="Filter by log level (INFO, WARNING, ERROR, DEBUG)"),
    source: Optional[str] = Query(None, description="Filter by source (nuclei, zap, crawler, empire_engine, system)"),
    search: Optional[str] = Query(None, description="Text search in message"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Query operational scan logs with date/day range, severity level, source, and text filters."""
    stmt = select(ScanLog)

    if scan_id:
        stmt = stmt.where(ScanLog.scan_id == scan_id)

    now = datetime.now(timezone.utc)
    if days is not None:
        threshold = now - timedelta(days=days)
        stmt = stmt.where(ScanLog.timestamp >= threshold)
    if from_date:
        stmt = stmt.where(ScanLog.timestamp >= from_date)
    if to_date:
        stmt = stmt.where(ScanLog.timestamp <= to_date)
    if level:
        stmt = stmt.where(func.upper(ScanLog.level) == level.upper())
    if source:
        stmt = stmt.where(ScanLog.source == source)
    if search:
        stmt = stmt.where(ScanLog.message.ilike(f"%{search}%"))

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_res = await db.execute(count_stmt)
    total = total_res.scalar() or 0

    stmt = stmt.order_by(ScanLog.timestamp.desc()).offset((page - 1) * size).limit(size)
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


@router.get("/export")
async def export_logs(
    scan_id: Optional[uuid.UUID] = None,
    days: Optional[int] = Query(None, ge=1, le=365),
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    level: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    format: str = Query("json", pattern="^(json|csv)$"),
    limit: int = Query(5000, ge=1, le=20000),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Export operational logs in JSON or CSV format."""
    stmt = select(ScanLog)

    if scan_id:
        stmt = stmt.where(ScanLog.scan_id == scan_id)

    now = datetime.now(timezone.utc)
    if days is not None:
        threshold = now - timedelta(days=days)
        stmt = stmt.where(ScanLog.timestamp >= threshold)
    if from_date:
        stmt = stmt.where(ScanLog.timestamp >= from_date)
    if to_date:
        stmt = stmt.where(ScanLog.timestamp <= to_date)
    if level:
        stmt = stmt.where(func.upper(ScanLog.level) == level.upper())
    if source:
        stmt = stmt.where(ScanLog.source == source)
    if search:
        stmt = stmt.where(ScanLog.message.ilike(f"%{search}%"))

    stmt = stmt.order_by(ScanLog.timestamp.desc()).limit(limit)
    result = await db.execute(stmt)
    items = result.scalars().all()

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["id", "scan_id", "timestamp", "level", "source", "message"])
        for item in items:
            writer.writerow([
                str(item.id),
                str(item.scan_id),
                item.timestamp.isoformat() if item.timestamp else "",
                item.level,
                item.source,
                item.message,
            ])
        csv_content = output.getvalue()
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=noosforge_logs.csv",
            },
        )
    else:
        log_dicts = [
            {
                "id": str(item.id),
                "scan_id": str(item.scan_id),
                "timestamp": item.timestamp.isoformat() if item.timestamp else None,
                "level": item.level,
                "source": item.source,
                "message": item.message,
            }
            for item in items
        ]
        return Response(
            content=json.dumps(log_dicts, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=noosforge_logs.json",
            },
        )


@router.post("/purge")
async def purge_logs(
    payload: Optional[PurgeLogsRequest] = None,
    days: Optional[int] = Query(None, ge=1, le=365),
    scan_id: Optional[uuid.UUID] = Query(None),
    purge_all: bool = Query(False),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Purge operational scan logs by age (days), specific scan ID, or entirely."""
    req_days = payload.days if payload and payload.days is not None else days
    req_scan_id = payload.scan_id if payload and payload.scan_id is not None else scan_id
    req_purge_all = payload.purge_all if payload and payload.purge_all else purge_all

    stmt = delete(ScanLog)
    now = datetime.now(timezone.utc)

    if req_purge_all:
        # Purge all
        res = await db.execute(stmt)
        await log_buffer.clear_all()
    elif req_days is not None:
        threshold = now - timedelta(days=req_days)
        stmt = stmt.where(ScanLog.timestamp <= threshold)
        if req_scan_id:
            stmt = stmt.where(ScanLog.scan_id == req_scan_id)
            await log_buffer.clear_scan(req_scan_id)
        res = await db.execute(stmt)
    elif req_scan_id is not None:
        stmt = stmt.where(ScanLog.scan_id == req_scan_id)
        res = await db.execute(stmt)
        await log_buffer.clear_scan(req_scan_id)
    else:
        # Default: purge all if no filter specified or bad request
        res = await db.execute(stmt)
        await log_buffer.clear_all()

    await db.commit()
    purged_count = res.rowcount if hasattr(res, "rowcount") else 0

    return {
        "status": "PURGED",
        "purged_count": max(0, purged_count),
        "message": f"Successfully purged {max(0, purged_count)} operational log entries.",
    }
