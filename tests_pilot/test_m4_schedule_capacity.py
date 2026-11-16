"""Milestone 4 · one planner for manual/asset/schedule, atomic slot claims, coalescing with a
single catch-up, restart recovery, capacity limits, metrics, cursor events and SSE.

Real API over ASGI, real queue claim and defensive runner in-process, disposable DB.
Synthetic labelled data only: assets `*.pilot-test.invalid`, advisories PILOT-TEST-*.
No network I/O: tls_health items are only planned here, never executed.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update

from backend.app.api import operations as ops_api
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.dispatcher import AsyncWorkerDispatcher
from backend.app.core.monitor_scheduler import MonitorScheduler, floor_slot, reap_and_dead_letter
from backend.app.core.planner import Selection, build_plan
from backend.app.core.queue import IDBDurableQueue
from backend.app.models.defensive import ExecutionRecord
from backend.app.models.operations import CapacitySettings, MonitorSchedule, ScheduleSlot
from backend.app.models.scan import Scan, ScanBatch
from tests_pilot.conftest import USER_PASSWORD, csrf_headers, login, make_asset, make_user, new_client
from tests_pilot.test_m3_sbom_flow import API, WORKER, import_snapshot, owner_session, upload, work_once

HOUR = timedelta(hours=1)


class _Owner:
    asset_ids = None

    def require(self, *a):
        return None

    def ids_with(self, *a):
        return None


async def _estate(client, h):
    """A: sbom ready · B: approved health endpoint · C: nothing configured."""
    await import_snapshot(client, h)
    a = await make_asset("svc-a")
    b = await make_asset("svc-b")
    c = await make_asset("svc-c")
    await upload(client, h, a)
    r = await client.put(f"{API}/assets/{b}/health-check", headers=h,
                         json={"url": "https://svc-b.pilot-test.invalid/health"})
    assert r.status_code == 200, r.text
    return a, b, c


def _decisions(plan: dict) -> dict:
    return {(i["asset_name"], i["engine"]): (i["decision"], i["reason_code"]) for i in plan["items"]}


async def _schedule(client, h, **kw) -> dict:
    body = {"name": "pilot-test hourly", "selection": {"kind": "all"}, "engines": ["sbom", "tls_health"],
            "profile": "light", "interval_minutes": 60, "max_workers": 2, **kw}
    r = await client.post(f"{API}/monitor-schedules", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def _rebase(schedule_id: str, start: datetime) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(update(MonitorSchedule).where(MonitorSchedule.id == uuid.UUID(schedule_id))
                         .values(start_after=start))
        await db.commit()


async def _slots(schedule_id: str) -> list:
    async with AsyncSessionLocal() as db:
        return list((await db.execute(select(ScheduleSlot).where(ScheduleSlot.schedule_id == uuid.UUID(schedule_id))
                                      .order_by(ScheduleSlot.slot_at))).scalars().all())


async def _drain() -> list:
    out = []
    while (st := await work_once()) is not None:
        out.append(st)
    return out


# --------------------------------------------------------------------------- planner

async def test_same_planner_for_whole_system_selection_and_schedule(client, owner):
    h = await owner_session(client)
    a, b, c = await _estate(client, h)

    whole = (await client.post(f"{API}/plans/preview", headers=h, json={"selection": {"kind": "all"},
                                                                         "engines": ["sbom", "tls_health"]})).json()
    assert whole["summary"]["assets_in_scope"] == 3 and whole["summary"]["pairs"] == 6
    d = _decisions(whole)
    assert d[("svc-a", "sbom")] == ("queue", None) and d[("svc-b", "tls_health")] == ("queue", None)
    assert d[("svc-a", "tls_health")] == ("skip", "NO_APPROVED_ENDPOINT")
    assert d[("svc-c", "sbom")] == ("skip", "NO_ARTIFACT")
    assert whole["summary"]["queue"] == 2 and whole["summary"]["skip"] == 4
    # Preview writes nothing.
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(ExecutionRecord))).scalar() == 0

    one = (await client.post(f"{API}/plans/preview", headers=h,
                             json={"selection": {"kind": "assets", "asset_ids": [str(a)]},
                                   "engines": ["sbom", "tls_health"]})).json()
    assert _decisions(one) == {k: v for k, v in d.items() if k[0] == "svc-a"}

    # The schedule's slot uses the same planner and reaches the same decisions.
    sched = await _schedule(client, h)
    t0 = floor_slot(datetime.now(timezone.utc), 60) - 5 * HOUR
    await _rebase(sched["id"], t0)
    rep = await MonitorScheduler().tick(now=t0 + timedelta(minutes=1))
    assert rep["launched"] == 1
    slot = (await _slots(sched["id"]))[0]
    assert slot.plan_summary["queue"] == whole["summary"]["queue"]
    assert slot.plan_summary["reasons"] == whole["summary"]["reasons"]

    # Manual run while the scheduled run is still queued: the planner skips duplicates.
    r = await client.post(f"{API}/runs", headers={**h, "Idempotency-Key": "pilot-run-1"},
                          json={"selection": {"kind": "all"}})
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["plan"]["summary"]["queue"] == 0
    assert run["plan"]["summary"]["reasons"]["ALREADY_ACTIVE"] == 2
    assert run["batch_id"] and run["accepted_at"] and run["tracker"].endswith(run["batch_id"])
    assert run["correlation_id"]


async def test_manual_run_idempotency_and_scope(client, owner):
    h = await owner_session(client)
    a, b, c = await _estate(client, h)
    body = {"selection": {"kind": "assets", "asset_ids": [str(a)]}, "engines": ["sbom"]}
    r1 = await client.post(f"{API}/runs", headers={**h, "Idempotency-Key": "k1"}, json=body)
    assert r1.status_code == 202 and r1.json()["by_status"] == {"queued": 1}
    r2 = await client.post(f"{API}/runs", headers={**h, "Idempotency-Key": "k1"}, json=body)
    assert r2.status_code == 200 and r2.json()["batch_id"] == r1.json()["batch_id"] and r2.json()["replayed"]
    r3 = await client.post(f"{API}/runs", headers={**h, "Idempotency-Key": "k1"},
                           json={**body, "profile": "slow"})
    assert r3.status_code == 409

    dev_id = await make_user("DEVELOPER", "dev-m4")
    g = await client.post(f"{API}/auth/users/{dev_id}/grants", headers=h,
                          json={"asset_id": str(b), "permissions": "READ"})
    assert g.status_code == 201
    async with new_client() as dev:
        await login(dev, "dev-m4", USER_PASSWORD)
        dh = csrf_headers(dev)
        # READ-only grant: 'all' resolves to nothing runnable; a named asset is 403; ungranted is 404.
        whole = (await dev.post(f"{API}/plans/preview", headers=dh, json={"selection": {"kind": "all"}})).json()
        assert whole["summary"]["pairs"] == 0
        r = await dev.post(f"{API}/runs", headers=dh, json={"selection": {"kind": "assets", "asset_ids": [str(b)]}})
        assert r.status_code == 403
        r = await dev.post(f"{API}/runs", headers=dh, json={"selection": {"kind": "assets", "asset_ids": [str(a)]}})
        assert r.status_code == 404
        # Same key as the owner's: keys are per user, so no leak of the owner's run.
        r = await dev.post(f"{API}/runs", headers={**dh, "Idempotency-Key": "k1"}, json=body)
        assert r.status_code == 404
        # Another user's run is invisible.
        assert (await dev.get(f"{API}/runs/{r1.json()['batch_id']}")).status_code == 404


async def test_host_quota_spacing_and_window_overflow(client, owner):
    h = await owner_session(client)
    r = await client.put(f"{API}/operations/capacity", headers=h,
                         json={"max_running_executions": 4, "per_host_hourly_quota": 2})
    assert r.status_code == 200
    ids = []
    for n in range(3):
        aid = await make_asset(f"svc-q{n}")
        ids.append(aid)
        await client.put(f"{API}/assets/{aid}/health-check", headers=h,
                         json={"url": f"https://shared-host.pilot-test.invalid/health/{n}"})
    run = (await client.post(f"{API}/runs", headers=h, json={"engines": ["tls_health"]})).json()
    s = run["plan"]["summary"]
    assert s["queue"] == 2 and s["defer"] == 1 and s["reasons"] == {"HOST_QUOTA": 1}
    deferred = [i for i in run["plan"]["items"] if i["decision"] == "defer"][0]
    assert deferred["available_at"] and "quota of 2" in deferred["reason"]
    async with AsyncSessionLocal() as db:
        sc = (await db.execute(select(Scan).join(ExecutionRecord, ExecutionRecord.scan_id == Scan.id)
                               .where(ExecutionRecord.plan_note.like("HOST_QUOTA%")))).scalars().one()
        assert sc.available_at is not None and sc.available_at > datetime.now(timezone.utc) + timedelta(minutes=50)

    # 'slow' profile: one slot, requests to the same host spaced apart.
    async with AsyncSessionLocal() as db:
        await db.execute(update(ExecutionRecord).values(status="cancelled"))
        await db.commit()
        plan = await build_plan(db, selection=Selection(), engines=["tls_health"], profile="slow",
                                trigger="preview", scope=_Owner())
        assert plan.slots == 1
        q = [i for i in plan.items if i.decision == "queue"]
        assert [i.reason_code for i in q] == [None, "HOST_SPACING"]
        gap = datetime.fromisoformat(q[1].available_at) - datetime.fromisoformat(plan.planned_at)
        assert gap == timedelta(seconds=20)

        # Window budget: 3 items x 3 s (default estimate) in a 7 s window with 1 slot -> 2 fit, 1 long lane.
        await db.execute(update(ExecutionRecord).values(status="cancelled"))
        await db.execute(update(MonitorSchedule).values(is_active=False))
        await db.commit()
        cs = await db.get(CapacitySettings, 1)
        cs.per_host_hourly_quota = 100
        await db.flush()
        plan = await build_plan(db, selection=Selection(), engines=["tls_health"], profile="light",
                                trigger="preview", scope=_Owner(), window_seconds=7, max_workers=1)
        summ = plan.summary()
        assert summ["queue"] == 2 and summ["defer"] == 1 and summ["reasons"] == {"WINDOW_OVERFLOW": 1}
        long = [i for i in plan.items if i.decision == "defer"][0]
        assert long.lane == "long" and "moved to the long lane" in long.reason
        await db.rollback()


# --------------------------------------------------------------------------- schedule slots

async def test_two_schedulers_claim_a_slot_exactly_once(client, owner):
    h = await owner_session(client)
    await _estate(client, h)
    sched = await _schedule(client, h)
    t0 = floor_slot(datetime.now(timezone.utc), 60) - 3 * HOUR
    await _rebase(sched["id"], t0)
    now = t0 + timedelta(minutes=2)
    r1, r2 = await asyncio.gather(MonitorScheduler().tick(now=now), MonitorScheduler().tick(now=now))
    assert r1["launched"] + r2["launched"] == 1
    slots = await _slots(sched["id"])
    assert len(slots) == 1 and slots[0].status == "launched"
    async with AsyncSessionLocal() as db:
        n = (await db.execute(select(func.count()).select_from(ScanBatch))).scalar()
        assert n == 1
    # A later tick in the same slot launches nothing.
    rep = await MonitorScheduler().tick(now=now + timedelta(minutes=20))
    assert rep["launched"] == 0 and len(await _slots(sched["id"])) == 1


async def test_overrun_coalesces_into_one_catchup(client, owner):
    h = await owner_session(client)
    await _estate(client, h)
    sched = await _schedule(client, h, engines=["sbom"])
    t0 = floor_slot(datetime.now(timezone.utc), 60) - 6 * HOUR
    await _rebase(sched["id"], t0)
    sch = MonitorScheduler()
    assert (await sch.tick(now=t0 + timedelta(minutes=1)))["launched"] == 1
    # No worker: the run is still queued at the next two slots.
    assert (await sch.tick(now=t0 + HOUR + timedelta(minutes=1)))["coalesced"] == 1
    assert (await sch.tick(now=t0 + 2 * HOUR + timedelta(minutes=1)))["coalesced"] == 1
    lst = (await client.get(f"{API}/monitor-schedules")).json()
    s = lst["items"][0]
    assert s["running"] and s["pending_catchup"] and s["missed_slots"] == 2 and s["backlog"] == 1
    assert s["overdue_reason"] and s["estimated_drain_at"]
    assert lst["server_time"] and s["next_run_at"]

    assert await _drain() == ["succeeded"]
    rep = await sch.tick(now=t0 + 2 * HOUR + timedelta(minutes=5))
    assert rep["finalized"] == 1 and rep["catchups"] == 1
    slots = await _slots(sched["id"])
    assert [(x.kind, x.status) for x in slots] == [("scheduled", "completed"), ("scheduled", "coalesced"),
                                                   ("catchup", "launched")]
    assert slots[2].coalesced_slots == 2
    # Exactly one catch-up, never one per missed slot.
    rep = await sch.tick(now=t0 + 2 * HOUR + timedelta(minutes=6))
    assert rep["catchups"] == 0 and rep["launched"] == 0
    assert await _drain() == ["succeeded"]
    await sch.tick(now=t0 + 2 * HOUR + timedelta(minutes=7))
    s = (await client.get(f"{API}/monitor-schedules")).json()["items"][0]
    assert s["latest_result"]["status"] == "completed" and s["last_full_success_at"]
    assert not s["pending_catchup"] and s["missed_slots"] == 0 and not s["running"]


async def test_restart_recovery_launches_newest_slot_once(client, owner):
    h = await owner_session(client)
    await _estate(client, h)
    sched = await _schedule(client, h, engines=["sbom"])
    t0 = floor_slot(datetime.now(timezone.utc), 60) - 8 * HOUR
    await _rebase(sched["id"], t0)
    await MonitorScheduler().tick(now=t0 + timedelta(minutes=1))
    await _drain()
    # Scheduler process down for ~3 hours, then a fresh process starts.
    rep = await MonitorScheduler().tick(now=t0 + 3 * HOUR + timedelta(minutes=10))
    assert rep["launched"] == 1 and rep["finalized"] == 1
    slots = await _slots(sched["id"])
    assert len(slots) == 2 and slots[1].slot_at.replace(tzinfo=timezone.utc) == t0 + 3 * HOUR
    assert slots[1].missed_before == 2 and slots[1].coalesced_slots == 2


async def test_partial_result_is_reported_separately_from_full_success(client, owner):
    h = await owner_session(client)
    a, b, c = await _estate(client, h)
    await upload(client, h, c, raw=b"{not json")  # svc-c sbom will fail to parse
    sched = await _schedule(client, h, engines=["sbom"])
    t0 = floor_slot(datetime.now(timezone.utc), 60) - 4 * HOUR
    await _rebase(sched["id"], t0)
    await MonitorScheduler().tick(now=t0 + timedelta(minutes=1))
    assert sorted(await _drain()) == ["failed", "succeeded"]
    await MonitorScheduler().tick(now=t0 + timedelta(minutes=5))
    s = (await client.get(f"{API}/monitor-schedules")).json()["items"][0]
    assert s["latest_result"]["status"] == "partial" and s["last_full_success_at"] is None
    ov = (await client.get(f"{API}/operations/overview")).json()
    assert ov["errors_24h"]["parse_errors"] == 1


async def test_schedule_admin_is_owner_only_and_validated(client, owner):
    h = await owner_session(client)
    r = await client.post(f"{API}/monitor-schedules", headers=h, json={"name": "x", "interval_minutes": 50})
    assert r.status_code == 422
    s = await _schedule(client, h)
    nxt = datetime.fromisoformat(s["next_run_at"])
    assert nxt.minute == 0 and nxt.second == 0 and nxt > datetime.now(timezone.utc)
    r = await client.patch(f"{API}/monitor-schedules/{s['id']}", headers=h,
                           json={"profile": "slow", "expected_revision": s["revision"]})
    assert r.status_code == 200 and r.json()["revision"] == s["revision"] + 1
    r = await client.patch(f"{API}/monitor-schedules/{s['id']}", headers=h,
                           json={"max_workers": 1, "expected_revision": s["revision"]})
    assert r.status_code == 409
    await make_user("OPERATOR", "op-m4")
    async with new_client() as op:
        await login(op, "op-m4", USER_PASSWORD)
        oh = csrf_headers(op)
        assert (await op.get(f"{API}/monitor-schedules")).status_code == 403
        assert (await op.post(f"{API}/monitor-schedules", headers=oh, json={"name": "x"})).status_code == 403
        assert (await op.put(f"{API}/operations/capacity", headers=oh,
                             json={"max_running_executions": 9, "per_host_hourly_quota": 9})).status_code == 403
        ov = (await op.get(f"{API}/operations/overview")).json()
        assert ov["schedules_visible"] is False and ov["schedules"] == []
    gone = await client.get(f"{API}/schedules")
    assert gone.status_code == 410 and gone.json()["replacement"] == "/api/v1/monitor-schedules"


# --------------------------------------------------------------------------- capacity

async def test_estate_cap_is_enforced_in_the_claim(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    for n in range(2):
        aid = await make_asset(f"svc-cap{n}")
        await upload(client, h, aid)
    await client.put(f"{API}/operations/capacity", headers=h,
                     json={"max_running_executions": 1, "per_host_hourly_quota": 12})
    await client.post(f"{API}/runs", headers=h, json={"engines": ["sbom"]})
    async with AsyncSessionLocal() as db:
        first = await IDBDurableQueue.claim_next_job(db, "w-a", max_running=1)
        assert first is not None
    async with AsyncSessionLocal() as db:
        assert await IDBDurableQueue.claim_next_job(db, "w-b", max_running=1) is None
    from backend.app.engines import runner
    assert await runner.run_execution(first.id, first.fencing_token, "w-a", None) == "succeeded"
    async with AsyncSessionLocal() as db:
        assert await IDBDurableQueue.claim_next_job(db, "w-b", max_running=1) is not None


async def test_worker_never_claims_beyond_its_slots(client, owner, monkeypatch):
    monkeypatch.setattr(settings, "PROCESS_ROLE", "worker")
    monkeypatch.setattr(settings, "THROTTLE_MEM_PCT", 100.0)
    monkeypatch.setattr(settings, "THROTTLE_CPU_PCT", 100.0)
    h = await owner_session(client)
    await import_snapshot(client, h)
    aid = await make_asset("svc-slot")
    await upload(client, h, aid)
    await client.post(f"{API}/runs", headers=h, json={"engines": ["sbom"]})
    d = AsyncWorkerDispatcher(max_concurrent=1)
    d._inflight = 1  # its only slot is busy
    d.start()
    await asyncio.sleep(1.5)
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(Scan.status))).scalars().all() == ["QUEUED"]
    d._inflight = 0  # slot frees up -> it claims and runs
    for _ in range(40):
        await asyncio.sleep(0.25)
        async with AsyncSessionLocal() as db:
            if (await db.execute(select(ExecutionRecord.status))).scalars().all() == ["succeeded"]:
                break
    await d.stop()
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(ExecutionRecord.status))).scalars().all() == ["succeeded"]


async def test_metrics_overview_and_dead_letters(client, owner):
    h = await owner_session(client)
    a, b, c = await _estate(client, h)
    run = (await client.post(f"{API}/runs", headers=h, json={"engines": ["sbom"]})).json()
    assert await _drain() == ["succeeded"]
    m = (await client.get(f"{API}/operations/metrics")).json()
    sb = m["engines"]["sbom"]
    assert sb["attempts"] == 1 and sb["by_status"] == {"succeeded": 1}
    assert sb["duration_p50_s"] is not None and sb["queue_delay_p50_s"] is not None
    assert sb["input_bytes"] > 0 and sb["output_bytes"] > 0 and sb["cpu_ms_avg"] is not None
    assert sb["theoretical_hourly_capacity"] > 0
    ov = (await client.get(f"{API}/operations/overview")).json()
    assert ov["engines"]["sbom"]["last_success_at"] and ov["engines"]["sbom"]["stale"] is False
    assert ov["engines"]["tls_health"]["stale"] is True and ov["engines"]["tls_health"]["last_success_at"] is None
    assert ov["evidence"]["newest_observation_at"] and ov["feed"]["digest"]
    assert ov["display_timezone"] == "Asia/Ho_Chi_Minh" and ov["event_cursor"] > 0
    got = (await client.get(f"{API}/runs/{run['batch_id']}")).json()
    assert got["finished"] and got["by_status"] == {"succeeded": 1}

    # Dead letter: queue row exhausted its retries without a committed result.
    run2 = (await client.post(f"{API}/runs", headers=h, json={"engines": ["sbom"]})).json()
    eid = run2["executions"][0]["execution_id"]
    async with AsyncSessionLocal() as db:
        rec = await db.get(ExecutionRecord, uuid.UUID(eid))
        await db.execute(update(Scan).where(Scan.id == rec.scan_id).values(
            status="FAILED", error_message="Scan abandoned: worker lease expired and maximum retry budget exceeded."))
        await db.commit()
    assert await reap_and_dead_letter() == 1
    ex = (await client.get(f"{API}/executions/{eid}")).json()
    assert ex["status"] == "failed" and ex["error_class"] == "DEAD_LETTER"
    ov = (await client.get(f"{API}/operations/overview")).json()
    assert ov["errors_24h"]["dead_letters"] == 1


# --------------------------------------------------------------------------- events & SSE

def _frames(text: str) -> list:
    out = []
    for block in text.split("\n\n"):
        f = {}
        for line in block.splitlines():
            k, _, v = line.partition(": ")
            f[k] = v
        if f:
            out.append(f)
    return out


async def test_cursor_events_are_scoped_and_carry_correlation(client, owner):
    h = await owner_session(client)
    a, b, c = await _estate(client, h)
    await upload(client, h, b)
    run = (await client.post(f"{API}/runs", headers=h, json={"engines": ["sbom"]})).json()
    corr = run["correlation_id"]
    assert await _drain() == ["succeeded", "succeeded"]
    ev = (await client.get(f"{API}/events", params={"after": 0, "limit": 500})).json()
    types = [e["type"] for e in ev["items"]]
    assert "RUN_ACCEPTED" in types and types.count("EXECUTION_FINISHED") == 2
    mine = [e for e in ev["items"] if e["batch_id"] == run["batch_id"]]
    assert mine and all(e["correlation_id"] == corr for e in mine)
    ids = [e["id"] for e in ev["items"]]
    assert ids == sorted(ids) and ev["cursor"] == ids[-1]
    page = (await client.get(f"{API}/events", params={"after": ids[2], "limit": 2})).json()
    assert [e["id"] for e in page["items"]] == ids[3:5] and page["has_more"]

    dev_id = await make_user("DEVELOPER", "dev-ev")
    await client.post(f"{API}/auth/users/{dev_id}/grants", headers=h, json={"asset_id": str(a), "permissions": "READ"})
    async with new_client() as dev:
        await login(dev, "dev-ev", USER_PASSWORD)
        dev_ev = (await dev.get(f"{API}/events", params={"after": 0, "limit": 500})).json()["items"]
        assert dev_ev and {e["asset_id"] for e in dev_ev} == {str(a)}  # no B, no estate-level events


async def test_sse_replay_heartbeat_reset_and_viewer_disconnect(client, owner, monkeypatch):
    monkeypatch.setattr(ops_api, "HEARTBEAT_SECONDS", 0.4)
    monkeypatch.setattr(ops_api, "POLL_SECONDS", 0.1)
    h = await owner_session(client)
    a, b, c = await _estate(client, h)
    run = (await client.post(f"{API}/runs", headers=h, json={"engines": ["sbom"]})).json()
    all_ev = (await client.get(f"{API}/events", params={"after": 0, "limit": 500})).json()["items"]
    mid = all_ev[0]["id"]

    r = await client.get(f"{API}/events/stream", params={"max_seconds": 1.2}, headers={"Last-Event-ID": str(mid)})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-store"
    frames = _frames(r.text)
    assert frames[0] == {"retry": "3000"}
    assert frames[1]["event"] == "hello"
    got = [int(f["id"]) for f in frames if "id" in f]
    assert got == [e["id"] for e in all_ev if e["id"] > mid]  # exact replay after Last-Event-ID
    assert {f["event"] for f in frames if "id" in f} <= {"execution", "run", "schedule", "scan"}
    assert any(f.get("event") == "heartbeat" for f in frames)

    r = await client.get(f"{API}/events/stream", params={"max_seconds": 1}, headers={"Last-Event-ID": "999999"})
    assert _frames(r.text)[1]["event"] == "reset"

    # The viewer went away (stream closed) -> the job is untouched and still runs.
    ex = (await client.get(f"{API}/executions/{run['executions'][0]['execution_id']}")).json()
    assert ex["status"] == "queued"
    assert await _drain() == ["succeeded"]


async def test_sse_closes_when_session_is_revoked(client, owner, monkeypatch):
    monkeypatch.setattr(ops_api, "HEARTBEAT_SECONDS", 0.3)
    monkeypatch.setattr(ops_api, "POLL_SECONDS", 0.1)
    await make_user("VIEWER", "viewer-ev")
    async with new_client() as v1, new_client() as v2:
        await login(v1, "viewer-ev", USER_PASSWORD)
        await login(v2, "viewer-ev", USER_PASSWORD)

        async def logout_later():
            await asyncio.sleep(0.6)
            r = await v2.post(f"{API}/auth/logout", headers=csrf_headers(v2))
            assert r.status_code in (200, 204)

        stream, _ = await asyncio.gather(v1.get(f"{API}/events/stream", params={"max_seconds": 5}), logout_later())
        frames = _frames(stream.text)
        assert frames[-1]["event"] == "auth_revoked"


async def test_host_egress_budget_defers_network_engines(client, owner):
    from backend.app.models.operations import ExecutionMetric

    h = await owner_session(client)
    await client.put(f"{API}/operations/capacity", headers=h,
                     json={"max_running_executions": 4, "per_host_hourly_quota": 50,
                           "per_host_egress_bytes_hourly": 10_000})
    aid = await make_asset("svc-egress")
    await client.put(f"{API}/assets/{aid}/health-check", headers=h,
                     json={"url": "https://egress-host.pilot-test.invalid/health"})
    async with AsyncSessionLocal() as db:  # synthetic prior usage on that host in the last hour
        db.add(ExecutionMetric(execution_id=uuid.uuid4(), attempt_id=uuid.uuid4(), engine_id="tls_health",
                               target_host="egress-host.pilot-test.invalid", status="succeeded", attempt_no=1,
                               duration_ms=10, egress_bytes=12_000))
        await db.commit()
    plan = (await client.post(f"{API}/plans/preview", headers=h, json={"engines": ["tls_health"]})).json()
    assert plan["summary"]["reasons"] == {"EGRESS_BUDGET": 1} and plan["summary"]["defer"] == 1
    m = (await client.get(f"{API}/operations/metrics")).json()
    host = m["hosts_last_hour"]["egress-host.pilot-test.invalid"]
    assert host["egress_bytes"] == 12_000 and host["over_budget"] is True
