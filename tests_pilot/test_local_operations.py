"""Local supervisor and durable-only execution controls, using disposable data only."""
from datetime import datetime, timedelta, timezone
import asyncio
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import uuid

import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.dispatcher import AsyncWorkerDispatcher
from backend.app.core.queue import IDBDurableQueue
from backend.app.models.defensive import ExecutionRecord
from backend.app.models.operations import CapacitySettings
from backend.app.models.scan import Scan
from backend.app.scanners.base import CancellationToken
from tests_pilot.conftest import make_asset

ROOT = Path(__file__).resolve().parent.parent


async def queued(asset_id, *, durable=False, expired=False):
    sid = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(Scan(id=sid, asset_id=asset_id, target_locator="fixture://local-operations",
                    status="RUNNING" if expired else "QUEUED",
                    lease_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1) if expired else None,
                    leased_by="expired-worker" if expired else None))
        await db.flush()
        if durable:
            db.add(ExecutionRecord(scan_id=sid, asset_id=asset_id, engine_id="sbom"))
        await db.commit()
    return sid


async def test_defensive_worker_leaves_legacy_queue_and_reaper_rows_untouched(monkeypatch):
    monkeypatch.setattr(settings, "DEFENSIVE_ONLY", True)
    aid = await make_asset("local-queue")
    legacy = await queued(aid)
    old_lease = await queued(aid, expired=True)
    durable = await queued(aid, durable=True)
    durable_expired = await queued(aid, durable=True, expired=True)
    async with AsyncSessionLocal() as db:
        scan = await IDBDurableQueue.claim_next_job(db, "test-worker")
        assert scan.id == durable
        assert await IDBDurableQueue.recover_expired_leases(db, 0) == 1
    async with AsyncSessionLocal() as db:
        assert (await db.get(Scan, legacy)).status == "QUEUED"
        assert (await db.get(Scan, old_lease)).status == "RUNNING"
        assert (await db.get(Scan, durable_expired)).status == "QUEUED"


async def test_global_stop_blocks_durable_claim_until_resumed(monkeypatch):
    monkeypatch.setattr(settings, "DEFENSIVE_ONLY", True)
    aid = await make_asset("local-stop")
    sid = await queued(aid, durable=True)
    async with AsyncSessionLocal() as db:
        db.add(CapacitySettings(id=1, emergency_stop_active=True))
        await db.commit()
        assert await IDBDurableQueue.claim_next_job(db, "test-worker") is None
        cap = await db.get(CapacitySettings, 1)
        cap.emergency_stop_active = False
        await db.commit()
        assert (await IDBDurableQueue.claim_next_job(db, "test-worker")).id == sid


async def test_zero_retry_budget_never_replays_failed_or_abandoned_observations(monkeypatch):
    monkeypatch.setattr(settings, "DEFENSIVE_ONLY", True)
    aid = await make_asset("local-no-replay")
    failed_id = await queued(aid, durable=True)
    abandoned_id = await queued(aid, durable=True, expired=True)
    async with AsyncSessionLocal() as db:
        for sid in (failed_id, abandoned_id):
            scan = await db.get(Scan, sid)
            scan.max_retries = 0
        await db.commit()
        scan = await IDBDurableQueue.claim_next_job(db, "test-worker")
        assert scan.id == failed_id
        result = await IDBDurableQueue.fail_or_retry_job(db, scan.id, scan.fencing_token,
                                                       RuntimeError("synthetic interruption"))
        assert result == "FAILED"
        assert await IDBDurableQueue.recover_expired_leases(db, 0) == 1
    async with AsyncSessionLocal() as db:
        assert (await db.get(Scan, failed_id)).status == "FAILED"
        assert (await db.get(Scan, abandoned_id)).status == "FAILED"
        assert await IDBDurableQueue.claim_next_job(db, "test-worker") is None


async def test_public_host_claim_is_atomic_and_has_minimum_spacing(monkeypatch):
    monkeypatch.setattr(settings, "DEFENSIVE_ONLY", True)
    aid = await make_asset("local-host-reservation")
    ids = [await queued(aid, durable=True) for _ in range(2)]
    async with AsyncSessionLocal() as db:
        for sid in ids:
            rec = (await db.execute(select(ExecutionRecord).where(ExecutionRecord.scan_id == sid))).scalar_one()
            rec.engine_id, rec.target_host = "public_web", "host.pilot-test.invalid"
        await db.commit()
    async def claim(worker):
        async with AsyncSessionLocal() as db:
            return await IDBDurableQueue.claim_next_job(db, worker)
    claims = await asyncio.gather(claim("concurrent-a"), claim("concurrent-b"))
    claimed = [s for s in claims if s is not None]
    assert len(claimed) == 1
    first = claimed[0]
    async with AsyncSessionLocal() as db:
        assert await IDBDurableQueue.complete_job(db, first.id, first.fencing_token, "COMPLETED")
    assert await claim("too-soon") is None
    async with AsyncSessionLocal() as db:
        previous = await db.get(Scan, first.id)
        previous.started_at = datetime.now(timezone.utc) - timedelta(seconds=21)
        await db.commit()
    second = await claim("after-spacing")
    assert second is not None and second.id != first.id


async def test_api_dispatch_does_not_start_a_worker_or_queue_in_memory(monkeypatch):
    monkeypatch.setattr(settings, "PROCESS_ROLE", "api")
    aid = await make_asset("local-api-only")
    sid = await queued(aid, durable=True)
    dispatcher = AsyncWorkerDispatcher()
    await dispatcher.dispatch_scan(sid)
    await dispatcher.batch_dispatch_scans([sid])
    assert dispatcher._worker_task is None and not dispatcher._is_running
    assert dispatcher.queue.empty()
    async with AsyncSessionLocal() as db:
        assert (await db.get(Scan, sid)).status == "QUEUED"


async def test_guard_cannot_create_or_steal_a_lease(monkeypatch):
    monkeypatch.setattr(settings, "DEFENSIVE_ONLY", True)
    aid = await make_asset("local-no-bypass")
    sid = await queued(aid, durable=True)
    dispatcher = AsyncWorkerDispatcher()
    await dispatcher._execute_scan_guarded_inner(sid)
    async with AsyncSessionLocal() as db:
        assert (await db.get(Scan, sid)).status == "QUEUED"
        await IDBDurableQueue.claim_next_job(db, "another-worker")
    await dispatcher._execute_scan_guarded_inner(sid)
    async with AsyncSessionLocal() as db:
        scan = await db.get(Scan, sid)
        assert scan.leased_by == "another-worker" and scan.fencing_token == 1


async def test_direct_legacy_paths_refuse_without_mutating_history(monkeypatch):
    monkeypatch.setattr(settings, "DEFENSIVE_ONLY", True)
    aid = await make_asset("local-legacy")
    sid = await queued(aid)
    dispatcher = AsyncWorkerDispatcher()
    await dispatcher._execute_scan_guarded_inner(sid)
    with pytest.raises(RuntimeError, match="LEGACY_EXECUTION_DISABLED"):
        await dispatcher._run_scan(sid, CancellationToken())
    async with AsyncSessionLocal() as db:
        assert (await db.get(Scan, sid)).status == "QUEUED"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_local_supervisor_console_jobs_restart_and_stop(tmp_path):
    static = tmp_path / "out"
    static.mkdir()
    (static / "index.html").write_text("<html>synthetic local console</html>")
    state_dir, database = tmp_path / "state", tmp_path / "local.db"
    env = {**os.environ, "NOOSPIRE_LOCAL_STATE_DIR": str(state_dir), "NOOSPIRE_STATIC_DIR": str(static),
           "DATABASE_URL": f"sqlite+aiosqlite:///{database}",
           "SENTINEL_DATABASE_URL": f"sqlite+aiosqlite:///{database}",
           "STORAGE_DIR": str(tmp_path / "storage"), "SENTINEL_STORAGE_DIR": str(tmp_path / "storage")}
    api_port, gw_port = free_port(), free_port()
    base = [sys.executable, "scripts/local_stack.py"]
    def run(*args):
        return subprocess.run([*base, *args], cwd=ROOT, env=env, text=True, capture_output=True, timeout=80)
    try:
        initial = run("start", "--api-port", str(api_port), "--port", str(gw_port))
        assert initial.returncode == 0, initial.stderr + initial.stdout
        state = json.loads(initial.stdout)
        assert state["api_ready"] and state["gateway_ready"]
        assert state["jobs_enabled"] is False and set(state["services"]) == {"api", "gateway"}
        assert run("logs", "api", "--lines", "5").returncode == 0
        # A second control directory must refuse occupied ports, leaving first stack alive.
        other = subprocess.run([*base, "start", "--api-port", str(api_port), "--port", str(gw_port)],
                               cwd=ROOT, env={**env, "NOOSPIRE_LOCAL_STATE_DIR": str(tmp_path / "other")},
                               text=True, capture_output=True, timeout=10)
        assert other.returncode == 1 and "already in use" in other.stderr
        assert run("status").returncode == 0
        assert run("stop").returncode == 0
        assert run("status").returncode == 1
        started = run("start", "--enable-jobs", "--api-port", str(api_port), "--port", str(gw_port))
        assert started.returncode == 0, started.stderr + started.stdout
        state = json.loads(started.stdout)
        assert state["jobs_enabled"] and state["defensive_only"]
        assert set(state["services"]) == {"api", "gateway", "worker", "scheduler"}
        # Simulate one worker crash; the supervisor must restore its process and heartbeat.
        import psutil
        pid = state["services"]["worker"]["pid"]
        psutil.Process(pid).kill()
        until = time.monotonic() + 15
        while time.monotonic() < until:
            state = json.loads(run("status").stdout)
            if state["services"]["worker"]["pid"] != pid:
                break
            time.sleep(0.2)
        assert state["services"]["worker"]["running"] and state["services"]["worker"]["pid"] != pid
        until = time.monotonic() + 15
        while time.monotonic() < until:
            with sqlite3.connect(database) as db:
                count = db.execute("SELECT count(*) FROM worker_heartbeats").fetchone()[0]
            if count:
                break
            time.sleep(0.2)
        assert count > 0
        with sqlite3.connect(database) as db:
            assert db.execute("SELECT count(*) FROM assets").fetchone()[0] == 0
        assert (state_dir.stat().st_mode & 0o777) == 0o700
    finally:
        stopped = run("stop")
        assert stopped.returncode == 0, stopped.stderr
