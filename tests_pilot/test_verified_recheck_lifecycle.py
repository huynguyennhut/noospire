"""Canonical lifecycle, evidence-backed closure and compatibility retest safety."""

import uuid

import pytest
from sqlalchemy import update

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.finding import NormalizedFinding

from tests_pilot.conftest import make_asset
from tests_pilot.test_m3_sbom_flow import import_snapshot, launch, owner_session, upload, work_once

API = "/api/v1"


async def test_manual_triage_cannot_claim_engine_verified_resolution(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("manual-resolution")
    art = await upload(client, h, asset)
    await launch(client, h, asset, art["id"])
    assert await work_once() == "succeeded"
    finding = (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["items"][0]
    fid = finding["id"]
    before = (await client.get(f"{API}/findings/{fid}/history")).json()
    response = await client.post(f"{API}/findings/{fid}/triage", headers=h, json={"status": "RESOLVED"})
    assert response.status_code == 409
    assert (await client.get(f"{API}/findings/{fid}")).json()["status"] == finding["status"]
    assert (await client.get(f"{API}/findings/{fid}/history")).json() == before
    claimed = await client.post(f"{API}/findings/{fid}/triage", headers=h, json={"status": "FIXED"})
    assert claimed.status_code == 200 and claimed.json()["status"] == "FIXED_PENDING_RETEST"


@pytest.mark.parametrize("state", ["NEW", "NEEDS_TRIAGE", "ASSIGNED", "IN_PROGRESS", "FIXED_PENDING_RETEST", "FIXED"])
async def test_successful_equivalent_recheck_resolves_each_active_state(client, owner, state):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("canonical-recheck")
    art = await upload(client, h, asset)
    await launch(client, h, asset, art["id"])
    assert await work_once() == "succeeded"
    findings = (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["items"]
    fid = next(f["id"] for f in findings if f["scanner_rule_id"] == "PILOT-TEST-0001")
    if state == "FIXED":
        # Historical rows remain untouched on disk but share pending-retest semantics.
        async with AsyncSessionLocal() as db:
            await db.execute(update(NormalizedFinding).where(NormalizedFinding.id == uuid.UUID(fid)).values(status="FIXED"))
            await db.commit()
    else:
        assert (await client.post(f"{API}/findings/{fid}/triage", headers=h, json={"status": state})).status_code == 200
    # Claimed fixes still count as open until the corresponding check verifies them.
    open_findings = (await client.get(f"{API}/findings", params={"asset_id": str(asset), "status_group": "open"})).json()
    assert fid in {f["id"] for f in open_findings["items"]}
    pending_summary = (await client.get(f"{API}/assets/{asset}/summary")).json()
    assert pending_summary["open_findings"] == 4 and pending_summary["fixed_findings"] == 0
    await upload(client, h, asset, "sbom_fixed.cdx.json")
    response = await client.post(f"{API}/findings/{fid}/retest", headers={**h, "Idempotency-Key": "canonical"})
    assert response.status_code == 202 and response.json()["status"] == state
    replay = await client.post(f"{API}/findings/{fid}/recheck", headers={**h, "Idempotency-Key": "canonical"})
    assert replay.status_code == 200 and replay.json()["execution_id"] == response.json()["execution_id"]
    assert await work_once() == "succeeded"
    finding = (await client.get(f"{API}/findings/{fid}")).json()
    assert finding["status"] == "RESOLVED"
    assert finding["evidence"]["verified_fixed_by_execution"] == response.json()["execution_id"]
    history = (await client.get(f"{API}/findings/{fid}/history")).json()
    assert history["observations"][-1]["outcome"] == "fixed"
    assert history["observations"][-1]["status_after"] == "RESOLVED"
    summary = (await client.get(f"{API}/assets/{asset}/summary")).json()
    assert summary["fixed_findings"] == 3 and summary["open_findings"] == 1


async def test_claimed_fix_reopens_when_the_same_check_still_matches(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    asset = await make_asset("unfixed-claim")
    art = await upload(client, h, asset)
    await launch(client, h, asset, art["id"])
    assert await work_once() == "succeeded"
    finding = (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["items"][0]
    fid = finding["id"]
    await client.post(f"{API}/findings/{fid}/triage", headers=h, json={"status": "FIXED_PENDING_RETEST"})
    assert (await client.post(f"{API}/findings/{fid}/retest", headers=h)).status_code == 202
    assert await work_once() == "succeeded"
    assert (await client.get(f"{API}/findings/{fid}")).json()["status"] == "REOPENED"
