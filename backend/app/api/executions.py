"""Defensive engine API (Milestone 3): artifacts, advisory snapshots, approved health
endpoints, executions (launch / status / attempts / output) and worker readiness.

Uploads use a raw request body (no multipart dependency):
  POST /api/v1/assets/{asset_id}/artifacts?kind=sbom&filename=bom.json   body = file bytes
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_active_user, load_scope, require_owner
from backend.app.core.inventory_reconciliation import execution_block_reasons
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.engines.advisories import AdvisoryFormatError, AdvisoryIndex, parse_snapshot
from backend.app.engines.runner import storage_root
from backend.app.models.asset import Asset
from backend.app.models.base import AdminAuditLog
from backend.app.models.defensive import (
    EXEC_CANCELLED,
    EXEC_QUEUED,
    TERMINAL_STATES,
    AdvisorySnapshot,
    Artifact,
    ExecutionAttempt,
    ExecutionRecord,
    WorkerHeartbeat,
)
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan, ScanBatch
from backend.app.models.user import User

router = APIRouter(tags=["Defensive engines"])

WORKER_STALE_SECONDS = 30
ENGINES = {"sbom", "tls_health", "public_web"}


def _audit(db, user: User, action: str, details: str, request: Request) -> None:
    db.add(AdminAuditLog(user_id=str(user.id), username=user.username, action=action, details=details[:1024],
                         ip_address=request.client.host if request.client else "unknown"))


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


async def _worker_status(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    rows = (await db.execute(select(WorkerHeartbeat))).scalars().all()
    fresh = []
    for w in rows:
        seen = w.last_seen_at if w.last_seen_at.tzinfo else w.last_seen_at.replace(tzinfo=timezone.utc)
        if now - seen <= timedelta(seconds=WORKER_STALE_SECONDS):
            fresh.append(w)
    return {"ready": bool(fresh), "fresh_workers": len(fresh), "known_workers": len(rows),
            "reason": None if fresh else ("no worker heartbeat in the last "
                                          f"{WORKER_STALE_SECONDS}s; jobs stay queued until a worker starts")}


# --------------------------------------------------------------------------- artifacts

@router.post("/assets/{asset_id}/artifacts", status_code=status.HTTP_201_CREATED)
async def upload_artifact(
    asset_id: uuid.UUID,
    request: Request,
    kind: Literal["sbom"] = Query("sbom"),
    filename: str = Query(..., min_length=1, max_length=200),
    source_note: Optional[str] = Query(None, max_length=500),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    (await load_scope(current_user, db)).require(asset_id, "SCAN")
    if await db.get(Asset, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=422, detail="Empty upload")
    if len(body) > settings.MAX_ARTIFACT_BYTES:
        raise HTTPException(status_code=413, detail=f"Artifact exceeds {settings.MAX_ARTIFACT_BYTES} bytes")
    digest = hashlib.sha256(body).hexdigest()
    d = storage_root() / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{digest}.bin"
    # Content-addressed store: reuse an existing file only if it still hashes to its name.
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(body)
        tmp.replace(path)
    safe_name = "".join(ch for ch in filename if ch.isalnum() or ch in "._-")[:200] or "artifact"
    art = Artifact(asset_id=asset_id, kind=kind, filename=safe_name,
                   media_type=request.headers.get("content-type", "application/octet-stream")[:128],
                   sha256=digest, size_bytes=len(body), storage_path=str(path), source_note=source_note,
                   uploaded_by=str(current_user.id))
    db.add(art)
    _audit(db, current_user, "ARTIFACT_UPLOAD", f"artifact_id={art.id} asset_id={asset_id} sha256={digest}", request)
    await db.commit()
    return _artifact_out(art)


def _artifact_out(a: Artifact) -> dict:
    return {"id": str(a.id), "asset_id": str(a.asset_id), "kind": a.kind, "filename": a.filename,
            "sha256": a.sha256, "size_bytes": a.size_bytes, "uploaded_by": a.uploaded_by,
            "uploaded_at": _iso(a.uploaded_at), "source_note": a.source_note}


@router.get("/assets/{asset_id}/artifacts")
async def list_artifacts(asset_id: uuid.UUID, current_user: User = Depends(get_current_active_user),
                         db: AsyncSession = Depends(get_db)) -> Any:
    (await load_scope(current_user, db)).require(asset_id, "READ")
    rows = (await db.execute(select(Artifact).where(Artifact.asset_id == asset_id)
                             .order_by(Artifact.uploaded_at.desc()))).scalars().all()
    return [_artifact_out(a) for a in rows]


# --------------------------------------------------------------------------- health endpoint approval

class HealthCheckApproval(BaseModel):
    url: str = Field(..., max_length=1024)
    allow_private: bool = False
    note: Optional[str] = Field(None, max_length=500)
    ca_pem: Optional[str] = Field(None, max_length=20000, description="Private CA bundle for internal services")


@router.put("/assets/{asset_id}/health-check")
async def approve_health_check(asset_id: uuid.UUID, payload: HealthCheckApproval, request: Request,
                               current_user: User = Depends(require_owner), db: AsyncSession = Depends(get_db)) -> Any:
    """Owner approves the single read-only health endpoint the tls_health engine may measure."""
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    parts = urlsplit(payload.url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise HTTPException(status_code=422, detail="Endpoint must be https://host[:port]/path without credentials")
    if parts.query and any(k in parts.query.lower() for k in ("token", "key", "secret", "password")):
        raise HTTPException(status_code=422, detail="Endpoint query must not carry credentials")
    rev = uuid.uuid4().hex[:12]
    ca_file = None
    if payload.ca_pem:
        if "BEGIN CERTIFICATE" not in payload.ca_pem or "PRIVATE KEY" in payload.ca_pem:
            raise HTTPException(status_code=422, detail="ca_pem must contain certificates only")
        d = storage_root() / "ca"
        d.mkdir(parents=True, exist_ok=True)
        ca_path = d / f"{hashlib.sha256(payload.ca_pem.encode()).hexdigest()}.pem"
        ca_path.write_text(payload.ca_pem, encoding="ascii")
        ca_file = str(ca_path)
    policy = dict(asset.assessment_policy or {})
    policy["health_check"] = {"url": payload.url, "allow_private": payload.allow_private, "note": payload.note,
                              "approved_by": str(current_user.id),
                              "approved_at": datetime.now(timezone.utc).isoformat(), "revision": rev,
                              "ca_file": ca_file}
    asset.assessment_policy = policy
    _audit(db, current_user, "HEALTH_ENDPOINT_APPROVED",
           f"asset_id={asset_id} host={parts.hostname} allow_private={payload.allow_private} revision={rev}", request)
    await db.commit()
    return policy["health_check"]


# --------------------------------------------------------------------------- advisory snapshots

@router.post("/threat-intel/advisory-snapshots", status_code=status.HTTP_201_CREATED)
async def import_advisory_snapshot(
    request: Request,
    source: str = Query(..., min_length=2, max_length=128),
    version_label: str = Query(..., min_length=1, max_length=128),
    activate: bool = Query(True),
    current_user: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
) -> Any:
    body = await request.body()
    try:
        records = parse_snapshot(body)
    except AdvisoryFormatError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    idx = AdvisoryIndex.build(records)
    existing = (await db.execute(select(AdvisorySnapshot).where(AdvisorySnapshot.digest == idx.digest))).scalars().first()
    if existing is None:
        d = storage_root() / "advisories"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{idx.digest}.json"
        path.write_bytes(json.dumps(records, sort_keys=True).encode("utf-8"))
        existing = AdvisorySnapshot(source=source, version_label=version_label, digest=idx.digest,
                                    record_count=idx.record_count, ecosystems=idx.ecosystems,
                                    data_modified_max=idx.modified_max, storage_path=str(path),
                                    imported_by=str(current_user.id))
        db.add(existing)
    if activate:
        for s in (await db.execute(select(AdvisorySnapshot).where(AdvisorySnapshot.is_active == True))).scalars():  # noqa
            s.is_active = False
        existing.is_active = True
    _audit(db, current_user, "ADVISORY_SNAPSHOT_IMPORT",
           f"digest={idx.digest} records={idx.record_count} source={source} version={version_label} active={activate}",
           request)
    await db.commit()
    return _snapshot_out(existing)


def _snapshot_out(s: AdvisorySnapshot) -> dict:
    return {"id": str(s.id), "source": s.source, "version_label": s.version_label, "digest": s.digest,
            "record_count": s.record_count, "ecosystems": s.ecosystems, "data_modified_max": s.data_modified_max,
            "is_active": s.is_active, "imported_by": s.imported_by, "imported_at": _iso(s.imported_at),
            "age_hours": round((datetime.now(timezone.utc) - (s.imported_at if s.imported_at.tzinfo else
                               s.imported_at.replace(tzinfo=timezone.utc))).total_seconds() / 3600, 1)}


@router.get("/threat-intel/advisory-snapshots")
async def list_advisory_snapshots(current_user: User = Depends(get_current_active_user),
                                  db: AsyncSession = Depends(get_db)) -> Any:
    rows = (await db.execute(select(AdvisorySnapshot).order_by(AdvisorySnapshot.imported_at.desc()))).scalars().all()
    return [_snapshot_out(s) for s in rows]


# --------------------------------------------------------------------------- executions

class ExecutionCreate(BaseModel):
    asset_id: uuid.UUID
    engine: Literal["sbom", "tls_health", "public_web"]
    artifact_id: Optional[uuid.UUID] = None
    timeout_seconds: int = Field(120, ge=5, le=1800)


@router.post("/executions", status_code=status.HTTP_202_ACCEPTED)
async def launch_execution(
    payload: ExecutionCreate,
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, max_length=128),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Queue one defensive engine execution. Returns the committed IDs; the worker runs it."""
    scope = await load_scope(current_user, db)
    scope.require(payload.asset_id, "SCAN")  # authorization BEFORE idempotency lookup
    asset = await db.get(Asset, payload.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    inventory_blocks = await execution_block_reasons(db, [asset])
    if inventory_blocks:
        raise HTTPException(status_code=409, detail=f"{inventory_blocks[str(asset.id)]}: reconcile the target before customer execution.")


    req_hash = hashlib.sha256(json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()
    scoped_key = f"{current_user.id}:{idempotency_key}" if idempotency_key else None
    if scoped_key:
        prior = (await db.execute(select(ExecutionRecord).where(ExecutionRecord.idempotency_key == scoped_key))
                 ).scalars().first()
        if prior is not None:
            if prior.request_hash != req_hash:
                raise HTTPException(status_code=409, detail="Idempotency-Key reused with a different request body")
            body = await _launch_response(db, prior, replayed=True)
            return JSONResponse(status_code=200, content=body)

    from backend.app.models.operations import CapacitySettings
    capacity = await db.get(CapacitySettings, 1)
    if ((capacity and capacity.emergency_stop_active)
            or (Path(settings.STORAGE_DIR) / "production-emergency-stop").exists()):
        raise HTTPException(status_code=409, detail="GLOBAL_STOP_ACTIVE: global emergency stop is active.")

    descriptor: dict = {}
    planned_item = None
    input_sha = None
    if payload.engine == "sbom":
        if payload.artifact_id is None:
            raise HTTPException(status_code=422, detail="engine 'sbom' requires artifact_id")
        art = await db.get(Artifact, payload.artifact_id)
        if art is None or art.asset_id != payload.asset_id:
            raise HTTPException(status_code=404, detail="Artifact not found for this asset")
        input_sha = art.sha256
        descriptor = {"artifact_id": str(art.id), "filename": art.filename, "kind": art.kind}
    elif payload.engine == "public_web":
        # The single-execution API must honor the same host quotas and duplicate suppression
        # as batch runs and schedules; it must not offer a bypass for repeated network probes.
        from backend.app.core.planner import Selection, build_plan
        plan = await build_plan(db, selection=Selection(kind="assets", asset_ids=[str(asset.id)]),
                                engines=["public_web"], profile="slow", trigger="manual", scope=scope)
        planned_item = plan.items[0]
        if planned_item.decision == "skip":
            raise HTTPException(status_code=409, detail=f"{planned_item.reason_code}: {planned_item.reason}")
        descriptor = {"public_web_revision": planned_item.public_web_revision, "url": planned_item.public_web_url}
    else:
        hc = (asset.assessment_policy or {}).get("health_check") or {}
        descriptor = {"health_check_revision": hc.get("revision"), "url": hc.get("url")}

    now = datetime.now(timezone.utc)
    batch = ScanBatch(name=f"{payload.engine} · {asset.name}", status="QUEUED", total_scans=1, target_count=1,
                      engines=[payload.engine], profiles=["DEFENSIVE"],
                      metadata_json={"trigger": "manual", "actor_id": str(current_user.id),
                                     "correlation_id": getattr(request.state, "request_id", None)})
    db.add(batch)
    await db.flush()
    scan = Scan(asset_id=asset.id, batch_id=batch.id, engine=payload.engine, profile="BASELINE", status="QUEUED",
                target_locator=f"engine://{payload.engine}/{asset.id}",
                timeout_seconds=min(payload.timeout_seconds, 12) if payload.engine == "public_web" else payload.timeout_seconds,
                max_retries=0 if payload.engine == "public_web" else 3,
                available_at=datetime.fromisoformat(planned_item.available_at) if planned_item and planned_item.available_at else None)
    db.add(scan)
    await db.flush()
    rec = ExecutionRecord(scan_id=scan.id, batch_id=batch.id, asset_id=asset.id, engine_id=payload.engine,
                          execution_mode="native", artifact_id=payload.artifact_id, input_sha256=input_sha,
                          input_descriptor=descriptor, scope_revision=descriptor.get("public_web_revision") or descriptor.get("health_check_revision"),
                          trigger="manual", actor_id=str(current_user.id), idempotency_key=scoped_key,
                          request_hash=req_hash, status=EXEC_QUEUED, queued_at=now,
                          plan_note=(f"{planned_item.reason_code}: {planned_item.reason}"[:512]
                                     if planned_item and planned_item.reason_code else None),
                          correlation_id=getattr(request.state, "request_id", None),
                          target_host=(urlsplit(descriptor["url"]).hostname or "").lower() or None
                          if descriptor.get("url") else None)
    db.add(rec)
    _audit(db, current_user, "EXECUTION_LAUNCH",
           f"execution_id={rec.id} batch_id={batch.id} asset_id={asset.id} engine={payload.engine}", request)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        if scoped_key:  # concurrent double-submit with the same key: return the winner
            prior = (await db.execute(select(ExecutionRecord).where(ExecutionRecord.idempotency_key == scoped_key))
                     ).scalars().first()
            if prior is not None and prior.request_hash == req_hash:
                return JSONResponse(status_code=200, content=await _launch_response(db, prior, replayed=True))
        raise
    return await _launch_response(db, rec, replayed=False)


async def _launch_response(db: AsyncSession, rec: ExecutionRecord, replayed: bool) -> dict:
    return {
        "execution_id": str(rec.id),
        "batch_id": str(rec.batch_id) if rec.batch_id else None,
        "scan_id": str(rec.scan_id),
        "status": rec.status,
        "queued_at": _iso(rec.queued_at),
        "planned_executions": 1,
        "tracker": f"/active-assessments/?execution={rec.id}",
        "replayed": replayed,
        "worker": await _worker_status(db),
    }


async def _scoped_record(db: AsyncSession, user: User, execution_id: uuid.UUID, action: str = "READ") -> ExecutionRecord:
    rec = await db.get(ExecutionRecord, execution_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    (await load_scope(user, db)).require(rec.asset_id, action)
    return rec


def _record_out(rec: ExecutionRecord) -> dict:
    return {
        "execution_id": str(rec.id), "batch_id": str(rec.batch_id) if rec.batch_id else None,
        "scan_id": str(rec.scan_id), "asset_id": str(rec.asset_id), "engine_id": rec.engine_id,
        "driver": rec.driver, "driver_version": rec.driver_version, "execution_mode": rec.execution_mode,
        "input": {"artifact_id": str(rec.artifact_id) if rec.artifact_id else None, "sha256": rec.input_sha256,
                  **(rec.input_descriptor or {})},
        "rules": {"source": rec.rule_source, "version": rec.rule_version, "digest": rec.rule_digest},
        "scope_revision": rec.scope_revision, "trigger": rec.trigger, "actor_id": rec.actor_id,
        "status": rec.status, "status_reason": rec.status_reason, "error_class": rec.error_class,
        "finding_count": rec.finding_count, "summary": rec.summary,
        "output": {"sha256": rec.output_sha256, "available": bool(rec.output_path)},
        "worker_id": rec.worker_id,
        "timestamps_utc": {"queued_at": _iso(rec.queued_at), "started_at": _iso(rec.started_at),
                           "observed_at": _iso(rec.observed_at), "finished_at": _iso(rec.finished_at)},
        "duration_ms": rec.duration_ms,
        "display_timezone": settings.DEFAULT_TIMEZONE,
        "correlation_id": rec.correlation_id, "lane": rec.lane, "plan_note": rec.plan_note,
        "schedule_slot_id": str(rec.schedule_slot_id) if rec.schedule_slot_id else None,
    }


@router.get("/executions")
async def list_executions(
    asset_id: Optional[uuid.UUID] = None,
    engine: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    from backend.app.models.lifecycle import HiddenRecord
    stmt = select(ExecutionRecord).where(ExecutionRecord.id.not_in(
        select(HiddenRecord.object_id).where(HiddenRecord.object_type == "execution")))
    scope = await load_scope(current_user, db)
    if scope.asset_ids is not None:
        stmt = stmt.where(ExecutionRecord.asset_id.in_(scope.asset_ids))
    if asset_id:
        stmt = stmt.where(ExecutionRecord.asset_id == asset_id)
    if engine:
        stmt = stmt.where(ExecutionRecord.engine_id == engine)
    if status_filter:
        stmt = stmt.where(ExecutionRecord.status == status_filter)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.order_by(ExecutionRecord.queued_at.desc()).offset((page - 1) * size).limit(size))
            ).scalars().all()
    return {"items": [_record_out(r) for r in rows], "total": total, "page": page, "size": size,
            "pages": max(1, (total + size - 1) // size)}


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: uuid.UUID, current_user: User = Depends(get_current_active_user),
                        db: AsyncSession = Depends(get_db)) -> Any:
    rec = await _scoped_record(db, current_user, execution_id)
    attempts = (await db.execute(select(ExecutionAttempt).where(ExecutionAttempt.execution_id == rec.id)
                                 .order_by(ExecutionAttempt.attempt_no))).scalars().all()
    finding_ids = []
    if rec.status == "succeeded":
        rows = (await db.execute(select(NormalizedFinding.id, NormalizedFinding.evidence).where(
            NormalizedFinding.asset_id == rec.asset_id, NormalizedFinding.scanner_engine == rec.engine_id))).all()
        finding_ids = [str(fid) for fid, ev in rows if (ev or {}).get("execution_id") == str(rec.id)]
    out = _record_out(rec)
    out["attempts"] = [{
        "attempt_id": str(a.id), "attempt_no": a.attempt_no, "fencing_token": a.fencing_token,
        "worker_id": a.worker_id, "phase": a.phase, "status": a.status, "started_at": _iso(a.started_at),
        "heartbeat_at": _iso(a.heartbeat_at), "finished_at": _iso(a.finished_at), "duration_ms": a.duration_ms,
        "exit_code": a.exit_code, "error_class": a.error_class, "error_detail": a.error_detail,
    } for a in attempts]
    out["finding_ids"] = finding_ids
    if rec.status not in TERMINAL_STATES:
        out["worker"] = await _worker_status(db)
    return out


@router.get("/executions/{execution_id}/output")
async def download_execution_output(execution_id: uuid.UUID, current_user: User = Depends(get_current_active_user),
                                    db: AsyncSession = Depends(get_db)) -> Any:
    rec = await _scoped_record(db, current_user, execution_id)
    if not rec.output_path:
        raise HTTPException(status_code=404, detail=f"No stored output (status={rec.status}, reason={rec.status_reason})")
    p = Path(rec.output_path).resolve()
    if not p.is_relative_to(storage_root()) or not p.is_file():
        raise HTTPException(status_code=404, detail="Output file missing from storage")
    if hashlib.sha256(p.read_bytes()).hexdigest() != rec.output_sha256:
        raise HTTPException(status_code=409, detail="Stored output does not match its recorded hash")
    return FileResponse(p, media_type="application/json", filename=f"execution-{rec.id}.json",
                        headers={"Cache-Control": "private, no-store", "X-Content-SHA256": rec.output_sha256})


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(execution_id: uuid.UUID, request: Request,
                           current_user: User = Depends(get_current_active_user),
                           db: AsyncSession = Depends(get_db)) -> Any:
    rec = await _scoped_record(db, current_user, execution_id, "SCAN")
    if rec.status in TERMINAL_STATES:
        raise HTTPException(status_code=409, detail=f"Execution already {rec.status}")
    from backend.app.core.queue import IDBDurableQueue
    await IDBDurableQueue.cancel_job(db, rec.scan_id, reason=f"Cancelled by user {current_user.id}")
    rec = await db.get(ExecutionRecord, execution_id)
    rec.status = EXEC_CANCELLED
    rec.status_reason = "Cancelled by user before completion."
    rec.error_class = "CANCELLED"
    rec.finished_at = datetime.now(timezone.utc)
    _audit(db, current_user, "EXECUTION_CANCEL", f"execution_id={rec.id}", request)
    await db.commit()
    return _record_out(rec)


@router.get("/engines/workers")
async def list_workers(current_user: User = Depends(get_current_active_user),
                       db: AsyncSession = Depends(get_db)) -> Any:
    rows = (await db.execute(select(WorkerHeartbeat).order_by(WorkerHeartbeat.last_seen_at.desc()))).scalars().all()
    now = datetime.now(timezone.utc)
    items = []
    for w in rows:
        seen = w.last_seen_at if w.last_seen_at.tzinfo else w.last_seen_at.replace(tzinfo=timezone.utc)
        age = (now - seen).total_seconds()
        items.append({"worker_id": w.worker_id, "hostname": w.hostname, "engines": w.engines,
                      "last_seen_at": _iso(seen), "age_seconds": round(age, 1),
                      "state": "online" if age <= WORKER_STALE_SECONDS else "stale",
                      "active_executions": w.active_executions, "throttle_reason": w.throttle_reason})
    return {"as_of": now.isoformat(), "workers": items, **(await _worker_status(db))}
