"""Platform authentication and asset authorization using synthetic ASGI fixtures only."""

import asyncio
import uuid

import pytest
from sqlalchemy import func, select

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import decode_access_token, get_password_hash
from backend.app.models.base import AdminAuditLog
from backend.app.models.user import User, UserRole
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


@pytest.mark.parametrize("environment", ["development", "test", "production"])
@pytest.mark.parametrize("wrong_password", ["REDACTED-ROTATE-ME", "ValidOwnerPassword123!"])
async def test_historical_test_passwords_cannot_authenticate_another_password(
    client, owner, monkeypatch, environment, wrong_password
):
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    response = await login(client, settings.SOLE_OWNER_EMAIL, wrong_password)
    assert response.status_code == 401
    assert "access_token" not in response.json()
    assert settings.SESSION_COOKIE_NAME not in client.cookies
    # The real password still works, including in development/test.
    assert (await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)).status_code == 200


async def test_login_checks_the_stored_hash_instead_of_a_password_denylist(client, owner):
    uid = await make_user("DEVELOPER", "hash-only")
    synthetic_password = "ValidOwnerPassword123!"
    async with AsyncSessionLocal() as db:
        user = await db.get(User, uid)
        user.hashed_password = get_password_hash(synthetic_password)
        await db.commit()
    assert (await login(client, "hash-only", synthetic_password)).status_code == 200


@pytest.mark.parametrize("environment", ["development", "test", "production"])
async def test_http_bootstrap_is_opt_in_and_requires_token_on_every_request(client, monkeypatch, environment):
    monkeypatch.setattr(settings, "ENVIRONMENT", environment)
    monkeypatch.setattr(settings, "BOOTSTRAP_TOKEN", None)
    body = {"username": "pilot-owner", "email": settings.SOLE_OWNER_EMAIL, "password": OWNER_PASSWORD}
    assert (await client.post(f"{API}/auth/bootstrap", json=body)).status_code == 404
    token = "bootstrap-" + uuid.uuid4().hex
    monkeypatch.setattr(settings, "BOOTSTRAP_TOKEN", token)
    for headers in ({}, {"X-Bootstrap-Token": "wrong"}):
        assert (await client.post(f"{API}/auth/bootstrap", json=body, headers=headers)).status_code == 403
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(User))).scalar_one() == 0
    response = await client.post(f"{API}/auth/bootstrap", json=body, headers={"X-Bootstrap-Token": token})
    assert response.status_code == 201
    assert (await client.post(f"{API}/auth/bootstrap", json=body,
                              headers={"X-Bootstrap-Token": token})).status_code == 409


async def test_concurrent_bootstrap_creates_one_owner_and_one_audit_record(client, monkeypatch):
    token = "bootstrap-" + uuid.uuid4().hex
    monkeypatch.setattr(settings, "BOOTSTRAP_TOKEN", token)
    body = {"username": "pilot-owner", "email": settings.SOLE_OWNER_EMAIL, "password": OWNER_PASSWORD}
    async with new_client() as second:
        responses = await asyncio.gather(
            client.post(f"{API}/auth/bootstrap", json=body, headers={"X-Bootstrap-Token": token}),
            second.post(f"{API}/auth/bootstrap", json=body, headers={"X-Bootstrap-Token": token}),
        )
    assert sorted(r.status_code for r in responses) == [201, 409]
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(User))).scalar_one() == 1
        assert (await db.execute(select(func.count()).select_from(AdminAuditLog)
                                 .where(AdminAuditLog.action == "SYSTEM_BOOTSTRAP"))).scalar_one() == 1


@pytest.mark.parametrize("role", [r.value for r in UserRole])
async def test_role_and_legacy_superuser_flag_never_replace_asset_grants(client, owner, role):
    visible = await make_asset("explicit-grant")
    hidden = await make_asset("outside-grant")
    username = "legacy-" + role.lower()
    uid = await make_user(role, username)
    async with AsyncSessionLocal() as db:
        user = await db.get(User, uid)
        user.is_superuser = True  # legacy rows must not bypass immutable owner identity
        await db.commit()

    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    owner_headers = csrf_headers(client)
    async with new_client() as account:
        response = await login(account, username, USER_PASSWORD)
        assert response.status_code == 200
        profile = response.json()["user"]
        assert not profile["is_owner"] and not profile["is_superuser"] and not profile["is_ultra_admin"]
        assert decode_access_token(response.json()["access_token"])["sub"] == str(uid)
        assert (await account.get(f"{API}/assets")).json()["total"] == 0
        assert (await account.get(f"{API}/assets/{hidden}")).status_code == 404
        assert (await account.get(f"{API}/auth/audit")).status_code == 403
        assert (await account.get(f"{API}/settings")).status_code == 403
        assert (await account.get(f"{API}/baselines")).status_code == 403

        grant = await client.post(f"{API}/auth/users/{uid}/grants", headers=owner_headers,
                                  json={"asset_id": str(visible), "permissions": "READ"})
        assert grant.status_code == 201
        assert {x["id"] for x in (await account.get(f"{API}/assets")).json()["items"]} == {str(visible)}
        assert (await account.get(f"{API}/assets/{visible}")).status_code == 200
        assert (await account.get(f"{API}/assets/{hidden}")).status_code == 404
        assert (await client.delete(f"{API}/auth/users/{uid}/grants/{grant.json()['id']}",
                                    headers=owner_headers)).status_code == 204
        assert (await account.get(f"{API}/assets/{visible}")).status_code == 404

    # Owner access is preserved without needing a grant.
    assert (await client.get(f"{API}/assets")).json()["total"] == 2
    assert (await client.get(f"{API}/auth/me")).json()["is_owner"] is True


async def test_ungranted_scan_is_opaque_before_scope_validation_or_egress(client, owner, monkeypatch):
    from backend.app.core.ssrf import SSRFProtector

    def unexpected_network(*args, **kwargs):
        pytest.fail("an unauthorized scan reached target resolution")

    monkeypatch.setattr(SSRFProtector, "validate_target", unexpected_network)
    hidden = await make_asset("no-egress")
    await make_user("DEVELOPER", "no-scan-grant")
    async with new_client() as account:
        await login(account, "no-scan-grant", USER_PASSWORD)
        response = await account.post(f"{API}/scans", headers=csrf_headers(account),
                                       json={"asset_id": str(hidden)})
        assert response.status_code == 404


async def test_scan_grant_cannot_retarget_or_administer_the_asset_registry(client, owner):
    asset = await make_asset("registered-target")
    uid = await make_user("DEVELOPER", "scan-only")
    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    assert (await client.post(f"{API}/auth/users/{uid}/grants", headers=csrf_headers(client),
                              json={"asset_id": str(asset), "permissions": "READ,SCAN"})).status_code == 201
    async with new_client() as account:
        await login(account, "scan-only", USER_PASSWORD)
        h = csrf_headers(account)
        for method, url, payload in (
            ("PUT", f"/assets/{asset}", {"target_locator": "https://other.pilot-test.invalid/"}),
            ("POST", f"/assets/{asset}/verify", {"verification_type": "ADMIN_OVERRIDE"}),
            ("DELETE", f"/assets/{asset}", None),
            ("POST", "/assets", {"name": "new-target", "target_locator": "https://new.pilot-test.invalid/", "asset_type": "WEB_APP"}),
        ):
            response = await account.request(method, API + url, json=payload, headers=h)
            assert response.status_code == 403, (method, url, response.text)
        assert (await account.get(f"{API}/assets/{asset}")).json()["target_locator"] == "https://registered-target.pilot-test.invalid/"
    # Ordinary owner editing still works without altering scope or contacting a target.
    response = await client.put(f"{API}/assets/{asset}", headers=csrf_headers(client), json={"name": "owner-renamed"})
    assert response.status_code == 200 and response.json()["name"] == "owner-renamed"


@pytest.mark.parametrize("permission,expected", [(None, 404), ("READ", 403), ("READ,SCAN", 200)])
async def test_emergency_stop_respects_target_grants(client, owner, permission, expected):
    from backend.app.models.scope import AssetAssessmentScope

    asset = await make_asset("stop-synthetic")
    uid = await make_user("DEVELOPER", "stop-grant")
    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    if permission:
        assert (await client.post(f"{API}/auth/users/{uid}/grants", headers=csrf_headers(client),
                                  json={"asset_id": str(asset), "permissions": permission})).status_code == 201
    async with new_client() as account:
        await login(account, "stop-grant", USER_PASSWORD)
        response = await account.post(f"{API}/assets/{asset}/emergency-stop", headers=csrf_headers(account))
        assert response.status_code == expected
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == asset))).scalars().all()
        assert bool(rows) is (expected == 200)
        if rows:
            assert rows[0].emergency_stop_active is True


async def _checklist_run(asset):
    from backend.app.core.checklist_seeder import seed_checklist_catalog
    from backend.app.models.checklist import ChecklistAssessmentRun, ChecklistResult

    async with AsyncSessionLocal() as db:
        await seed_checklist_catalog(db)
        run = ChecklistAssessmentRun(id=uuid.uuid4(), asset_id=asset, total_checks=1, status="COMPLETED")
        db.add(run)
        db.add(ChecklistResult(id=uuid.uuid4(), run_id=run.id, check_id="WEB-001", state="NEEDS_REVIEW",
                               evidence_payload={"source": "synthetic-checklist-fixture"}))
        await db.commit()
        return run.id


async def test_checklist_reads_review_and_launch_enforce_separate_asset_actions(client, owner, monkeypatch):
    from backend.app.core.scope_gate import ScopeValidator

    async def unexpected_preflight(*args, **kwargs):
        pytest.fail("unauthorized checklist launch reached target preflight")

    monkeypatch.setattr(ScopeValidator, "validate_preflight", unexpected_preflight)
    a, b = await make_asset("checklist-visible"), await make_asset("checklist-hidden")
    ra, rb = await _checklist_run(a), await _checklist_run(b)
    uid = await make_user("DEVELOPER", "checklist-reader")
    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    h = csrf_headers(client)
    grant = await client.post(f"{API}/auth/users/{uid}/grants", headers=h,
                              json={"asset_id": str(a), "permissions": "READ"})
    assert grant.status_code == 201
    async with new_client() as account:
        await login(account, "checklist-reader", USER_PASSWORD)
        ah = csrf_headers(account)
        for params in ({}, {"asset_id": str(b)}):
            runs = (await account.get(f"{API}/checklist/runs", params=params)).json()
            assert {r["id"] for r in runs} == ({str(ra)} if not params else set())
        for suffix in ("", "/results", "/metrics"):
            assert (await account.get(f"{API}/checklist/runs/{ra}{suffix}")).status_code == 200
            assert (await account.get(f"{API}/checklist/runs/{rb}{suffix}")).status_code == 404
        payload = {"state": "NOT_APPLICABLE", "review_notes": "synthetic manual review"}
        assert (await account.post(f"{API}/checklist/runs/{ra}/review/WEB-001", headers=ah, json=payload)).status_code == 403
        assert (await account.post(f"{API}/checklist/runs/{rb}/review/WEB-001", headers=ah, json=payload)).status_code == 404
        for asset, expected in ((a, 403), (b, 404)):
            assert (await account.post(f"{API}/checklist/runs", headers=ah,
                                       json={"asset_id": str(asset)})).status_code == expected

        assert (await client.post(f"{API}/auth/users/{uid}/grants", headers=h,
                                  json={"asset_id": str(a), "permissions": "TRIAGE"})).status_code == 201
        response = await account.post(f"{API}/checklist/runs/{ra}/review/WEB-001", headers=ah, json=payload)
        assert response.status_code == 200 and response.json()["reviewed_by"] == "checklist-reader"
        assert (await client.delete(f"{API}/auth/users/{uid}/grants/{grant.json()['id']}", headers=h)).status_code == 204
    assert {r["id"] for r in (await client.get(f"{API}/checklist/runs")).json()} == {str(ra), str(rb)}


@pytest.mark.parametrize("authenticated", [False, True])
async def test_retired_schedule_routes_never_read_or_dispatch_jobs(client, owner, authenticated):
    # Retired route handlers have no DB/worker dependency and always give migration guidance.
    if authenticated:
        await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    target = uuid.uuid4()
    for method, path in (("GET", ""), ("POST", ""), ("GET", f"/{target}"),
                         ("GET", f"/{target}/status"), ("POST", f"/{target}/trigger"),
                         ("PUT", f"/{target}/toggle"), ("DELETE", f"/{target}")):
        response = await client.request(method, f"{API}/schedules{path}", headers=csrf_headers(client))
        assert response.status_code == 410
        assert response.json()["replacement"] == "/api/v1/monitor-schedules"
        assert response.json()["request_id"] == response.headers["x-request-id"]
