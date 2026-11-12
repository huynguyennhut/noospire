"""Round B seed through the gateway API as the owner: synthetic labelled data only.
Starts a local HTTPS health service (self-signed, 127.0.0.1) for the tls_health engine.
Usage: python scripts/round_b_seed.py <run_dir>
"""

from __future__ import annotations

import datetime as dt
import ssl
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tests_pilot" / "data"
GW = "http://127.0.0.1:8080"


def make_cert(run: Path, days: float = 10):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    (run / "tls.key").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                    serialization.NoEncryption()))
    pem = cert.public_bytes(serialization.Encoding.PEM)
    (run / "tls.crt").write_bytes(pem)
    return pem.decode()


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok pilot-test health\n")

    def log_message(self, *a):
        pass


def serve_https(run: Path, port: int = 8443) -> None:
    srv = HTTPServer(("127.0.0.1", port), Health)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(run / "tls.crt", run / "tls.key")
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def main(run: Path) -> None:
    creds = dict(line.split("=", 1) for line in (run / "test_credentials.txt").read_text().splitlines())
    c = httpx.Client(base_url=GW, timeout=30)
    r = c.post("/api/v1/auth/login", json={"username": "owner@pilot-test.invalid", "password": creds["owner"]})
    r.raise_for_status()
    c.headers["X-CSRF-Token"] = c.cookies.get("noospire_csrf")
    c.post("/api/v1/threat-intel/advisory-snapshots",
           params={"source": "pilot-test synthetic OSV", "version_label": "pilot-v1"},
           content=(DATA / "advisories_pilot_v1.json").read_bytes(),
           headers={"content-type": "application/json"}).raise_for_status()
    ids = {}
    for name, module in (("pilot-test-portal", "WEB_APPLICATION"), ("pilot-test-api", "API_SERVICES"),
                         ("pilot-test-media", "LEARNING_MATERIALS")):
        a = c.post("/api/v1/assets", json={"name": name, "target_locator": f"https://{name}.pilot-test.invalid/",
                                           "empire_module": module})
        a.raise_for_status()
        ids[name] = a.json()["id"]
    for name in ("pilot-test-portal", "pilot-test-api"):
        c.post(f"/api/v1/assets/{ids[name]}/artifacts", params={"filename": "bom.json"},
               content=(DATA / "sbom_vulnerable.cdx.json").read_bytes(),
               headers={"content-type": "application/json"}).raise_for_status()
    pem = make_cert(run)
    c.put(f"/api/v1/assets/{ids['pilot-test-portal']}/health-check",
          json={"url": "https://localhost:8443/health", "allow_private": True, "ca_pem": pem,
                "note": "pilot-test local service"}).raise_for_status()
    (run / "assets.json").write_text(__import__("json").dumps(ids, indent=1))
    print("seeded", ids)


if __name__ == "__main__":
    run = Path(sys.argv[1])
    main(run)
    if "--serve" in sys.argv:
        serve_https(run)
        print("https health service on https://localhost:8443/health", flush=True)
        threading.Event().wait()
