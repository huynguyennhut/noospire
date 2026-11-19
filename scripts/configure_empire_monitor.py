"""Configure the owner-designated Empire root monitor on this self-hosted installation.

Default is a read-only preview. --apply makes an online SQLite backup, migrates the
schema and records an audited exact-root approval plus a 120-minute schedule.
No HTTP requests, credentials or ownership proofs are created by this command.
An optional first run is queued for the existing durable worker, never executed here.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


async def configure(db, schedule_id: uuid.UUID, *, queue_first_run=False, mode="head") -> dict:
    from sqlalchemy import select
    from backend.app.core.config import settings
    from backend.app.core.inventory_reconciliation import PRIMARY_TARGET
    from backend.app.core.monitor_scheduler import _OwnerScope, active_work, next_slot_after
    from backend.app.core.planner import Selection, build_plan, materialize
    from backend.app.engines.public_web import approval_policy, validate_approval
    from backend.app.engines import web_surface
    from backend.app.models.asset import Asset
    from backend.app.models.base import AdminAuditLog
    from backend.app.models.operations import MonitorSchedule, RunRequest
    from backend.app.core.planner import capacity_settings
    from backend.app.models.scope import AssetAssessmentScope
    from backend.app.models.user import User

    owner = await db.get(User, uuid.UUID(str(settings.SOLE_OWNER_ACCOUNT_ID)))
    if not owner or not owner.is_active or owner.email != settings.SOLE_OWNER_EMAIL:
        raise ValueError("Configured active sole owner is missing; no changes applied")
    assets = (await db.execute(select(Asset).where(Asset.target_locator == PRIMARY_TARGET))).scalars().all()
    if len(assets) != 1:
        raise ValueError("Exactly one owner-designated root asset must already exist")
    asset = assets[0]
    schedule = await db.get(MonitorSchedule, schedule_id)
    if not schedule:
        raise ValueError("Explicit existing schedule ID was not found")
    if await active_work(db, schedule_id):
        raise ValueError("Schedule still has active work; allow it to finish before reconfiguration")
    now = datetime.now(timezone.utc)
    marker = "noosforge:public-monitor"
    grant = (await db.execute(select(AssetAssessmentScope).where(
        AssetAssessmentScope.asset_id == asset.id, AssetAssessmentScope.created_by == marker))).scalars().first()
    if grant is None:
        grant = AssetAssessmentScope(asset_id=asset.id, exact_origin="https://empire.edu.vn",
            ports=[443], allowed_path_patterns=["/"], permitted_checks=["public_web"],
            rate_limit_rps=1, concurrency_limit=1, max_requests_per_run=1,
            byte_budget=131072, created_by=marker)
        db.add(grant)
        await db.flush()
    if mode == "surface":
        grant.allowed_path_patterns = ["/*"]
        grant.max_requests_per_run = web_surface.MAX_REQUESTS
        grant.byte_budget = web_surface.MAX_BYTES
    elif mode != "head":
        raise ValueError("Unknown monitor mode")
    old_policy = (asset.assessment_policy or {}).get("public_web") or {}
    policy = old_policy if old_policy.get("url") == PRIMARY_TARGET and old_policy.get("mode", "head") == mode else approval_policy(asset, PRIMARY_TARGET, str(owner.id), mode=mode)
    asset.assessment_policy = {**(asset.assessment_policy or {}), "public_web": policy}
    await validate_approval(db, asset)  # real proof, exact scope, stop and expiry are mandatory
    capacity = await capacity_settings(db)
    previous_capacity = capacity.max_running_executions
    capacity.max_running_executions = 1
    capacity.updated_by = str(owner.id)
    capacity.updated_at = now

    desired = {"name": "Empire public surface · every 2 hours" if mode == "surface" else "Empire public root · every 2 hours", "selection": {"kind": "assets", "asset_ids": [str(asset.id)]},
               "engines": ["public_web"], "profile": "slow", "interval_minutes": 120, "max_workers": 1, "is_active": True}
    before = {k: getattr(schedule, k) for k in desired}
    changed = before != desired
    if changed:
        for key, value in desired.items():
            setattr(schedule, key, value)
        schedule.start_after = now
        schedule.next_run_at = next_slot_after(now, 120)
        schedule.pending_catchup = False
        schedule.overdue_reason = None
        schedule.revision += 1
        schedule.updated_at = now
    first_batch = None
    if queue_first_run:
        key = f"operator-public-monitor-v1:{asset.id}:{mode}:{policy['revision']}"
        prior = (await db.execute(select(RunRequest).where(RunRequest.idempotency_key == key))).scalars().first()
        if prior:
            first_batch = str(prior.batch_id)
        else:
            plan = await build_plan(db, selection=Selection.parse(desired["selection"]), engines=["public_web"],
                                    profile="slow", trigger="manual", scope=_OwnerScope())
            if plan.summary()["queue"] != 1:
                raise ValueError(f"Initial observation not runnable: {plan.summary()['reasons']}")
            batch = await materialize(db, plan, name="Empire public root · initial operator observation",
                                      actor_id=str(owner.id), correlation_id=f"operator-{uuid.uuid4().hex[:16]}")
            db.add(RunRequest(idempotency_key=key, user_id=str(owner.id), request_hash="public-monitor-v1", batch_id=batch.id))
            first_batch = str(batch.id)
    details = {"schedule_id": str(schedule.id), "asset_id": str(asset.id), "before": before, "after": desired,
               "policy_revision": policy["revision"], "first_batch_id": first_batch,
               "capacity_before": previous_capacity, "capacity_after": 1,
               "authorization_source": "docs/EMPIRE_INVENTORY_GUIDANCE.md and owner request for a 2-hour monitor"}
    db.add(AdminAuditLog(user_id=str(owner.id), username=owner.username, action="PUBLIC_MONITOR_CONFIGURE",
                         details=json.dumps(details), ip_address="local-operator"))
    await db.commit()
    return {"schedule_id": str(schedule.id), "asset_id": str(asset.id), "interval_minutes": 120,
            "next_run_at": schedule.next_run_at.isoformat(), "changed": changed, "first_batch_id": first_batch,
            "target": PRIMARY_TARGET, "mode": mode,
            "checks": "bounded same-origin public GET traversal; TLS, headers and HTML policy checks" if mode == "surface" else "one unauthenticated HTTPS HEAD; TLS and response metadata",
            "application_health_assessed": False, "full_assessment_complete": False}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--database", required=True, type=Path)
    p.add_argument("--schedule-id", required=True, type=uuid.UUID)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--queue-first-run", action="store_true")
    p.add_argument("--mode", choices=("head", "surface"), default="head")
    args = p.parse_args()
    source = args.database.resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as con:
        roots = con.execute("SELECT id FROM assets WHERE target_locator=?", ("https://empire.edu.vn/",)).fetchall()
        schedules = con.execute("SELECT name, interval_minutes FROM monitor_schedules WHERE id=?", (str(args.schedule_id),)).fetchall()
        preview = {"database": str(source), "root_count": len(roots), "schedule": schedules,
                   "proposed_interval_minutes": 120, "target": "https://empire.edu.vn/", "mode": args.mode,
                   "network_requests": 0}
        if not args.apply:
            print(json.dumps({**preview, "applied": False}))
            return 0
        if len(roots) != 1 or len(schedules) != 1:
            p.error("Root/schedule preconditions failed")
        backup = source.parent / "backups" / ("before-public-monitor-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".db")
        backup.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(backup)) as dest:
            con.backup(dest)
            if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")
    os.environ["DATABASE_URL"] = os.environ["SENTINEL_DATABASE_URL"] = f"sqlite+aiosqlite:///{source}"
    os.environ["PROCESS_ROLE"] = os.environ["SENTINEL_PROCESS_ROLE"] = "api"
    os.environ["SEED_DEMO_DATA"] = os.environ["SENTINEL_SEED_DEMO_DATA"] = "false"
    async def apply():
        from backend.app.core.database import AsyncSessionLocal, init_db
        await init_db()
        async with AsyncSessionLocal() as db:
            return await configure(db, args.schedule_id, queue_first_run=args.queue_first_run, mode=args.mode)
    result = asyncio.run(apply())
    print(json.dumps({**result, "applied": True, "backup": str(backup), "backup_integrity": "ok"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
