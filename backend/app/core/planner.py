"""One planner for every trigger (Milestone 4).

"Run whole system", a single asset/module selection and the hourly schedule all call
`build_plan()` then `materialize()`. The plan decides, per (asset, engine):

  queue  -> an execution row is created and becomes claimable now
  defer  -> created but claimable later (`available_at`), with the reason and resume time
  skip   -> not created; the reason is reported (missing input, already active, rules missing)

Capacity rules applied here (all estate-wide, owner-configurable):
  * per-host hourly quota for engines that open network connections (tls_health)
  * profile spacing between requests to the same host ("slow" profile)
  * window budget: if the estimated backlog cannot finish inside the window with the
    available slots, quick checks are kept and the longest items move to the long lane.
"""

from __future__ import annotations

import hashlib
import json
import statistics
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.asset import Asset
from backend.app.models.defensive import (
    EXEC_QUEUED,
    EXEC_RUNNING,
    EXEC_SUCCEEDED,
    AdvisorySnapshot,
    Artifact,
    ExecutionRecord,
)
from backend.app.models.operations import CapacitySettings
from backend.app.models.scan import Scan, ScanBatch

ENGINES = ("tls_health", "sbom")  # order = priority inside a plan (network-free work is cheap either way)
DEFAULT_EST_SECONDS = {"tls_health": 3.0, "sbom": 2.0}
LONG_LANE_SECONDS = 60.0  # items estimated above this are "long" regardless of window pressure

PROFILES: Dict[str, dict] = {
    # light: quick checks, short budgets, no spacing
    "light": {"timeouts": {"tls_health": 30, "sbom": 60}, "host_spacing_seconds": 0, "max_workers": None},
    # slow: gentle on targets: one worker, spaced requests to the same host, larger budgets
    "slow": {"timeouts": {"tls_health": 60, "sbom": 300}, "host_spacing_seconds": 20, "max_workers": 1},
}

NOT_APPLICABLE = {"NO_ARTIFACT", "NO_APPROVED_ENDPOINT"}  # configuration gaps, not run failures


@dataclass
class Selection:
    kind: str = "all"  # all | assets | module
    asset_ids: List[str] = field(default_factory=list)
    module: Optional[str] = None

    @staticmethod
    def parse(raw: dict) -> "Selection":
        kind = (raw or {}).get("kind", "all")
        if kind not in ("all", "assets", "module"):
            raise HTTPException(status_code=422, detail="selection.kind must be all | assets | module")
        sel = Selection(kind=kind, asset_ids=[str(a) for a in (raw.get("asset_ids") or [])],
                        module=raw.get("module"))
        if kind == "assets" and not sel.asset_ids:
            raise HTTPException(status_code=422, detail="selection.asset_ids is required for kind=assets")
        if kind == "module" and not sel.module:
            raise HTTPException(status_code=422, detail="selection.module is required for kind=module")
        return sel


@dataclass
class PlanItem:
    asset_id: str
    asset_name: str
    module: Optional[str]
    engine: str
    decision: str  # queue | defer | skip
    reason_code: Optional[str] = None
    reason: Optional[str] = None
    lane: str = "quick"
    est_seconds: float = 0.0
    available_at: Optional[str] = None
    target_host: Optional[str] = None
    artifact_id: Optional[str] = None
    input_sha256: Optional[str] = None
    health_revision: Optional[str] = None
    health_url: Optional[str] = None
    active_execution_id: Optional[str] = None
    timeout_seconds: int = 60


@dataclass
class Plan:
    trigger: str
    profile: str
    engines: List[str]
    selection: dict
    window_seconds: int
    slots: int
    items: List[PlanItem]
    planned_at: str
    backlog_seconds_before: float
    capacity: dict

    def summary(self) -> dict:
        by_decision: Dict[str, int] = {}
        reasons: Dict[str, int] = {}
        for it in self.items:
            by_decision[it.decision] = by_decision.get(it.decision, 0) + 1
            if it.reason_code:
                reasons[it.reason_code] = reasons.get(it.reason_code, 0) + 1
        queued = [i for i in self.items if i.decision == "queue"]
        deferred = [i for i in self.items if i.decision == "defer"]
        est_queue = sum(i.est_seconds for i in queued)
        slots = max(1, self.slots)
        finish_s = (self.backlog_seconds_before + est_queue) / slots
        planned_dt = datetime.fromisoformat(self.planned_at)
        resume = min((i.available_at for i in deferred if i.available_at), default=None)
        return {
            "assets_in_scope": len({i.asset_id for i in self.items}),
            "pairs": len(self.items),
            "queue": by_decision.get("queue", 0),
            "defer": by_decision.get("defer", 0),
            "skip": by_decision.get("skip", 0),
            "reasons": reasons,
            "estimated_work_seconds": round(est_queue, 1),
            "backlog_seconds_before": round(self.backlog_seconds_before, 1),
            "slots": slots,
            "estimated_finish_at": (planned_dt + timedelta(seconds=finish_s)).isoformat(),
            "fits_window": finish_s <= self.window_seconds,
            "deferred_resume_at": resume,
            "window_seconds": self.window_seconds,
            "theoretical_hourly_capacity": self.capacity.get("theoretical_hourly_capacity"),
        }

    def to_dict(self) -> dict:
        return {"trigger": self.trigger, "profile": self.profile, "engines": self.engines,
                "selection": self.selection, "planned_at": self.planned_at, "summary": self.summary(),
                "items": [asdict(i) for i in self.items]}


async def capacity_settings(db: AsyncSession) -> CapacitySettings:
    cs = await db.get(CapacitySettings, 1)
    if cs is None:
        cs = CapacitySettings(id=1)
        db.add(cs)
        await db.flush()
    return cs


async def engine_estimates(db: AsyncSession) -> Dict[str, dict]:
    """p50/p95 seconds a slot is held per execution (attempt start -> commit, which includes queue
    bookkeeping, not just engine time), from the last 200 succeeded attempts; fallback: defaults."""
    from backend.app.models.operations import ExecutionMetric

    out = {}
    for eng in ENGINES:
        rows = (await db.execute(select(ExecutionMetric.slot_ms).where(
            ExecutionMetric.engine_id == eng, ExecutionMetric.status == EXEC_SUCCEEDED,
            ExecutionMetric.slot_ms.is_not(None)).order_by(ExecutionMetric.recorded_at.desc()).limit(200))
        ).scalars().all()
        secs = sorted(max(0.001, r / 1000.0) for r in rows)
        if secs:
            p50 = statistics.median(secs)
            p95 = secs[min(len(secs) - 1, int(round(0.95 * (len(secs) - 1))))]
            out[eng] = {"p50": p50, "p95": p95, "samples": len(secs), "basis": "measured"}
        else:
            d = DEFAULT_EST_SECONDS[eng]
            out[eng] = {"p50": d, "p95": d, "samples": 0, "basis": "default"}
    return out


async def queued_backlog_seconds(db: AsyncSession, est: Dict[str, dict], now: datetime) -> float:
    rows = (await db.execute(select(ExecutionRecord.engine_id, func.count()).join(Scan, Scan.id == ExecutionRecord.scan_id)
                             .where(ExecutionRecord.status.in_((EXEC_QUEUED, EXEC_RUNNING)),
                                    (Scan.available_at.is_(None)) | (Scan.available_at <= now))
                             .group_by(ExecutionRecord.engine_id))).all()
    return float(sum(n * est.get(e, {"p50": 5.0})["p50"] for e, n in rows))


async def resolve_assets(db: AsyncSession, sel: Selection, scope, action: str = "SCAN") -> List[Asset]:
    """Assets the actor may act on. `scope` is an AccessScope (owner: asset_ids is None)."""
    if sel.kind == "assets":
        ids = []
        for raw in sel.asset_ids:
            try:
                aid = uuid.UUID(raw)
            except ValueError:
                raise HTTPException(status_code=422, detail=f"Invalid asset id: {raw[:40]}")
            scope.require(aid, action)  # 404 outside scope, 403 without the action
            ids.append(aid)
        rows = (await db.execute(select(Asset).where(Asset.id.in_(ids)))).scalars().all()
        if len(rows) != len(set(ids)):
            raise HTTPException(status_code=404, detail="Asset not found")
        return sorted(rows, key=lambda a: a.name)
    stmt = select(Asset)
    if sel.kind == "module":
        stmt = stmt.where(Asset.empire_module == sel.module)
    if scope.asset_ids is not None:
        allowed = scope.ids_with(action)
        if not allowed:
            return []
        stmt = stmt.where(Asset.id.in_(allowed))
    return list((await db.execute(stmt.order_by(Asset.name))).scalars().all())


def _host_of(url: Optional[str]) -> Optional[str]:
    return (urlsplit(url).hostname or "").lower() or None if url else None


async def build_plan(db: AsyncSession, *, selection: Selection, engines: Sequence[str], profile: str,
                     trigger: str, scope, window_seconds: int = 3600, max_workers: Optional[int] = None,
                     now: Optional[datetime] = None) -> Plan:
    if profile not in PROFILES:
        raise HTTPException(status_code=422, detail="profile must be light | slow")
    engines = [e for e in ENGINES if e in set(engines)]
    if not engines:
        raise HTTPException(status_code=422, detail=f"engines must be a non-empty subset of {list(ENGINES)}")
    now = now or datetime.now(timezone.utc)
    prof = PROFILES[profile]
    cs = await capacity_settings(db)
    est = await engine_estimates(db)
    slots = cs.max_running_executions
    for cap in (max_workers, prof["max_workers"]):
        if cap:
            slots = min(slots, cap)
    slots = max(1, slots)
    backlog = await queued_backlog_seconds(db, est, now)
    assets = await resolve_assets(db, selection, scope)
    asset_ids = [a.id for a in assets]

    active_rows = (await db.execute(select(ExecutionRecord.asset_id, ExecutionRecord.engine_id, ExecutionRecord.id)
                                    .where(ExecutionRecord.status.in_((EXEC_QUEUED, EXEC_RUNNING)),
                                           ExecutionRecord.asset_id.in_(asset_ids or [uuid.uuid4()])))).all()
    active = {(a, e): str(i) for a, e, i in active_rows}
    latest_art: Dict[uuid.UUID, Artifact] = {}
    if "sbom" in engines and asset_ids:
        for art in (await db.execute(select(Artifact).where(Artifact.asset_id.in_(asset_ids), Artifact.kind == "sbom")
                                     .order_by(Artifact.uploaded_at.asc()))).scalars():
            latest_art[art.asset_id] = art  # ascending order -> last wins = newest
    snapshot = (await db.execute(select(AdvisorySnapshot).where(AdvisorySnapshot.is_active == True)  # noqa: E712
                                 )).scalars().first()

    # Host usage inside the trailing hour (quota) and the newest request time per host (spacing).
    hour_ago = now - timedelta(hours=1)
    host_rows = (await db.execute(select(ExecutionRecord.target_host, ExecutionRecord.queued_at)
                                  .where(ExecutionRecord.engine_id == "tls_health",
                                         ExecutionRecord.target_host.is_not(None),
                                         ExecutionRecord.queued_at >= hour_ago,
                                         ExecutionRecord.status != "cancelled"))).all()
    host_times: Dict[str, List[datetime]] = {}
    for h, t in host_rows:
        host_times.setdefault(h, []).append(t if t.tzinfo else t.replace(tzinfo=timezone.utc))
    from backend.app.models.operations import ExecutionMetric
    host_egress = dict((await db.execute(select(ExecutionMetric.target_host, func.sum(ExecutionMetric.egress_bytes))
                                         .where(ExecutionMetric.target_host.is_not(None),
                                                ExecutionMetric.recorded_at >= hour_ago)
                                         .group_by(ExecutionMetric.target_host))).all())

    items: List[PlanItem] = []
    host_next_free: Dict[str, datetime] = {}
    spacing = timedelta(seconds=prof["host_spacing_seconds"])
    for asset in assets:
        for eng in engines:
            it = PlanItem(asset_id=str(asset.id), asset_name=asset.name, module=asset.empire_module, engine=eng,
                          decision="queue", est_seconds=round(est[eng]["p50"], 3),
                          timeout_seconds=prof["timeouts"][eng])
            if (asset.id, eng) in active:
                it.decision, it.reason_code = "skip", "ALREADY_ACTIVE"
                it.active_execution_id = active[(asset.id, eng)]
                it.reason = "An execution for this asset and engine is already queued or running."
                items.append(it)
                continue
            if eng == "sbom":
                art = latest_art.get(asset.id)
                if art is None:
                    it.decision, it.reason_code = "skip", "NO_ARTIFACT"
                    it.reason = "No SBOM uploaded for this asset."
                elif snapshot is None:
                    it.decision, it.reason_code = "skip", "RULES_UNAVAILABLE"
                    it.reason = "No active advisory snapshot; import one before running sbom."
                else:
                    it.artifact_id, it.input_sha256 = str(art.id), art.sha256
            else:
                hc = (asset.assessment_policy or {}).get("health_check") or {}
                if not hc.get("url"):
                    it.decision, it.reason_code = "skip", "NO_APPROVED_ENDPOINT"
                    it.reason = "Owner has not approved a health endpoint for this asset."
                else:
                    it.health_url, it.health_revision = hc["url"], hc.get("revision")
                    it.target_host = _host_of(hc["url"])
                    times = sorted(host_times.get(it.target_host, []))
                    used_bytes = int(host_egress.get(it.target_host) or 0)
                    if used_bytes >= cs.per_host_egress_bytes_hourly:
                        it.decision, it.reason_code = "defer", "EGRESS_BUDGET"
                        it.available_at = (now + timedelta(hours=1)).isoformat()
                        it.reason = (f"Host {it.target_host} used {used_bytes} of {cs.per_host_egress_bytes_hourly} "
                                     f"egress bytes in the last hour; resumes at {it.available_at}.")
                    elif len(times) >= cs.per_host_hourly_quota:
                        resume = times[len(times) - cs.per_host_hourly_quota] + timedelta(hours=1)
                        it.decision, it.reason_code = "defer", "HOST_QUOTA"
                        it.available_at = resume.isoformat()
                        it.reason = (f"Host {it.target_host} reached its quota of {cs.per_host_hourly_quota} "
                                     f"requests/hour; resumes at {it.available_at}.")
                    else:
                        start = max(now, host_next_free.get(it.target_host, now))
                        if spacing and it.target_host in host_next_free:
                            it.available_at = start.isoformat()
                            it.reason_code = "HOST_SPACING"
                            it.reason = f"Spaced {prof['host_spacing_seconds']}s from the previous request to this host."
                        host_next_free[it.target_host] = start + spacing
                        host_times.setdefault(it.target_host, []).append(start)
            items.append(it)

    # Window budget: keep quick work inside the window, move the longest items to the long lane.
    budget = window_seconds * slots - backlog
    used = 0.0
    window_end = now + timedelta(seconds=window_seconds)
    for it in sorted((i for i in items if i.decision == "queue"), key=lambda i: i.est_seconds):
        if it.est_seconds > LONG_LANE_SECONDS or used + it.est_seconds > budget:
            it.decision, it.lane = "defer", "long"
            it.reason_code = "WINDOW_OVERFLOW"
            it.available_at = window_end.isoformat()
            it.reason = (f"Estimated backlog exceeds the {window_seconds // 60}-minute window with {slots} slot(s); "
                         f"moved to the long lane, resumes at {it.available_at}.")
        else:
            used += it.est_seconds
    avg = statistics.mean([est[e]["p50"] for e in engines])
    capacity = {"slots": slots, "avg_seconds_per_execution": round(avg, 3),
                "theoretical_hourly_capacity": int(3600 * slots / max(avg, 0.001)),
                "per_host_hourly_quota": cs.per_host_hourly_quota, "estimates": est}
    return Plan(trigger=trigger, profile=profile, engines=list(engines), selection=asdict(selection),
                window_seconds=window_seconds, slots=slots, items=items, planned_at=now.isoformat(),
                backlog_seconds_before=backlog, capacity=capacity)


def request_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


async def materialize(db: AsyncSession, plan: Plan, *, name: str, actor_id: Optional[str],
                      correlation_id: str, schedule_slot_id: Optional[uuid.UUID] = None,
                      schedule_id: Optional[uuid.UUID] = None) -> ScanBatch:
    """Create the batch and one queue row + execution record per queue/defer item, in the
    caller's transaction. Events are emitted in the same transaction."""
    from backend.app.core.event_bus import emit_event

    now = datetime.fromisoformat(plan.planned_at)
    runnable = [i for i in plan.items if i.decision in ("queue", "defer")]
    batch = ScanBatch(name=name[:255], status="QUEUED" if runnable else "COMPLETED", total_scans=len(runnable),
                      target_count=plan.summary()["assets_in_scope"], engines=plan.engines, profiles=[plan.profile],
                      schedule_id=None,
                      metadata_json={"trigger": plan.trigger, "actor_id": actor_id, "correlation_id": correlation_id,
                                     "schedule_id": str(schedule_id) if schedule_id else None,
                                     "schedule_slot_id": str(schedule_slot_id) if schedule_slot_id else None,
                                     "plan_summary": plan.summary(), "profile": plan.profile})
    db.add(batch)
    await db.flush()
    # Quick items first, then by available_at; distinct created_at keeps claim order stable.
    order = sorted(runnable, key=lambda i: (i.lane != "quick", i.available_at or "", i.est_seconds))
    for n, it in enumerate(order):
        avail = datetime.fromisoformat(it.available_at) if it.available_at else None
        aid = uuid.UUID(it.asset_id)
        scan = Scan(asset_id=aid, batch_id=batch.id, engine=it.engine, profile="BASELINE", status="QUEUED",
                    target_locator=f"engine://{it.engine}/{aid}", timeout_seconds=it.timeout_seconds,
                    max_retries=3, available_at=avail)
        scan.created_at = now + timedelta(microseconds=n)
        db.add(scan)
        await db.flush()
        descriptor = ({"artifact_id": it.artifact_id} if it.engine == "sbom"
                      else {"health_check_revision": it.health_revision, "url": it.health_url})
        rec = ExecutionRecord(scan_id=scan.id, batch_id=batch.id, asset_id=aid, engine_id=it.engine,
                              execution_mode="native",
                              artifact_id=uuid.UUID(it.artifact_id) if it.artifact_id else None,
                              input_sha256=it.input_sha256, input_descriptor=descriptor,
                              scope_revision=it.health_revision, trigger=plan.trigger, actor_id=actor_id,
                              status=EXEC_QUEUED, queued_at=now, correlation_id=correlation_id,
                              schedule_slot_id=schedule_slot_id, lane=it.lane, target_host=it.target_host,
                              plan_note=(f"{it.reason_code}: {it.reason}"[:512] if it.reason_code else None))
        db.add(rec)
        await db.flush()
        await emit_event("EXECUTION_QUEUED", f"{it.engine} queued for {it.asset_name}"
                         + (f" (deferred: {it.reason_code})" if it.decision == "defer" else ""),
                         scan_id=scan.id, batch_id=batch.id, target_id=aid, engine=it.engine, session=db,
                         details={"execution_id": str(rec.id), "correlation_id": correlation_id,
                                  "lane": it.lane, "available_at": it.available_at, "trigger": plan.trigger})
    await emit_event("RUN_ACCEPTED", f"{plan.trigger} run accepted: {len(runnable)} execution(s)",
                     batch_id=batch.id, session=db, actor_id=actor_id,
                     details={"correlation_id": correlation_id, "summary": plan.summary(),
                              "schedule_id": str(schedule_id) if schedule_id else None})
    return batch
