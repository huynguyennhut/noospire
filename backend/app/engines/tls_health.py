"""Read-only TLS certificate + service health measurement for an owner-approved endpoint.

Safety properties
- Only the endpoint the owner approved on the asset (`assessment_policy.health_check`).
- Every resolved address is checked; cloud metadata always blocked; private/loopback only
  when the owner approved `allow_private` for that endpoint.
- Connects to the vetted IP (pins it, no DNS rebinding), SNI = hostname.
- One GET, no redirects followed, no credentials sent, response body capped, hard timeouts.
- Service unavailability is recorded as operational status, not as a security finding.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlsplit

from cryptography import x509

from backend.app.core.ssrf import SSRFProtector

DRIVER_NAME = "noospire-tls-health-native"
DRIVER_VERSION = "1.0.0"
ENGINE_ID = "tls_health"
RULESET = {"id": "tls-health-baseline", "version": "2026.11.1",
           "rules": {"TLS-CERT-EXPIRED": "certificate notAfter < observed_at",
                     "TLS-CERT-EXPIRING": "certificate expires within 14 days",
                     "TLS-VERIFY-FAILED": "chain or hostname verification failed"}}
EXPIRY_WARN_DAYS = 14
MAX_BODY = 64 * 1024


class EgressDenied(PermissionError):
    pass


@dataclass
class HealthResult:
    url: str
    observed_at: str
    resolved: List[str] = field(default_factory=list)
    connected_ip: Optional[str] = None
    service_status: str = "unknown"  # up | degraded | down | unknown
    http_status: Optional[int] = None
    latency_ms: Optional[int] = None
    tls_verified: Optional[bool] = None
    tls_verify_error: Optional[str] = None
    tls_version: Optional[str] = None
    cert_subject: Optional[str] = None
    cert_issuer: Optional[str] = None
    cert_not_after: Optional[str] = None
    cert_days_remaining: Optional[float] = None
    missing: List[str] = field(default_factory=list)
    error: Optional[str] = None
    bytes_sent: int = 0  # application bytes only (TLS overhead excluded)
    bytes_received: int = 0


def _allowed_ip(ip: str, allow_private: bool) -> bool:
    obj = ipaddress.ip_address(ip)
    if ip in SSRFProtector.CLOUD_METADATA_IPS:
        return False
    if not SSRFProtector._is_ip_blocked(obj):
        return True
    return allow_private and any(obj in net for net in SSRFProtector.ALLOWED_LAB_NETWORKS)


async def resolve_vetted(host: str, port: int, allow_private: bool) -> List[str]:
    if host.lower() in SSRFProtector.CLOUD_METADATA_HOSTS:
        raise EgressDenied(f"host {host} is a metadata endpoint")
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ips = sorted({i[4][0] for i in infos})
    if not ips:
        raise EgressDenied("no addresses resolved")
    bad = [ip for ip in ips if not _allowed_ip(ip, allow_private)]
    if bad:
        raise EgressDenied(f"resolved address(es) not permitted by egress policy: {', '.join(bad)}")
    return ips


def _name(n: x509.Name) -> str:
    return n.rfc4514_string()


async def measure(url: str, *, allow_private: bool, ca_file: Optional[str] = None,
                  timeout: float = 10.0) -> HealthResult:
    parts = urlsplit(url)
    observed = datetime.now(timezone.utc)
    res = HealthResult(url=url, observed_at=observed.isoformat())
    if parts.scheme != "https" or not parts.hostname:
        res.error = "only https:// endpoints are measured"
        res.missing.append("tls")
        return res
    host, port = parts.hostname, parts.port or 443
    path = (parts.path or "/") + (("?" + parts.query) if parts.query else "")

    res.resolved = await resolve_vetted(host, port, allow_private)
    ip = res.resolved[0]
    res.connected_ip = ip

    verify_ctx = ssl.create_default_context(cafile=ca_file) if ca_file else ssl.create_default_context()
    t0 = time.monotonic()
    reader = writer = None
    try:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port, ssl=verify_ctx, server_hostname=host), timeout)
            res.tls_verified = True
        except ssl.SSLCertVerificationError as exc:
            res.tls_verified = False
            res.tls_verify_error = exc.verify_message or str(exc)
            # Re-connect without verification only to READ the certificate for expiry reporting.
            nv = ssl.create_default_context()
            nv.check_hostname = False
            nv.verify_mode = ssl.CERT_NONE
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port, ssl=nv, server_hostname=host), timeout)
    except (OSError, asyncio.TimeoutError) as exc:
        res.service_status = "down"
        res.error = f"connect failed: {type(exc).__name__}"
        res.missing += ["tls", "http"]
        return res

    try:
        sslobj = writer.get_extra_info("ssl_object")
        res.tls_version = sslobj.version() if sslobj else None
        der = sslobj.getpeercert(binary_form=True) if sslobj else None
        if der:
            cert = x509.load_der_x509_certificate(der)
            na = cert.not_valid_after_utc
            res.cert_subject, res.cert_issuer = _name(cert.subject), _name(cert.issuer)
            res.cert_not_after = na.isoformat()
            res.cert_days_remaining = round((na - observed).total_seconds() / 86400, 2)
        else:
            res.missing.append("certificate")

        req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: noospire-health/1.0\r\n"
               f"Accept: */*\r\nConnection: close\r\n\r\n").encode()
        writer.write(req)
        await writer.drain()
        res.bytes_sent = len(req)
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout)
        res.bytes_received = len(head)
        res.latency_ms = int((time.monotonic() - t0) * 1000)
        status_line = head.split(b"\r\n", 1)[0].decode("latin-1")
        try:
            res.http_status = int(status_line.split(" ")[1])
        except (IndexError, ValueError):
            res.missing.append("http_status")
        # Drain at most MAX_BODY; content is not stored (may contain personal data).
        try:
            res.bytes_received += len(await asyncio.wait_for(reader.read(MAX_BODY), timeout))
        except asyncio.TimeoutError:
            pass
        if res.http_status is None:
            res.service_status = "unknown"
        elif 200 <= res.http_status < 300:
            res.service_status = "up"
        elif res.http_status in (301, 302, 303, 307, 308, 401, 403):
            res.service_status = "degraded"  # reachable but not a health answer; redirect not followed
        else:
            res.service_status = "down" if res.http_status >= 500 else "degraded"
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        res.service_status = "down"
        res.error = f"http failed: {type(exc).__name__}"
        res.missing.append("http")
    finally:
        try:
            writer.close()
        except Exception:
            pass
    return res


def findings_from(res: HealthResult) -> List[dict]:
    """Configuration findings only (certificate). Availability is reported as status."""
    out = []
    if res.cert_days_remaining is not None:
        if res.cert_days_remaining < 0:
            out.append({"rule": "TLS-CERT-EXPIRED", "severity": "CRITICAL",
                        "title": "TLS certificate has expired",
                        "detail": f"notAfter={res.cert_not_after}"})
        elif res.cert_days_remaining < EXPIRY_WARN_DAYS:
            out.append({"rule": "TLS-CERT-EXPIRING", "severity": "HIGH",
                        "title": f"TLS certificate expires in {res.cert_days_remaining:.1f} days",
                        "detail": f"notAfter={res.cert_not_after}"})
    if res.tls_verified is False:
        out.append({"rule": "TLS-VERIFY-FAILED", "severity": "HIGH",
                    "title": "TLS certificate verification failed",
                    "detail": res.tls_verify_error or "verification error"})
    return out
