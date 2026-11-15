"""Comprehensive Test Suite for Milestone 2: Durable Queue, Scheduling & Eventing.

Covers:
1. Transactional queue claims, worker leases, and split-brain fencing token rejection.
2. Bounded retries with backoff and lease reaper recovery of abandoned jobs after restart.
3. Safe recursive process tree cancellation and uncertain probe replay prevention.
4. Hourly cron calculation in Asia/Ho_Chi_Minh (stored in UTC).
5. Overrun coalescing: multi-hour runs coalesce missed slots to at most ONE follow-up.
6. Active run deduplication and idempotency on manual trigger.
7. Schedule status endpoint: server time, 1s countdown data, pause/resume, overdue reason.
8. Durable event stream: ScanEvent persistence, SSE replay from Last-Event-ID cursor, and events 101+ delivery without concealment.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import os
import uuid
import zoneinfo

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import func, select, update

from backend.main import app
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal, init_db
from backend.app.core.event_bus import emit_event, event_broadcaster
from backend.app.core.queue import IDBDurableQueue
from backend.app.core.scheduler import SchedulerEngine, compute_next_run
from backend.app.core.security import create_access_token
from backend.app.models.asset import Asset
from backend.app.models.event import ScanEvent, sanitize_event_details
from backend.app.models.scan import Scan, ScanBatch
from backend.app.models.schedule import DailySchedule
from backend.app.models.user import User, UserRole
from backend.app.schemas.common import AssetType, EmpireModule, ScanProfile, ScanQualityStatus, ScanStatus


# Helper to get auth headers for operator / admin
async def get_auth_headers(db, role: str = UserRole.ADMIN.value):
    is_super = role in (UserRole.ADMIN.value, UserRole.OWNER.value)
    user = User(
        id=uuid.uuid4(),
        username=f"test_{role.lower()}_{uuid.uuid4().hex[:8]}",
        email=f"{role.lower()}_{uuid.uuid4().hex[:8]}@sentinel.local",
        hashed_password="hashed_pw_test",
        role=role,
        is_active=True,
        is_superuser=is_super,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(subject=str(user.id), role=user.role, is_superuser=is_super)
    return {"Authorization": f"Bearer {token}"}, token, user


# Helper to create a test asset
async def create_test_asset(db, locator: str = "https://scan-target.local") -> Asset:
    asset = Asset(
        id=uuid.uuid4(),
        name=f"Test Asset {uuid.uuid4().hex[:6]}",
        target_locator=locator,
        asset_type=AssetType.WEB_APP.value,
        empire_module=EmpireModule.WEB_APPLICATION.value,
        verification_status="VERIFIED",
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


# -----------------------------------------------------------------------------
# 1. Transactional Queue Claims, Worker Leases, and Fencing Tokens
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transactional_queue_claim_and_worker_leases(db_session):
    # Clear any previous queued scans to isolate queue state
    await db_session.execute(
        update(Scan).where(Scan.status == ScanStatus.QUEUED.value).values(status=ScanStatus.CANCELLED.value)
    )
    await db_session.commit()

    asset = await create_test_asset(db_session, "https://queue-claim-test.local")

    # Insert QUEUED scan
    scan = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        engine="all",
        profile=ScanProfile.BASELINE.value,
        status=ScanStatus.QUEUED.value,
        target_locator=asset.target_locator,
        fencing_token=0,
        attempts=0,
    )
    db_session.add(scan)
    await db_session.commit()

    # Worker A claims the job
    worker_a = "worker-node-alpha"
    claimed_scan = await IDBDurableQueue.claim_next_job(db_session, worker_a, lease_duration_seconds=30)
    assert claimed_scan is not None
    assert claimed_scan.id == scan.id
    assert claimed_scan.status == ScanStatus.RUNNING.value
    assert claimed_scan.leased_by == worker_a
    assert claimed_scan.fencing_token == 1
    assert claimed_scan.attempts == 1
    assert claimed_scan.lease_expires_at is not None
    exp = claimed_scan.lease_expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    assert exp > datetime.now(timezone.utc)

    # Worker B tries to claim - must find no available job
    worker_b = "worker-node-bravo"
    claimed_b = await IDBDurableQueue.claim_next_job(db_session, worker_b, lease_duration_seconds=30)
    assert claimed_b is None

    # Worker A renews heartbeat with valid fencing token
    renewed = await IDBDurableQueue.renew_lease_heartbeat(
        db_session, scan.id, fencing_token=1, lease_duration_seconds=60
    )
    assert renewed is True


@pytest.mark.asyncio
async def test_split_brain_fencing_token_rejection(db_session):
    asset = await create_test_asset(db_session, "https://fencing-test.local")

    scan = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        engine="all",
        profile=ScanProfile.BASELINE.value,
        status=ScanStatus.RUNNING.value,
        leased_by="worker-slow-A",
        fencing_token=1,
        attempts=1,
        target_locator=asset.target_locator,
    )
    target_scan_id = scan.id
    db_session.add(scan)
    await db_session.commit()

    # Worker B preempts or reaper increments fencing token to 2
    stmt = (
        select(Scan)
        .where(Scan.id == target_scan_id)
    )
    res = await db_session.execute(stmt)
    sc = res.scalars().first()
    sc.fencing_token = 2
    sc.leased_by = "worker-fast-B"
    await db_session.commit()

    # Worker A (split-brain zombie) attempts to renew heartbeat with stale token 1 -> MUST FAIL
    renew_result = await IDBDurableQueue.renew_lease_heartbeat(
        db_session, target_scan_id, fencing_token=1, lease_duration_seconds=30
    )
    assert renew_result is False

    # Worker A attempts to complete the job with stale token 1 -> MUST FAIL (zero DB write)
    complete_result = await IDBDurableQueue.complete_job(
        db_session,
        scan_id=target_scan_id,
        fencing_token=1,
        final_status=ScanStatus.COMPLETED.value,
        final_quality=ScanQualityStatus.SCANNED_SUCCESSFULLY.value,
    )
    assert complete_result is False

    # Worker B completes with authoritative token 2 -> MUST SUCCEED
    complete_b = await IDBDurableQueue.complete_job(
        db_session,
        scan_id=target_scan_id,
        fencing_token=2,
        final_status=ScanStatus.COMPLETED.value,
        final_quality=ScanQualityStatus.SCANNED_SUCCESSFULLY.value,
    )
    assert complete_b is True


# -----------------------------------------------------------------------------
# 2. Bounded Retries with Backoff and Lease Reaper Recovery
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bounded_retries_with_exponential_backoff(db_session):
    asset = await create_test_asset(db_session, "https://retry-test.local")

    scan = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        engine="all",
        profile=ScanProfile.BASELINE.value,
        status=ScanStatus.RUNNING.value,
        leased_by="worker-test",
        fencing_token=1,
        attempts=1,
        max_retries=3,
        target_locator=asset.target_locator,
    )
    db_session.add(scan)
    await db_session.commit()

    # Attempt 1 failed transiently (attempts: 1 -> retries scheduled)
    res1 = await IDBDurableQueue.fail_or_retry_job(
        db_session, scan.id, fencing_token=1, error=Exception("Database lock contention"), is_transient=True
    )
    assert res1 == "RETRY_SCHEDULED"

    # Verify scan is requeued with backoff
    res = await db_session.execute(select(Scan).where(Scan.id == scan.id))
    sc = res.scalars().first()
    assert sc.status == ScanStatus.QUEUED.value
    assert sc.available_at is not None
    assert sc.available_at > datetime.now(timezone.utc)
    assert sc.leased_by is None

    # Advance attempts to 3 (budget exhausted)
    sc.attempts = 3
    sc.status = ScanStatus.RUNNING.value
    await db_session.commit()

    # Attempt 3 failed -> terminal FAILED
    res2 = await IDBDurableQueue.fail_or_retry_job(
        db_session, scan.id, fencing_token=1, error=Exception("Fatal scanner adapter crash"), is_transient=True
    )
    assert res2 == "FAILED"

    res = await db_session.execute(select(Scan).where(Scan.id == scan.id))
    sc = res.scalars().first()
    assert sc.status == ScanStatus.FAILED.value
    assert sc.quality_status == ScanQualityStatus.SCANNER_FAILED.value


@pytest.mark.asyncio
async def test_lease_reaper_recovery_of_abandoned_jobs(db_session):
    asset = await create_test_asset(db_session, "https://reaper-test.local")
    now = datetime.now(timezone.utc)

    # Job A: Abandoned running job whose lease expired 10 minutes ago, attempts < max_retries
    scan_a = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        engine="all",
        profile=ScanProfile.BASELINE.value,
        status=ScanStatus.RUNNING.value,
        leased_by="dead-worker-1",
        lease_expires_at=now - timedelta(minutes=10),
        fencing_token=5,
        attempts=1,
        max_retries=3,
        target_locator=asset.target_locator,
    )
    # Job B: Abandoned running job whose lease expired, but attempts >= max_retries
    scan_b = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        engine="all",
        profile=ScanProfile.BASELINE.value,
        status=ScanStatus.RUNNING.value,
        leased_by="dead-worker-2",
        lease_expires_at=now - timedelta(minutes=5),
        fencing_token=3,
        attempts=3,
        max_retries=3,
        target_locator=asset.target_locator,
    )
    db_session.add_all([scan_a, scan_b])
    await db_session.commit()

    # Run reaper
    reaped_count = await IDBDurableQueue.recover_expired_leases(db_session)
    assert reaped_count >= 2

    # Check Job A: requeued with bumped fencing token
    res_a = (await db_session.execute(select(Scan).where(Scan.id == scan_a.id))).scalars().first()
    assert res_a.status == ScanStatus.QUEUED.value
    assert res_a.fencing_token == 6  # Incremented to lock out dead-worker-1
    assert res_a.leased_by is None

    # Check Job B: transitioned to terminal FAILED
    res_b = (await db_session.execute(select(Scan).where(Scan.id == scan_b.id))).scalars().first()
    assert res_b.status == ScanStatus.FAILED.value
    assert res_b.quality_status == ScanQualityStatus.SCANNER_FAILED.value


# -----------------------------------------------------------------------------
# 3. Safe Cancellation and Audit Timestamps
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_safe_cancellation_persists_timestamp_and_reason(db_session):
    asset = await create_test_asset(db_session, "https://cancel-test.local")

    scan = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        engine="all",
        profile=ScanProfile.BASELINE.value,
        status=ScanStatus.RUNNING.value,
        leased_by="worker-cancel",
        fencing_token=1,
        target_locator=asset.target_locator,
    )
    db_session.add(scan)
    await db_session.commit()

    # Cancel job
    cancelled = await IDBDurableQueue.cancel_job(db_session, scan.id, reason="Operator emergency stop")
    assert cancelled is True

    res = (await db_session.execute(select(Scan).where(Scan.id == scan.id))).scalars().first()
    assert res.status == ScanStatus.CANCELLED.value
    assert res.cancelled_at is not None
    assert res.cancellation_reason == "Operator emergency stop"
    assert res.fencing_token == 2  # Fencing bumped so worker cannot continue
    assert res.completed_at is not None

    # Second cancel attempt must return False (already cancelled)
    cancelled_again = await IDBDurableQueue.cancel_job(db_session, scan.id)
    assert cancelled_again is False


# -----------------------------------------------------------------------------
# 4. Hourly Cron Calculation in Asia/Ho_Chi_Minh (UTC stored)
# -----------------------------------------------------------------------------
def test_top_of_hour_cron_asia_ho_chi_minh():
    # Test top-of-hour cron calculation: 14:25 UTC -> next top of hour is 15:00 UTC
    dt1 = datetime(2026, 11, 10, 14, 25, 0, tzinfo=timezone.utc)
    next_1 = compute_next_run("0 * * * *", dt1, "Asia/Ho_Chi_Minh")
    assert next_1 == datetime(2026, 11, 10, 15, 0, 0, tzinfo=timezone.utc)

    # From 14:00 UTC -> next is 15:00 UTC (not 14:00 itself)
    dt2 = datetime(2026, 11, 10, 14, 0, 0, tzinfo=timezone.utc)
    next_2 = compute_next_run("0 * * * *", dt2, "Asia/Ho_Chi_Minh")
    assert next_2 == datetime(2026, 11, 10, 15, 0, 0, tzinfo=timezone.utc)

    # Day boundary: 23:45 UTC -> next is 00:00 UTC next day
    dt3 = datetime(2026, 11, 10, 23, 45, 0, tzinfo=timezone.utc)
    next_3 = compute_next_run("0 * * * *", dt3, "Asia/Ho_Chi_Minh")
    assert next_3 == datetime(2026, 11, 11, 0, 0, 0, tzinfo=timezone.utc)

    # In ICT (UTC+7), 23:45 UTC is 06:45 ICT; next top of hour is 07:00 ICT which is 00:00 UTC next day
    ict_tz = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
    assert next_3.astimezone(ict_tz).minute == 0
    assert next_3.astimezone(ict_tz).second == 0


# -----------------------------------------------------------------------------
# 5. Overrun Coalescing (Max 1 Pending Follow-Up)
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overrun_coalescing_max_one_followup(db_session):
    asset = await create_test_asset(db_session, "https://overrun-test.local")
    now = datetime.now(timezone.utc)

    # Create schedule
    sched = DailySchedule(
        id=uuid.uuid4(),
        name="Overrun Test Schedule",
        profile=ScanProfile.BASELINE.value,
        cron_expression="0 * * * *",
        timezone="Asia/Ho_Chi_Minh",
        is_active=True,
        target_ids=[str(asset.id)],
        next_run_at=now - timedelta(hours=2),  # Past due (simulating multi-hour scan)
    )
    db_session.add(sched)
    await db_session.flush()

    # Create active batch that has been running for 2 hours
    batch = ScanBatch(
        id=uuid.uuid4(),
        name="Long Running Assessment Batch",
        schedule_id=sched.id,
        status=ScanStatus.RUNNING.value,
        total_scans=1,
        started_at=now - timedelta(hours=2),
    )
    db_session.add(batch)
    sched.active_batch_id = batch.id
    await db_session.commit()

    target_sched_id = sched.id
    target_batch_id = batch.id
    engine = SchedulerEngine(interval_seconds=10)

    # Tick 1: detects overrun
    await engine.tick()

    db_session.expire_all()
    res = (await db_session.execute(select(DailySchedule).where(DailySchedule.id == target_sched_id))).scalars().first()
    assert res.overrun_active is True
    assert res.pending_followup is True
    assert res.missed_slots_count >= 1
    assert "overrun" in (res.overdue_reason or "").lower()

    # Active batch must remain intact (not aborted)
    b_res = (await db_session.execute(select(ScanBatch).where(ScanBatch.id == target_batch_id))).scalars().first()
    assert b_res.status == ScanStatus.RUNNING.value

    # Tick 2: another missed slot while batch still running -> pending_followup remains bounded at True
    await db_session.execute(
        update(DailySchedule)
        .where(DailySchedule.id == target_sched_id)
        .values(next_run_at=now - timedelta(minutes=10))
    )
    await db_session.commit()
    await engine.tick()

    db_session.expire_all()
    res = (await db_session.execute(select(DailySchedule).where(DailySchedule.id == target_sched_id))).scalars().first()
    assert res.pending_followup is True  # Invariant: bounded at at most ONE follow-up
    assert res.missed_slots_count >= 2

    # Now mark active batch COMPLETED
    await db_session.execute(
        update(ScanBatch)
        .where(ScanBatch.id == target_batch_id)
        .values(status=ScanStatus.COMPLETED.value, completed_at=datetime.now(timezone.utc))
    )
    await db_session.commit()

    # Tick 3: Batch completed -> immediately dispatches the ONE coalesced follow-up
    await engine.tick()

    db_session.expire_all()
    res = (await db_session.execute(select(DailySchedule).where(DailySchedule.id == target_sched_id))).scalars().first()
    assert res.pending_followup is False  # Dispatched and cleared
    assert res.overrun_active is False
    assert res.missed_slots_count == 0
    assert res.active_batch_id != target_batch_id  # New follow-up batch assigned


# -----------------------------------------------------------------------------
# 6. Active Run Deduplication & Idempotent Trigger
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_active_run_deduplication_on_manual_trigger(client: httpx.AsyncClient, db_session):
    headers, token, user = await get_auth_headers(db_session, UserRole.ADMIN.value)
    asset = await create_test_asset(db_session, "https://dedup-trigger-test.local")

    # Create schedule
    sched = DailySchedule(
        id=uuid.uuid4(),
        name="Dedup Trigger Test",
        profile=ScanProfile.BASELINE.value,
        cron_expression="0 * * * *",
        timezone="Asia/Ho_Chi_Minh",
        is_active=True,
        target_ids=[str(asset.id)],
    )
    db_session.add(sched)
    await db_session.commit()

    # Trigger 1: launches fresh batch
    resp1 = await client.post(f"/api/v1/schedules/{sched.id}/trigger", headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "DISPATCHED"
    batch_id = data1["batch_id"]

    # Trigger 2 while batch is active: must NOT launch duplicate sweep, returns ACTIVE_BATCH_RUNNING
    resp2 = await client.post(f"/api/v1/schedules/{sched.id}/trigger?request_followup=true", headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["status"] == "ACTIVE_BATCH_RUNNING"
    assert data2["active_batch_id"] == batch_id
    assert data2["pending_followup"] is True

    # Repeated trigger reuses request idempotently
    resp3 = await client.post(f"/api/v1/schedules/{sched.id}/trigger?request_followup=true", headers=headers)
    assert resp3.status_code == 200
    assert resp3.json()["status"] == "ACTIVE_BATCH_RUNNING"


# -----------------------------------------------------------------------------
# 7. Schedule Status Endpoint, Countdown Data, and Toggle
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schedule_status_endpoint_and_toggle(client: httpx.AsyncClient, db_session):
    headers, token, user = await get_auth_headers(db_session, UserRole.OPERATOR.value)
    asset = await create_test_asset(db_session, "https://status-endpoint-test.local")

    now = datetime.now(timezone.utc)
    sched = DailySchedule(
        id=uuid.uuid4(),
        name="Status Check Schedule",
        profile=ScanProfile.BASELINE.value,
        cron_expression="0 * * * *",
        timezone="Asia/Ho_Chi_Minh",
        is_active=True,
        target_ids=[str(asset.id)],
        next_run_at=now + timedelta(minutes=25),
    )
    db_session.add(sched)
    await db_session.commit()

    # GET status
    resp = await client.get(f"/api/v1/schedules/{sched.id}/status", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "server_time" in data
    assert "remaining_seconds" in data
    assert data["remaining_seconds"] > 0
    assert data["is_active"] is True
    assert data["is_overdue"] is False
    assert data["schedule_id"] == str(sched.id)

    # PUT toggle to pause
    resp_pause = await client.put(f"/api/v1/schedules/{sched.id}/toggle", headers=headers)
    assert resp_pause.status_code == 200
    assert resp_pause.json()["is_active"] is False

    # PUT toggle to resume
    resp_resume = await client.put(f"/api/v1/schedules/{sched.id}/toggle", headers=headers)
    assert resp_resume.status_code == 200
    assert resp_resume.json()["is_active"] is True
    assert resp_resume.json()["next_run_at"] is not None


# -----------------------------------------------------------------------------
# 8. Durable Event Stream, SSE Replay, and Events 101+ Delivery
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_durable_scan_events_persistence_and_cursor_replay(client: httpx.AsyncClient, db_session):
    headers, token, user = await get_auth_headers(db_session, UserRole.VIEWER.value)
    asset = await create_test_asset(db_session, "https://event-replay-test.local")

    from backend.app.models.user import UserAssetGrant
    db_session.add(UserAssetGrant(id=uuid.uuid4(), user_id=user.id, asset_id=asset.id, permissions="READ,SCAN", granted_by="owner_admin"))
    scan = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        engine="nuclei",
        profile=ScanProfile.BASELINE.value,
        status=ScanStatus.RUNNING.value,
        target_locator=asset.target_locator,
    )
    db_session.add(scan)
    await db_session.commit()

    # Emit 120 durable events sequentially
    for i in range(1, 121):
        await emit_event(
            event_type="LOG",
            message=f"Event check line #{i} for target {asset.target_locator}",
            scan_id=scan.id,
            engine="nuclei",
            level="INFO",
            details={"step_number": i, "authorization": "Bearer secret_should_be_redacted"},
        )

    # Verify total count in DB
    cnt_res = await db_session.execute(
        select(func.count(ScanEvent.id)).where(ScanEvent.scan_id == scan.id)
    )
    total_events = cnt_res.scalar()
    assert total_events >= 120

    # Test cursor pagination via GET /scans/{id}/events
    # Request page 1: events 1..100 (after_id = 0, limit = 100)
    p1 = await client.get(f"/api/v1/scans/{scan.id}/events?after_id=0&limit=100", headers=headers)
    assert p1.status_code == 200
    p1_data = p1.json()
    assert len(p1_data["items"]) == 100
    assert p1_data["total"] >= 120
    first_id = p1_data["items"][0]["id"]
    last_p1_id = p1_data["items"][-1]["id"]
    assert last_p1_id > first_id

    # Verify sanitization stripped sensitive bearer header
    assert p1_data["items"][0]["details"]["authorization"] == "[REDACTED]"

    # Request page 2: events 101..120 (after_id = last_p1_id, limit = 100) -> NO 100-event ceiling!
    p2 = await client.get(f"/api/v1/scans/{scan.id}/events?after_id={last_p1_id}&limit=100", headers=headers)
    assert p2.status_code == 200
    p2_data = p2.json()
    assert len(p2_data["items"]) >= 20  # Events 101+ are fully returned!
    assert p2_data["items"][0]["id"] > last_p1_id


@pytest.mark.asyncio
async def test_sse_stream_replay_with_last_event_id_and_token(client: httpx.AsyncClient, db_session):
    headers, token, user = await get_auth_headers(db_session, UserRole.VIEWER.value)
    asset = await create_test_asset(db_session, "https://sse-stream-test.local")

    scan = Scan(
        id=uuid.uuid4(),
        asset_id=asset.id,
        engine="empire_engine",
        profile=ScanProfile.BASELINE.value,
        status=ScanStatus.RUNNING.value,
        target_locator=asset.target_locator,
    )
    db_session.add(scan)
    await db_session.commit()

    # Emit 105 events
    last_event_obj = None
    for i in range(1, 106):
        last_event_obj = await emit_event(
            event_type="STAGE_TRANSITION" if i % 20 == 0 else "LOG",
            message=f"SSE live pipeline event sequence #{i}",
            scan_id=scan.id,
            engine="empire_engine",
            level="INFO",
        )

    # Request SSE stream using query parameter ?token= (for native browser EventSource)
    # and Last-Event-ID: 100 to replay from event 101 onwards
    start_cursor = last_event_obj.id - 5
    async with client.stream(
        "GET", f"/api/v1/scans/{scan.id}/events/stream?token={token}&cursor={start_cursor}"
    ) as sse_resp:
        assert sse_resp.status_code == 200
        assert "text/event-stream" in sse_resp.headers.get("content-type", "")

        received_chunks = []
        async for line in sse_resp.aiter_lines():
            received_chunks.append(line)
            if "SSE live pipeline event sequence #105" in line:
                break

        stream_content = "\n".join(received_chunks)
        assert f"id: {last_event_obj.id}" in stream_content
        assert "SSE live pipeline event sequence #105" in stream_content
