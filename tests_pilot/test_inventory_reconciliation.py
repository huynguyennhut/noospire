"""Reconciliation and fixture-denial regressions on synthetic data only."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.inventory_reconciliation import (
    PRIMARY_TARGET, acceptance_fixture_index, fixture_provenance, reconcile, usable_proof,
)
from backend.app.models.asset import Asset
from backend.app.models.proof import AssetOwnershipProof
from backend.app.models.scan import Scan, ScanBatch
from tests_pilot.conftest import USER_PASSWORD, csrf_headers, login, make_asset, make_user, new_client
from tests_pilot.test_m3_sbom_flow import owner_session

API = "/api/v1"


async def fixture_asset(seed=False):
    if seed:
        aid, target = uuid.uuid4(), "https://unverified-seed.pilot-test.invalid/"
    else:
        raw, target = next(iter(acceptance_fixture_index().items()))
        aid = uuid.UUID(raw)
    async with AsyncSessionLocal() as db:
        db.add(Asset(id=aid, name="Synthetic fixture", target_locator=target, verification_status="VERIFIED"))
        if seed:
            db.add(AssetOwnershipProof(asset_id=aid, method="HTTP_WELL_KNOWN", status="VERIFIED",
                                      challenge_token="synthetic", verified_at=datetime.now(timezone.utc),
                                      proof_data={"initial_seed": True}))
        await db.commit()
    return aid


def test_fixture_origin_requires_source_match_not_hostname_heuristics():
    fixtures = acceptance_fixture_index()
    assert len(fixtures) == 379
    raw, target = next(iter(fixtures.items()))
    assert fixture_provenance(raw, target) == "ACCEPTANCE_FIXTURE_379"
    assert fixture_provenance(raw, "https://changed.pilot-test.invalid/") == "ACCEPTANCE_FIXTURE_ID_RETARGETED"
    assert fixture_provenance(uuid.uuid4(), target) == "ACCEPTANCE_FIXTURE_LOCATOR"
    assert fixture_provenance(uuid.uuid4(), "https://service-9999.empire.edu.vn") is None
    assert fixture_provenance(uuid.uuid4(), "https://retry-test.local").startswith("LEGACY_TEST_LOCATOR:")
    assert fixture_provenance(uuid.uuid4(), "https://asset-renamed-123abc.example.com/").startswith("LEGACY_TEST_LOCATOR:")
    assert fixture_provenance(uuid.uuid4(), "https://unrelated.example.com/") is None
    from backend.app.core.ultra_planner import UltraScanPlanner
    assert {r["environment"] for r in UltraScanPlanner().generate_acceptance_fixture_379()} == {"SYNTHETIC"}


def test_seed_and_expired_proofs_do_not_become_ownership_evidence():
    proof = {"status": "VERIFIED", "verified_at": datetime.now(timezone.utc), "proof_data": {}}
    assert usable_proof(proof)
    assert not usable_proof({**proof, "proof_data": {"initial_seed": True}})
    assert not usable_proof({**proof, "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
    assert not usable_proof({**proof, "verified_at": None})
    assert not usable_proof({**proof, "expires_at": "malformed"})


def test_report_separates_owner_designation_provenance_and_coverage_without_secret_values():
    root, seeded, unknown = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    rows = [{"id": root, "target_locator": PRIMARY_TARGET, "environment": "PRODUCTION", "verification_status": "VERIFIED"},
            {"id": seeded, "target_locator": "https://seed.pilot-test.invalid/", "environment": "PRODUCTION"},
            {"id": unknown, "target_locator": "https://unconfirmed.empire.edu.vn/?token=hidden", "environment": "PRODUCTION",
             "auth_profile": {"secret_ref": "never-echo-reference-value", "token": "never-echo-token"},
             "assessment_policy": {"health_check": {"url": "https://user:password@unconfirmed.empire.edu.vn/status?key=secret"}}}]
    r = reconcile(rows, [{"asset_id": root, "proof_data": {"initial_seed": True}}], [])
    assert r["counts"] == {"total": 3, "OWNER_DESIGNATED_PRIMARY": 1, "SEEDED_OR_TEST": 1, "UNKNOWN_OR_UNVERIFIED": 1}
    assert r["owner_designated_production_targets"] == [PRIMARY_TARGET]
    assert not r["production_scope_is_complete"]
    assert r["assessment_authorization"] == {
        "scope": "ALL_EMPIRE_OWNED_INFRASTRUCTURE",
        "per_run_approval_required": False,
        "primary_target_is_authorization_limit": False,
        "inventory_membership_requires_evidence": True,
    }
    assert all(not a["automated_assessment_ready"] for a in r["assets"])
    raw = json.dumps(r)
    for secret in ["never-echo-reference-value", "never-echo-token", "password", "token=hidden", "key=secret"]:
        assert secret not in raw
    assert r["credential_reference_locations"][0]["approval_verified"] is False
    candidate = next(a for a in r["assets"] if a["asset_id"] == unknown)
    assert candidate["classification"] == "UNKNOWN_OR_UNVERIFIED"
    assert "Estate-wide authorization exists" in candidate["scope_basis"]
    assert not candidate["automated_assessment_ready"]


@pytest.mark.parametrize("target", ["https://empire.edu.vn/evil", "https://evil.empire.edu.vn/", "https://empire.edu.vn/?token=x", "https://user:pw@empire.edu.vn/"])
def test_root_designation_does_not_expand_to_other_paths_hosts_or_credentials(target):
    row = reconcile([{"id": str(uuid.uuid4()), "target_locator": target}], [], [])["assets"][0]
    assert not row["owner_designation_matches"]


async def test_reconciliation_is_owner_only_and_does_not_mutate_asset_flags(client, owner):
    aid = await fixture_asset(seed=True)
    await owner_session(client)
    r = await client.get(f"{API}/assets/reconciliation")
    assert r.status_code == 200 and r.json()["counts"]["total"] == 1
    assert (await client.get(f"{API}/assets/{aid}")).json()["verification_state"] == "UNPROVEN"
    async with AsyncSessionLocal() as db:
        assert (await db.get(Asset, aid)).verification_status == "VERIFIED"
    await make_user("ADMIN", "inventory-outsider")
    async with new_client() as outsider:
        await login(outsider, "inventory-outsider", USER_PASSWORD)
        assert (await outsider.get(f"{API}/assets/reconciliation")).status_code == 403


@pytest.mark.parametrize("seed", [False, True])
async def test_single_batch_and_defensive_dispatch_reject_unreconciled_inventory_before_egress(client, owner, monkeypatch, seed):
    from backend.app.core.ssrf import SSRFProtector
    monkeypatch.setattr(SSRFProtector, "validate_target", lambda *a, **k: pytest.fail("unreconciled inventory reached DNS"))
    aid = await fixture_asset(seed=seed)
    headers = await owner_session(client)
    for path, body in [("/scans", {"asset_id": str(aid)}),
                       ("/scans/batch", {"targets": [str(aid)], "profile": "BASELINE"}),
                       ("/executions", {"asset_id": str(aid), "engine": "tls_health"})]:
        r = await client.post(API + path, headers=headers, json=body)
        assert r.status_code == 409, (path, r.text)
    plan = await client.post(f"{API}/plans/preview", headers=headers,
                             json={"selection": {"kind": "assets", "asset_ids": [str(aid)]}})
    assert plan.status_code == 200
    assert all(i["decision"] == "skip" for i in plan.json()["items"])
    assert {i["reason_code"] for i in plan.json()["items"]} == {"SEEDED_OWNERSHIP_NOT_VERIFIED" if seed else "SYNTHETIC_INVENTORY"}
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(Scan))).scalar() == 0
        assert (await db.execute(select(func.count()).select_from(ScanBatch))).scalar() == 0


async def test_stale_tls_execution_is_blocked_in_worker_before_network(client, owner, monkeypatch):
    from backend.app.engines.runner import _run_tls
    from backend.app.engines import tls_health
    aid = await fixture_asset()
    async def never_measure(*a, **k):
        pytest.fail("fixture reached HTTP/TLS")
    monkeypatch.setattr(tls_health, "measure", never_measure)
    async with AsyncSessionLocal() as db:
        asset = await db.get(Asset, aid)
        outcome = await _run_tls(None, None, asset, 10)
    assert outcome.status == "skipped" and outcome.error_class == "SYNTHETIC_INVENTORY"


@pytest.mark.parametrize("kind", ["fixture", "seed", "legacy"])
async def test_scope_and_legacy_worker_recheck_inventory_before_target_egress(client, owner, monkeypatch, kind):
    from backend.app.core.dispatcher import AsyncWorkerDispatcher
    from backend.app.core.scope_gate import ScopeEnforcementError, ScopeValidator
    from backend.app.core.ssrf import SSRFProtector
    from backend.app.scanners.base import CancellationToken

    monkeypatch.setattr(SSRFProtector, "validate_target", lambda *a, **k: pytest.fail("fixture reached egress validation"))
    aid = await fixture_asset(seed=kind != "fixture")
    expected = "SEEDED_OWNERSHIP_NOT_VERIFIED" if kind == "seed" else "SYNTHETIC_INVENTORY"
    scan_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        if kind == "legacy":
            asset = await db.get(Asset, aid)
            asset.target_locator = "https://retry-test.local"
            await db.commit()
        with pytest.raises(ScopeEnforcementError) as exc:
            await ScopeValidator.validate_preflight(aid, db=db)
        assert exc.value.reason == expected
        asset = await db.get(Asset, aid)
        db.add(Scan(id=scan_id, asset_id=aid, target_locator=asset.target_locator,
                    engine="nuclei", profile="BASELINE", status="QUEUED"))
        await db.commit()
    dispatcher = AsyncWorkerDispatcher(max_concurrent=1)
    await dispatcher._run_scan(scan_id, CancellationToken())
    async with AsyncSessionLocal() as db:
        row = await db.get(Scan, scan_id)
        assert row.status == "FAILED" and row.quality_status == "PARTIAL_COVERAGE"
        assert row.error_message.startswith(expected + ":")


@pytest.mark.parametrize("scope", ["FIXTURE_379", "EMPIRE_ESTATE_379", "ALL"])
async def test_ultra_never_creates_assets_from_fixture_or_empty_inventory(client, owner, scope):
    headers = await owner_session(client)
    response = await client.post(f"{API}/scans/ultra", headers=headers, json={"scope": scope})
    assert response.status_code == 409, response.text
    preview = await client.get(f"{API}/scans/ultra/fixture-379")
    assert preview.status_code == 200
    assert len(preview.json()["items"]) == 379
    assert {row["environment"] for row in preview.json()["items"]} == {"SYNTHETIC"}
    async with AsyncSessionLocal() as db:
        for model in (Asset, Scan, ScanBatch):
            assert (await db.execute(select(func.count()).select_from(model))).scalar() == 0


async def test_ultra_rejects_persisted_fixtures_and_missing_ids_without_writes(client, owner):
    await fixture_asset()
    headers = await owner_session(client)
    for scope, expected in [("ALL", 409), ([str(uuid.uuid4())], 404), (["bad-id"], 400)]:
        r = await client.post(f"{API}/scans/ultra", headers=headers, json={"scope": scope})
        assert r.status_code == expected, r.text
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(Asset))).scalar() == 1
        assert (await db.execute(select(func.count()).select_from(ScanBatch))).scalar() == 0


async def test_ultra_grants_and_idempotent_recovery_are_scoped_before_dispatch(client, owner, monkeypatch):
    from backend.app.api import scans

    dispatched = []
    class LocalDispatcher:
        async def batch_dispatch_scans(self, ids, batch_id):
            dispatched.append((ids, batch_id))
    monkeypatch.setattr(scans, "get_dispatcher", lambda: LocalDispatcher())
    visible, hidden = await make_asset("ultra-visible"), await make_asset("ultra-hidden")
    uid = await make_user("DEVELOPER", "ultra-grantee")
    headers = await owner_session(client)
    assert (await client.post(f"{API}/auth/users/{uid}/grants", headers=headers,
                              json={"asset_id": str(visible), "permissions": "READ,SCAN"})).status_code == 201
    hidden_body = {"scope": [str(hidden)], "engines": ["nuclei"], "idempotency_key": "hidden-batch"}
    assert (await client.post(f"{API}/scans/ultra", headers=headers, json=hidden_body)).status_code == 201
    async with new_client() as account:
        await login(account, "ultra-grantee", USER_PASSWORD)
        h = csrf_headers(account)
        assert (await account.post(f"{API}/scans/ultra", headers=h, json=hidden_body)).status_code == 404
        # A permitted requested target cannot recover an unrelated hidden batch.
        assert (await account.post(f"{API}/scans/ultra", headers=h,
                                   json={**hidden_body, "scope": [str(visible)]})).status_code == 404
        body = {"scope": [str(visible)], "engines": ["nuclei"], "idempotency_key": "visible-batch"}
        created = await account.post(f"{API}/scans/ultra", headers=h, json=body)
        assert created.status_code == 201, created.text
        replay = await account.post(f"{API}/scans/ultra", headers=h, json=body)
        assert replay.status_code == 201 and replay.json()["idempotency_recovered"]
        assert replay.json()["batch_id"] == created.json()["batch_id"]
    assert len(dispatched) == 2  # each authorized batch dispatches once
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(Asset))).scalar() == 2


def test_cli_is_read_only_and_refuses_database_output(tmp_path):
    database, output = tmp_path / "inventory.db", tmp_path / "report.json"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE assets(id TEXT, target_locator TEXT, environment TEXT, verification_status TEXT, assessment_policy TEXT, auth_profile TEXT)")
        db.execute("INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), PRIMARY_TARGET, "PRODUCTION", "VERIFIED", "{}", "{}"))
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    cmd = [sys.executable, "scripts/reconcile_production_inventory.py", "--database", str(database), "--output"]
    r = subprocess.run([*cmd, str(output)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    result = json.loads(output.read_text())
    assert result["sqlite_connection_changes"] == 0 and result["network_requests"] == 0
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    assert subprocess.run([*cmd, str(database)], capture_output=True).returncode == 2
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
