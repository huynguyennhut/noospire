"""Synthetic, offline public_web checks, durable execution and safety regressions.

No customer requests: TLS/DNS transport is replaced with bounded in-memory streams.
Database/assets/credentials come from the disposable pilot fixture.
"""
from __future__ import annotations

import asyncio
import json
import socket
import ssl
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from sqlalchemy import select, update

from backend.app.core.database import AsyncSessionLocal
from backend.app.engines import public_web, tls_health
from backend.app.models.asset import Asset, AssetOwnershipProof
from backend.app.models.operations import CapacitySettings
from backend.app.models.scope import AssetAssessmentScope
from tests_pilot.conftest import make_asset
from tests_pilot.test_m3_sbom_flow import owner_session, work_once

API = "/api/v1"


async def approved_asset(name="public-monitor"):
    aid = await make_asset(name)
    async with AsyncSessionLocal() as db:
        a = await db.get(Asset, aid)
        a.assessment_policy = {"public_web": public_web.approval_policy(a, a.target_locator, "synthetic-owner")}
        db.add(AssetOwnershipProof(asset_id=aid, method="ADMIN_OVERRIDE", status="VERIFIED",
                                  challenge_token="synthetic-proof", verified_at=datetime.now(timezone.utc),
                                  proof_data={"synthetic_pilot": True}))
        db.add(AssetAssessmentScope(asset_id=aid, exact_origin=a.target_locator.rstrip("/"), ports=[443],
                                    allowed_path_patterns=["/"], permitted_checks=["public_web"],
                                    max_requests_per_run=1, concurrency_limit=1, rate_limit_rps=1,
                                    byte_budget=public_web.MAX_HEADER_BYTES + 2048))
        await db.commit()
    return aid


def fake_transport(monkeypatch, response: bytes, *, bad_tls=False):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "synthetic.pilot-test.invalid")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=60)).sign(key, hashes.SHA256()))

    class SSLObject:
        def version(self):
            return "TLSv1.3"

        def getpeercert(self, binary_form=False):
            assert binary_form
            return cert.public_bytes(serialization.Encoding.DER)

    class Writer:
        def __init__(self):
            self.requests, self.connections, self.closed = [], [], False

        def get_extra_info(self, key):
            assert key == "ssl_object"
            return SSLObject()

        def write(self, value):
            self.requests.append(value)

        async def drain(self):
            pass

        def close(self):
            self.closed = True

        async def wait_closed(self):
            pass

    writer = Writer()
    reader = asyncio.StreamReader(limit=public_web.MAX_HEADER_BYTES)
    reader.feed_data(response)
    reader.feed_eof()

    async def resolve(host, port, allow_private):
        assert not allow_private
        return ["93.184.216.34"]

    async def connect(host, port, **kwargs):
        writer.connections.append((host, port, kwargs))
        assert host == "93.184.216.34"  # vetted IP, never a second DNS lookup
        assert kwargs["ssl"].verify_mode == ssl.CERT_REQUIRED and kwargs["ssl"].check_hostname
        if bad_tls:
            raise ssl.SSLCertVerificationError("synthetic invalid certificate")
        return reader, writer

    monkeypatch.setattr(tls_health, "resolve_vetted", resolve)
    monkeypatch.setattr(asyncio, "open_connection", connect)
    return reader, writer


@pytest.mark.parametrize("url", ["http://public.test/", "https://user:secret@public.test/", "https://public.test/?token=x",
                                 "https://public.test/#x", "https://public.test/%2e%2e/", "https://public.test/a/../b",
                                 "https://public.test/\r\nX: injected", "https://public.test/" + "a" * 2049])
def test_public_url_rejects_ambiguous_or_credential_bearing_inputs(url):
    with pytest.raises(public_web.PolicyDenied) as exc:
        public_web.normalized_url(url)
    assert exc.value.code == "INVALID_PUBLIC_URL"


async def test_one_pinned_head_no_auth_no_body_no_sensitive_metadata(monkeypatch):
    response = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nStrict-Transport-Security: max-age=31536000\r\n"
                b"Content-Security-Policy: default-src 'self'; frame-ancestors 'none'\r\n"
                b"X-Content-Type-Options: NOSNIFF\r\nSet-Cookie: session=synthetic-sensitive; Secure; HttpOnly\r\n"
                b"Server: synthetic-private-version\r\n\r\nBODY_MUST_NOT_BE_READ")
    reader, writer = fake_transport(monkeypatch, response)
    result = await public_web.measure("https://public.pilot-test.invalid/")
    assert len(writer.requests) == len(writer.connections) == 1 and writer.closed
    request = writer.requests[0]
    assert request.startswith(b"HEAD / HTTP/1.1\r\nHost: public.pilot-test.invalid\r\n")
    assert b"authorization" not in request.lower() and b"cookie" not in request.lower()
    assert request.endswith(b"\r\n\r\n") and await reader.read() == b"BODY_MUST_NOT_BE_READ"
    assert all(c["status"] == "PASS" for c in result["checks"])
    assert result["requests_sent"] == 1 and result["http_status"] == 200
    assert result["service_status"] == "reachable" and result["application_health_assessed"] is False
    assert result["full_assessment_complete"] is False and result["cookies_observed"] == 1
    assert "AUTHENTICATED_COVERAGE_NOT_CONFIGURED" in result["coverage_gaps"]
    assert "synthetic-sensitive" not in json.dumps(result) and "synthetic-private-version" not in json.dumps(result)


@pytest.mark.parametrize("status,gap", [(302, "REDIRECT_NOT_FOLLOWED"), (401, "PUBLIC_RESPONSE_ACCESS_RESTRICTED"),
                                      (403, "PUBLIC_RESPONSE_ACCESS_RESTRICTED"), (429, "TARGET_DEGRADATION_NO_FURTHER_REQUESTS"),
                                      (503, "TARGET_DEGRADATION_NO_FURTHER_REQUESTS")])
async def test_redirect_auth_and_degraded_responses_are_gaps_not_baseline_pass(monkeypatch, status, gap):
    _, writer = fake_transport(monkeypatch, f"HTTP/1.1 {status} Synthetic\r\nLocation: https://other.invalid/private\r\n\r\n".encode())
    result = await public_web.measure("https://public.pilot-test.invalid/")
    assert gap in result["coverage_gaps"] and len(writer.requests) == 1
    assert {c["id"] for c in result["checks"]} == {"PUBLIC-TLS-VERIFY", "PUBLIC-TLS-EXPIRY"}
    assert "other.invalid" not in json.dumps(result)


async def test_invalid_certificate_never_reconnects_unverified_or_sends_http(monkeypatch):
    _, writer = fake_transport(monkeypatch, b"", bad_tls=True)
    result = await public_web.measure("https://public.pilot-test.invalid/")
    assert writer.requests == [] and len(writer.connections) == 1
    assert result["tls_verified"] is False and result["http_status"] is None
    assert result["checks"][0]["status"] == "FAIL"


@pytest.mark.parametrize("policy,expected", [("frame-ancestors *", "FAIL"), ("frame-ancestors https:", "FAIL"),
    ("frame-ancestors nonsense", "FAIL"), ("frame-ancestors 'none' https://allowed.invalid", "FAIL"),
    ("frame-ancestors 'none'", "PASS"), ("frame-ancestors 'self' https://allowed.invalid", "PASS")])
def test_permissive_or_invalid_frame_policy_is_not_marked_protected(policy, expected):
    checks, _ = public_web.assess_headers(200, [("content-type", "text/html"),
                                               ("content-security-policy", policy), ("x-frame-options", "DENY")])
    assert next(c["status"] for c in checks if c["id"] == "PUBLIC-FRAME-POLICY") == expected


@pytest.mark.parametrize("ips", [["127.0.0.1"], ["169.254.169.254"], ["93.184.216.34", "10.0.0.1"]])
async def test_private_metadata_or_mixed_dns_never_connects(monkeypatch, ips):
    async def dns(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]

    async def forbidden(*args, **kwargs):
        pytest.fail("unsafe address reached transport")

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    monkeypatch.setattr(asyncio, "open_connection", forbidden)
    with pytest.raises(tls_health.EgressDenied):
        await public_web.measure("https://public.pilot-test.invalid/")


async def test_oversized_headers_close_connection_without_header_findings(monkeypatch):
    _, writer = fake_transport(monkeypatch, b"HTTP/1.1 200 OK\r\nX-Fill: " + b"x" * 20000 + b"\r\n\r\n")
    result = await public_web.measure("https://public.pilot-test.invalid/")
    assert writer.closed and result["error"] and result["bytes_received"] == 0
    assert "HTTP_OBSERVATION_INCOMPLETE" in result["coverage_gaps"]
    assert all(c["id"].startswith("PUBLIC-TLS") for c in result["checks"])


@pytest.mark.parametrize("change,expected", [
    ("no_checks", "PUBLIC_SCOPE_NOT_APPROVED"), ("wrong_path", "PUBLIC_SCOPE_NOT_APPROVED"),
    ("wrong_origin", "PUBLIC_SCOPE_NOT_APPROVED"), ("wrong_port", "PUBLIC_SCOPE_NOT_APPROVED"),
    ("expired_scope", "PUBLIC_SCOPE_NOT_APPROVED"), ("low_budget", "PUBLIC_SCOPE_NOT_APPROVED"),
    ("target_stop", "TARGET_STOP_ACTIVE"), ("seed_proof", "SEEDED_OWNERSHIP_NOT_VERIFIED"),
    ("expired_proof", "OWNERSHIP_NOT_VERIFIED"), ("revoked_asset", "OWNERSHIP_NOT_VERIFIED"),
])
async def test_scope_and_proof_preconditions_fail_closed(change, expected):
    aid = await approved_asset()
    async with AsyncSessionLocal() as db:
        asset = await db.get(Asset, aid)
        scope = (await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == aid))).scalar_one()
        proof = (await db.execute(select(AssetOwnershipProof).where(AssetOwnershipProof.asset_id == aid))).scalar_one()
        if change == "no_checks": scope.permitted_checks = []
        if change == "wrong_path": scope.allowed_path_patterns = ["/approved-only"]
        if change == "wrong_origin": scope.exact_origin = "https://different.pilot-test.invalid"
        if change == "wrong_port": scope.ports = [8443]
        if change == "expired_scope": scope.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        if change == "low_budget": scope.byte_budget = 100
        if change == "target_stop": scope.emergency_stop_active = True
        if change == "seed_proof": proof.proof_data = {"initial_seed": True}
        if change == "expired_proof": proof.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        if change == "revoked_asset": asset.verification_status = "PENDING"
        await db.flush()
        with pytest.raises(public_web.PolicyDenied) as exc:
            await public_web.validate_approval(db, asset)
        assert exc.value.code == expected


async def test_durable_plan_worker_findings_and_report_keep_coverage_truthful(client, owner, monkeypatch):
    aid = await approved_asset()
    h = await owner_session(client)
    _, writer = fake_transport(monkeypatch, b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
    r = await client.post(f"{API}/runs", headers=h, json={"selection": {"kind": "assets", "asset_ids": [str(aid)]},
                                                       "engines": ["public_web"], "profile": "slow"})
    assert r.status_code == 202, r.text
    run = r.json()
    assert run["plan"]["summary"]["queue"] == 1 and await work_once() == "succeeded"
    assert len(writer.requests) == 1
    executions = (await client.get(f"{API}/executions", params={"asset_id": str(aid)})).json()
    eid = executions["items"][0]["execution_id"]
    ex = (await client.get(f"{API}/executions/{eid}")).json()
    assert ex["driver"] == public_web.DRIVER_NAME and ex["rules"]["digest"] == public_web.rules_digest()
    assert ex["summary"]["checks_failed"] == 4 and ex["summary"]["full_assessment_complete"] is False
    output = await client.get(f"{API}/executions/{eid}/output")
    assert output.status_code == 200 and output.headers["x-content-sha256"] == ex["output"]["sha256"]
    rep = await client.post(f"{API}/report-snapshots", headers=h,
                            json={"title": "Synthetic public baseline", "batch_id": run["batch_id"]})
    assert rep.status_code == 201, rep.text
    doc = (await client.get(f"{API}/report-snapshots/{rep.json()['id']}/download", params={"format": "json"})).json()
    coverage = doc["coverage"][0]["engines"]["public_web"]
    assert coverage["succeeded"] == 1 and "AUTHENTICATED_COVERAGE_NOT_CONFIGURED" in coverage["coverage_gaps"]
    assert "CRAWLING_AND_INJECTION_NOT_EVALUATED" in doc["appendix_errors_exclusions"][0]["reason"]

    # A later restricted response only evaluates TLS, so it cannot resolve the header findings.
    fake_transport(monkeypatch, b"HTTP/1.1 403 Forbidden\r\n\r\n")
    r = await client.post(f"{API}/executions", headers=h, json={"asset_id": str(aid), "engine": "public_web"})
    assert r.status_code == 202, r.text
    assert await work_once() is None  # Real claim enforces host spacing across consecutive runs.
    from backend.app.models.scan import Scan
    async with AsyncSessionLocal() as db:
        elapsed = datetime.now(timezone.utc) - timedelta(seconds=21)
        await db.execute(update(Scan).where(Scan.asset_id == aid).values(started_at=elapsed, available_at=elapsed))
        await db.commit()
    assert await work_once() == "succeeded"
    findings = (await client.get(f"{API}/findings", params={"asset_id": str(aid)})).json()["items"]
    assert len(findings) == 4 and all(f["status"] == "NEW" for f in findings)


async def test_approval_revision_change_cancels_queued_probe_before_transport(client, owner, monkeypatch):
    aid = await approved_asset()
    h = await owner_session(client)
    r = await client.post(f"{API}/executions", headers=h, json={"asset_id": str(aid), "engine": "public_web"})
    assert r.status_code == 202, r.text
    async with AsyncSessionLocal() as db:
        asset = await db.get(Asset, aid)
        asset.assessment_policy = {"public_web": public_web.approval_policy(asset, asset.target_locator, "synthetic-owner")}
        await db.commit()
    _, writer = fake_transport(monkeypatch, b"")
    assert await work_once() == "skipped" and writer.connections == []
    ex = (await client.get(f"{API}/executions/{r.json()['execution_id']}")).json()
    assert ex["error_class"] == "SCOPE_CHANGED"


async def test_global_stop_blocks_planning_and_interrupts_running_measurement(client, owner, monkeypatch):
    aid = await approved_asset()
    h = await owner_session(client)
    r = await client.post(f"{API}/executions", headers=h, json={"asset_id": str(aid), "engine": "public_web"})
    assert r.status_code == 202, r.text
    started, closed = asyncio.Event(), asyncio.Event()

    async def pending(*args, **kwargs):
        started.set()
        try:
            await asyncio.Future()
        finally:
            closed.set()

    monkeypatch.setattr(public_web, "measure", pending)
    work = asyncio.create_task(work_once())
    await asyncio.wait_for(started.wait(), 3)
    async with AsyncSessionLocal() as db:
        cap = await db.get(CapacitySettings, 1)
        cap.emergency_stop_active = True
        await db.commit()
    assert await asyncio.wait_for(work, 3) == "cancelled" and closed.is_set()
    ex = (await client.get(f"{API}/executions/{r.json()['execution_id']}")).json()
    assert ex["error_class"] == "GLOBAL_STOP_ACTIVE"
    preview = (await client.post(f"{API}/plans/preview", headers=h, json={"selection": {"kind": "all"}})).json()
    assert preview["summary"]["queue"] == 0 and preview["summary"]["reasons"] == {"GLOBAL_STOP_ACTIVE": 3}
    blocked = await client.post(f"{API}/executions", headers=h, json={"asset_id": str(aid), "engine": "public_web"})
    assert blocked.status_code == 409 and "GLOBAL_STOP_ACTIVE" in blocked.text


async def test_scope_revoked_after_tls_does_not_send_head(monkeypatch):
    _, writer = fake_transport(monkeypatch, b"")
    checks = 0

    async def gate():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise public_web.PolicyDenied("TARGET_STOP_ACTIVE", "Synthetic stop after handshake")

    with pytest.raises(public_web.PolicyDenied):
        await public_web.measure("https://public.pilot-test.invalid/", before_request=gate)
    assert len(writer.connections) == 1 and writer.requests == [] and writer.closed
