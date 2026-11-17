"""Milestone 5 · data contracts behind the six operator screens, through the real API, real queue
claim and defensive runner (in-process), disposable DB, synthetic labelled data only."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.asset import Asset
from backend.app.models.base import AdminAuditLog
from backend.app.models.lifecycle import Notification
from backend.app.core.config import settings
from tests_pilot.conftest import USER_PASSWORD, csrf_headers, login, make_asset, make_finding, make_user, new_client
from tests_pilot.test_m3_sbom_flow import API, import_snapshot, owner_session, upload, work_once

OWNER_ID = settings.SOLE_OWNER_ACCOUNT_ID


async def _drain():
    out = []
    while (st := await work_once()) is not None:
        out.append(st)
    return out


async def _run_sbom(client, h, asset):
    r = await client.post(f"{API}/runs", headers=h,
                          json={"selection": {"kind": "assets", "asset_ids": [str(asset)]}, "engines": ["sbom"]})
    assert r.status_code == 202, r.text
    assert await _drain() == ["succeeded"]
    return r.json()


async def _findings(client, asset):
    items = (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["items"]
    return {x["scanner_rule_id"]: x for x in items}


async def _granted_dev(client, h, asset, perms="READ,SCAN", name="dev-m5"):
    uid = await make_user("DEVELOPER", name)
    g = await client.post(f"{API}/auth/users/{uid}/grants", headers=h,
                          json={"asset_id": str(asset), "permissions": perms})
    assert g.status_code == 201, g.text
    return uid


# --------------------------------------------------------------------------- findings lifecycle

async def test_observations_diff_recheck_fixed_and_reopened(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("svc-life")
    dev = await _granted_dev(client, h, asset)
    await upload(client, h, asset)
    run1 = await _run_sbom(client, h, asset)
    d1 = (await client.get(f"{API}/runs/{run1['batch_id']}/diff")).json()
    assert d1["counts"]["new"] == 4 and sum(d1["counts"].values()) == 4

    f = await _findings(client, asset)
    fid = f["PILOT-TEST-0001"]["id"]
    hist = (await client.get(f"{API}/findings/{fid}/history")).json()
    assert hist["first_seen_at"] and hist["last_seen_at"] and hist["last_verified_at"]
    assert hist["source"]["engine"] == "sbom" and hist["confidence"] == "high"
    assert [(c["field"], c["new"], c["actor"]) for c in hist["changes"]] == [("status", "NEW", "noospire-engine")]
    assert [o["outcome"] for o in hist["observations"]] == ["new"]

    # Developer fixes and uploads a patched SBOM; Recheck reruns the same control on it.
    await upload(client, h, asset, "sbom_fixed.cdx.json")
    r = await client.post(f"{API}/findings/{fid}/recheck", headers={**h, "Idempotency-Key": "rc-1"})
    assert r.status_code == 202, r.text
    rc = r.json()
    assert rc["status"] == "NEW"  # recheck itself never changes the finding
    again = await client.post(f"{API}/findings/{fid}/recheck", headers={**h, "Idempotency-Key": "rc-1"})
    assert again.status_code == 200 and again.json()["execution_id"] == rc["execution_id"]
    assert await _drain() == ["succeeded"]
    d2 = (await client.get(f"{API}/runs/{rc['batch_id']}/diff")).json()["counts"]
    assert d2["fixed"] == 3 and d2["changed_scope"] == 1 and d2["new"] == 0
    f = await _findings(client, asset)
    assert f["PILOT-TEST-0001"]["status"] == "RESOLVED" and f["PILOT-TEST-0004"]["status"] == "NEW"
    hist = (await client.get(f"{API}/findings/{fid}/history")).json()
    assert [o["outcome"] for o in hist["observations"]] == ["new", "fixed"]
    assert hist["changes"][-1]["new"] == "RESOLVED" and hist["changes"][-1]["execution_id"] == rc["execution_id"]

    # Regression: vulnerable SBOM again -> reopened, with notifications to owner and granted dev.
    await upload(client, h, asset)
    run3 = await _run_sbom(client, h, asset)
    d3 = (await client.get(f"{API}/runs/{run3['batch_id']}/diff")).json()["counts"]
    assert d3["reopened"] == 3 and d3["unchanged"] == 1
    async with AsyncSessionLocal() as db:
        kinds = {(n.user_id, n.kind) for n in (await db.execute(select(Notification))).scalars()}
    assert (OWNER_ID, "finding_reopened") in kinds and (str(dev), "finding_reopened") in kinds
    assert (OWNER_ID, "finding_new") in kinds and (str(dev), "finding_new") in kinds

    # Run tree: module -> asset -> engine -> attempt -> evidence
    tree = (await client.get(f"{API}/runs/{run3['batch_id']}/tree")).json()
    eng = tree["modules"][0]["assets"][0]["engines"][0]
    assert eng["engine_id"] == "sbom" and eng["attempts"][0]["status"] == "succeeded"
    assert eng["evidence"]["output_sha256"] and len(eng["evidence"]["findings"]) == 4

    # Today's results (ICT day) list all three runs with their diffs.
    today = (await client.get(f"{API}/runs")).json()
    assert len(today["runs"]) == 3 and today["totals"]["new"] == 4 and today["totals"]["reopened"] == 3


async def test_recheck_rules_and_legacy_retest_alias(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("svc-rc")
    legacy = await make_finding(asset, "legacy fixture finding")  # engine 'fixture': no approved control
    r = await client.post(f"{API}/findings/{legacy}/recheck", headers=h)
    assert r.status_code == 409 and "No approved defensive control" in r.json()["detail"]
    r = await client.post(f"{API}/findings/{legacy}/retest", headers=h)
    assert r.status_code == 409  # old live-GET retest is gone; it never marks FIXED by itself

    await upload(client, h, asset)
    await _run_sbom(client, h, asset)
    fid = (await _findings(client, asset))["PILOT-TEST-0002"]["id"]
    r = await client.post(f"{API}/findings/{fid}/retest", headers=h)
    assert r.status_code == 202 and r.json()["execution_id"]
    # Already queued: a second recheck points to the same execution.
    r2 = await client.post(f"{API}/findings/{fid}/recheck", headers=h)
    assert r2.status_code == 200 and r2.json()["execution_id"] == r.json()["execution_id"]

    viewer = await _granted_dev(client, h, asset, perms="READ", name="dev-ro")
    async with new_client() as v:
        await login(v, "dev-ro", USER_PASSWORD)
        assert (await v.post(f"{API}/findings/{fid}/recheck", headers=csrf_headers(v))).status_code == 403
        assert (await v.get(f"{API}/findings/{fid}/history")).status_code == 200
    assert viewer


async def test_triage_is_in_change_log_and_failed_run_is_unavailable(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("svc-tri")
    await upload(client, h, asset)
    await _run_sbom(client, h, asset)
    fid = (await _findings(client, asset))["PILOT-TEST-0003"]["id"]
    r = await client.post(f"{API}/findings/{fid}/triage", headers=h,
                          json={"status": "IN_REMEDIATION", "comment": "ticket EMP-1 (synthetic)", "assignee": "dev-team"})
    assert r.status_code == 200
    hist = (await client.get(f"{API}/findings/{fid}/history")).json()
    tri = [c for c in hist["changes"] if c["actor"] == "pilot-owner"]
    assert {(c["field"], c["new"]) for c in tri} >= {("status", "IN_PROGRESS"), ("assignee", "dev-team")}
    assert hist["assignee"] == "dev-team"

    await upload(client, h, asset, raw=b"{broken")
    r = await client.post(f"{API}/runs", headers=h,
                          json={"selection": {"kind": "assets", "asset_ids": [str(asset)]}, "engines": ["sbom"]})
    assert await _drain() == ["failed"]
    d = (await client.get(f"{API}/runs/{r.json()['batch_id']}/diff")).json()["counts"]
    assert d["unavailable"] == 4 and d["fixed"] == 0  # nothing changes state on a failed check
    assert (await _findings(client, asset))["PILOT-TEST-0003"]["status"] == "IN_PROGRESS"
    async with AsyncSessionLocal() as db:
        n = (await db.execute(select(Notification).where(Notification.kind == "job_failed"))).scalars().all()
    assert {x.user_id for x in n} == {OWNER_ID}
    today = (await client.get(f"{API}/runs")).json()
    failed = [x for x in today["runs"] if x["batch_id"] == r.json()["batch_id"]][0]
    assert failed["skip_or_fail"][0]["status"] == "failed" and failed["skip_or_fail"][0]["reason"]


# --------------------------------------------------------------------------- notifications

async def test_notifications_are_per_user(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("svc-notif")
    await _granted_dev(client, h, asset, name="dev-n")
    await upload(client, h, asset)
    await _run_sbom(client, h, asset)
    mine = (await client.get(f"{API}/notifications")).json()
    # Owner launched the run: 4 new-finding alerts + 1 "job succeeded" for the actor.
    assert mine["unread"] == 5
    assert sorted(n["kind"] for n in mine["items"]) == ["finding_new"] * 4 + ["job_succeeded"]
    assert all(n["link"].startswith("/findings/?finding=") for n in mine["items"] if n["kind"] == "finding_new")
    owner_nid = mine["items"][0]["id"]
    async with new_client() as d:
        await login(d, "dev-n", USER_PASSWORD)
        dh = csrf_headers(d)
        dn = (await d.get(f"{API}/notifications")).json()
        assert dn["unread"] == 4
        # Someone else's notification: rejected as not found.
        assert (await d.post(f"{API}/notifications/{owner_nid}/read", headers=dh)).status_code == 404
        assert (await d.delete(f"{API}/notifications/{owner_nid}", headers=dh)).status_code == 404
        assert (await d.post(f"{API}/notifications/{dn['items'][0]['id']}/read", headers=dh)).json()["read"] is True
        assert (await d.delete(f"{API}/notifications/{dn['items'][1]['id']}", headers=dh)).status_code == 204
        assert (await d.post(f"{API}/notifications/read-all", headers=dh)).json()["marked"] == 2
        assert (await d.get(f"{API}/notifications/unread-count")).json()["unread"] == 0
        assert len((await d.get(f"{API}/notifications")).json()["items"]) == 3
    # The owner's inbox is untouched by the developer's actions.
    assert (await client.get(f"{API}/notifications/unread-count")).json()["unread"] == 5


# --------------------------------------------------------------------------- dashboard & module hub

async def test_dashboard_summary_states_and_scope(client, owner):
    h = await owner_session(client)
    empty = (await client.get(f"{API}/dashboard/summary")).json()
    assert empty["data_state"] == "unknown" and empty["last_real_data_at"] is None
    assert len(empty["window"]["ict_days"]) == 7 and empty["display_timezone"] == "Asia/Ho_Chi_Minh"

    await import_snapshot(client, h)
    a = await make_asset("svc-dash-a")
    b = await make_asset("svc-dash-b")
    await upload(client, h, a)
    await upload(client, h, b)
    await _run_sbom(client, h, a)
    s = (await client.get(f"{API}/dashboard/summary")).json()
    assert s["new_today"] == 4 and s["risk"]["open_total"] == 4
    assert s["findings_per_day"][-1]["new"] == 4 and sum(d["new"] for d in s["findings_per_day"]) == 4
    assert s["data_state"] == "partial" and "no worker online" in s["data_state_reasons"]
    svc = {x["name"]: x for x in s["services"]["items"]}
    assert svc["svc-dash-a"]["status"] == "unknown" and svc["svc-dash-a"]["reason"] == "no approved health endpoint"
    assert s["services"]["counts"]["up"] == 0  # nothing is shown healthy without a measurement

    await _granted_dev(client, h, b, perms="READ", name="dev-dash")
    async with new_client() as d:
        await login(d, "dev-dash", USER_PASSWORD)
        ds = (await d.get(f"{API}/dashboard/summary")).json()
        assert ds["new_today"] == 0 and ds["risk"]["open_total"] == 0
        assert [x["name"] for x in ds["services"]["items"]] == ["svc-dash-b"]


async def test_module_hub_lists_every_module_and_reconciles_scope(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    a = await make_asset("svc-hub-a")
    b = await make_asset("svc-hub-b")
    async with AsyncSessionLocal() as db:
        await db.execute(update(Asset).where(Asset.id == b).values(empire_module="API_SERVICES"))
        await db.commit()
    await upload(client, h, a)
    await _run_sbom(client, h, a)
    hub = (await client.get(f"{API}/modules/hub")).json()
    mods = {m["module"]: m for m in hub["modules"]}
    assert len(mods) == 6 and mods["WEB_APPLICATION"]["assets"] == 0  # zero-asset modules still listed
    assert hub["assets_in_scope"] == hub["assets_in_modules"] + hub["assets_unassigned"] == 2
    sm = mods["STUDENT_MANAGEMENT"]
    assert sm["assets"] == 1 and sm["open_total"] == 4 and sm["coverage_24h"] == {"covered": 1, "total": 1}
    assert sm["links"]["findings"] == "/findings/?empire_module=STUDENT_MANAGEMENT"
    await _granted_dev(client, h, b, perms="READ", name="dev-hub")
    async with new_client() as d:
        await login(d, "dev-hub", USER_PASSWORD)
        dh = (await d.get(f"{API}/modules/hub")).json()
        dm = {m["module"]: m for m in dh["modules"]}
        assert dh["assets_in_scope"] == 1 and dm["API_SERVICES"]["assets"] == 1
        assert dm["STUDENT_MANAGEMENT"]["assets"] == 0 and dm["STUDENT_MANAGEMENT"]["open_total"] == 0


# --------------------------------------------------------------------------- history

async def test_selective_hide_with_preview_confirmation_and_audit(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("svc-hist")
    await upload(client, h, asset)
    r1 = await _run_sbom(client, h, asset)
    await _run_sbom(client, h, asset)
    hist = (await client.get(f"{API}/history", params={"asset_id": str(asset)})).json()
    assert hist["total"] == 2
    target = {"batch_id": r1["batch_id"]}
    pv = (await client.post(f"{API}/history/hide/preview", headers=h, json=target)).json()
    assert pv["would_hide"] == 1
    bad = await client.post(f"{API}/history/hide", headers=h, json={**target, "reason": "test run", "confirm_count": 5})
    assert bad.status_code == 409
    ok = await client.post(f"{API}/history/hide", headers=h, json={**target, "reason": "test run", "confirm_count": 1})
    assert ok.status_code == 200 and ok.json()["hidden"] == 1
    assert (await client.get(f"{API}/history", params={"asset_id": str(asset)})).json()["total"] == 1
    assert (await client.get(f"{API}/executions", params={"asset_id": str(asset)})).json()["total"] == 1
    assert len(await _findings(client, asset)) == 4  # evidence and findings are kept
    async with AsyncSessionLocal() as db:
        logs = (await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "HISTORY_HIDE"))).scalars().all()
    assert len(logs) == 1 and "count=1" in logs[0].details

    await _granted_dev(client, h, asset, name="dev-hist")
    async with new_client() as d:
        await login(d, "dev-hist", USER_PASSWORD)
        assert (await d.post(f"{API}/history/hide/preview", headers=csrf_headers(d), json=target)).status_code == 403
    eid = r1["executions"][0]["execution_id"]
    assert (await client.post(f"{API}/history/unhide", headers=h, json={"execution_ids": [eid]})).json()["restored"] == 1
    assert (await client.get(f"{API}/history", params={"asset_id": str(asset)})).json()["total"] == 2


# --------------------------------------------------------------------------- reports

async def test_report_snapshot_is_reproducible_and_scoped(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("svc-rep")
    await upload(client, h, asset)
    run = await _run_sbom(client, h, asset)
    r = await client.post(f"{API}/report-snapshots", headers=h, json={"title": "Báo cáo pilot-test", "batch_id": run["batch_id"]})
    assert r.status_code == 201, r.text
    rep = r.json()
    assert rep["template_version"] == "noospire-pilot-report/1.2" and rep["finding_count"] == 4
    assert rep["execution_ids"] == [run["executions"][0]["execution_id"]] and rep["correlation_ids"]

    got = {}
    for fmt in ("json", "html", "pdf"):
        d = await client.get(f"{API}/report-snapshots/{rep['id']}/download", params={"format": fmt})
        assert d.status_code == 200 and d.headers["x-content-sha256"] == rep["files"][fmt]["sha256"]
        assert d.headers["x-snapshot-sha256"] == rep["snapshot_sha256"]
        assert d.headers["cache-control"] == "private, no-store"
        got[fmt] = d.content
    assert got["pdf"].startswith(b"%PDF")
    html = got["html"].decode()
    assert rep["snapshot_sha256"] in html and "noospire-pilot-report/1.2" in html and "Asia/Ho_Chi_Minh" in html
    doc = __import__("json").loads(got["json"])
    assert set(doc) >= {"executive_summary", "scope", "coverage", "changes_vs_previous", "findings",
                        "appendix_errors_exclusions", "redaction"}
    inline = await client.get(f"{API}/report-snapshots/{rep['id']}/download", params={"format": "html", "inline": True})
    assert inline.headers["content-disposition"].startswith("inline")

    # Finding status changes afterwards: the stored report does not change.
    fid = (await _findings(client, asset))["PILOT-TEST-0001"]["id"]
    await client.post(f"{API}/findings/{fid}/triage", headers=h, json={"status": "FALSE_POSITIVE", "comment": "synthetic"})
    again = await client.get(f"{API}/report-snapshots/{rep['id']}/download", params={"format": "pdf"})
    assert again.content == got["pdf"]

    # A second report of the same scope records the change vs the previous one.
    r2 = (await client.post(f"{API}/report-snapshots", headers=h,
                            json={"title": "Báo cáo pilot-test 2", "batch_id": run["batch_id"]})).json()
    assert r2["previous_snapshot_id"] == rep["id"] and r2["snapshot_sha256"] != rep["snapshot_sha256"]

    est = (await client.post(f"{API}/report-snapshots", headers=h, json={"title": "estate"})).json()
    await _granted_dev(client, h, asset, perms="READ", name="dev-rep")
    async with new_client() as d:
        await login(d, "dev-rep", USER_PASSWORD)
        dh = csrf_headers(d)
        assert (await d.post(f"{API}/report-snapshots", headers=dh,
                             json={"title": "x", "asset_ids": [str(asset)]})).status_code == 403  # no REPORT grant
        assert (await d.post(f"{API}/report-snapshots", headers=dh, json={"title": "x"})).status_code == 403
        assert (await d.get(f"{API}/report-snapshots/{est['id']}/download")).status_code == 404
        ids = {x["id"] for x in (await d.get(f"{API}/report-snapshots")).json()}
        assert rep["id"] in ids and est["id"] not in ids
        assert (await d.get(f"{API}/report-snapshots/{rep['id']}/download", params={"format": "json"})).status_code == 200
    # Tampered file is refused, not served.
    from backend.app.models.lifecycle import ReportSnapshot
    async with AsyncSessionLocal() as db:
        rs = await db.get(ReportSnapshot, uuid.UUID(rep["id"]))
        path = rs.files["html"]["path"]
    with open(path, "ab") as fh:
        fh.write(b"<!-- tampered -->")
    assert (await client.get(f"{API}/report-snapshots/{rep['id']}/download", params={"format": "html"})).status_code == 409


async def test_findings_drilldown_filters_match_dashboard(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("svc-drill")
    await upload(client, h, asset)
    run = await _run_sbom(client, h, asset)
    s = (await client.get(f"{API}/dashboard/summary")).json()
    today = s["window"]["ict_days"][-1]
    new_today = (await client.get(f"{API}/findings", params={"outcome": "new", "day": today})).json()
    assert new_today["total"] == s["new_today"] == 4
    for sev, n in s["risk"]["open_by_severity"].items():
        got = (await client.get(f"{API}/findings", params={"status_group": "open", "severity": sev})).json()["total"]
        assert got == n
    by_exec = (await client.get(f"{API}/findings",
                                params={"execution_id": run["executions"][0]["execution_id"]})).json()
    assert by_exec["total"] == 4
    yesterday = (await client.get(f"{API}/findings", params={"outcome": "new", "day": "2000-01-01"})).json()
    assert yesterday["total"] == 0
