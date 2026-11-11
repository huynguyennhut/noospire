"""Milestone 6 · API contract: every console call resolves to a real OpenAPI operation with the
same method; response shapes of the main operations; honest engine health; verification state;
Cloudflare Access verification at the gateway (locally generated keys, no Cloudflare contact)."""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK
from sqlalchemy import update

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.asset import Asset
from tests_pilot.conftest import USER_PASSWORD, csrf_headers, login, make_asset, make_user, new_client
from tests_pilot.test_m3_sbom_flow import API, import_snapshot, owner_session, upload

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


# --------------------------------------------------------------------------- client ↔ OpenAPI

def test_every_console_call_matches_an_openapi_operation():
    import contract_audit

    r = contract_audit.audit()
    bad = [c for c in r["calls"] if c["status"] != "ok"]
    assert not bad, "\n".join(f"{c['status']} {c['method']} {c['path'] or c['raw']} {c['file']}:{c['line']}"
                              for c in bad)
    assert r["summary"]["ok"] >= 100
    # The removed contracts stay removed from the client.
    paths = {c["path"] for c in r["calls"]}
    assert not any(p.startswith("/intel/") for p in paths)
    assert "/threat-intel/summary" in paths and "/engines/health" in paths


async def test_api_404_is_json_and_inventory_is_paginated(client, owner):
    h = await owner_session(client)
    r = await client.get(f"{API}/no-such-route")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")
    assert r.json()["code"] == "NOT_FOUND" and r.json()["request_id"]
    for n in range(3):
        await make_asset(f"svc-page-{n}")
    page = (await client.get(f"{API}/assets", params={"page": 2, "size": 2})).json()
    assert {"items", "total", "page", "size", "pages"} <= set(page) and page["total"] == 3 and len(page["items"]) == 1
    assert page["pages"] == 2


async def test_async_launch_contract(client, owner):
    h = await owner_session(client)
    await import_snapshot(client, h)
    a = await make_asset("svc-contract")
    await upload(client, h, a)
    preview = (await client.post(f"{API}/plans/preview", headers=h, json={"engines": ["sbom"]})).json()
    assert {"summary", "items", "planned_at", "trigger"} <= set(preview)
    r = await client.post(f"{API}/runs", headers={**h, "Idempotency-Key": "c-1"}, json={"engines": ["sbom"]})
    assert r.status_code == 202
    body = r.json()
    for k in ("batch_id", "accepted_at", "tracker", "correlation_id", "by_status", "plan"):
        assert k in body, k
    assert body["plan"]["summary"]["queue"] == 1  # planned (expected) executions, not results
    assert body["by_status"] == {"queued": 1}
    one = await client.post(f"{API}/executions", headers=h, json={"asset_id": str(a), "engine": "tls_health"})
    assert one.status_code == 202
    w = one.json()["worker"]
    assert w["ready"] is False and "jobs stay queued" in w["reason"]  # worker readiness is its own signal
    ready = (await client.get("/healthz/ready")).json()
    assert ready["status"] == "ready"  # API readiness does not depend on workers


async def test_threat_intel_contract_shapes(client, owner):
    await owner_session(client)
    s = (await client.get(f"{API}/threat-intel/summary")).json()
    assert {"total_cves", "total_kev_exploited", "sources"} <= set(s)
    kev = await client.get(f"{API}/threat-intel/kev", params={"limit": 5})
    assert kev.status_code == 200 and isinstance(kev.json(), list)
    assert (await client.get(f"{API}/intel/status")).status_code == 404


# --------------------------------------------------------------------------- engine health (single contract)

async def test_engine_health_reports_measured_state_only(client, owner):
    h = await owner_session(client)
    r = (await client.get(f"{API}/engines/health")).json()
    by = {e["id"]: e for e in r["engines"]}
    assert r["status"] == "UNAVAILABLE" and r["all_healthy"] is False and r["operational_count"] == 0
    assert by["sbom"]["status"] == "UNAVAILABLE" and "no worker heartbeat" in by["sbom"]["reason"]
    for legacy in ("nuclei", "zap", "trivy", "crawler", "empire_engine"):
        assert by[legacy]["status"] == "NOT_INTEGRATED"

    from backend.app.models.defensive import WorkerHeartbeat
    from datetime import datetime, timezone
    async with AsyncSessionLocal() as db:
        db.add(WorkerHeartbeat(worker_id="pilot-test-worker", engines=["sbom", "tls_health"],
                               last_seen_at=datetime.now(timezone.utc)))
        await db.commit()
    r = (await client.get(f"{API}/engines/health")).json()
    by = {e["id"]: e for e in r["engines"]}
    assert by["tls_health"]["status"] == "OPERATIONAL"
    assert by["sbom"]["status"] == "DEGRADED" and "advisory snapshot" in by["sbom"]["reason"]
    await import_snapshot(client, h)
    r = (await client.get(f"{API}/engines/health")).json()
    assert r["status"] == "HEALTHY" and r["all_healthy"] is True

    t = (await client.post(f"{API}/engines/test", headers=h)).json()
    assert t["overall_status"] == "PASS" and [x["engine"] for x in t["results"]] == ["sbom", "tls_health"]
    assert all(x["status"] == "PASS" for x in t["results"]) and "duration_ms" in t
    u = (await client.post(f"{API}/engines/check-updates", headers=h)).json()
    assert u["updates_available"] is False and u["engines"][0]["latest_version"] is None


# --------------------------------------------------------------------------- verification_status

async def test_verified_flag_without_proof_is_unproven(client, owner):
    await owner_session(client)
    a = await make_asset("svc-unproven", verified=True)  # flag set, no proof row (like imported fixtures)
    got = (await client.get(f"{API}/assets/{a}")).json()
    assert got["verification_status"] == "VERIFIED" and got["verification_state"] == "UNPROVEN"
    assert got["verification_proof"] is None
    listed = (await client.get(f"{API}/assets")).json()["items"][0]
    assert listed["verification_state"] == "UNPROVEN"

    from backend.app.models.proof import AssetOwnershipProof
    from datetime import datetime, timezone
    async with AsyncSessionLocal() as db:
        db.add(AssetOwnershipProof(asset_id=a, method="HTTP_WELL_KNOWN", challenge_token="pilot-test-token",
                                   status="VERIFIED", verified_at=datetime.now(timezone.utc), proof_data={},
                                   created_by="pilot-owner"))
        await db.commit()
    got = (await client.get(f"{API}/assets/{a}")).json()
    assert got["verification_state"] == "VERIFIED" and got["verification_proof"]["method"] == "HTTP_WELL_KNOWN"

    b = await make_asset("svc-hidden")
    await make_user("VIEWER", "viewer-m6")
    async with new_client() as v:
        await login(v, "viewer-m6", USER_PASSWORD)
        assert (await v.get(f"{API}/assets/{b}")).status_code == 404  # outside scope looks missing


# --------------------------------------------------------------------------- Cloudflare Access at the gateway

TEAM = "pilot-test.cloudflareaccess.com"
AUD = "pilot-test-aud-" + uuid.uuid4().hex[:8]


def _keypair(kid: str):
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return priv, jwk


def _token(priv, kid, **over):
    now = int(time.time())
    claims = {"aud": [AUD], "iss": f"https://{TEAM}", "sub": "pilot-sub", "email": "owner@pilot-test.invalid",
              "iat": now, "nbf": now, "exp": now + 600, **over}
    return jwt.encode(claims, priv, algorithm="RS256", headers={"kid": kid})


@pytest.fixture
def gw(monkeypatch, tmp_path):
    import deploy.gateway.gateway as g
    from deploy.gateway.access import AccessVerifier

    priv, jwk = _keypair("k1")
    v = AccessVerifier(team_domain=TEAM, audience=AUD, required=True)
    v.set_keys({"k1": PyJWK(jwk, algorithm="RS256")})
    (tmp_path / "index.html").write_text("<html>console</html>", encoding="utf-8")
    monkeypatch.setattr(g, "ACCESS", v)
    monkeypatch.setattr(g, "STATIC_DIR", tmp_path.resolve())
    monkeypatch.setattr(g, "API_ORIGIN", "")  # API calls stop at the gateway (503) once Access passes
    return g, priv


async def _gw_get(g, path, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=g.app), base_url="http://gw") as c:
        return await c.get(path, **kw)


async def test_access_gate_verifies_signature_audience_issuer_expiry(gw):
    g, priv = gw
    ok = _token(priv, "k1")
    r = await _gw_get(g, "/", headers={"Cf-Access-Jwt-Assertion": ok})
    assert r.status_code == 200 and "console" in r.text
    r = await _gw_get(g, "/", cookies={"CF_Authorization": ok})
    assert r.status_code == 200
    r = await _gw_get(g, "/api/v1/assets", headers={"Cf-Access-Jwt-Assertion": ok})
    assert r.status_code == 503 and r.json()["code"] == "GATEWAY_NOT_CONFIGURED"  # passed Access, reached proxy

    cases = {
        "ACCESS_TOKEN_MISSING": None,
        "ACCESS_TOKEN_EXPIRED": _token(priv, "k1", exp=int(time.time()) - 3600, iat=int(time.time()) - 7200,
                                       nbf=int(time.time()) - 7200),
        "ACCESS_TOKEN_AUDIENCE": _token(priv, "k1", aud=["someone-else"]),
        "ACCESS_TOKEN_ISSUER": _token(priv, "k1", iss="https://evil.cloudflareaccess.com"),
        "ACCESS_TOKEN_MALFORMED": "not-a-jwt",
    }
    other, _ = _keypair("k1")
    cases["ACCESS_TOKEN_INVALID"] = _token(other, "k1")  # right kid, wrong signature
    for code, tok in cases.items():
        hdr = {"Cf-Access-Jwt-Assertion": tok} if tok else {}
        r = await _gw_get(g, "/api/v1/assets", headers=hdr)
        assert r.status_code == 403 and r.json()["code"] == code, (code, r.text)
        page = await _gw_get(g, "/", headers=hdr)
        assert page.status_code == 403 and code in page.text
    hs = jwt.encode({"aud": [AUD], "iss": f"https://{TEAM}", "exp": int(time.time()) + 60, "iat": int(time.time())},
                    "secret", algorithm="HS256", headers={"kid": "k1"})
    r = await _gw_get(g, "/api/v1/assets", headers={"Cf-Access-Jwt-Assertion": hs})
    assert r.json()["code"] == "ACCESS_TOKEN_ALG"  # no algorithm confusion
    live = await _gw_get(g, "/gateway/live")
    assert live.status_code == 200 and live.json()["access"]["enabled"] is True


async def test_access_required_but_missing_fails_closed(monkeypatch, tmp_path):
    import deploy.gateway.gateway as g
    from deploy.gateway.access import AccessVerifier

    monkeypatch.setattr(g, "ACCESS", AccessVerifier(required=True))
    monkeypatch.setattr(g, "STATIC_DIR", tmp_path.resolve())
    r = await _gw_get(g, "/")
    assert r.status_code == 503 and r.json()["code"] == "ACCESS_NOT_CONFIGURED"


async def test_gateway_drops_spoofed_identity_headers(monkeypatch):
    """A client cannot inject the identity headers the gateway forwards after Access."""
    import deploy.gateway.gateway as g

    seen = {}

    async def fake_send(req, stream=False):
        seen.update({k.lower(): v for k, v in req.headers.items()})
        return httpx.Response(200, headers={"content-type": "application/json"},
                              stream=httpx.ByteStream(b'{"ok": true}'), request=req)

    from deploy.gateway.access import AccessVerifier
    monkeypatch.setattr(g, "ACCESS", AccessVerifier())
    monkeypatch.setattr(g, "API_ORIGIN", "http://api.internal")
    client = g._get_client()
    monkeypatch.setattr(client, "send", fake_send)
    r = await _gw_get(g, "/api/v1/x", headers={"X-Noospire-Access-Email": "attacker@pilot-test.invalid"})
    assert r.status_code == 200 and "x-noospire-access-email" not in seen
