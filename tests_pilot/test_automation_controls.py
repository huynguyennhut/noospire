"""Synthetic automation acceptance: actual queue/runner, no customer network/data."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.monitor_scheduler import MonitorScheduler
from backend.app.models.operations import SchedulerHeartbeat
from tests_pilot.test_m3_sbom_flow import API, import_snapshot, owner_session, upload
from tests_pilot.conftest import make_asset
from tests_pilot.test_m4_schedule_capacity import _schedule, _rebase, _slots, _drain


async def test_scheduler_heartbeat_distinguishes_missing_fresh_stale_and_failed_loop(client, owner, monkeypatch):
    await owner_session(client)
    async def overview():
        r = await client.get(f'{API}/operations/overview')
        assert r.status_code == 200, r.text
        return r.json()['scheduler']
    assert await overview() == {'online': False, 'last_tick_at': None, 'age_seconds': None}
    scheduler = MonitorScheduler()
    await scheduler.tick()
    assert (await overview())['online'] is True
    async with AsyncSessionLocal() as db:
        await db.execute(update(SchedulerHeartbeat).values(last_tick_at=datetime.now(timezone.utc)-timedelta(seconds=90)))
        await db.commit()
    assert (await overview())['online'] is False
    async def broken():
        raise RuntimeError('synthetic scheduler DB failure')
    monkeypatch.setattr('backend.app.core.monitor_scheduler.reap_and_dead_letter', broken)
    with pytest.raises(RuntimeError):
        await scheduler.tick()
    assert (await overview())['online'] is False


async def test_two_hour_automation_morning_evening_overnight_restart_and_pause(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    aid = await make_asset('synthetic-overnight')
    await upload(client, h, aid)
    schedule = await _schedule(client, h, name='SYNTHETIC 24-hour acceptance',
        selection={'kind': 'assets', 'asset_ids': [str(aid)]}, engines=['sbom'], interval_minutes=120)
    start = (datetime.now(timezone.utc)-timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
    await _rebase(schedule['id'], start)
    for i in range(12):
        # New scheduler instance at every slot proves persisted state survives restart.
        now = start + timedelta(hours=2*i, minutes=1)
        report = await MonitorScheduler().tick(now=now)
        assert report['launched'] == 1
        assert await _drain() == ['succeeded']
        repeat = await MonitorScheduler().tick(now=now+timedelta(minutes=1))
        assert repeat['launched'] == 0
    slots = await _slots(schedule['id'])
    assert len(slots) == 12 and all(s.status == 'completed' for s in slots)
    ict_hours = {(s.slot_at+timedelta(hours=7)).hour for s in slots}
    assert {1, 7, 19, 23}.issubset(ict_hours)
    updated = await client.patch(f"{API}/monitor-schedules/{schedule['id']}", headers=h,
        json={'is_active': False, 'expected_revision': schedule['revision']})
    assert updated.status_code == 200, updated.text
    assert (await MonitorScheduler().tick(now=start+timedelta(hours=24, minutes=1)))['launched'] == 0
    assert len(await _slots(schedule['id'])) == 12


async def test_scan_launch_needs_no_preview_or_per_run_approval_and_retries_are_idempotent(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    aid = await make_asset('synthetic-one-click')
    await upload(client, h, aid)
    body = {'selection': {'kind': 'assets', 'asset_ids': [str(aid)]}, 'engines': ['sbom'], 'profile': 'light'}
    headers = {**h, 'Idempotency-Key': 'synthetic-one-click-intent'}
    first = await client.post(f'{API}/runs', headers=headers, json=body)
    assert first.status_code == 202, first.text
    assert len(first.json()['executions']) == 1
    retry = await client.post(f'{API}/runs', headers=headers, json=body)
    assert retry.status_code == 200 and retry.json()['batch_id'] == first.json()['batch_id']
    assert await _drain() == ['succeeded']
    completed = await client.get(f"{API}/runs/{first.json()['batch_id']}")
    assert completed.json()['finished'] is True
    assert completed.json()['by_status'] == {'succeeded': 1}

async def test_two_schedulers_finalize_public_slot_with_one_frozen_report(client,owner,monkeypatch):
    import asyncio
    import uuid
    from sqlalchemy import select
    from backend.app.engines import native_nuclei
    from backend.app.models.lifecycle import ReportSnapshot
    from tests_pilot.test_web_surface import surface_asset, no_native
    from tests_pilot.test_public_web_monitor import fake_transport
    h=await owner_session(client);aid=await surface_asset()
    fake_transport(monkeypatch,b'HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 0\r\n\r\n')
    monkeypatch.setattr(native_nuclei,'analyze',no_native)
    schedule=await _schedule(client,h,name='SYNTHETIC automatic public report',
        selection={'kind':'assets','asset_ids':[str(aid)]},engines=['public_web'],interval_minutes=120)
    start=(datetime.now(timezone.utc)-timedelta(days=2)).replace(hour=0,minute=0,second=0,microsecond=0)
    await _rebase(schedule['id'],start)
    now=start+timedelta(minutes=1)
    await MonitorScheduler().tick(now=now)
    assert await _drain()==['succeeded']
    finalized=await asyncio.gather(*(MonitorScheduler().tick(now=now+timedelta(minutes=1)) for _ in range(2)))
    assert sum(r['finalized'] for r in finalized)==1
    slots=await _slots(schedule['id']);assert len(slots)==1
    rid=slots[0].result_summary['report_id']
    async with AsyncSessionLocal() as db:
        reports=(await db.execute(select(ReportSnapshot).where(ReportSnapshot.batch_id==slots[0].batch_id))).scalars().all()
        assert len(reports)==1 and str(reports[0].id)==rid
    downloaded=await client.get(API+'/report-snapshots/'+rid+'/download',params={'format':'json'})
    assert downloaded.status_code==200,downloaded.text
    assert downloaded.json()['template_version']=='noospire-pilot-report/1.3'
    listing=(await client.get(API+'/monitor-schedules')).json()['items']
    assert next(s for s in listing if s['id']==schedule['id'])['latest_result']['report_id']==rid
