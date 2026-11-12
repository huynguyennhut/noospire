"""Milestone 7 · Round A additions: the mandatory acceptance cases not already covered by the
M1–M6 suites. Disposable DB, real API over ASGI, real queue/runner, synthetic labelled data."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select, update

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.queue import IDBDurableQueue
from backend.app.core.ultra_planner import InventoryRowClassification as C
from backend.app.core.ultra_planner import ultra_planner
from backend.app.engines import runner
from backend.app.models.asset import Asset
from backend.app.models.defensive import ExecutionAttempt, ExecutionRecord
from backend.app.models.finding import NormalizedFinding
from backend.app.models.lifecycle import FindingObservation
from backend.app.models.scan import Scan
from tests_pilot.conftest import USER_PASSWORD, csrf_headers, login, make_asset, make_user, new_client
from tests_pilot.test_m3_sbom_flow import API, DATA, import_snapshot, owner_session, upload, work_once

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = DATA / "golden_sbom_matches.json"


async def _launch_sbom(client, h, asset) -> dict:
    r = await client.post(f"{API}/runs", headers=h,
                          json={"selection": {"kind": "assets", "asset_ids": [str(asset)]}, "engines": ["sbom"]})
    assert r.status_code == 202, r.text
    return r.json()


# --------------------------------------------------------------------------- 379 fixture and arbitrary inventories

def test_fixture_379_accounting_and_edge_inventories():
    p = ultra_planner.plan_inventory(ultra_planner.generate_acceptance_fixture_379()).to_summary_dict()
    assert p["accounted_inventory_rows"] == 379
    assert (p["independent_execution_targets"], p["shared_alias_count"], p["excluded_count"]) == (368, 6, 5)
    assert p["engine_executions_count"] == 728  # 350×2 web + 10×2 api + 8×1 artifact

    assert ultra_planner.plan_inventory([]).to_summary_dict()["accounted_inventory_rows"] == 0
    one = ultra_planner.plan_inventory([{"id": "x", "target_locator": "https://a.pilot-test.invalid"}])
    assert one.accounted_inventory_rows == 1 and one.engine_executions_count == 2

    big = [{"id": f"r{i}", "target_locator": f"https://r{i}.pilot-test.invalid"} for i in range(500)]
    pb = ultra_planner.plan_inventory(big)
    assert pb.accounted_inventory_rows == 500 and pb.engine_executions_count == 1000

    bad = [{"id": "p1", "target_locator": "https://p1.pilot-test.invalid"},
           {"id": "a1", "target_locator": "https://a1.pilot-test.invalid", "is_alias": True, "alias_of": "missing"},
           {"id": "a2", "target_locator": "https://a2.pilot-test.invalid", "is_alias": True},
           {"id": "x1", "target_locator": "https://x1.pilot-test.invalid", "is_out_of_scope": True},
           {"id": "a3", "target_locator": "https://a3.pilot-test.invalid", "is_alias": True, "alias_of": "x1"}]
    pa = ultra_planner.plan_inventory(bad)
    cls = {r.inventory_id: r.classification for r in pa.inventory_entries}
    assert cls == {"p1": C.EXECUTION_TARGET, "a1": C.INVALID_ALIAS, "a2": C.INVALID_ALIAS, "x1": C.EXCLUDED,
                   "a3": C.INVALID_ALIAS}  # alias of an excluded row is not silently shared
    assert pa.accounted_inventory_rows == len(bad) and pa.to_summary_dict()["invalid_alias_count"] == 3

    pn = ultra_planner.plan_inventory(big[:3], requested_engines=["trivy"])  # web targets, artifact-only profile
    assert pn.engine_executions_count == 0 and pn.to_summary_dict()["no_applicable_engine_count"] == 3
    assert all(r.exclusion_reason for r in pn.inventory_entries)


async def test_fixture_endpoint_writes_nothing_to_an_empty_db(client, owner):
    await owner_session(client)
    r = await client.get(f"{API}/scans/ultra/fixture-379")
    assert r.status_code == 200
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(Asset))).scalar() == 0
        assert (await db.execute(select(func.count()).select_from(Scan))).scalar() == 0
        assert (await db.execute(select(func.count()).select_from(NormalizedFinding))).scalar() == 0


# --------------------------------------------------------------------------- real engine

async def test_sbom_golden_output(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    a = await make_asset("svc-golden")
    await upload(client, h, a)
    run = await _launch_sbom(client, h, a)
    assert await work_once() == "succeeded"
    eid = run["executions"][0]["execution_id"]
    doc = (await client.get(f"{API}/executions/{eid}/output")).json()
    stable = sorted(({k: m[k] for k in sorted(m) if k not in ("observed_at",)} for m in doc["matches"]),
                    key=lambda m: json.dumps(m, sort_keys=True))
    if os.getenv("NOOSPIRE_UPDATE_GOLDEN") == "1":
        GOLDEN.write_text(json.dumps(stable, indent=2, sort_keys=True), encoding="utf-8")
    assert stable == json.loads(GOLDEN.read_text(encoding="utf-8"))


async def test_timeout_missing_adapter_and_redacted_error(client, owner, monkeypatch):
    h = await owner_session(client)
    await import_snapshot(client, h)
    a = await make_asset("svc-engine-edge")
    await upload(client, h, a)

    async def slow(*args, **kw):
        await asyncio.sleep(30)

    monkeypatch.setitem(runner.ENGINES, "sbom", (slow, "pilot-slow", "0"))
    run = await _launch_sbom(client, h, a)
    async with AsyncSessionLocal() as db:
        await db.execute(update(Scan).values(timeout_seconds=1))
        await db.commit()
    assert await work_once() == "timed_out"
    ex = (await client.get(f"{API}/executions/{run['executions'][0]['execution_id']}")).json()
    assert ex["error_class"] == "TIMEOUT" and ex["attempts"][0]["exit_code"] == 124

    async def boom(*args, **kw):
        raise RuntimeError("upstream said token=pilot-secret-value and Authorization: Bearer abc.def.ghi")

    monkeypatch.setitem(runner.ENGINES, "sbom", (boom, "pilot-boom", "0"))
    run = await _launch_sbom(client, h, a)
    assert await work_once() == "failed"
    ex = (await client.get(f"{API}/executions/{run['executions'][0]['execution_id']}")).json()
    assert ex["error_class"] == "INTERNAL_ERROR"
    blob = json.dumps(ex)
    assert "pilot-secret-value" not in blob and "abc.def.ghi" not in blob and "[REDACTED]" in blob

    monkeypatch.delitem(runner.ENGINES, "sbom")  # adapter/binary missing on this worker
    run = await _launch_sbom(client, h, a)
    assert await work_once() == "unavailable"
    ex = (await client.get(f"{API}/executions/{run['executions'][0]['execution_id']}")).json()
    assert ex["error_class"] == "ENGINE_UNAVAILABLE" and ex["status_reason"]


# --------------------------------------------------------------------------- worker loss, cancel

class _Crash(Exception):
    pass


async def _expire_and_reap():
    async with AsyncSessionLocal() as db:
        await db.execute(update(Scan).where(Scan.status == "RUNNING")
                         .values(lease_expires_at=datetime.now(timezone.utc) - timedelta(seconds=5)))
        await db.commit()
    async with AsyncSessionLocal() as db:
        await IDBDurableQueue.recover_expired_leases(db, requeue_backoff_seconds=0)


async def _claim(worker):
    async with AsyncSessionLocal() as db:
        s = await IDBDurableQueue.claim_next_job(db, worker)
        return s.id, s.fencing_token


@pytest.mark.parametrize("crash_at", ["preflight", "after_output"])
async def test_worker_killed_mid_execution_yields_one_logical_result(client, owner, monkeypatch, crash_at):
    h = await owner_session(client)
    await import_snapshot(client, h)
    a = await make_asset(f"svc-kill-{crash_at}")
    await upload(client, h, a)
    run = await _launch_sbom(client, h, a)
    eid = run["executions"][0]["execution_id"]
    sid, tok = await _claim("worker-A")

    real_set_phase, real_commit = runner._set_phase, runner._commit
    if crash_at == "preflight":
        async def dying_phase(attempt_id, phase):
            if phase == "running":
                raise _Crash("worker A died before touching the input")
            return await real_set_phase(attempt_id, phase)
        monkeypatch.setattr(runner, "_set_phase", dying_phase)
    else:
        async def dying_commit(scan_id, token, rec, attempt, asset, outcome, duration_ms, cpu_ms=None):
            d = runner.storage_root() / "executions" / str(rec.id)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"attempt-{attempt.attempt_no}.json").write_bytes(outcome.output)  # output written...
            raise _Crash("...then worker A died before the DB commit")
        monkeypatch.setattr(runner, "_commit", dying_commit)
    with pytest.raises(_Crash):
        await runner.run_execution(sid, tok, "worker-A", None)
    monkeypatch.setattr(runner, "_set_phase", real_set_phase)
    monkeypatch.setattr(runner, "_commit", real_commit)

    await _expire_and_reap()
    sid2, tok2 = await _claim("worker-B")
    assert sid2 == sid and tok2 > tok
    assert await runner.run_execution(sid2, tok2, "worker-B", None) == "succeeded"
    # A late commit from worker A with its old token is fenced.
    ex = (await client.get(f"{API}/executions/{eid}")).json()
    assert ex["status"] == "succeeded" and ex["worker_id"] == "worker-B"
    assert [x["status"] for x in ex["attempts"]] == ["abandoned", "succeeded"]
    async with AsyncSessionLocal() as db:
        n = (await db.execute(select(func.count()).select_from(NormalizedFinding)
                              .where(NormalizedFinding.asset_id == a))).scalar()
        occ = (await db.execute(select(func.max(NormalizedFinding.occurrence_count))
                                .where(NormalizedFinding.asset_id == a))).scalar()
        obs = (await db.execute(select(func.count()).select_from(FindingObservation)
                                .where(FindingObservation.asset_id == a))).scalar()
    assert (n, occ, obs) == (4, 1, 4)  # one logical result


async def test_cancel_while_running_discards_the_result(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    a = await make_asset("svc-cancel-run")
    await upload(client, h, a)
    run = await _launch_sbom(client, h, a)
    eid = run["executions"][0]["execution_id"]
    sid, tok = await _claim("worker-C")
    r = await client.post(f"{API}/executions/{eid}/cancel", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert await runner.run_execution(sid, tok, "worker-C", None) == "fenced"
    ex = (await client.get(f"{API}/executions/{eid}")).json()
    assert ex["status"] == "cancelled" and ex["attempts"] == []  # never started: no attempt opened
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(NormalizedFinding))).scalar() == 0


# --------------------------------------------------------------------------- events, ICT day boundary

async def test_replay_over_250_events_without_gaps_or_duplicates(client, owner, monkeypatch):
    from backend.app.api import operations as ops
    from backend.app.core.event_bus import emit_event

    monkeypatch.setattr(ops, "POLL_SECONDS", 0.05)
    await owner_session(client)
    a = await make_asset("svc-events")
    for i in range(260):
        await emit_event("EXECUTION_QUEUED", f"pilot-test event {i}", target_id=a, details={"n": i})
    seen, cursor = [], 0
    while True:
        page = (await client.get(f"{API}/events", params={"after": cursor, "limit": 100})).json()
        seen += [e["id"] for e in page["items"]]
        cursor = page["cursor"]
        if not page["has_more"]:
            break
    assert len(seen) == 260 and len(set(seen)) == 260 and seen == sorted(seen)
    mid = seen[129]
    for _ in range(2):  # reconnecting twice with the same Last-Event-ID gives the same set
        r = await client.get(f"{API}/events/stream", params={"max_seconds": 2}, headers={"Last-Event-ID": str(mid)})
        ids = [int(x) for x in re.findall(r"^id: (\d+)$", r.text, flags=re.M)]
        assert ids == seen[130:]

    dev = await make_user("DEVELOPER", "dev-ev7")
    async with new_client() as d:
        await login(d, "dev-ev7", USER_PASSWORD)
        assert (await d.get(f"{API}/events", params={"after": 0})).json()["items"] == []  # not granted


async def test_ict_day_boundary_in_dashboard_and_filters(client, owner):
    await owner_session(client)
    a = await make_asset("svc-ict")
    from backend.app.api.console import ict_today
    today = ict_today()
    start = datetime(today.year, today.month, today.day, tzinfo=timezone(timedelta(hours=7))).astimezone(timezone.utc)
    async with AsyncSessionLocal() as db:
        s = Scan(asset_id=a, target_locator="fixture://pilot", status="COMPLETED")
        db.add(s)
        await db.flush()
        for n, at in enumerate((start - timedelta(seconds=1), start)):  # 16:59:59Z yesterday-ICT, 17:00:00Z today-ICT
            f = NormalizedFinding(scan_id=s.id, asset_id=a, fingerprint=uuid.uuid4().hex, scanner_engine="sbom",
                                  scanner_rule_id=f"PILOT-ICT-{n}", title=f"pilot ict {n}", description="synthetic",
                                  severity="LOW", original_severity="LOW", target_location="fixture://pilot")
            db.add(f)
            await db.flush()
            db.add(FindingObservation(finding_id=f.id, execution_id=uuid.uuid4(), asset_id=a, engine_id="sbom",
                                      outcome="new", observed_at=at))
        await db.commit()
    s = (await client.get(f"{API}/dashboard/summary")).json()
    assert s["findings_per_day"][-1]["new"] == 1 and s["findings_per_day"][-2]["new"] == 1
    t = (await client.get(f"{API}/findings", params={"outcome": "new", "day": today.isoformat()})).json()
    assert [x["scanner_rule_id"] for x in t["items"]] == ["PILOT-ICT-1"]


# --------------------------------------------------------------------------- report formats

def _pdf_structure_ok(data: bytes) -> list:
    """Minimal PDF parse: header, trailer, startxref -> xref table, every in-use offset is `N G obj`."""
    assert data.startswith(b"%PDF-1.") and data.rstrip().endswith(b"%%EOF")
    sx = int(re.findall(rb"startxref\s+(\d+)", data)[-1])
    assert data[sx:sx + 4] == b"xref"
    head = re.match(rb"xref\s+(\d+)\s+(\d+)\s+", data[sx:])
    first, count = int(head.group(1)), int(head.group(2))
    body = data[sx + head.end():]
    objs = []
    for i in range(count):
        off, gen, kind = body[i * 20:i * 20 + 18].split()
        if kind == b"n":
            num = first + i
            assert re.match(rb"%d\s+%d\s+obj" % (num, int(gen)), data[int(off):int(off) + 20]), num
            objs.append(num)
    return objs


async def test_report_formats_parse_validate_and_escape(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    a = await make_asset("svc-report-esc")
    await upload(client, h, a)
    run = await _launch_sbom(client, h, a)
    assert await work_once() == "succeeded"
    async with AsyncSessionLocal() as db:  # hostile text reaching the report through a finding title
        await db.execute(update(NormalizedFinding).where(NormalizedFinding.scanner_rule_id == "PILOT-TEST-0001")
                         .values(title='<script>alert("pilot")</script><img src=x onerror=1>'))
        await db.commit()
    rep = (await client.post(f"{API}/report-snapshots", headers=h,
                             json={"title": "Báo cáo <b>pilot</b>", "batch_id": run["batch_id"]})).json()
    get = lambda f: client.get(f"{API}/report-snapshots/{rep['id']}/download", params={"format": f})  # noqa: E731
    pdf, html, js = (await get("pdf")).content, (await get("html")).text, (await get("json")).json()
    assert len(_pdf_structure_ok(pdf)) >= 4
    assert "<script>" not in html and "&lt;script&gt;" in html and "<b>pilot</b>" not in html
    schema = {"template_version": str, "title": str, "generated_at_utc": str, "display_timezone": str,
              "scope": dict, "executive_summary": dict, "coverage": list, "changes_vs_previous": dict,
              "findings": list, "executions": list, "correlation_ids": list, "appendix_errors_exclusions": list,
              "redaction": str}
    for k, t in schema.items():
        assert isinstance(js[k], t), k
    for f in js["findings"]:
        assert {"id", "severity", "status", "evidence", "remediation", "last_verified_at"} <= set(f)
        assert set(f["evidence"]) >= {"execution_id", "output_sha256", "rule_digest"}
    assert js["executive_summary"]["open_total"] == 4 and len(js["findings"]) == 4


# --------------------------------------------------------------------------- packaging: legacy DB, backup

LEGACY_DB = ROOT / "noospire.db"


@pytest.mark.skipif(not LEGACY_DB.exists(), reason="audit-era database not present on this host")
def test_legacy_database_upgrades_in_place_and_backup_restores():
    tmp = Path(tempfile.mkdtemp(prefix="noospire-legacy-"))
    db = tmp / "legacy.db"
    shutil.copy2(LEGACY_DB, db)  # never touch the original
    before = sqlite3.connect(db)
    assets_before = before.execute("select count(*) from assets").fetchone()[0]
    before.close()
    env = {**os.environ, "SENTINEL_DATABASE_URL": f"sqlite+aiosqlite:///{db.as_posix()}", "SENTINEL_ENV": "test",
           "SENTINEL_STORAGE_DIR": str(tmp / "storage"), "SENTINEL_SEED_DEMO_DATA": "false"}
    py = os.sys.executable
    r = subprocess.run([py, "-m", "backend.app.cli", "init-db"], cwd=str(ROOT), env=env, capture_output=True,
                       text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    con = sqlite3.connect(db)
    tables = {x[0] for x in con.execute("select name from sqlite_master where type='table'")}
    assert {"execution_records", "schedule_slots", "finding_observations", "notifications",
            "report_snapshots"} <= tables
    assert con.execute("select count(*) from assets").fetchone()[0] == assets_before  # data untouched
    con.close()
    out = tmp / "backup.db"
    r = subprocess.run([py, "-m", "backend.app.cli", "backup", "--out", str(out)], cwd=str(ROOT), env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and out.exists(), r.stderr
    r = subprocess.run([py, "-m", "backend.app.cli", "restore-check", "--backup", str(out)], cwd=str(ROOT), env=env,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
