"""Milestone 5 console API: the data behind the six operator screens.

  Dashboard & Health    GET  /dashboard/summary?days=7
  Scan Center/tracker   GET  /runs?day=YYYY-MM-DD (ICT) · /runs/{id}/tree · /runs/{id}/diff
  Module hub            GET  /modules/hub
  Findings              GET  /findings/{id}/history · POST /findings/{id}/recheck
  History               GET  /history · POST /history/hide/preview · POST /history/hide · POST /history/unhide
  Notifications         GET  /notifications · /notifications/unread-count · POST read / read-all · DELETE
  Reports               POST/GET /report-snapshots · GET /report-snapshots/{id}/download

All reads are filtered by the caller's grants. Dates are stored in UTC; "day" boundaries use
Asia/Ho_Chi_Minh (settings.DEFAULT_TIMEZONE).
"""

from __future__ import annotations

import uuid
import zoneinfo
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_active_user, is_sole_owner, load_scope, require_owner
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.core.planner import Selection, build_plan, materialize
from backend.app.models.asset import Asset
from backend.app.models.base import AdminAuditLog
from backend.app.models.defensive import (
    EXEC_QUEUED,
    EXEC_RUNNING,
    EXEC_SUCCEEDED,
    ExecutionAttempt,
    ExecutionRecord,
    WorkerHeartbeat,
)
from backend.app.models.finding import NormalizedFinding
from backend.app.models.lifecycle import FindingChange, FindingObservation, HiddenRecord, Notification, OUTCOMES
from backend.app.models.operations import MonitorSchedule, RunRequest
from backend.app.models.scan import ScanBatch
from backend.app.models.user import User
from backend.app.schemas.common import EmpireModule, OPEN_FINDING_STATES

router = APIRouter(tags=["Console"])

TZ = zoneinfo.ZoneInfo(settings.DEFAULT_TIMEZONE)
OPEN_STATES = OPEN_FINDING_STATES
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
SERVICE_STALE = timedelta(hours=2)
WORKER_STALE = timedelta(seconds=30)
NONE_ID = uuid.UUID(int=0)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def ict_day_bounds(day: date):
    start = datetime.combine(day, time.min, tzinfo=TZ).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def ict_today(now: Optional[datetime] = None) -> date:
    return (now or datetime.now(timezone.utc)).astimezone(TZ).date()


def _audit(db, user: User, action: str, details: str, request: Request) -> None:
    db.add(AdminAuditLog(user_id=str(user.id), username=user.username, action=action, details=details[:1024],
                         ip_address=request.client.host if request.client else "unknown"))


async def _visible_ids(db, user) -> Optional[List[uuid.UUID]]:
    scope = await load_scope(user, db)
    if scope.asset_ids is None:
        return None
    return scope.ids_with("READ") or [NONE_ID]


def _scoped(stmt, col, ids):
    return stmt if ids is None else stmt.where(col.in_(ids))


async def _hidden_exec_ids(db) -> set:
    return set((await db.execute(select(HiddenRecord.object_id).where(HiddenRecord.object_type == "execution"))
                ).scalars())


# =========================================================================== dashboard & health

async def _service_health(db, ids, now) -> List[dict]:
    assets = (await db.execute(_scoped(select(Asset), Asset.id, ids).order_by(Asset.name))).scalars().all()
    latest: Dict[uuid.UUID, ExecutionRecord] = {}
    rows = (await db.execute(_scoped(select(ExecutionRecord).where(ExecutionRecord.engine_id == "tls_health",
                                                                    ExecutionRecord.finished_at.is_not(None)),
                                     ExecutionRecord.asset_id, ids).order_by(ExecutionRecord.finished_at))).scalars()
    for r in rows:
        latest[r.asset_id] = r  # ascending -> newest wins
    out = []
    for a in assets:
        hc = (a.assessment_policy or {}).get("health_check") or {}
        r = latest.get(a.id)
        item = {"asset_id": str(a.id), "name": a.name, "module": a.empire_module, "status": "unknown",
                "observed_at": None, "execution_id": None, "stale": True, "reason": None}
        if not hc.get("url"):
            item["reason"] = "no approved health endpoint"
        elif r is None:
            item["reason"] = "never measured"
        else:
            item["execution_id"] = str(r.id)
            item["observed_at"] = _iso(r.observed_at or r.finished_at)
            item["stale"] = now - _utc(r.observed_at or r.finished_at) > SERVICE_STALE
            if r.status == EXEC_SUCCEEDED:
                item["status"] = (r.summary or {}).get("service_status", "unknown")
                if item["stale"]:
                    item["reason"] = "last measurement older than 2 h"
            else:
                item["reason"] = f"last check {r.status}: {(r.status_reason or '')[:160]}"
        out.append(item)
    return out


@router.get("/dashboard/summary")
async def dashboard_summary(days: int = Query(7, ge=1, le=90), current_user: User = Depends(get_current_active_user),
                            db: AsyncSession = Depends(get_db)) -> Any:
    now = datetime.now(timezone.utc)
    ids = await _visible_ids(db, current_user)
    today = ict_today(now)
    day_list = [today - timedelta(days=i) for i in range(days - 1, -1, -1)]
    start, _ = ict_day_bounds(day_list[0])

    services = await _service_health(db, ids, now)
    svc_counts = {k: sum(1 for s in services if s["status"] == k) for k in ("up", "degraded", "down", "unknown")}
    svc_counts["stale"] = sum(1 for s in services if s["stale"])

    open_rows = (await db.execute(_scoped(select(NormalizedFinding.severity, func.count())
                                          .where(NormalizedFinding.status.in_(OPEN_STATES)),
                                          NormalizedFinding.asset_id, ids).group_by(NormalizedFinding.severity))).all()
    by_sev = {s: 0 for s in SEVERITIES}
    for sev, n in open_rows:
        by_sev[sev] = by_sev.get(sev, 0) + n

    obs = (await db.execute(_scoped(select(FindingObservation.outcome, FindingObservation.observed_at)
                                    .where(FindingObservation.observed_at >= start,
                                           FindingObservation.outcome.in_(("new", "reopened", "fixed"))),
                                    FindingObservation.asset_id, ids))).all()
    per_day = {d.isoformat(): {"day": d.isoformat(), "new": 0, "reopened": 0, "fixed": 0} for d in day_list}
    for outcome, at in obs:
        key = _utc(at).astimezone(TZ).date().isoformat()
        if key in per_day:
            per_day[key][outcome] += 1

    workers = (await db.execute(select(WorkerHeartbeat))).scalars().all()
    online = [w for w in workers if now - _utc(w.last_seen_at) <= WORKER_STALE]
    newest = (await db.execute(_scoped(select(func.max(FindingObservation.observed_at)), FindingObservation.asset_id,
                                       ids))).scalar()
    newest_exec = (await db.execute(_scoped(select(func.max(ExecutionRecord.finished_at)), ExecutionRecord.asset_id,
                                            ids))).scalar()
    reasons = []
    if not workers or not online:
        reasons.append("no worker online")
    if svc_counts["stale"]:
        reasons.append(f"{svc_counts['stale']} service(s) without a fresh measurement")
    if newest_exec is None:
        reasons.append("no completed execution yet")
    state = "unknown" if newest_exec is None else ("partial" if reasons else "ok")

    return {
        "as_of": now.isoformat(), "display_timezone": settings.DEFAULT_TIMEZONE, "data_state": state,
        "data_state_reasons": reasons,
        "last_real_data_at": _iso(max([x for x in (newest, newest_exec) if x is not None], default=None)),
        "window": {"days": days, "from_utc": start.isoformat(), "to_utc": now.isoformat(),
                   "ict_days": [d.isoformat() for d in day_list]},
        "services": {"counts": svc_counts, "items": services},
        "workers": {"online": len(online), "total": len(workers),
                    "throttled": sum(1 for w in online if w.throttle_reason)},
        "risk": {"open_by_severity": by_sev, "open_total": sum(by_sev.values())},
        "findings_per_day": list(per_day.values()),
        "new_today": per_day[today.isoformat()]["new"],
        "drilldown": {
            "open_by_severity": "/findings/?status_group=open&severity={severity}",
            "new_on_day": "/findings/?outcome=new&day={day}",
            "service": "/engine-runs/?asset={asset_id}",
        },
    }


# =========================================================================== module hub

@router.get("/modules/hub")
async def module_hub(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> Any:
    now = datetime.now(timezone.utc)
    ids = await _visible_ids(db, current_user)
    assets = (await db.execute(_scoped(select(Asset), Asset.id, ids))).scalars().all()
    services = {s["asset_id"]: s for s in await _service_health(db, ids, now)}
    covered = set((await db.execute(_scoped(select(ExecutionRecord.asset_id).where(
        ExecutionRecord.status == EXEC_SUCCEEDED, ExecutionRecord.finished_at >= now - timedelta(hours=24)),
        ExecutionRecord.asset_id, ids))).scalars())
    frows = (await db.execute(_scoped(select(NormalizedFinding.asset_id, NormalizedFinding.severity, func.count())
                                      .where(NormalizedFinding.status.in_(OPEN_STATES)), NormalizedFinding.asset_id, ids)
                              .group_by(NormalizedFinding.asset_id, NormalizedFinding.severity))).all()
    schedules = (await db.execute(select(MonitorSchedule).where(MonitorSchedule.is_active == True))).scalars().all()  # noqa

    by_module: Dict[str, List[Asset]] = {m.value: [] for m in EmpireModule}
    other: List[Asset] = []
    for a in assets:
        (by_module[a.empire_module] if a.empire_module in by_module else other).append(a)

    cards = []
    for m in EmpireModule:
        mas = by_module[m.value]
        aid = {str(a.id) for a in mas}
        sev = {s: 0 for s in SEVERITIES}
        for asset_id, s, n in frows:
            if str(asset_id) in aid:
                sev[s] = sev.get(s, 0) + n
        health = {k: sum(1 for x in aid if services.get(x, {}).get("status") == k)
                  for k in ("up", "degraded", "down", "unknown")}
        nexts = []
        for s in schedules:
            sel = s.selection or {}
            hit = sel.get("kind") == "all" or (sel.get("kind") == "module" and sel.get("module") == m.value) or \
                (sel.get("kind") == "assets" and aid & set(sel.get("asset_ids") or []))
            if hit and s.next_run_at:
                nexts.append(_utc(s.next_run_at))
        cards.append({
            "module": m.value, "assets": len(mas),
            "coverage_24h": {"covered": len(aid & {str(x) for x in covered}), "total": len(mas)},
            "service_health": health, "open_findings": sev, "open_total": sum(sev.values()),
            "next_scheduled_run_at": _iso(min(nexts)) if nexts else None,
            "links": {"assets": f"/assets/?module={m.value}", "findings": f"/findings/?empire_module={m.value}",
                      "runs": f"/reports/?module={m.value}"},
        })
    return {"as_of": now.isoformat(), "display_timezone": settings.DEFAULT_TIMEZONE, "modules": cards,
            "assets_in_scope": len(assets), "assets_in_modules": sum(c["assets"] for c in cards),
            "assets_unassigned": len(other), "scope": "estate" if ids is None else "granted"}


# =========================================================================== findings: history & recheck

@router.get("/findings/{finding_id}/history")
async def finding_history(finding_id: uuid.UUID, current_user: User = Depends(get_current_active_user),
                          db: AsyncSession = Depends(get_db)) -> Any:
    f = await db.get(NormalizedFinding, finding_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    (await load_scope(current_user, db)).require(f.asset_id, "READ")
    asset = await db.get(Asset, f.asset_id)
    changes = (await db.execute(select(FindingChange).where(FindingChange.finding_id == f.id)
                                .order_by(FindingChange.changed_at))).scalars().all()
    obs = (await db.execute(select(FindingObservation).where(FindingObservation.finding_id == f.id)
                            .order_by(FindingObservation.observed_at))).scalars().all()
    verified = [o for o in obs if o.outcome in ("new", "unchanged", "reopened", "fixed")]
    ev = f.evidence or {}
    return {
        "finding_id": str(f.id), "title": f.title, "status": f.status, "severity": f.severity,
        "asset": {"id": str(f.asset_id), "name": asset.name if asset else None,
                  "module": asset.empire_module if asset else None},
        "first_seen_at": _iso(f.first_seen_at), "last_seen_at": _iso(f.last_seen_at),
        "last_verified_at": _iso(verified[-1].observed_at) if verified else None,
        "source": ev.get("source") or {"engine": f.scanner_engine}, "confidence": ev.get("confidence", "unrated"),
        "owner": (asset.assessment_policy or {}).get("owner_contact") if asset else None,
        "assignee": f.assignee,
        "changes": [{"field": c.field, "old": c.old_value, "new": c.new_value, "actor": c.actor_name,
                     "actor_id": c.actor_id, "reason": c.reason,
                     "execution_id": str(c.execution_id) if c.execution_id else None,
                     "at": _iso(c.changed_at)} for c in changes],
        "observations": [{"execution_id": str(o.execution_id), "batch_id": str(o.batch_id) if o.batch_id else None,
                          "outcome": o.outcome, "status_before": o.status_before, "status_after": o.status_after,
                          "reason": o.reason, "output_sha256": o.output_sha256, "input_sha256": o.input_sha256,
                          "rule_digest": o.rule_digest, "observed_at": _iso(o.observed_at)} for o in obs],
        "display_timezone": settings.DEFAULT_TIMEZONE,
    }


async def recheck_finding_impl(db: AsyncSession, user: User, finding_id: uuid.UUID, request: Request,
                               idempotency_key: Optional[str]) -> JSONResponse:
    """Re-run exactly the defensive control that produced the finding (same engine) on its asset,
    with the currently approved input. RESOLVED is only set later by the runner if equivalent evidence
    no longer matches; this endpoint never changes the finding's status itself."""
    f = await db.get(NormalizedFinding, finding_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    scope = await load_scope(user, db)
    scope.require(f.asset_id, "SCAN")
    if f.scanner_engine not in ("sbom", "tls_health"):
        raise HTTPException(status_code=409, detail=f"No approved defensive control for engine '{f.scanner_engine}'; "
                                                    "import a manual verification as evidence instead.")
    key = f"{user.id}:recheck:{finding_id}:{idempotency_key}" if idempotency_key else None
    if key:
        prior = (await db.execute(select(RunRequest).where(RunRequest.idempotency_key == key))).scalars().first()
        if prior is not None:
            rec = (await db.execute(select(ExecutionRecord).where(ExecutionRecord.batch_id == prior.batch_id))
                   ).scalars().first()
            return JSONResponse(status_code=200, content={"finding_id": str(f.id), "replayed": True,
                                                          "batch_id": str(prior.batch_id),
                                                          "execution_id": str(rec.id) if rec else None})
    plan = await build_plan(db, selection=Selection(kind="assets", asset_ids=[str(f.asset_id)]),
                            engines=[f.scanner_engine], profile="light", trigger="recheck", scope=scope)
    item = plan.items[0]
    if item.decision == "skip":
        if item.reason_code == "ALREADY_ACTIVE":
            return JSONResponse(status_code=200, content={"finding_id": str(f.id), "replayed": False,
                                                          "execution_id": item.active_execution_id,
                                                          "note": "An execution of this control is already queued "
                                                                  "or running; it will verify this finding."})
        raise HTTPException(status_code=409, detail=f"{item.reason_code}: {item.reason}")
    corr = getattr(request.state, "request_id", None) or f"recheck-{uuid.uuid4().hex[:12]}"
    batch = await materialize(db, plan, name=f"Recheck · {f.title[:80]}", actor_id=str(user.id), correlation_id=corr)
    if key:
        db.add(RunRequest(idempotency_key=key, user_id=str(user.id), request_hash=str(finding_id), batch_id=batch.id))
    _audit(db, user, "FINDING_RECHECK", f"finding_id={f.id} engine={f.scanner_engine} batch_id={batch.id}", request)
    await db.flush()
    rec = (await db.execute(select(ExecutionRecord).where(ExecutionRecord.batch_id == batch.id))).scalars().first()
    await db.commit()
    return JSONResponse(status_code=202, content={
        "finding_id": str(f.id), "status": f.status, "batch_id": str(batch.id), "execution_id": str(rec.id),
        "decision": item.decision, "reason": item.reason, "correlation_id": corr, "replayed": False,
        "tracker": f"/engine-runs/?execution={rec.id}"})


@router.post("/findings/{finding_id}/recheck", status_code=status.HTTP_202_ACCEPTED)
async def recheck_finding(finding_id: uuid.UUID, request: Request,
                          idempotency_key: Optional[str] = Header(default=None, max_length=128),
                          current_user: User = Depends(get_current_active_user),
                          db: AsyncSession = Depends(get_db)) -> Any:
    return await recheck_finding_impl(db, current_user, finding_id, request, idempotency_key)


# =========================================================================== runs: list, tree, diff

async def _diff_counts(db, batch_ids: List[uuid.UUID], ids) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {str(b): {o: 0 for o in OUTCOMES} for b in batch_ids}
    if not batch_ids:
        return out
    rows = (await db.execute(_scoped(select(FindingObservation.batch_id, FindingObservation.outcome, func.count())
                                     .where(FindingObservation.batch_id.in_(batch_ids)),
                                     FindingObservation.asset_id, ids)
                             .group_by(FindingObservation.batch_id, FindingObservation.outcome))).all()
    for b, o, n in rows:
        out[str(b)][o] = n
    return out


@router.get("/runs")
async def list_runs(day: Optional[date] = Query(None, description="ICT calendar day; default today"),
                    current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> Any:
    ids = await _visible_ids(db, current_user)
    d = day or ict_today()
    start, end = ict_day_bounds(d)
    hidden = await _hidden_exec_ids(db)
    recs = (await db.execute(_scoped(select(ExecutionRecord).where(ExecutionRecord.queued_at >= start,
                                                                    ExecutionRecord.queued_at < end),
                                     ExecutionRecord.asset_id, ids))).scalars().all()
    recs = [r for r in recs if r.id not in hidden]
    by_batch: Dict[uuid.UUID, List[ExecutionRecord]] = {}
    for r in recs:
        by_batch.setdefault(r.batch_id, []).append(r)
    diffs = await _diff_counts(db, list(by_batch), ids)
    out = []
    for bid, rs in by_batch.items():
        b = await db.get(ScanBatch, bid)
        meta = (b.metadata_json or {}) if b else {}
        counts: Dict[str, int] = {}
        for r in rs:
            counts[r.status] = counts.get(r.status, 0) + 1
        out.append({"batch_id": str(bid), "name": b.name if b else None, "accepted_at": _iso(b.created_at) if b else None,
                    "trigger": meta.get("trigger"), "correlation_id": meta.get("correlation_id"),
                    "by_status": counts, "finished": all(r.status not in (EXEC_QUEUED, EXEC_RUNNING) for r in rs),
                    "diff": diffs[str(bid)],
                    "skip_or_fail": [{"execution_id": str(r.id), "engine_id": r.engine_id, "status": r.status,
                                      "reason": r.status_reason or r.plan_note} for r in rs
                                     if r.status not in (EXEC_SUCCEEDED, EXEC_QUEUED, EXEC_RUNNING)]})
    out.sort(key=lambda x: x["accepted_at"] or "", reverse=True)
    return {"day_ict": d.isoformat(), "from_utc": start.isoformat(), "to_utc": end.isoformat(), "runs": out,
            "totals": {o: sum(r["diff"][o] for r in out) for o in OUTCOMES}}


async def _batch_records(db, user, batch_id) -> List[ExecutionRecord]:
    b = await db.get(ScanBatch, batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail="Run not found")
    ids = await _visible_ids(db, user)
    recs = (await db.execute(_scoped(select(ExecutionRecord).where(ExecutionRecord.batch_id == batch_id),
                                     ExecutionRecord.asset_id, ids))).scalars().all()
    if ids is not None and not recs:
        raise HTTPException(status_code=404, detail="Run not found")
    return list(recs)


@router.get("/runs/{batch_id}/tree")
async def run_tree(batch_id: uuid.UUID, current_user: User = Depends(get_current_active_user),
                   db: AsyncSession = Depends(get_db)) -> Any:
    """module -> asset -> engine (execution) -> attempt -> evidence"""
    recs = await _batch_records(db, current_user, batch_id)
    tree: Dict[str, Dict[str, dict]] = {}
    for r in recs:
        a = await db.get(Asset, r.asset_id)
        module = a.empire_module if a else "UNKNOWN"
        node = tree.setdefault(module, {}).setdefault(str(r.asset_id), {
            "asset_id": str(r.asset_id), "name": a.name if a else None, "engines": []})
        attempts = (await db.execute(select(ExecutionAttempt).where(ExecutionAttempt.execution_id == r.id)
                                     .order_by(ExecutionAttempt.attempt_no))).scalars().all()
        obs = (await db.execute(select(FindingObservation.finding_id, FindingObservation.outcome)
                                .where(FindingObservation.execution_id == r.id))).all()
        node["engines"].append({
            "execution_id": str(r.id), "engine_id": r.engine_id, "status": r.status,
            "reason": r.status_reason or r.plan_note, "lane": r.lane,
            "attempts": [{"attempt_no": t.attempt_no, "status": t.status, "worker_id": t.worker_id,
                          "phase": t.phase, "duration_ms": t.duration_ms, "error_class": t.error_class}
                         for t in attempts],
            "evidence": {"input_sha256": r.input_sha256, "output_sha256": r.output_sha256,
                         "rule_digest": r.rule_digest, "observed_at": _iso(r.observed_at),
                         "output_url": f"/api/v1/executions/{r.id}/output" if r.output_path else None,
                         "findings": [{"finding_id": str(fid), "outcome": o} for fid, o in obs]},
        })
    return {"batch_id": str(batch_id), "modules": [
        {"module": m, "assets": sorted(v.values(), key=lambda x: x["name"] or "")} for m, v in sorted(tree.items())]}


@router.get("/runs/{batch_id}/diff")
async def run_diff(batch_id: uuid.UUID, current_user: User = Depends(get_current_active_user),
                   db: AsyncSession = Depends(get_db)) -> Any:
    recs = await _batch_records(db, current_user, batch_id)
    exec_ids = [r.id for r in recs]
    rows = (await db.execute(select(FindingObservation, NormalizedFinding)
                             .join(NormalizedFinding, NormalizedFinding.id == FindingObservation.finding_id)
                             .where(FindingObservation.execution_id.in_(exec_ids or [NONE_ID]))
                             .order_by(FindingObservation.outcome, NormalizedFinding.severity))).all()
    counts = {o: 0 for o in OUTCOMES}
    items = []
    for o, f in rows:
        counts[o.outcome] += 1
        items.append({"finding_id": str(f.id), "title": f.title, "severity": f.severity, "asset_id": str(f.asset_id),
                      "engine_id": o.engine_id, "outcome": o.outcome, "status_before": o.status_before,
                      "status_after": o.status_after, "reason": o.reason, "execution_id": str(o.execution_id)})
    return {"batch_id": str(batch_id), "counts": counts, "items": items}


# =========================================================================== history

class HistoryFilter(BaseModel):
    execution_ids: Optional[List[uuid.UUID]] = None
    batch_id: Optional[uuid.UUID] = None
    asset_id: Optional[uuid.UUID] = None
    engine: Optional[str] = None
    module: Optional[str] = None
    actor_id: Optional[str] = None
    status: Optional[str] = None
    day_from: Optional[date] = None
    day_to: Optional[date] = None


async def _history_stmt(db, user, flt: HistoryFilter, include_hidden: bool = False):
    ids = await _visible_ids(db, user)
    stmt = _scoped(select(ExecutionRecord), ExecutionRecord.asset_id, ids)
    if flt.execution_ids:
        stmt = stmt.where(ExecutionRecord.id.in_(flt.execution_ids))
    if flt.batch_id:
        stmt = stmt.where(ExecutionRecord.batch_id == flt.batch_id)
    if flt.asset_id:
        stmt = stmt.where(ExecutionRecord.asset_id == flt.asset_id)
    if flt.engine:
        stmt = stmt.where(ExecutionRecord.engine_id == flt.engine)
    if flt.actor_id:
        stmt = stmt.where(ExecutionRecord.actor_id == flt.actor_id)
    if flt.status:
        stmt = stmt.where(ExecutionRecord.status == flt.status)
    if flt.module:
        stmt = stmt.where(ExecutionRecord.asset_id.in_(select(Asset.id).where(Asset.empire_module == flt.module)))
    if flt.day_from:
        stmt = stmt.where(ExecutionRecord.queued_at >= ict_day_bounds(flt.day_from)[0])
    if flt.day_to:
        stmt = stmt.where(ExecutionRecord.queued_at < ict_day_bounds(flt.day_to)[1])
    if not include_hidden:
        stmt = stmt.where(ExecutionRecord.id.not_in(select(HiddenRecord.object_id)
                                                     .where(HiddenRecord.object_type == "execution")))
    return stmt


@router.get("/history")
async def history(batch_id: Optional[uuid.UUID] = None, asset_id: Optional[uuid.UUID] = None,
                  engine: Optional[str] = None, module: Optional[str] = None, actor_id: Optional[str] = None,
                  status_filter: Optional[str] = Query(None, alias="status"), day_from: Optional[date] = None,
                  day_to: Optional[date] = None, page: int = Query(1, ge=1), size: int = Query(50, ge=1, le=200),
                  current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> Any:
    flt = HistoryFilter(batch_id=batch_id, asset_id=asset_id, engine=engine, module=module, actor_id=actor_id,
                        status=status_filter, day_from=day_from, day_to=day_to)
    stmt = await _history_stmt(db, current_user, flt)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.order_by(ExecutionRecord.queued_at.desc()).offset((page - 1) * size).limit(size))
            ).scalars().all()
    return {"total": total, "page": page, "size": size, "pages": max(1, (total + size - 1) // size),
            "display_timezone": settings.DEFAULT_TIMEZONE,
            "items": [{"execution_id": str(r.id), "batch_id": str(r.batch_id) if r.batch_id else None,
                       "asset_id": str(r.asset_id), "engine_id": r.engine_id, "status": r.status,
                       "trigger": r.trigger, "actor_id": r.actor_id, "finding_count": r.finding_count,
                       "status_reason": r.status_reason, "queued_at": _iso(r.queued_at),
                       "finished_at": _iso(r.finished_at), "correlation_id": r.correlation_id} for r in rows]}


class HideRequest(HistoryFilter):
    reason: str = Field(..., min_length=3, max_length=500)
    confirm_count: int = Field(..., ge=1)


@router.post("/history/hide/preview")
async def hide_preview(flt: HistoryFilter, current_user: User = Depends(require_owner),
                       db: AsyncSession = Depends(get_db)) -> Any:
    stmt = await _history_stmt(db, current_user, flt)
    rows = (await db.execute(stmt)).scalars().all()
    running = [r for r in rows if r.status in (EXEC_QUEUED, EXEC_RUNNING)]
    return {"would_hide": len(rows) - len(running), "excluded_active": len(running),
            "note": "Hidden executions disappear from console lists; evidence, findings and the audit log are kept."}


@router.post("/history/hide")
async def hide_history(payload: HideRequest, request: Request, current_user: User = Depends(require_owner),
                       db: AsyncSession = Depends(get_db)) -> Any:
    stmt = await _history_stmt(db, current_user, payload)
    rows = [r for r in (await db.execute(stmt)).scalars().all() if r.status not in (EXEC_QUEUED, EXEC_RUNNING)]
    if len(rows) != payload.confirm_count:
        raise HTTPException(status_code=409, detail=f"Selection changed: {len(rows)} execution(s) match now, "
                                                    f"confirmation was for {payload.confirm_count}. Preview again.")
    for r in rows:
        db.add(HiddenRecord(object_type="execution", object_id=r.id, hidden_by=str(current_user.id),
                            reason=payload.reason))
    _audit(db, current_user, "HISTORY_HIDE", f"count={len(rows)} reason={payload.reason} "
           f"ids={','.join(str(r.id) for r in rows)[:800]}", request)
    await db.commit()
    return {"hidden": len(rows)}


class UnhideRequest(BaseModel):
    execution_ids: List[uuid.UUID]


@router.post("/history/unhide")
async def unhide_history(payload: UnhideRequest, request: Request, current_user: User = Depends(require_owner),
                         db: AsyncSession = Depends(get_db)) -> Any:
    rows = (await db.execute(select(HiddenRecord).where(HiddenRecord.object_type == "execution",
                                                        HiddenRecord.object_id.in_(payload.execution_ids)))
            ).scalars().all()
    for h in rows:
        await db.delete(h)
    _audit(db, current_user, "HISTORY_UNHIDE", f"count={len(rows)}", request)
    await db.commit()
    return {"restored": len(rows)}


# =========================================================================== notifications (per user)

def _notif_out(n: Notification) -> dict:
    return {"id": str(n.id), "kind": n.kind, "severity": n.severity, "title": n.title, "message": n.message,
            "object_type": n.object_type, "object_id": n.object_id, "link": n.link,
            "created_at": _iso(n.created_at), "read": n.read_at is not None}


def _mine(user):
    return select(Notification).where(Notification.user_id == str(user.id), Notification.deleted_at.is_(None))


@router.get("/notifications")
async def list_notifications(unread_only: bool = False, limit: int = Query(30, ge=1, le=200),
                             current_user: User = Depends(get_current_active_user),
                             db: AsyncSession = Depends(get_db)) -> Any:
    stmt = _mine(current_user)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = (await db.execute(stmt.order_by(Notification.created_at.desc()).limit(limit))).scalars().all()
    unread = (await db.execute(select(func.count()).select_from(
        _mine(current_user).where(Notification.read_at.is_(None)).subquery()))).scalar() or 0
    return {"items": [_notif_out(n) for n in rows], "unread": unread}


@router.get("/notifications/unread-count")
async def unread_count(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> Any:
    n = (await db.execute(select(func.count()).select_from(
        _mine(current_user).where(Notification.read_at.is_(None)).subquery()))).scalar() or 0
    return {"unread": n}


async def _own_notification(db, user, nid: uuid.UUID) -> Notification:
    n = await db.get(Notification, nid)
    if n is None or n.user_id != str(user.id) or n.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return n


@router.post("/notifications/{nid}/read")
async def read_notification(nid: uuid.UUID, current_user: User = Depends(get_current_active_user),
                            db: AsyncSession = Depends(get_db)) -> Any:
    n = await _own_notification(db, current_user, nid)
    n.read_at = n.read_at or datetime.now(timezone.utc)
    await db.commit()
    return _notif_out(n)


@router.post("/notifications/read-all")
async def read_all(current_user: User = Depends(get_current_active_user), db: AsyncSession = Depends(get_db)) -> Any:
    res = await db.execute(update(Notification).where(Notification.user_id == str(current_user.id),
                                                      Notification.read_at.is_(None),
                                                      Notification.deleted_at.is_(None))
                           .values(read_at=datetime.now(timezone.utc)))
    await db.commit()
    return {"marked": res.rowcount}


@router.delete("/notifications/{nid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(nid: uuid.UUID, current_user: User = Depends(get_current_active_user),
                              db: AsyncSession = Depends(get_db)) -> Response:
    n = await _own_notification(db, current_user, nid)
    n.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return Response(status_code=204)


# =========================================================================== report snapshots

class SnapshotCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    asset_ids: Optional[List[uuid.UUID]] = None
    batch_id: Optional[uuid.UUID] = None
    days: int = Field(7, ge=1, le=90)


def _snap_out(r) -> dict:
    return {"id": str(r.id), "title": r.title, "scope": r.scope, "template_version": r.template_version,
            "snapshot_sha256": r.snapshot_sha256, "finding_count": r.finding_count,
            "execution_ids": r.execution_ids, "correlation_ids": r.correlation_ids,
            "previous_snapshot_id": str(r.previous_snapshot_id) if r.previous_snapshot_id else None,
            "files": {k: {"sha256": v["sha256"], "bytes": v["bytes"]} for k, v in (r.files or {}).items()
                      if k != "snapshot"},
            "created_by": r.created_by, "generated_at": _iso(r.generated_at),
            "display_timezone": settings.DEFAULT_TIMEZONE}


@router.post("/report-snapshots", status_code=status.HTTP_201_CREATED)
async def create_report_snapshot(payload: SnapshotCreate, request: Request,
                                 current_user: User = Depends(get_current_active_user),
                                 db: AsyncSession = Depends(get_db)) -> Any:
    from backend.app.reporting.pilot_report import create_snapshot

    scope = await load_scope(current_user, db)
    if payload.batch_id:
        recs = (await db.execute(select(ExecutionRecord.asset_id).where(ExecutionRecord.batch_id == payload.batch_id)
                                 )).scalars().all()
        if not recs:
            raise HTTPException(status_code=404, detail="Run not found")
        asset_ids, kind = sorted(set(recs), key=str), "run"
    elif payload.asset_ids:
        asset_ids, kind = payload.asset_ids, "assets"
    else:
        if scope.asset_ids is not None:
            raise HTTPException(status_code=403, detail="Estate-wide reports are restricted to the owner.")
        asset_ids, kind = [a for a in (await db.execute(select(Asset.id))).scalars()], "estate"
    for aid in asset_ids:
        scope.require(aid, "REPORT")
    assets = (await db.execute(select(Asset).where(Asset.id.in_(asset_ids or [NONE_ID])).order_by(Asset.name))
              ).scalars().all()
    rs = await create_snapshot(db, title=payload.title, assets=list(assets), batch_id=payload.batch_id,
                               days=payload.days, user_id=str(current_user.id), scope_kind=kind)
    _audit(db, current_user, "REPORT_SNAPSHOT_CREATE", f"report_id={rs.id} kind={kind} sha256={rs.snapshot_sha256}",
           request)
    await db.commit()
    return _snap_out(rs)


async def _scoped_snapshot(db, user, rid: uuid.UUID):
    from backend.app.models.lifecycle import ReportSnapshot

    r = await db.get(ReportSnapshot, rid)
    if r is None:
        raise HTTPException(status_code=404, detail="Report not found")
    scope = await load_scope(user, db)
    if scope.asset_ids is not None:
        if r.scope.get("kind") == "estate" or not all(scope.can(uuid.UUID(a), "READ") for a in r.asset_ids):
            raise HTTPException(status_code=404, detail="Report not found")
    return r


@router.get("/report-snapshots")
async def list_report_snapshots(current_user: User = Depends(get_current_active_user),
                                db: AsyncSession = Depends(get_db)) -> Any:
    from backend.app.models.lifecycle import ReportSnapshot

    scope = await load_scope(current_user, db)
    rows = (await db.execute(select(ReportSnapshot).order_by(ReportSnapshot.generated_at.desc()))).scalars().all()
    if scope.asset_ids is not None:
        rows = [r for r in rows if r.scope.get("kind") != "estate"
                and all(scope.can(uuid.UUID(a), "READ") for a in r.asset_ids)]
    return [_snap_out(r) for r in rows]


@router.get("/report-snapshots/{rid}/download")
async def download_report_snapshot(rid: uuid.UUID, format: str = Query("pdf", pattern="^(pdf|html|json)$"),
                                   inline: bool = False, current_user: User = Depends(get_current_active_user),
                                   db: AsyncSession = Depends(get_db)) -> Any:
    import hashlib
    from pathlib import Path

    from backend.app.engines.runner import storage_root

    r = await _scoped_snapshot(db, current_user, rid)
    meta = (r.files or {}).get(format)
    if not meta:
        raise HTTPException(status_code=404, detail=f"No {format} rendering")
    p = Path(meta["path"]).resolve()
    if not p.is_relative_to(storage_root()) or not p.is_file():
        raise HTTPException(status_code=404, detail="Report file missing from storage")
    data = p.read_bytes()
    if hashlib.sha256(data).hexdigest() != meta["sha256"]:
        raise HTTPException(status_code=409, detail="Stored report does not match its recorded checksum")
    media = {"pdf": "application/pdf", "html": "text/html; charset=utf-8", "json": "application/json"}[format]
    disp = "inline" if inline else "attachment"
    return Response(content=data, media_type=media, headers={
        "Content-Disposition": f'{disp}; filename="report-{r.id}.{format}"', "Cache-Control": "private, no-store",
        "X-Content-SHA256": meta["sha256"], "X-Snapshot-SHA256": r.snapshot_sha256,
        "X-Template-Version": r.template_version, "X-Content-Type-Options": "nosniff",
        # inline HTML is the console's own report: no scripts, no external loads
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'"})
