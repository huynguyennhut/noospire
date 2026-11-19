"""Real API/queue/runner regressions on disposable data, never customer targets."""
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.base import AdminAuditLog
from backend.app.models.defensive import AdvisorySnapshot
from tests_pilot.conftest import USER_PASSWORD, csrf_headers, login, make_asset, make_finding, make_user, new_client
from tests_pilot.test_m3_sbom_flow import DATA, import_snapshot, launch, owner_session, upload, work_once

API = "/api/v1"


async def stage(client, headers, records=None):
    raw = (DATA / "advisories_pilot_v1.json").read_bytes() if records is None else json.dumps(records).encode()
    response = await client.post(f"{API}/threat-intel/advisory-snapshots",
                                params={"source": "synthetic workflow", "version_label": "staged-lab", "activate": False},
                                content=raw, headers={**headers, "Content-Type": "application/json"})
    assert response.status_code == 201, response.text
    return response.json()


async def activate(client, headers, sid, active=True):
    return await client.put(f"{API}/threat-intel/advisory-snapshots/{sid}/activation", headers=headers,
                            json={"active": active, "reason": "Synthetic reviewed change; token=do-not-publish"})


async def test_pending_asset_can_analyze_artifacts_without_network_admission(client, owner):
    headers = await owner_session(client)
    asset = await make_asset("offline-only", verified=False)
    metadata = (await client.get(f"{API}/assets/{asset}")).json()
    assert metadata["artifact_analysis_eligible"] is True
    assert metadata["assessment_eligible"] is False
    await import_snapshot(client, headers)
    art = await upload(client, headers, asset)
    assert (await launch(client, headers, asset, art["id"])).status_code == 202
    assert await work_once() == "succeeded"
    # Offline admission must not enable customer egress.
    denied = await launch(client, headers, asset, None, engine="public_web")
    assert denied.status_code == 409


@pytest.mark.parametrize("seed", [False, True])
async def test_known_fixture_provenance_still_denies_artifact_analysis(client, owner, seed):
    from tests_pilot.test_inventory_reconciliation import fixture_asset
    headers = await owner_session(client)
    asset = await fixture_asset(seed)
    metadata = (await client.get(f"{API}/assets/{asset}")).json()
    assert metadata["artifact_analysis_eligible"] is False
    art = await upload(client, headers, asset)
    assert (await launch(client, headers, asset, art["id"])).status_code == 409


async def test_historical_execution_keeps_detected_findings_after_rescan(client, owner):
    headers = await owner_session(client)
    await import_snapshot(client, headers)
    asset = await make_asset("history-persisted")
    art = await upload(client, headers, asset)
    first = (await launch(client, headers, asset, art["id"])).json()["execution_id"]
    assert await work_once() == "succeeded"
    original = (await client.get(f"{API}/executions/{first}")).json()
    logs = (await client.get(f"{API}/executions/{first}/logs", params={"size": 1})).json()
    assert logs["total"] >= 2 and logs["pages"] == logs["total"]
    assert logs["items"][0]["event_type"] == "EXECUTION_ATTEMPT_STARTED"
    assert (await client.get(f"{API}/executions/{first}/logs", params={"page": 2, "size": 1})).json()["items"]
    output = (await client.get(f"{API}/executions/{first}/output")).content
    second = (await launch(client, headers, asset, art["id"])).json()["execution_id"]
    assert await work_once() == "succeeded"
    assert (await client.get(f"{API}/executions/{first}")).json()["finding_ids"] == original["finding_ids"]
    old = (await client.get(f"{API}/findings", params={"execution_id": first, "observation_group": "detected"})).json()
    assert old["total"] == 4
    assert set(original["finding_ids"]) == {f["id"] for f in old["items"]}
    assert (await client.get(f"{API}/findings", params={"scan_id": original["scan_id"]})).json()["total"] == 4
    assert (await client.get(f"{API}/executions/{first}/output")).content == output
    fixed = await upload(client, headers, asset, "sbom_fixed.cdx.json")
    third = (await launch(client, headers, asset, fixed["id"])).json()["execution_id"]
    assert await work_once() == "succeeded"
    assert (await client.get(f"{API}/findings", params={"execution_id": third, "observation_group": "detected"})).json()["total"] == 0
    assert (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["total"] == 4
    assert (await client.get(f"{API}/executions/{second}")).json()["finding_ids"] == original["finding_ids"]
    unrelated = await make_finding(asset, "UNRELATED-LAB-FINDING")
    report = await client.post(f"{API}/report-snapshots", headers=headers,
                               json={"title": "Historical lab run", "batch_id": original["batch_id"]})
    assert report.status_code == 201, report.text
    frozen = (await client.get(f"{API}/report-snapshots/{report.json()['id']}/download", params={"format": "json"})).json()
    assert len(frozen["findings"]) == 4
    assert str(unrelated) not in {f["id"] for f in frozen["findings"]}
    exported = await client.post(f"{API}/reports/generate", headers=headers,
                                 json={"scan_id": original["scan_id"], "asset_id": str(asset), "formats": ["json"]})
    assert exported.status_code == 201, exported.text
    legacy = (await client.get(f"{API}/reports/{exported.json()['id']}/download", params={"format": "json"})).json()
    assert len(legacy["findings"]) == 4


async def test_stage_activate_disable_and_rollback_preserve_evidence(client, owner):
    headers = await owner_session(client)
    original = await import_snapshot(client, headers)
    records = json.loads((DATA / "advisories_pilot_v1.json").read_bytes())
    records.append({"id": "SYNTHETIC-NEXT-1", "affected": [{"package": {"ecosystem": "PyPI", "name": "new-lab-package"}, "versions": ["1.0"]}]})
    candidate = await stage(client, headers, records)
    assert not candidate["is_active"]
    rows = (await client.get(f"{API}/threat-intel/advisory-snapshots")).json()
    assert [r["id"] for r in rows if r["is_active"]] == [original["id"]]
    assert (await activate(client, headers, candidate["id"])).status_code == 200
    assert (await activate(client, headers, original["id"])).status_code == 200
    rows = (await client.get(f"{API}/threat-intel/advisory-snapshots")).json()
    assert [r["id"] for r in rows if r["is_active"]] == [original["id"]]
    asset = await make_asset("disabled-rules")
    art = await upload(client, headers, asset)
    await launch(client, headers, asset, art["id"])
    assert await work_once() == "succeeded"
    assert (await activate(client, headers, original["id"], False)).status_code == 200
    await launch(client, headers, asset, art["id"])
    assert await work_once() == "unavailable"
    items = (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["items"]
    assert len(items) == 4 and all(f["status"] == "NEW" for f in items)
    async with AsyncSessionLocal() as db:
        actions = (await db.execute(select(AdminAuditLog).where(AdminAuditLog.action == "ADVISORY_SNAPSHOT_ACTIVATION"))).scalars().all()
        assert len(actions) == 3
        assert all("do-not-publish" not in a.details for a in actions)


async def test_tampered_snapshot_activation_is_atomic_and_owner_only(client, owner):
    headers = await owner_session(client)
    original = await import_snapshot(client, headers)
    records = [{"id": "SYNTHETIC-OTHER", "affected": [{"package": {"ecosystem": "PyPI", "name": "other"}, "versions": ["1"]}]}]
    candidate = await stage(client, headers, records)
    async with AsyncSessionLocal() as db:
        row = await db.get(AdvisorySnapshot, candidate["id"])
        Path(row.storage_path).write_bytes((DATA / "advisories_pilot_v1.json").read_bytes())
    response = await activate(client, headers, candidate["id"])
    assert response.status_code == 409 and "integrity" in response.text.lower()
    rows = (await client.get(f"{API}/threat-intel/advisory-snapshots")).json()
    assert [r["id"] for r in rows if r["is_active"]] == [original["id"]]
    await make_user("DEVELOPER", "cannot-activate")
    async with new_client() as developer:
        await login(developer, "cannot-activate", USER_PASSWORD)
        assert (await activate(developer, csrf_headers(developer), original["id"], False)).status_code == 403
    assert (await activate(client, {}, original["id"], False)).status_code == 403


async def test_public_web_findings_have_durable_recheck(client, owner, monkeypatch):
    from tests_pilot.test_public_web_monitor import approved_asset, fake_transport
    headers = await owner_session(client)
    asset = await approved_asset("web-recheck-lab")
    fake_transport(monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
    first = (await launch(client, headers, asset, None, engine="public_web")).json()["execution_id"]
    assert await work_once() == "succeeded"
    ex = (await client.get(f"{API}/executions/{first}")).json()
    fid = ex["finding_ids"][0]
    response = await client.post(f"{API}/findings/{fid}/recheck", headers=headers)
    assert response.status_code == 202, response.text
    assert (await client.get(f"{API}/executions/{response.json()['execution_id']}")).json()["engine_id"] == "public_web"


async def test_daily_schedule_uses_real_server_slot_and_can_be_paused(client, owner):
    headers = await owner_session(client)
    asset = await make_asset("daily-artifact-lab", verified=False)
    response = await client.post(f"{API}/monitor-schedules", headers=headers,
                                json={"name": "Daily synthetic SBOM", "selection": {"kind": "assets", "asset_ids": [str(asset)]},
                                      "engines": ["sbom"], "interval_minutes": 1440})
    assert response.status_code == 201, response.text
    schedule = response.json()
    assert schedule["next_run_at"][11:16] == "00:00" and schedule["interval_minutes"] == 1440
    paused = await client.patch(f"{API}/monitor-schedules/{schedule['id']}", headers=headers,
                                json={"is_active": False, "expected_revision": schedule["revision"]})
    assert paused.status_code == 200 and not paused.json()["is_active"]


@pytest.mark.parametrize("state", ["FALSE_POSITIVE", "ACCEPTED_RISK"])
async def test_dismissal_needs_a_reason_and_cannot_forge_resolution(client, owner, state):
    headers = await owner_session(client)
    asset = await make_asset("triage-reason-lab")
    fid = await make_finding(asset, "synthetic triage")
    assert (await client.post(f"{API}/findings/{fid}/triage", headers=headers, json={"status": state})).status_code == 422
    accepted = await client.post(f"{API}/findings/{fid}/triage", headers=headers,
                                 json={"status": state, "comment": "Synthetic reviewed exception; token=private-lab-value"})
    assert accepted.status_code == 200 and accepted.json()["status"] == state
    assert "private-lab-value" not in accepted.text


async def test_report_scope_cannot_expand_via_mismatched_scan_or_unknown_batch(client, owner):
    from backend.app.models.finding import NormalizedFinding
    headers = await owner_session(client)
    allowed = await make_asset("report-allowed")
    hidden = await make_asset("report-hidden")
    fid = await make_finding(hidden, "unreadable lab record")
    async with AsyncSessionLocal() as db:
        scan_id = (await db.get(NormalizedFinding, fid)).scan_id
    assert (await client.post(f"{API}/reports/generate", headers=headers,
                             json={"asset_id": str(allowed), "scan_id": str(scan_id)})).status_code == 422
    assert (await client.post(f"{API}/reports/generate", headers=headers,
                             json={"batch_id": str(uuid.uuid4())})).status_code == 404
    uid = await make_user("DEVELOPER", "report-limited")
    await client.post(f"{API}/auth/users/{uid}/grants", headers=headers,
                      json={"asset_id": str(allowed), "permissions": "READ,REPORT"})
    async with new_client() as developer:
        await login(developer, "report-limited", USER_PASSWORD)
        response = await developer.post(f"{API}/reports/generate", headers=csrf_headers(developer),
                                        json={"asset_id": str(allowed), "scan_id": str(scan_id)})
        assert response.status_code == 404


def test_pdf_preserves_long_text_hashes_and_page_bounds(tmp_path):
    """Inspect actual PDF text and coordinates, not a mocked renderer."""
    import shutil
    import subprocess
    from xml.etree import ElementTree
    from backend.app.reporting.pilot_report import render_pdf

    converter = shutil.which("pdftotext")
    if not converter:
        pytest.skip("Poppler pdftotext is required for PDF layout acceptance")
    title = ("Synthetic <literal> & long title " * 15) + "END_TITLE"
    remediation = ("Complete remediation instructions must wrap and remain visible. " * 20) + "END_FIX"
    finding = {"severity": "MEDIUM", "status": "NEW", "title": title,
               "asset": "Synthetic lab", "location": "pkg:pypi/example", "last_verified_at": None,
               "remediation": remediation, "owner": None, "assignee": None,
               "evidence": {"input_sha256": "a" * 64, "output_sha256": "b" * 64,
                            "rule_digest": "c" * 64, "execution_id": str(uuid.uuid4())}}
    snap = {"title": title, "generated_at_local": "2026-11-17 ICT", "generated_at_utc": "2026-11-17T00:00:00Z",
            "template_version": "synthetic-pdf-test", "scope": {"kind": "assets", "window_days": 7},
            "coverage": [], "findings": [finding, finding],
            "executive_summary": {"open_total": 2, "open_by_severity": {"MEDIUM": 2},
                                  "new_since_previous": 0, "fixed_since_previous": 0,
                                  "reopened_since_previous": 0, "errors_or_exclusions": 1,
                                  "coverage": {"assets_with_successful_check": 1, "assets_in_scope": 1}},
            "appendix_errors_exclusions": [{"asset": "Synthetic lab", "engine": "sbom", "status": "unavailable",
                                           "reason": ("Full reason must remain visible. " * 15) + "END_REASON"}],
            "redaction": "Synthetic data only."}
    pdf = render_pdf(snap, "d" * 64)
    assert pdf == render_pdf(snap, "d" * 64)
    path = tmp_path / "long-report.pdf"
    path.write_bytes(pdf)
    text = subprocess.run([converter, str(path), "-"], check=True, capture_output=True, text=True).stdout
    for marker in ("END_TITLE", "END_FIX", "END_REASON", "<literal>", "d" * 64, "a" * 64, "b" * 64):
        assert marker in text
    bbox = subprocess.run([converter, "-bbox", str(path), "-"], check=True, capture_output=True).stdout
    root = ElementTree.fromstring(bbox)
    pages = root.findall(".//{http://www.w3.org/1999/xhtml}page")
    assert len(pages) >= 2
    for page in pages:
        for word in page.findall(".//{http://www.w3.org/1999/xhtml}word"):
            assert 39 <= float(word.attrib["xMin"]) <= float(word.attrib["xMax"]) <= float(page.attrib["width"]) - 39
