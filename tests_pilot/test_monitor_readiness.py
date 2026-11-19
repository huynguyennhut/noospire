"""Inventory readiness, approvals and global pause on disposable pilot data."""
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.asset import Asset
from backend.app.models.base import AdminAuditLog
from backend.app.models.operations import CapacitySettings, MonitorSchedule, ScheduleSlot
from backend.app.models.proof import AssetOwnershipProof
from backend.app.models.scope import AssetAssessmentScope
from tests_pilot.conftest import USER_PASSWORD, csrf_headers, login, make_asset, make_user, new_client
from tests_pilot.test_inventory_reconciliation import fixture_asset
from tests_pilot.test_m3_sbom_flow import owner_session

API = "/api/v1"


async def ready_asset(name="approved-monitor"):
    aid = await make_asset(name)
    async with AsyncSessionLocal() as db:
        db.add(AssetOwnershipProof(asset_id=aid, method="ADMIN_OVERRIDE", status="VERIFIED",
                                   challenge_token="synthetic-proof", verified_at=datetime.now(timezone.utc),
                                   proof_data={"source": "synthetic owner attestation"}))
        db.add(AssetAssessmentScope(asset_id=aid, exact_origin=f"https://{name}.pilot-test.invalid",
                                   allowed_path_patterns=["/"], permitted_checks=["public_web"]))
        await db.commit()
    return aid


async def test_eligible_filter_applies_before_pagination_and_honors_grants(client, owner):
    seed = await fixture_asset(seed=True)
    fixture = await fixture_asset()
    approved = await ready_asset()
    h = await owner_session(client)
    response = await client.get(f"{API}/assets", params={"size": 1, "assessment_eligible": "true"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["id"] == str(approved)
    for aid, reason in [(seed, "SEEDED_OWNERSHIP_NOT_VERIFIED"), (fixture, "SYNTHETIC_INVENTORY")]:
        row = (await client.get(f"{API}/assets/{aid}")).json()
        assert row["assessment_eligible"] is False
        assert row["assessment_block_reason"] == reason
        assert row["inventory_classification"] == "SEEDED_OR_TEST"
    uid = await make_user("VIEWER", "readiness-viewer")
    assert (await client.post(f"{API}/auth/users/{uid}/grants", headers=h,
                             json={"asset_id": str(seed), "permissions": "READ"})).status_code == 201
    async with new_client() as outsider:
        await login(outsider, "readiness-viewer", USER_PASSWORD)
        assert (await outsider.get(f"{API}/assets?assessment_eligible=true")).json()["total"] == 0


async def test_eligibility_expires_and_obeys_target_stop(client, owner):
    aid = await ready_asset()
    await owner_session(client)
    async with AsyncSessionLocal() as db:
        scope = (await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == aid))).scalar_one()
        scope.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    assert (await client.get(f"{API}/assets/{aid}")).json()["assessment_block_reason"] == "SCOPE_EXPIRED"
    async with AsyncSessionLocal() as db:
        scope = (await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == aid))).scalar_one()
        scope.emergency_stop_active = True
        await db.commit()
    assert (await client.get(f"{API}/assets/{aid}")).json()["assessment_block_reason"] == "TARGET_EMERGENCY_STOP"


async def test_public_approval_is_owner_only_audited_and_failed_change_rolls_back(client, owner):
    aid = await ready_asset()
    h = await owner_session(client)
    url = "https://approved-monitor.pilot-test.invalid/"
    accepted = await client.put(f"{API}/assets/{aid}/public-web", headers=h, json={"url": url})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["method"] == "HEAD"
    bad = await client.put(f"{API}/assets/{aid}/public-web", headers=h, json={"url": url + "not-approved"})
    assert bad.status_code == 409
    async with AsyncSessionLocal() as db:
        assert (await db.get(Asset, aid)).assessment_policy["public_web"]["revision"] == accepted.json()["revision"]
        assert len((await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "PUBLIC_WEB_APPROVAL"))).scalars().all()) == 1
    await make_user("ADMIN", "approval-outsider")
    async with new_client() as outsider:
        await login(outsider, "approval-outsider", USER_PASSWORD)
        assert (await outsider.put(f"{API}/assets/{aid}/public-web", headers=csrf_headers(outsider),
                                  json={"url": url})).status_code == 403


async def test_global_stop_persists_is_owner_only_and_pauses_schedule(client, owner):
    from backend.app.core.monitor_scheduler import MonitorScheduler, floor_slot
    h = await owner_session(client)
    response = await client.put(f"{API}/operations/emergency-stop", headers=h, json={"active": True})
    assert response.status_code == 200 and response.json()["emergency_stop_active"] is True
    now = floor_slot(datetime.now(timezone.utc), 120)
    sid = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(MonitorSchedule(id=sid, name="Synthetic paused schedule", selection={"kind": "all"},
                               engines=["public_web"], interval_minutes=120, start_after=now,
                               created_by=str(owner.id)))
        await db.commit()
    result = await MonitorScheduler().tick(now)
    assert result["launched"] == 0
    async with AsyncSessionLocal() as db:
        assert (await db.get(CapacitySettings, 1)).emergency_stop_active
        assert (await db.get(MonitorSchedule, sid)).overdue_reason.startswith("Global emergency stop")
        assert (await db.execute(select(ScheduleSlot))).scalars().all() == []
    await make_user("ADMIN", "stop-outsider")
    async with new_client() as outsider:
        await login(outsider, "stop-outsider", USER_PASSWORD)
        assert (await outsider.put(f"{API}/operations/emergency-stop", headers=csrf_headers(outsider),
                                  json={"active": False})).status_code == 403
    assert (await client.put(f"{API}/operations/emergency-stop", headers=h, json={"active": False})).status_code == 200


async def test_existing_capacity_schema_migrates_without_losing_limits(tmp_path, monkeypatch):
    from backend.app.core import database
    temp_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old-schema.db'}")
    async with temp_engine.begin() as conn:
        await conn.execute(text("CREATE TABLE capacity_settings (id INTEGER PRIMARY KEY, max_running_executions INTEGER NOT NULL, per_host_hourly_quota INTEGER NOT NULL, per_host_egress_bytes_hourly INTEGER NOT NULL, updated_by VARCHAR(64), updated_at DATETIME NOT NULL)"))
        await conn.execute(text("INSERT INTO capacity_settings VALUES (1, 1, 7, 500000, 'synthetic-owner', '2026-01-01')"))
    monkeypatch.setattr(database, "engine", temp_engine)
    monkeypatch.setattr(database, "AsyncSessionLocal", async_sessionmaker(temp_engine, expire_on_commit=False))
    try:
        await database.init_db()
        await database.init_db()
        async with temp_engine.connect() as conn:
            row = (await conn.execute(text("SELECT max_running_executions, per_host_hourly_quota, emergency_stop_active FROM capacity_settings"))).one()
            assert tuple(row) == (1, 7, 0)
    finally:
        await temp_engine.dispose()


async def test_operator_configuration_is_exact_root_idempotent_and_preserves_other_inventory(client, owner):
    from scripts.configure_empire_monitor import configure
    from backend.app.models.defensive import ExecutionRecord
    from backend.app.core.inventory_reconciliation import PRIMARY_TARGET
    aid = await ready_asset()
    seeded = await fixture_asset(seed=True)
    sid = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        root = await db.get(Asset, aid)
        root.target_locator = PRIMARY_TARGET
        db.add(MonitorSchedule(id=sid, name="Synthetic previous monitor", selection={"kind": "all"},
                               engines=["tls_health"], interval_minutes=60, created_by=str(owner.id)))
        await db.commit()
    async with AsyncSessionLocal() as db:
        first = await configure(db, sid, queue_first_run=True)
    async with AsyncSessionLocal() as db:
        second = await configure(db, sid, queue_first_run=True)
        assert second["first_batch_id"] == first["first_batch_id"]
        assert second["changed"] is False
        schedule = await db.get(MonitorSchedule, sid)
        assert schedule.interval_minutes == 120
        assert schedule.selection == {"kind": "assets", "asset_ids": [str(aid)]}
        assert schedule.engines == ["public_web"]
        assert (await db.get(Asset, seeded)).assessment_policy == {}
        assert len((await db.execute(select(ExecutionRecord))).scalars().all()) == 1
        grants = (await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == aid))).scalars().all()
        assert len(grants) == 2  # original scope preserved; dedicated exact-root grant added
        dedicated = next(s for s in grants if s.created_by == "noosforge:public-monitor")
        assert dedicated.allowed_path_patterns == ["/"] and dedicated.max_requests_per_run == 1

async def test_surface_configuration_upgrades_only_dedicated_grant_and_keeps_revision_on_retry(client,owner):
    from scripts.configure_empire_monitor import configure
    from backend.app.core.inventory_reconciliation import PRIMARY_TARGET
    aid=await ready_asset();seeded=await fixture_asset(seed=True);sid=uuid.uuid4()
    async with AsyncSessionLocal() as db:
        (await db.get(Asset,aid)).target_locator=PRIMARY_TARGET
        db.add(MonitorSchedule(id=sid,name='SYNTHETIC surface upgrade',selection={'kind':'all'},
                              engines=['tls_health'],interval_minutes=60,created_by=str(owner.id)))
        await db.commit()
    async with AsyncSessionLocal() as db:
        await configure(db,sid)
        original=next(s for s in (await db.execute(select(AssetAssessmentScope).where(
            AssetAssessmentScope.asset_id==aid))).scalars() if s.created_by!='noosforge:public-monitor')
        original_id=original.id;original_paths=list(original.allowed_path_patterns)
    async with AsyncSessionLocal() as db:
        first=await configure(db,sid,mode='surface')
        revision=(await db.get(Asset,aid)).assessment_policy['public_web']['revision']
    async with AsyncSessionLocal() as db:
        second=await configure(db,sid,mode='surface')
        root=await db.get(Asset,aid)
        assert root.assessment_policy['public_web']['revision']==revision
        grant=(await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id==aid,
            AssetAssessmentScope.created_by=='noosforge:public-monitor'))).scalar_one()
        assert grant.allowed_path_patterns==['/*'] and grant.max_requests_per_run==12 and grant.byte_budget==1_000_000
        assert (await db.get(AssetAssessmentScope,original_id)).allowed_path_patterns==original_paths
        assert (await db.get(Asset,seeded)).assessment_policy=={}
        assert first['mode']==second['mode']=='surface'
