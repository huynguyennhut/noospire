"""Milestone 1 · one data source, one verified owner, object-scoped access."""

from __future__ import annotations

import uuid

import pytest

from backend.app.core.config import settings
from tests_pilot.conftest import (
    OWNER_PASSWORD,
    USER_PASSWORD,
    csrf_headers,
    login,
    make_asset,
    make_finding,
    make_user,
    new_client,
)

API = "/api/v1"


# --------------------------------------------------------------------------- probes / errors

async def test_empty_db_stays_empty_and_probes(client, owner):
    r = await client.get("/healthz/live")
    assert r.status_code == 200 and r.json()["status"] == "live"
    r = await client.get("/healthz/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok"

    assert (await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)).status_code == 200
    r = await client.get(f"{API}/assets")
    assert r.status_code == 200
    assert r.json()["total"] == 0, "boot must not create inventory"
    r = await client.get(f"{API}/findings")
    assert r.json()["total"] == 0


async def test_unknown_api_route_is_json_404_with_request_id(client):
    r = await client.get(f"{API}/definitely-not-a-route")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    assert body["code"] == "NOT_FOUND" and body["request_id"] == r.headers["x-request-id"]


async def test_unauthenticated_is_401_json(client):
    r = await client.get(f"{API}/findings")
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHENTICATED"


# --------------------------------------------------------------------------- bootstrap

async def test_http_bootstrap_disabled_without_operator_token(client):
    r = await client.post(f"{API}/auth/bootstrap",
                          json={"username": "x-owner", "email": settings.SOLE_OWNER_EMAIL, "password": "a" * 16})
    assert r.status_code == 404


async def test_http_bootstrap_token_gated_and_one_time(client, monkeypatch):
    monkeypatch.setattr(settings, "BOOTSTRAP_TOKEN", "boot-" + uuid.uuid4().hex)
    body = {"username": "pilot-owner", "email": settings.SOLE_OWNER_EMAIL, "password": OWNER_PASSWORD}
    assert (await client.post(f"{API}/auth/bootstrap", json=body,
                              headers={"X-Bootstrap-Token": "wrong"})).status_code == 403
    wrong_email = dict(body, email="intruder@pilot-test.invalid")
    assert (await client.post(f"{API}/auth/bootstrap", json=wrong_email,
                              headers={"X-Bootstrap-Token": settings.BOOTSTRAP_TOKEN})).status_code == 400
    r = await client.post(f"{API}/auth/bootstrap", json=body, headers={"X-Bootstrap-Token": settings.BOOTSTRAP_TOKEN})
    assert r.status_code == 201 and r.json()["id"] == settings.SOLE_OWNER_ACCOUNT_ID
    r2 = await client.post(f"{API}/auth/bootstrap", json=body, headers={"X-Bootstrap-Token": settings.BOOTSTRAP_TOKEN})
    assert r2.status_code == 409


# --------------------------------------------------------------------------- session cookie + CSRF

async def test_login_sets_httponly_cookie_and_csrf_enforced(client, owner):
    r = await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    assert r.status_code == 200
    set_cookie = ";".join(r.headers.get_list("set-cookie")).lower()
    assert f"{settings.SESSION_COOKIE_NAME}=" in set_cookie and "httponly" in set_cookie
    assert "samesite=strict" in set_cookie

    me = await client.get(f"{API}/auth/me")
    assert me.status_code == 200 and me.json()["is_owner"] is True

    # Cookie-authenticated mutation without CSRF header is refused.
    r = await client.post(f"{API}/auth/users/invite",
                          json={"username": "dev1", "email": "dev1@pilot-test.invalid",
                                "password": USER_PASSWORD, "role": "DEVELOPER"})
    assert r.status_code == 403 and "CSRF" in r.json()["detail"]
    r = await client.post(f"{API}/auth/users/invite", headers=csrf_headers(client),
                          json={"username": "dev1", "email": "dev1@pilot-test.invalid",
                                "password": USER_PASSWORD, "role": "DEVELOPER"})
    assert r.status_code == 201


async def test_token_in_query_string_is_ignored(client, owner):
    token = (await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)).json()["access_token"]
    async with new_client() as anon:
        r = await anon.get(f"{API}/auth/me", params={"token": token})
        assert r.status_code == 401
        r = await anon.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200


async def test_logout_revokes_cookie_and_bearer_server_side(client, owner):
    r = await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    stolen_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
    bearer = r.json()["access_token"]
    assert (await client.post(f"{API}/auth/logout", headers=csrf_headers(client))).status_code == 200
    async with new_client() as replay:
        replay.cookies.set(settings.SESSION_COOKIE_NAME, stolen_cookie)
        assert (await replay.get(f"{API}/auth/me")).status_code == 401
        assert (await replay.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {bearer}"})).status_code == 401
    # Fresh login right after logout works (ms-precision invalidation).
    assert (await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)).status_code == 200
    assert (await client.get(f"{API}/auth/me")).status_code == 200


# --------------------------------------------------------------------------- owner-only admin

async def test_only_owner_manages_users_grants_and_audit(client, owner):
    dev_id = await make_user("DEVELOPER", "dev-a")
    asset = await make_asset("svc-a")
    async with new_client() as dev:
        await login(dev, "dev-a", USER_PASSWORD)
        h = csrf_headers(dev)
        assert (await dev.get(f"{API}/auth/users")).status_code == 403
        assert (await dev.get(f"{API}/auth/audit")).status_code == 403
        assert (await dev.post(f"{API}/auth/users/{dev_id}/grants", headers=h,
                               json={"asset_id": str(asset), "permissions": "READ"})).status_code == 403
        assert (await dev.post(f"{API}/auth/users/invite", headers=h,
                               json={"username": "x2", "email": "x2@pilot-test.invalid", "password": USER_PASSWORD,
                                     "role": "VIEWER"})).status_code == 403
        assert (await dev.post(f"{API}/scans/scan-all", headers=h, json={"targets": "ALL"})).status_code == 403
        assert (await dev.get(f"{API}/metrics/overview")).status_code == 403


async def test_invite_cannot_mint_owner_or_admin(client, owner):
    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    for role in ("OWNER", "ADMIN", "SUPER_ADMIN"):
        r = await client.post(f"{API}/auth/users/invite", headers=csrf_headers(client),
                              json={"username": f"r-{role.lower()}", "email": f"{role.lower()}@pilot-test.invalid",
                                    "password": USER_PASSWORD, "role": role})
        assert r.status_code == 422, role


async def test_role_owner_without_immutable_id_is_not_owner(client, owner):
    await make_user("OWNER", "fake-owner")
    async with new_client() as c:
        await login(c, "fake-owner", USER_PASSWORD)
        assert (await c.get(f"{API}/auth/users")).status_code == 403
        assert (await c.get(f"{API}/auth/me")).json()["is_owner"] is False


# --------------------------------------------------------------------------- object scope

async def test_developer_sees_only_granted_assets_findings_reports(client, owner):
    a = await make_asset("svc-granted")
    b = await make_asset("svc-other")
    fa = await make_finding(a, "finding on granted")
    fb = await make_finding(b, "finding on other")
    dev_id = await make_user("DEVELOPER", "dev-scope")

    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    g = await client.post(f"{API}/auth/users/{dev_id}/grants", headers=csrf_headers(client),
                          json={"asset_id": str(a), "permissions": "READ"})
    assert g.status_code == 201
    grant_id = g.json()["id"]

    async with new_client() as dev:
        await login(dev, "dev-scope", USER_PASSWORD)
        assets = (await dev.get(f"{API}/assets")).json()
        assert [x["id"] for x in assets["items"]] == [str(a)] and assets["total"] == 1
        assert (await dev.get(f"{API}/assets/{b}")).status_code in (403, 404)
        findings = (await dev.get(f"{API}/findings", params={"search": "finding"})).json()
        assert {x["id"] for x in findings["items"]} == {str(fa)} and findings["total"] == 1
        assert (await dev.get(f"{API}/findings/{fb}")).status_code == 404
        # READ-only grant: no scan, no triage, no retest.
        h = csrf_headers(dev)
        assert (await dev.post(f"{API}/scans", headers=h, json={"asset_id": str(a)})).status_code == 403
        assert (await dev.post(f"{API}/scans", headers=h, json={"asset_id": str(b)})).status_code == 404
        assert (await dev.post(f"{API}/findings/{fa}/retest", headers=h)).status_code == 403
        # Estate-wide report is owner-only.
        r = await dev.post(f"{API}/reports/generate", headers=h, json={"title": "x", "formats": ["json"]})
        assert r.status_code == 403

        # Owner revokes → access disappears on the next request (no re-login).
        assert (await client.delete(f"{API}/auth/users/{dev_id}/grants/{grant_id}",
                                    headers=csrf_headers(client))).status_code == 204
        assert (await dev.get(f"{API}/assets")).json()["total"] == 0
        assert (await dev.get(f"{API}/findings/{fa}")).status_code == 404

    audit = (await client.get(f"{API}/auth/audit", params={"action": "GRANT_REVOKE"})).json()
    assert audit and audit[0]["user_id"] == settings.SOLE_OWNER_ACCOUNT_ID


async def test_viewer_without_grants_sees_nothing(client, owner):
    await make_asset("svc-hidden")
    await make_user("VIEWER", "viewer-0")
    async with new_client() as v:
        await login(v, "viewer-0", USER_PASSWORD)
        assert (await v.get(f"{API}/assets")).json()["total"] == 0
        assert (await v.get(f"{API}/findings")).json()["total"] == 0
        assert (await v.get(f"{API}/scans")).json()["total"] == 0
        assert (await v.get(f"{API}/reports")).json() == []


async def test_disabled_account_loses_live_session_and_cannot_login(client, owner):
    uid = await make_user("DEVELOPER", "dev-off")
    async with new_client() as dev:
        await login(dev, "dev-off", USER_PASSWORD)
        assert (await dev.get(f"{API}/auth/me")).status_code == 200
        await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
        r = await client.patch(f"{API}/auth/users/{uid}/status", headers=csrf_headers(client),
                               json={"is_active": False})
        assert r.status_code == 200
        assert (await dev.get(f"{API}/auth/me")).status_code in (401, 403)
        assert (await login(dev, "dev-off", USER_PASSWORD)).status_code == 403


async def test_stream_revalidation_drops_after_grant_revoked(owner):
    """SSE streams re-check session + grant each heartbeat (session_still_valid)."""
    from starlette.requests import Request

    from backend.app.api.deps import session_still_valid
    from backend.app.core.database import AsyncSessionLocal
    from backend.app.models.user import UserAssetGrant

    a = await make_asset("svc-stream")
    uid = await make_user("DEVELOPER", "dev-stream")
    async with AsyncSessionLocal() as db:
        g = UserAssetGrant(user_id=uid, asset_id=a, permissions="READ", granted_by="test")
        db.add(g)
        await db.commit()
        gid = g.id
    async with new_client() as dev:
        token = (await login(dev, "dev-stream", USER_PASSWORD)).json()["access_token"]
    scope = {"type": "http", "method": "GET", "path": "/", "query_string": b"",
             "headers": [(b"authorization", f"Bearer {token}".encode())]}
    req = Request(scope)
    assert await session_still_valid(req, a) is True
    async with AsyncSessionLocal() as db:
        await db.delete(await db.get(UserAssetGrant, gid))
        await db.commit()
    assert await session_still_valid(req, a) is False
