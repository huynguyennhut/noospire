"""One bounded HEAD of an explicitly approved public URL; no crawling or authentication.

Only redacted response metadata is retained. The homepage is a reachability observation,
never an application health check. Connection-time IP pinning is shared with tls_health.
"""
from __future__ import annotations

import asyncio
import fnmatch
import hashlib
import json
import re
import ssl
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from cryptography import x509
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.inventory_reconciliation import execution_block_reasons, usable_proof
from backend.app.engines import tls_health
from backend.app.models.asset import AssetOwnershipProof
from backend.app.models.operations import CapacitySettings
from backend.app.models.scope import AssetAssessmentScope

ENGINE_ID = "public_web"
DRIVER_NAME = "noospire-public-web-native"
DRIVER_VERSION = "1.1.0"
MAX_HEADER_BYTES = 16384
MAX_SECONDS = 12.0
RULESET = {"id": "public-web-head-baseline", "version": "2026.11.15", "rules": {
    "PUBLIC-TLS-VERIFY": "TLS peer chain and hostname verify",
    "PUBLIC-TLS-EXPIRY": "Peer certificate has at least 14 days remaining",
    "PUBLIC-HSTS": "Successful HTTPS HEAD includes a positive HSTS max-age",
    "PUBLIC-NOSNIFF": "Successful HTML HEAD includes X-Content-Type-Options nosniff",
    "PUBLIC-FRAME-POLICY": "Successful HTML HEAD includes a restrictive frame-ancestors or valid X-Frame-Options",
    "PUBLIC-CSP": "Successful HTML HEAD includes an enforced Content-Security-Policy",
    "PUBLIC-COOKIE-SECURE": "Observed Set-Cookie headers include Secure",
}}
AUTH_GAPS = ["AUTHENTICATED_COVERAGE_NOT_CONFIGURED", "APPLICATION_HEALTH_ENDPOINT_NOT_CONFIGURED",
             "CRAWLING_AND_INJECTION_NOT_EVALUATED", "SOURCE_CONTAINER_CLOUD_MOBILE_NOT_EVALUATED"]


class PolicyDenied(ValueError):
    def __init__(self, code: str, detail: str):
        self.code, self.detail = code, detail
        super().__init__(detail)


def normalized_url(raw: str) -> str:
    """No query, userinfo, control characters or ambiguous path encodings on public HEAD."""
    try:
        parts = urlsplit(raw)
        port = parts.port or 443
        if (len(raw) > 2048 or parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or any(ord(c) < 33 or ord(c) > 126 for c in raw)
                or "\\" in raw or "%" in parts.netloc):
            raise ValueError()
        path = parts.path or "/"
        if unquote(path) != path or any(x in (".", "..") for x in path.split("/")):
            raise ValueError()
        host = parts.hostname.lower()
        authority = f"[{host}]" if ":" in host else host
        return f"https://{authority}{':' + str(port) if port != 443 else ''}{path}"
    except (ValueError, AttributeError, TypeError):
        raise PolicyDenied("INVALID_PUBLIC_URL", "Use an exact HTTPS URL without credentials, query or fragment.")


def approval_policy(asset, url: str, actor_id: str, *, mode: str = "head") -> dict:
    """Pure approval builder for the owner API; it does not assert ownership or invent scope."""
    canonical = normalized_url(url)
    if canonical != normalized_url(asset.target_locator):
        raise PolicyDenied("TARGET_MISMATCH", "Public monitoring must use this asset's exact target URL.")
    if mode not in ("head", "surface"):
        raise PolicyDenied("INVALID_PUBLIC_MODE", "Choose head or surface mode.")
    import uuid
    policy = {"url": canonical, "approved_by": actor_id, "approved_at": datetime.now(timezone.utc).isoformat(),
            "revision": uuid.uuid4().hex, "method": "HEAD", "max_requests": 1, "allow_private": False}
    if mode == "surface":
        from backend.app.engines import web_surface
        policy.update(mode="surface", method="GET", max_requests=web_surface.MAX_REQUESTS,
                      byte_budget=web_surface.MAX_BYTES)
    return policy


def scope_allows(scope, url: str, now: datetime, *, max_requests: int = 1, byte_budget: int = MAX_HEADER_BYTES + 2048) -> bool:
    parts, origin = urlsplit(url), urlsplit(scope.exact_origin)
    if (origin.scheme != "https" or origin.hostname != parts.hostname
            or (origin.port or 443) != (parts.port or 443) or (parts.port or 443) not in (scope.ports or [])):
        return False
    expiry = scope.expires_at
    if expiry and (expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)) <= now:
        return False
    checks = scope.permitted_checks or []
    if not ("*" in checks or ENGINE_ID in checks or set(RULESET["rules"]).issubset(checks)):
        return False
    if not any(fnmatch.fnmatchcase(parts.path or "/", p) for p in (scope.allowed_path_patterns or [])):
        return False
    if min(scope.rate_limit_rps or 0, scope.concurrency_limit or 0, scope.max_requests_per_run or 0) < 1:
        return False
    if (scope.byte_budget or 0) < byte_budget or (scope.max_requests_per_run or 0) < max_requests:
        return False
    # Windows are UTC HH:MM; an incomplete/invalid window fails closed.
    if scope.time_window_start or scope.time_window_end:
        try:
            start = datetime.strptime(scope.time_window_start, "%H:%M").time()
            end = datetime.strptime(scope.time_window_end, "%H:%M").time()
            current = now.time().replace(tzinfo=None)
            if not (start <= current < end if start < end else current >= start or current < end):
                return False
        except (ValueError, TypeError):
            return False
    return True


async def validate_approval(db, asset, revision: str | None = None) -> dict:
    blocks = await execution_block_reasons(db, [asset])
    if blocks:
        raise PolicyDenied(blocks[str(asset.id)], "Seeded/test inventory cannot be assessed as production.")
    if asset.verification_status != "VERIFIED":
        raise PolicyDenied("OWNERSHIP_NOT_VERIFIED", "Asset ownership verification is not active.")
    policy = (asset.assessment_policy or {}).get(ENGINE_ID) or {}
    if (not isinstance(policy, dict) or not policy.get("url") or not policy.get("approved_by")
            or not policy.get("approved_at") or not policy.get("revision")):
        raise PolicyDenied("NO_PUBLIC_WEB_APPROVAL", "Owner has not configured the exact public URL for monitoring.")
    url = normalized_url(policy["url"])
    if url != normalized_url(asset.target_locator):
        raise PolicyDenied("TARGET_MISMATCH", "The asset URL changed after monitoring approval.")
    if revision is not None and revision != policy["revision"]:
        raise PolicyDenied("SCOPE_CHANGED", "Public monitoring approval changed after this job was queued.")
    mode = policy.get("mode", "head")
    if mode not in ("head", "surface"):
        raise PolicyDenied("INVALID_PUBLIC_MODE", "Unknown configured public web mode.")
    if mode == "surface":
        from backend.app.engines import web_surface
        if (policy.get("method") != "GET" or policy.get("max_requests") != web_surface.MAX_REQUESTS
                or policy.get("byte_budget") != web_surface.MAX_BYTES):
            raise PolicyDenied("INVALID_SURFACE_BUDGET", "Surface mode requires the bounded request/byte policy.")
    now = datetime.now(timezone.utc)
    try:
        approved_at = datetime.fromisoformat(policy["approved_at"])
        if approved_at.tzinfo is None or approved_at > now:
            raise ValueError()
    except (ValueError, TypeError):
        raise PolicyDenied("INVALID_PUBLIC_WEB_APPROVAL", "Monitoring approval requires a valid past timestamp with timezone.")
    proofs = (await db.execute(select(AssetOwnershipProof).where(AssetOwnershipProof.asset_id == asset.id))).scalars().all()
    if not any(usable_proof({"status": p.status, "proof_data": p.proof_data, "verified_at": p.verified_at,
                             "expires_at": p.expires_at}, now) for p in proofs):
        raise PolicyDenied("OWNERSHIP_NOT_VERIFIED", "An unexpired, non-seeded ownership proof is required.")
    scopes = (await db.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == asset.id))).scalars().all()
    if any(s.emergency_stop_active for s in scopes):
        raise PolicyDenied("TARGET_STOP_ACTIVE", "Target emergency stop is active.")
    cap = await db.get(CapacitySettings, 1)
    if ((cap and getattr(cap, "emergency_stop_active", False))
            or (Path(settings.STORAGE_DIR) / "production-emergency-stop").exists()):
        raise PolicyDenied("GLOBAL_STOP_ACTIVE", "Global emergency stop is active.")
    grant = next((s for s in scopes if scope_allows(s, url, now,
        max_requests=policy.get("max_requests", 1),
        byte_budget=policy.get("byte_budget", MAX_HEADER_BYTES+2048))), None)
    if not grant:
        raise PolicyDenied("PUBLIC_SCOPE_NOT_APPROVED", "No active scope permits this exact URL and public_web check budget.")
    return {**policy, "url": url, "scope_id": str(grant.id)}


def _check(rule, passed, detail, severity="LOW"):
    return {"id": rule, "status": "PASS" if passed else "FAIL", "detail": detail, "severity": severity}


def _restrictive_framing(csp: list[str], xfo: list[str]) -> bool:
    directives = [m.group(1).split() for header in csp
                  for m in re.finditer(r"(?:^|;)\s*frame-ancestors\s+([^;]+)", header, re.I)]
    if not directives:
        return len(xfo) == 1 and xfo[0].strip().lower() in ("deny", "sameorigin")
    # CSP framing takes precedence over XFO. A wildcard/scheme-only/invalid value must
    # not appear as protection. Conservatively recognize self/none or exact HTTPS origins.
    for sources in directives:
        if sources == ["'none'"]:
            return True
        if sources and all(source == "'self'" or re.fullmatch(r"https://[a-z0-9.-]+(?::[0-9]+)?", source, re.I)
                           for source in sources):
            return True
    return False


def assess_headers(status: int, raw_headers: list[tuple[str, str]]) -> tuple[list, dict]:
    """Only policy booleans/counts leave this function; cookie/redirect values never do."""
    headers: dict[str, list[str]] = {}
    for key, val in raw_headers:
        headers.setdefault(key.lower(), []).append(val)
    checks = []
    cookies = headers.get("set-cookie", [])
    summary = {"content_type_html": any("text/html" in h.lower() for h in headers.get("content-type", [])),
               "cookies_observed": len(cookies),
               "cookies_without_secure": sum(not re.search(r"(?:^|;)\s*secure\s*(?:;|$)", h, re.I) for h in cookies)}
    if 200 <= status < 300:
        hsts = headers.get("strict-transport-security", [])
        hsts_valid = len(hsts) == 1 and bool(re.search(r"(?:^|;)\s*max-age\s*=\s*[1-9][0-9]*\s*(?:;|$)", hsts[0], re.I))
        checks.append(_check("PUBLIC-HSTS", hsts_valid, "Positive HSTS max-age on the observed HEAD response.", "MEDIUM"))
        if summary["content_type_html"]:
            csp = headers.get("content-security-policy", [])
            frame = _restrictive_framing(csp, headers.get("x-frame-options", []))
            checks.extend([
                _check("PUBLIC-NOSNIFF", [v.lower() for v in headers.get("x-content-type-options", [])] == ["nosniff"], "nosniff on the observed HTML HEAD response."),
                _check("PUBLIC-FRAME-POLICY", frame, "A supported restrictive framing policy is present on the observed HTML HEAD response."),
                _check("PUBLIC-CSP", any(bool(h.strip()) for h in csp), "An enforced CSP header is present; policy strength is not evaluated.", "INFO"),
            ])
        if cookies:
            checks.append(_check("PUBLIC-COOKIE-SECURE", summary["cookies_without_secure"] == 0,
                                 "Secure attribute on observed cookies; cookie identity and value are not stored."))
    return checks, summary


async def measure(url: str, *, timeout: float = MAX_SECONDS, before_request=None) -> dict:
    url = normalized_url(url)
    parts = urlsplit(url)
    observed = datetime.now(timezone.utc)
    result = {"url": url, "observed_at": observed.isoformat(), "http_status": None, "tls_verified": None,
              "tls_version": None, "cert_not_after": None, "cert_days_remaining": None,
              "requests_sent": 0, "bytes_sent": 0, "bytes_received": 0, "checks": [],
              "coverage_gaps": list(AUTH_GAPS), "application_health_assessed": False,
              "full_assessment_complete": False, "measurement_type": "tls_handshake+http_head",
              "service_status": "unknown", "error": None}
    writer = None
    t0 = time.monotonic()
    try:
        async with asyncio.timeout(min(timeout, MAX_SECONDS)):
            addresses = await tls_health.resolve_vetted(parts.hostname, parts.port or 443, False)
            if before_request is not None:
                await before_request()
            result["connected_ip"] = addresses[0]
            try:
                reader, writer = await asyncio.open_connection(addresses[0], parts.port or 443,
                    ssl=ssl.create_default_context(), server_hostname=parts.hostname, limit=MAX_HEADER_BYTES)
            except ssl.SSLCertVerificationError:
                result["tls_verified"] = False
                result["checks"].append(_check("PUBLIC-TLS-VERIFY", False, "TLS chain or hostname verification failed.", "HIGH"))
                result["coverage_gaps"].append("HTTP_NOT_EVALUATED_TLS_VERIFICATION_FAILED")
                result["error"] = "TLS_VERIFICATION_FAILED"
                return result
            result["tls_verified"] = True
            result["checks"].append(_check("PUBLIC-TLS-VERIFY", True, "TLS chain and hostname verified."))
            sslobj = writer.get_extra_info("ssl_object")
            result["tls_version"] = sslobj.version()
            cert = x509.load_der_x509_certificate(sslobj.getpeercert(binary_form=True))
            expiry = cert.not_valid_after_utc
            days = (expiry - observed).total_seconds() / 86400
            result.update(cert_not_after=expiry.isoformat(), cert_days_remaining=round(days, 2))
            result["checks"].append(_check("PUBLIC-TLS-EXPIRY", days >= 14, "Certificate expiry compared with a 14-day warning threshold.", "HIGH"))
            host = parts.netloc
            request = (f"HEAD {parts.path or '/'} HTTP/1.1\r\nHost: {host}\r\n"
                       f"User-Agent: noosforge-public-web/{DRIVER_VERSION}\r\nAccept: */*\r\nConnection: close\r\n\r\n").encode("ascii")
            if before_request is not None:
                await before_request()
            writer.write(request)
            result.update(requests_sent=1, bytes_sent=len(request))
            await writer.drain()
            head = await reader.readuntil(b"\r\n\r\n")
            if len(head) > MAX_HEADER_BYTES:
                raise ValueError("HEADER_LIMIT")
            result["bytes_received"] = len(head)
            lines = head.decode("latin-1").split("\r\n")
            if not re.fullmatch(r"HTTP/1\.[01] [1-5][0-9]{2}(?: .*)?", lines[0]):
                raise ValueError("INVALID_STATUS")
            result["http_status"] = status = int(lines[0].split()[1])
            raw = []
            for line in lines[1:]:
                if line:
                    if ":" not in line or line[0].isspace():
                        raise ValueError("INVALID_HEADERS")
                    key, value = line.split(":", 1)
                    raw.append((key.strip().lower(), value.strip()))
            checks, meta = assess_headers(status, raw)
            result["checks"].extend(checks)
            result.update(meta)
            result["service_status"] = "reachable"  # Never claims application health.
            if status in (401, 403):
                result["coverage_gaps"].append("PUBLIC_RESPONSE_ACCESS_RESTRICTED")
            elif 300 <= status < 400:
                result["coverage_gaps"].append("REDIRECT_NOT_FOLLOWED")
            elif status == 429 or status >= 500:
                result["coverage_gaps"].append("TARGET_DEGRADATION_NO_FURTHER_REQUESTS")
            elif status < 200 or status >= 400:
                result["coverage_gaps"].append("PUBLIC_HEADER_BASELINE_NOT_EVALUATED")
    except (tls_health.EgressDenied, PolicyDenied):
        raise
    except (OSError, TimeoutError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError) as exc:
        result["error"] = type(exc).__name__
        result["coverage_gaps"].append("HTTP_OBSERVATION_INCOMPLETE")
    finally:
        result["latency_ms"] = int((time.monotonic() - t0) * 1000)
        if writer is not None:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 0.5)
            except (OSError, TimeoutError):
                pass
    return result


def rules_digest() -> str:
    return hashlib.sha256(json.dumps(RULESET, sort_keys=True).encode()).hexdigest()
