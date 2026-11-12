"""Milestone 3 · slice 1 through the real API, durable queue claim and worker runner
(in-process), disposable DB. Process-level restart is covered in test_m3_restart.py."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, update

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.queue import IDBDurableQueue
from backend.app.engines import runner
from backend.app.models.scan import Scan
from tests_pilot.conftest import (
    OWNER_PASSWORD,
    USER_PASSWORD,
    csrf_headers,
    login,
    make_asset,
    make_user,
    new_client,
)

API = "/api/v1"
DATA = Path(__file__).parent / "data"
WORKER = "pilot-test-worker"


async def work_once(worker_id: str = WORKER) -> str | None:
    """One real worker iteration: atomic DB claim + defensive runner."""
    async with AsyncSessionLocal() as db:
        scan = await IDBDurableQueue.claim_next_job(db, worker_id)
        if scan is None:
            return None
        sid, tok = scan.id, scan.fencing_token
    return await runner.run_execution(sid, tok, worker_id, None)


async def owner_session(client):
    r = await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    assert r.status_code == 200
    return csrf_headers(client)


async def import_snapshot(client, h):
    r = await client.post(f"{API}/threat-intel/advisory-snapshots",
                          params={"source": "pilot-test synthetic OSV", "version_label": "pilot-v1"},
                          content=(DATA / "advisories_pilot_v1.json").read_bytes(),
                          headers={**h, "content-type": "application/json"})
    assert r.status_code == 201, r.text
    return r.json()


async def upload(client, h, asset_id, name="sbom_vulnerable.cdx.json", raw: bytes | None = None):
    r = await client.post(f"{API}/assets/{asset_id}/artifacts", params={"kind": "sbom", "filename": name},
                          content=raw if raw is not None else (DATA / name).read_bytes(),
                          headers={**h, "content-type": "application/json"})
    assert r.status_code == 201, r.text
    return r.json()


async def launch(client, h, asset_id, artifact_id, key=None, engine="sbom"):
    headers = dict(h)
    if key:
        headers["Idempotency-Key"] = key
    body = {"asset_id": str(asset_id), "engine": engine}
    if artifact_id:
        body["artifact_id"] = artifact_id
    return await client.post(f"{API}/executions", json=body, headers=headers)


async def test_sbom_end_to_end_findings_evidence_report(client, owner):
    asset = await make_asset("svc-sbom")
    h = await owner_session(client)
    snap = await import_snapshot(client, h)
    assert snap["record_count"] == 5 and snap["is_active"] and len(snap["digest"]) == 64
    art = await upload(client, h, asset)

    r = await launch(client, h, asset, art["id"])
    assert r.status_code == 202
    body = r.json()
    eid = body["execution_id"]
    assert body["status"] == "queued" and body["planned_executions"] == 1 and body["batch_id"]
    assert body["worker"]["ready"] is False and "queued" in body["worker"]["reason"]

    assert await work_once() == "succeeded"
    ex = (await client.get(f"{API}/executions/{eid}")).json()
    assert ex["status"] == "succeeded" and ex["finding_count"] == 4
    assert ex["driver"] == "noospire-sbom-native" and ex["execution_mode"] == "native"
    assert ex["rules"]["digest"] == snap["digest"] and ex["input"]["sha256"] == art["sha256"]
    assert ex["summary"]["components_evaluated"] == 5 and ex["summary"]["components_not_evaluated"] == 2
    assert [a["status"] for a in ex["attempts"]] == ["succeeded"]
    assert ex["attempts"][0]["phase"] == "reporting" and ex["attempts"][0]["worker_id"] == WORKER
    assert ex["timestamps_utc"]["finished_at"] and ex["duration_ms"] is not None
    assert len(ex["finding_ids"]) == 4

    out = await client.get(f"{API}/executions/{eid}/output")
    assert out.status_code == 200 and out.headers["x-content-sha256"] == ex["output"]["sha256"]
    doc = out.json()
    assert doc["execution_id"] == eid and doc["rules"]["digest"] == snap["digest"] and len(doc["matches"]) == 4

    f = (await client.get(f"{API}/findings/{ex['finding_ids'][0]}")).json()
    assert f["evidence"]["execution_id"] == eid and f["evidence"]["output_sha256"] == ex["output"]["sha256"]
    findings = (await client.get(f"{API}/findings", params={"scan_id": ex["scan_id"]})).json()
    assert findings["total"] == 4
    assert {x["scanner_rule_id"] for x in findings["items"]} == {
        "PILOT-TEST-0001", "PILOT-TEST-0002", "PILOT-TEST-0003", "PILOT-TEST-0004"}

    rep = await client.post(f"{API}/reports/generate", headers=h,
                            json={"title": "pilot sbom", "scan_id": ex["scan_id"], "asset_id": str(asset),
                                  "formats": ["json", "html", "pdf"]})
    assert rep.status_code == 201, rep.text
    rid = rep.json()["id"]
    for fmt in ("json", "html", "pdf"):
        d = await client.get(f"{API}/reports/{rid}/download", params={"format": fmt})
        assert d.status_code == 200, (fmt, d.text[:200])
        assert d.headers["cache-control"] == "private, no-store" and len(d.headers["x-content-sha256"]) == 64
        if fmt == "pdf":
            assert d.content.startswith(b"%PDF")
        else:
            assert "PILOT-TEST-0001" in d.text


async def test_rescan_patched_marks_fixed_then_reopens(client, owner):
    asset = await make_asset("svc-lifecycle")
    h = await owner_session(client)
    await import_snapshot(client, h)
    art1 = await upload(client, h, asset)
    await launch(client, h, asset, art1["id"])
    assert await work_once() == "succeeded"

    art2 = await upload(client, h, asset, "sbom_fixed.cdx.json")
    e2 = (await launch(client, h, asset, art2["id"])).json()["execution_id"]
    assert await work_once() == "succeeded"
    assert (await client.get(f"{API}/executions/{e2}")).json()["finding_count"] == 0  # valid zero, evaluated
    items = (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["items"]
    status = {x["scanner_rule_id"]: x["status"] for x in items}
    # delta is absent from the patched SBOM: not observed -> unchanged, never "fixed" by omission.
    assert status == {"PILOT-TEST-0001": "FIXED", "PILOT-TEST-0002": "FIXED", "PILOT-TEST-0003": "FIXED",
                      "PILOT-TEST-0004": "NEW"}
    fixed = next(x for x in items if x["scanner_rule_id"] == "PILOT-TEST-0001")
    assert fixed["evidence"]["verified_fixed_by_execution"] == e2

    art3 = await upload(client, h, asset)
    await launch(client, h, asset, art3["id"])
    assert await work_once() == "succeeded"
    items = (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["items"]
    assert {x["scanner_rule_id"]: x["status"] for x in items}["PILOT-TEST-0001"] == "REOPENED"
    assert len(items) == 4  # deduplicated by fingerprint, history kept in occurrence/evidence


@pytest.mark.parametrize("raw,expected_status,expected_class", [
    (b"{broken json", "failed", "INPUT_PARSE_ERROR"),
    (json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.5", "components": []}).encode(), "skipped", "INPUT_EMPTY"),
    (json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "x", "version": "1"}]}).encode(), "skipped",
     "INPUT_NOT_EVALUABLE"),
])
async def test_bad_inputs_have_distinct_terminal_states(client, owner, raw, expected_status, expected_class):
    asset = await make_asset("svc-bad-" + uuid.uuid4().hex[:6])
    h = await owner_session(client)
    await import_snapshot(client, h)
    art = await upload(client, h, asset, "bad.json", raw=raw)
    eid = (await launch(client, h, asset, art["id"])).json()["execution_id"]
    assert await work_once() == expected_status
    ex = (await client.get(f"{API}/executions/{eid}")).json()
    assert ex["status"] == expected_status and ex["error_class"] == expected_class
    assert ex["status_reason"] and ex["finding_count"] is None and ex["output"]["available"] is False
    assert ex["attempts"][0]["error_class"] == expected_class
    assert (await client.get(f"{API}/executions/{eid}/output")).status_code == 404


async def test_no_advisory_snapshot_is_unavailable_and_tamper_detected(client, owner):
    asset = await make_asset("svc-norules")
    h = await owner_session(client)
    art = await upload(client, h, asset)
    eid = (await launch(client, h, asset, art["id"])).json()["execution_id"]
    assert await work_once() == "unavailable"
    ex = (await client.get(f"{API}/executions/{eid}")).json()
    assert ex["error_class"] == "RULES_UNAVAILABLE"

    await import_snapshot(client, h)
    # Tamper with the stored artifact after upload: hash check must fail the execution.
    Path(next((Path(settings.STORAGE_DIR) / "artifacts").glob(f"{art['sha256']}.bin"))).write_bytes(b"{}")
    eid2 = (await launch(client, h, asset, art["id"])).json()["execution_id"]
    assert await work_once() == "failed"
    assert (await client.get(f"{API}/executions/{eid2}")).json()["error_class"] == "INPUT_INTEGRITY"


async def test_idempotency_key_scoped_per_user_and_payload(client, owner):
    asset = await make_asset("svc-idem")
    h = await owner_session(client)
    await import_snapshot(client, h)
    art = await upload(client, h, asset)
    r1 = await launch(client, h, asset, art["id"], key="pilot-key-1")
    r2 = await launch(client, h, asset, art["id"], key="pilot-key-1")
    assert r1.status_code == 202 and r2.status_code == 200
    assert r1.json()["execution_id"] == r2.json()["execution_id"] and r2.json()["replayed"] is True
    other = await upload(client, h, asset, "sbom_fixed.cdx.json")
    r3 = await launch(client, h, asset, other["id"], key="pilot-key-1")
    assert r3.status_code == 409

    dev = await make_user("DEVELOPER", "dev-idem")
    async with new_client() as d:
        await login(d, "dev-idem", USER_PASSWORD)
        # No grant: authorization is checked before the key lookup -> 404, no leak of the owner's run.
        assert (await launch(d, csrf_headers(d), asset, art["id"], key="pilot-key-1")).status_code == 404
        await client.post(f"{API}/auth/users/{dev}/grants", headers=h,
                          json={"asset_id": str(asset), "permissions": "READ,SCAN"})
        r4 = await launch(d, csrf_headers(d), asset, art["id"], key="pilot-key-1")
        assert r4.status_code == 202 and r4.json()["execution_id"] != r1.json()["execution_id"]
    async with AsyncSessionLocal() as db:
        n = (await db.execute(select(Scan).where(Scan.asset_id == asset))).scalars().all()
    assert len(n) == 2  # one per (user, key); the double click created nothing extra


async def test_lost_lease_is_fenced_and_retry_succeeds(client, owner):
    asset = await make_asset("svc-fence")
    h = await owner_session(client)
    await import_snapshot(client, h)
    art = await upload(client, h, asset)
    eid = (await launch(client, h, asset, art["id"])).json()["execution_id"]

    async with AsyncSessionLocal() as db:
        scan = await IDBDurableQueue.claim_next_job(db, "worker-dies")
        sid, stale = scan.id, scan.fencing_token

    # The worker freezes after doing the work; meanwhile its lease expires and the reaper runs.
    # Its commit must then be fenced (lease lost DURING the run, not before it).
    real_set_phase = runner._set_phase

    async def freeze_then_reap(attempt_id, phase):
        await real_set_phase(attempt_id, phase)
        if phase == "reporting":
            async with AsyncSessionLocal() as db2:
                await db2.execute(update(Scan).where(Scan.id == sid).values(lease_expires_at=scan.leased_at))
                await db2.commit()
                assert await IDBDurableQueue.recover_expired_leases(db2, requeue_backoff_seconds=0) == 1

    runner._set_phase = freeze_then_reap
    try:
        assert await runner.run_execution(sid, stale, "worker-dies", None) == "fenced"
    finally:
        runner._set_phase = real_set_phase
    ex = (await client.get(f"{API}/executions/{eid}")).json()
    assert ex["finding_count"] is None and ex["attempts"][0]["status"] == "fenced"
    assert (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["total"] == 0

    st = await work_once("worker-healthy")
    assert st == "succeeded", (await client.get(f"{API}/executions/{eid}")).json()
    ex = (await client.get(f"{API}/executions/{eid}")).json()
    assert [a["status"] for a in ex["attempts"]] == ["fenced", "succeeded"]
    assert ex["attempts"][1]["fencing_token"] > ex["attempts"][0]["fencing_token"]
    assert ex["finding_count"] == 4


async def test_cancel_queued_execution_is_never_run(client, owner):
    asset = await make_asset("svc-cancel")
    h = await owner_session(client)
    await import_snapshot(client, h)
    art = await upload(client, h, asset)
    eid = (await launch(client, h, asset, art["id"])).json()["execution_id"]
    r = await client.post(f"{API}/executions/{eid}/cancel", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    assert await work_once() is None
    assert (await client.post(f"{API}/executions/{eid}/cancel", headers=h)).status_code == 409


async def test_execution_scope_for_grantees(client, owner):
    a = await make_asset("svc-granted-x")
    b = await make_asset("svc-hidden-x")
    h = await owner_session(client)
    await import_snapshot(client, h)
    art_b = await upload(client, h, b)
    eid_b = (await launch(client, h, b, art_b["id"])).json()["execution_id"]
    dev = await make_user("DEVELOPER", "dev-exec")
    await client.post(f"{API}/auth/users/{dev}/grants", headers=h, json={"asset_id": str(a), "permissions": "READ"})
    async with new_client() as d:
        await login(d, "dev-exec", USER_PASSWORD)
        dh = csrf_headers(d)
        assert (await d.get(f"{API}/executions/{eid_b}")).status_code == 404
        assert (await d.get(f"{API}/executions/{eid_b}/output")).status_code == 404
        assert (await d.get(f"{API}/executions")).json()["total"] == 0
        r = await d.post(f"{API}/assets/{a}/artifacts", params={"filename": "x.json"}, content=b"{}",
                         headers={**dh, "content-type": "application/json"})
        assert r.status_code == 403  # READ grant cannot upload/launch
        assert (await d.post(f"{API}/threat-intel/advisory-snapshots", params={"source": "x", "version_label": "y"},
                             content=b"[]", headers=dh)).status_code == 403


async def test_heartbeat_renews_lease_in_every_leased_phase(owner):
    """Regression: renewal used to require status RUNNING, so legacy jobs in INITIALIZING
    lost their lease after the first heartbeat and self-cancelled."""
    asset = await make_asset("svc-hb")
    async with AsyncSessionLocal() as db:
        db.add(Scan(asset_id=asset, target_locator="fixture://hb", status="QUEUED"))
        await db.commit()
        scan = await IDBDurableQueue.claim_next_job(db, "hb-worker")
        for phase in ("RUNNING", "INITIALIZING", "COMPLETING"):
            await db.execute(update(Scan).where(Scan.id == scan.id).values(status=phase))
            await db.commit()
            assert await IDBDurableQueue.renew_lease_heartbeat(db, scan.id, scan.fencing_token) is True, phase
        assert await IDBDurableQueue.renew_lease_heartbeat(db, scan.id, scan.fencing_token + 99) is False
