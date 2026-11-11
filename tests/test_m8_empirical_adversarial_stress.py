"""Adversarial Empirical Stress & Robustness Suite for Milestone M8.
Empirically stress-tests the 'Scan All' batch scan orchestration and device resource optimization:
1. Rapid concurrent batch creation (POST /api/v1/scans/batch).
2. Emergency stop (POST /api/v1/scans/stop-all) during active execution.
3. Rapid concurrent cancellation of running batches.
4. Heavy concurrent SQLite read/write operations under WAL mode (verifying zero 'database is locked').
5. Subprocess tree termination and zombie process prevention using real OS processes.
6. Malformed and boundary payload handling.
"""

import asyncio
from datetime import datetime, timezone
import os
import subprocess
import sys
import time
from typing import List
from unittest.mock import patch
import uuid

import psutil
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.dispatcher import (
    AsyncWorkerDispatcher,
    check_system_resources,
    get_dispatcher,
    process_safety,
)
from backend.app.models.asset import Asset
from backend.app.models.scan import Scan, ScanBatch, ScanLog
from backend.app.schemas.common import ScanProfile, ScanStatus


def drain_dispatcher_queue(dispatcher):
    while not dispatcher.queue.empty():
        try:
            dispatcher.queue.get_nowait()
            dispatcher.queue.task_done()
        except Exception:
            break


async def fast_mock_run_scan(self, scan_id, cancel_token, thread_id=1):
    """Fast simulation of scan lifecycle without external network/crawler latency."""
    now_iso = datetime.now(timezone.utc).isoformat()
    start_mono = asyncio.get_event_loop().time()
    self._active_threads[scan_id] = {
        "thread_id": thread_id,
        "scan_id": scan_id,
        "target_locator": "https://test.target.local",
        "profile": "BASELINE",
        "engine": "all",
        "stage": "running",
        "progress_percentage": 50,
        "started_at": now_iso,
        "start_time": start_mono,
        "elapsed_seconds": 0,
        "last_log": "Fast mock executing...",
    }

    for _ in range(10):
        if cancel_token.is_cancelled:
            return
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Scan.status).where(Scan.id == scan_id))
            st = res.scalar()
            if st == ScanStatus.CANCELLED.value:
                return
        await asyncio.sleep(0.005)

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Scan).where(Scan.id == scan_id))
        s = res.scalars().first()
        if s and s.status not in (ScanStatus.CANCELLED.value, ScanStatus.FAILED.value):
            s.status = ScanStatus.COMPLETED.value
            s.progress_percentage = 100
            s.completed_at = datetime.now(timezone.utc)
            await session.commit()
            if s.batch_id:
                await self._update_batch_progress(s.batch_id)


@pytest_asyncio.fixture(autouse=True)
async def setup_dispatcher_isolation():
    """Ensures each test gets a fresh AsyncWorkerDispatcher created on the active event loop."""
    import backend.app.core.dispatcher as disp_mod
    if disp_mod._dispatcher_instance and disp_mod._dispatcher_instance._is_running:
        await disp_mod._dispatcher_instance.stop()
    disp_mod._dispatcher_instance = AsyncWorkerDispatcher()
    dispatcher = disp_mod._dispatcher_instance

    patcher_run = patch.object(AsyncWorkerDispatcher, "_run_scan", fast_mock_run_scan)
    patcher_res = patch(
        "backend.app.core.dispatcher.check_system_resources",
        return_value={
            "is_throttled": False,
            "cpu_percent": 10.0,
            "memory_percent": 50.0,
            "memory_available_mb": 4096.0,
            "memory_used_mb": 4096.0,
            "cpu_count": 4,
        },
    )
    patcher_run.start()
    patcher_res.start()

    yield

    if disp_mod._dispatcher_instance and disp_mod._dispatcher_instance._is_running:
        await disp_mod._dispatcher_instance.stop()
    disp_mod._dispatcher_instance = None

    patcher_run.stop()
    patcher_res.stop()


# ============================================================================
# STRESS-01: Rapid Concurrent Batch Creation Under Load
# ============================================================================

@pytest.mark.asyncio
async def test_stress_concurrent_batch_creation(client: AsyncClient):
    """Fires 10 simultaneous batch creation requests with varying profiles and scopes.
    Verifies that all 10 batches are created with unique IDs, correct constituent
    scans, and SQLite WAL handles the concurrency without 'database is locked' errors.
    """
    dispatcher = get_dispatcher()
    assets_res = await client.get("/api/v1/assets?page=1&size=3")
    assert assets_res.status_code == 200
    target_ids = [a["id"] for a in assets_res.json()["items"]]
    assert len(target_ids) >= 2

    profiles_pool = [
        ["BASELINE"],
        ["DAILY_SECURITY"],
        ["STANDARD"],
        ["BASELINE", "DAILY_SECURITY"],
    ]

    async def create_one(idx: int):
        payload = {
            "targets": target_ids,
            "profiles": profiles_pool[idx % len(profiles_pool)],
            "engines": ["all"],
            "name": f"Stress Batch #{idx} - {uuid.uuid4().hex[:6]}",
            "concurrency_limit": 4,
        }
        res = await client.post("/api/v1/scans/batch", json=payload)
        return res

    # Launch 10 concurrent requests simultaneously
    responses = await asyncio.gather(*[create_one(i) for i in range(10)], return_exceptions=True)

    batch_ids = []
    for i, res in enumerate(responses):
        assert not isinstance(res, Exception), f"Concurrent batch {i} raised exception: {res}"
        assert res.status_code == 201, f"Batch {i} failed: {res.status_code} - {res.text}"
        data = res.json()
        assert "batch_id" in data
        assert data["target_count"] == len(target_ids)
        assert data["total_scans"] >= len(target_ids)
        batch_ids.append(data["batch_id"])

    # Ensure all batch IDs are strictly distinct
    assert len(set(batch_ids)) == 10, "Duplicate batch IDs generated under concurrency!"

    # Verify database persistence integrity
    async with AsyncSessionLocal() as session:
        db_batches_res = await session.execute(
            select(ScanBatch).where(ScanBatch.id.in_([uuid.UUID(bid) for bid in batch_ids]))
        )
        db_batches = db_batches_res.scalars().all()
        assert len(db_batches) == 10

        for b in db_batches:
            assert b.target_count == len(target_ids)
            assert b.status in (ScanStatus.QUEUED.value, ScanStatus.RUNNING.value, ScanStatus.COMPLETED.value)

    # Wait cleanly for queue to drain before moving to next test
    try:
        await asyncio.wait_for(dispatcher.queue.join(), timeout=3.0)
    except Exception:
        pass


# ============================================================================
# STRESS-02: Emergency Stop-All During Active Execution
# ============================================================================

@pytest.mark.asyncio
async def test_stress_emergency_stop_all_during_batch_execution(client: AsyncClient):
    """Dispatches multiple batches and triggers POST /api/v1/scans/stop-all
    while tasks are active.
    Verifies that all running and queued scans/batches transition to CANCELLED,
    active threads are cleared, and no scans remain stranded in QUEUED or RUNNING.
    """
    assets_res = await client.get("/api/v1/assets?page=1&size=3")
    target_ids = [a["id"] for a in assets_res.json()["items"]]

    # 1. Create 2 batches to enqueue scans
    res1 = await client.post("/api/v1/scans/batch", json={
        "targets": target_ids,
        "profiles": ["BASELINE"],
        "engines": ["all"],
        "name": "Stop-All Test Batch 1",
    })
    assert res1.status_code == 201
    b1_id = res1.json()["batch_id"]

    res2 = await client.post("/api/v1/scans/batch", json={
        "targets": target_ids,
        "profiles": ["DAILY_SECURITY"],
        "engines": ["all"],
        "name": "Stop-All Test Batch 2",
    })
    assert res2.status_code == 201
    b2_id = res2.json()["batch_id"]

    # Allow dispatcher a brief tick to start running scans
    await asyncio.sleep(0.02)

    # 2. Trigger platform-wide emergency stop
    stop_res = await client.post("/api/v1/scans/stop-all")
    assert stop_res.status_code == 200, f"Stop-all failed: {stop_res.text}"
    stop_data = stop_res.json()
    assert stop_data["status"] == "STOPPED"
    assert "halted_count" in stop_data

    # 3. Verify in DB that no scans from these batches remain in QUEUED or RUNNING
    async with AsyncSessionLocal() as session:
        active_scans_res = await session.execute(
            select(Scan).where(
                Scan.batch_id.in_([uuid.UUID(b1_id), uuid.UUID(b2_id)]),
                Scan.status.in_([
                    ScanStatus.QUEUED.value,
                    ScanStatus.INITIALIZING.value,
                    ScanStatus.RUNNING.value,
                    ScanStatus.PENDING.value,
                ]),
            )
        )
        active_scans = active_scans_res.scalars().all()
        assert len(active_scans) == 0, f"Found {len(active_scans)} scans still active after stop-all!"

        # Batches must be CANCELLED or COMPLETED (if mock scans finished before stop-all arrived)
        for bid in (b1_id, b2_id):
            b_res = await session.execute(select(ScanBatch).where(ScanBatch.id == uuid.UUID(bid)))
            b = b_res.scalars().first()
            assert b.status in (ScanStatus.CANCELLED.value, ScanStatus.COMPLETED.value)

    # 4. Verify telemetry shows zero active workers
    telemetry_res = await client.get("/api/v1/scans/trackcurrent")
    assert telemetry_res.status_code == 200
    telemetry = telemetry_res.json()
    assert telemetry["active_workers"] == 0
    assert len(telemetry["active_threads"]) == 0


# ============================================================================
# STRESS-03: Rapid Concurrent Batch Cancellation Race Conditions
# ============================================================================

@pytest.mark.asyncio
async def test_stress_rapid_concurrent_batch_cancellation(client: AsyncClient):
    """Tests rapid, simultaneous cancellation of the same batch to verify idempotency
    and absence of race conditions or double-free locks.
    """
    assets_res = await client.get("/api/v1/assets?page=1&size=3")
    target_ids = [a["id"] for a in assets_res.json()["items"]]

    # 1. Create a batch
    batch_res = await client.post("/api/v1/scans/batch", json={
        "targets": target_ids,
        "profiles": ["BASELINE"],
        "engines": ["all"],
        "name": "Rapid Cancel Race Batch",
    })
    assert batch_res.status_code == 201
    batch_id = batch_res.json()["batch_id"]

    # 2. Fire 5 concurrent cancellation requests on the exact same batch_id
    cancel_responses = await asyncio.gather(
        client.post(f"/api/v1/scans/batch/{batch_id}/cancel"),
        client.post(f"/api/v1/scans/batch/{batch_id}/cancel"),
        client.post(f"/api/v1/scans/batch/{batch_id}/cancel"),
        client.post(f"/api/v1/scans/batch/{batch_id}/cancel"),
        client.post(f"/api/v1/scans/batch/{batch_id}/cancel"),
        return_exceptions=True,
    )

    for i, cr in enumerate(cancel_responses):
        assert not isinstance(cr, Exception), f"Cancel request {i} raised exception: {cr}"
        assert cr.status_code == 200, f"Cancel {i} failed: {cr.status_code} - {cr.text}"
        data = cr.json()
        assert data["batch_id"] == batch_id
        assert data["status"] == "CANCELLED"

    # 3. Allow active worker tasks a brief moment to settle
    await asyncio.sleep(0.05)

    # Verify batch in DB is CANCELLED (or COMPLETED if already finished) and scans are CANCELLED/COMPLETED
    async with AsyncSessionLocal() as session:
        b_res = await session.execute(select(ScanBatch).where(ScanBatch.id == uuid.UUID(batch_id)))
        b = b_res.scalars().first()
        assert b.status in (ScanStatus.CANCELLED.value, ScanStatus.COMPLETED.value), f"Batch status was {b.status}"

        scans_res = await session.execute(select(Scan).where(Scan.batch_id == uuid.UUID(batch_id)))
        scans = scans_res.scalars().all()
        for s in scans:
            assert s.status in (ScanStatus.CANCELLED.value, ScanStatus.COMPLETED.value)

    # 4. Verify cancelling a non-existent batch returns 404
    fake_id = uuid.uuid4()
    bad_cancel = await client.post(f"/api/v1/scans/batch/{fake_id}/cancel")
    assert bad_cancel.status_code == 404


# ============================================================================
# STRESS-04: Heavy Concurrent SQLite Read/Write Under WAL Mode
# ============================================================================

@pytest.mark.asyncio
async def test_stress_sqlite_wal_heavy_concurrent_read_write(client: AsyncClient):
    """Executes 25 concurrent mixed async operations across batch creation,
    batch listing, telemetry polling, scan querying, and direct log commits.
    Verifies that SQLite Write-Ahead Logging (WAL) and busy timeout prevent
    'database is locked' errors.
    """
    assets_res = await client.get("/api/v1/assets?page=1&size=3")
    target_ids = [a["id"] for a in assets_res.json()["items"]]

    errors: List[str] = []

    async def op_create_batch(idx: int):
        try:
            r = await client.post("/api/v1/scans/batch", json={
                "targets": target_ids,
                "profiles": ["BASELINE"],
                "engines": ["all"],
                "name": f"WAL Stress Batch #{idx}",
            })
            if r.status_code != 201:
                errors.append(f"CreateBatch #{idx} returned {r.status_code}")
        except Exception as e:
            errors.append(f"CreateBatch #{idx} exception: {e}")

    async def op_list_batches(idx: int):
        try:
            r = await client.get("/api/v1/scans/batches?page=1&size=10")
            if r.status_code != 200:
                errors.append(f"ListBatches #{idx} returned {r.status_code}")
        except Exception as e:
            errors.append(f"ListBatches #{idx} exception: {e}")

    async def op_telemetry(idx: int):
        try:
            r = await client.get("/api/v1/scans/trackcurrent")
            if r.status_code != 200:
                errors.append(f"Telemetry #{idx} returned {r.status_code}")
        except Exception as e:
            errors.append(f"Telemetry #{idx} exception: {e}")

    async def op_list_scans(idx: int):
        try:
            r = await client.get("/api/v1/scans?page=1&size=20")
            if r.status_code != 200:
                errors.append(f"ListScans #{idx} returned {r.status_code}")
        except Exception as e:
            errors.append(f"ListScans #{idx} exception: {e}")

    async def op_direct_log_write(idx: int):
        try:
            async with AsyncSessionLocal() as session:
                dummy_sid = uuid.uuid4()
                log_entry = ScanLog(
                    scan_id=dummy_sid,
                    level="INFO",
                    message=f"WAL Concurrent write log message #{idx}",
                    source="stress_test",
                )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            errors.append(f"DirectLogWrite #{idx} exception: {e}")

    tasks = []
    for i in range(5):
        tasks.append(op_create_batch(i))
        tasks.append(op_list_batches(i))
        tasks.append(op_telemetry(i))
        tasks.append(op_list_scans(i))
        tasks.append(op_direct_log_write(i))

    # Run all 25 operations concurrently
    await asyncio.gather(*tasks)

    # Assert zero locking failures
    lock_errors = [e for e in errors if "locked" in e.lower()]
    assert len(lock_errors) == 0, f"SQLite database lock errors occurred: {lock_errors}"
    assert len(errors) == 0, f"Operations failed under concurrent load: {errors}"


# ============================================================================
# STRESS-05: Real OS Subprocess Tree Termination (Zombie Process Prevention)
# ============================================================================

@pytest.mark.asyncio
async def test_stress_real_subprocess_tree_termination_no_zombies():
    """Spawns an actual OS process tree (a parent python process that spawns a child process)
    and verifies that ProcessSafetyManager recursively terminates all descendants,
    leaving no orphaned/zombie background processes running.
    """
    parent_code = (
        "import subprocess, sys, time\n"
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "time.sleep(60)\n"
    )

    parent_proc = subprocess.Popen(
        [sys.executable, "-c", parent_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    parent_pid = parent_proc.pid

    # Wait briefly for child process to spawn
    time.sleep(0.5)

    try:
        psutil_parent = psutil.Process(parent_pid)
        children = psutil_parent.children(recursive=True)
        assert len(children) >= 1, "Child process failed to spawn in time."
        child_pids = [c.pid for c in children]

        # Register parent in ProcessSafetyManager under a test scan_id
        test_scan_id = uuid.uuid4()
        await process_safety.register_pid(test_scan_id, parent_pid)
        assert test_scan_id in process_safety._scan_pids

        # Terminate the process tree via ProcessSafetyManager
        process_safety.terminate_process_tree(test_scan_id)

        # Allow OS time to process termination
        time.sleep(0.5)

        # Verify parent is terminated
        assert not psutil.pid_exists(parent_pid) or psutil.Process(parent_pid).status() == psutil.STATUS_ZOMBIE, \
            f"Parent process {parent_pid} still running!"

        # Verify all children are terminated
        for cpid in child_pids:
            is_alive = False
            try:
                cp = psutil.Process(cpid)
                if cp.is_running() and cp.status() != psutil.STATUS_ZOMBIE:
                    is_alive = True
            except psutil.NoSuchProcess:
                is_alive = False
            assert not is_alive, f"Child process {cpid} still alive! Zombie process leaked."

        # Verify scan_id is removed from registry
        assert test_scan_id not in process_safety._scan_pids
    finally:
        try:
            if psutil.pid_exists(parent_pid):
                parent_proc.kill()
        except Exception:
            pass


# ============================================================================
# STRESS-06: Malformed, Empty, and Boundary Batch Payloads
# ============================================================================

@pytest.mark.asyncio
async def test_stress_malformed_and_boundary_batch_payloads(client: AsyncClient):
    """Validates system robustness against empty target arrays, non-existent UUIDs,
    negative concurrency values, and boundary profile configurations.
    """
    # 1. Empty target array
    res_empty = await client.post("/api/v1/scans/batch", json={
        "targets": [],
        "profiles": ["BASELINE"],
        "name": "Empty Targets Test",
    })
    assert res_empty.status_code in (404, 422)

    # 2. Non-existent UUIDs
    fake_target_id = str(uuid.uuid4())
    res_nonexistent = await client.post("/api/v1/scans/batch", json={
        "targets": [fake_target_id],
        "profiles": ["BASELINE"],
        "name": "Non-existent Target Test",
    })
    assert res_nonexistent.status_code == 404
    assert "No target assets found" in res_nonexistent.json().get("detail", "")

    # 3. Extreme concurrency limits (-1, 0, 9999)
    for extreme_cap in [-1, 0, 9999]:
        res_cap = await client.post("/api/v1/scans/batch", json={
            "targets": "ALL",
            "profiles": ["BASELINE"],
            "name": f"Extreme Concurrency {extreme_cap}",
            "concurrency_limit": extreme_cap,
        })
        assert res_cap.status_code in (201, 422), f"Unexpected status code {res_cap.status_code} for limit {extreme_cap}"
