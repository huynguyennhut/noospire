"""Milestone 3 · slice 2: read-only TLS/health measurement of a team-owned test service.
The service is a local HTTPS server started by the test with a freshly generated cert."""

from __future__ import annotations

import asyncio
import datetime as dt
import socket
import ssl
import tempfile
import threading
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from backend.app.core.config import settings
from tests_pilot.conftest import csrf_headers, login, make_asset, OWNER_PASSWORD
from tests_pilot.test_m3_sbom_flow import work_once

API = "/api/v1"


def _make_cert(days_valid: float):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "pilot-test (SYNTHETIC)")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=days_valid))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    d = Path(tempfile.mkdtemp(prefix="pilot-tls-"))
    (d / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (d / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                  serialization.NoEncryption()))
    return d / "cert.pem", d / "key.pem"


class HttpsService:
    """Minimal HTTPS health service on 127.0.0.1 (owned by the test)."""

    def __init__(self, days_valid: float, status_line: str = "200 OK"):
        self.cert, self.key = _make_cert(days_valid)
        self.status_line = status_line
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self.ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.ctx.load_cert_chain(self.cert, self.key)
        self.requests = []
        self._stop = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        self.sock.settimeout(0.2)
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            try:
                with self.ctx.wrap_socket(conn, server_side=True) as tls:
                    data = tls.recv(4096)
                    self.requests.append(data)
                    tls.sendall(f"HTTP/1.1 {self.status_line}\r\nContent-Type: application/json\r\n"
                                f"Content-Length: 15\r\nConnection: close\r\n\r\n{{\"status\":\"ok\"}}".encode())
            except (ssl.SSLError, OSError):
                pass

    def close(self):
        self._stop = True
        self.sock.close()


async def _owner(client):
    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    return csrf_headers(client)


async def _approve(client, h, asset, url, allow_private=True, ca_pem=None):
    body = {"url": url, "allow_private": allow_private}
    if ca_pem:
        body["ca_pem"] = ca_pem
    r = await client.put(f"{API}/assets/{asset}/health-check", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def _run_tls(client, h, asset):
    r = await client.post(f"{API}/executions", headers=h, json={"asset_id": str(asset), "engine": "tls_health"})
    assert r.status_code == 202, r.text
    eid = r.json()["execution_id"]
    status = await work_once()
    return status, (await client.get(f"{API}/executions/{eid}")).json()


async def test_expiring_self_signed_cert_reports_config_findings(client, owner):
    svc = HttpsService(days_valid=5)
    try:
        asset = await make_asset("svc-tls")
        h = await _owner(client)
        await _approve(client, h, asset, f"https://localhost:{svc.port}/healthz")
        status, ex = await _run_tls(client, h, asset)
        assert status == "succeeded"
        s = ex["summary"]
        assert s["service_status"] == "up" and s["http_status"] == 200 and s["tls_verified"] is False
        assert 3.5 < s["cert_days_remaining"] < 5.1 and s["measurement_type"] == "tls_handshake+http_get"
        assert ex["timestamps_utc"]["observed_at"] and ex["driver"] == "noospire-tls-health-native"
        rules = {f["scanner_rule_id"] for f in (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["items"]}
        assert rules == {"TLS-CERT-EXPIRING", "TLS-VERIFY-FAILED"}
        # Read-only: exactly one GET, no credentials, no body sent.
        assert len(svc.requests) == 1 and svc.requests[0].startswith(b"GET /healthz HTTP/1.1")
        assert b"authorization" not in svc.requests[0].lower() and b"cookie" not in svc.requests[0].lower()
    finally:
        svc.close()


async def test_private_ca_trusted_only_expiry_remains(client, owner):
    svc = HttpsService(days_valid=5)
    try:
        asset = await make_asset("svc-tls-ca")
        h = await _owner(client)
        await _approve(client, h, asset, f"https://localhost:{svc.port}/healthz", ca_pem=svc.cert.read_text())
        status, ex = await _run_tls(client, h, asset)
        assert status == "succeeded" and ex["summary"]["tls_verified"] is True
        rules = {f["scanner_rule_id"] for f in (await client.get(f"{API}/findings", params={"asset_id": str(asset)})).json()["items"]}
        assert rules == {"TLS-CERT-EXPIRING"}
    finally:
        svc.close()


async def test_service_down_is_operational_status_not_a_finding(client, owner):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        dead_port = s.getsockname()[1]
    asset = await make_asset("svc-down")
    h = await _owner(client)
    await _approve(client, h, asset, f"https://localhost:{dead_port}/healthz")
    status, ex = await _run_tls(client, h, asset)
    assert status == "succeeded"
    assert ex["summary"]["service_status"] == "down" and "tls" in ex["summary"]["missing"]
    assert ex["finding_count"] == 0


@pytest.mark.parametrize("url,allow_private,reason_class", [
    ("https://169.254.169.254/latest/meta-data", True, "EGRESS_DENIED"),
    ("https://127.0.0.1:9/healthz", False, "EGRESS_DENIED"),
])
async def test_egress_policy_blocks_before_io(client, owner, url, allow_private, reason_class):
    asset = await make_asset("svc-egress")
    h = await _owner(client)
    await _approve(client, h, asset, url, allow_private=allow_private)
    status, ex = await _run_tls(client, h, asset)
    assert status == "skipped" and ex["error_class"] == reason_class


async def test_no_approved_endpoint_and_credentials_rejected(client, owner):
    asset = await make_asset("svc-unapproved")
    h = await _owner(client)
    status, ex = await _run_tls(client, h, asset)
    assert status == "skipped" and ex["error_class"] == "NO_APPROVED_ENDPOINT"
    for bad in ("http://localhost/healthz", "https://user:pw@localhost/", "https://localhost/h?token=abc"):
        r = await client.put(f"{API}/assets/{asset}/health-check", headers=h, json={"url": bad})
        assert r.status_code == 422, bad


async def test_approval_change_after_queue_is_scope_changed(client, owner):
    svc = HttpsService(days_valid=60)
    try:
        asset = await make_asset("svc-scope")
        h = await _owner(client)
        await _approve(client, h, asset, f"https://localhost:{svc.port}/healthz")
        r = await client.post(f"{API}/executions", headers=h, json={"asset_id": str(asset), "engine": "tls_health"})
        eid = r.json()["execution_id"]
        await _approve(client, h, asset, f"https://localhost:{svc.port}/other")
        assert await work_once() == "skipped"
        ex = (await client.get(f"{API}/executions/{eid}")).json()
        assert ex["error_class"] == "SCOPE_CHANGED" and svc.requests == []
    finally:
        svc.close()
