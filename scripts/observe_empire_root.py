"""Single root-only production observation; preview unless --execute is explicit.

Not a crawler, authenticated assessment, application health check or full scanner.
Uses the existing vetted-IP TLS driver. No redirects, retries, bodies or credentials.
Honors recorded per-target emergency stops and an optional local stop-file signal.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app.core.inventory_reconciliation import PRIMARY_TARGET  # noqa: E402
from scripts.reconcile_production_inventory import read_inventory  # noqa: E402


def stop_reason(database: Path, stop_file: Path) -> str | None:
    if stop_file.exists():
        return "GLOBAL_STOP_FILE"
    # Recheck all primary-root records, including duplicate scope rows. Never
    # ignore a stop because a different scope row was returned first.
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as con:
        con.execute("PRAGMA query_only=ON")
        rows = con.execute("SELECT s.emergency_stop_active,s.exact_origin,s.ports,s.expires_at FROM asset_assessment_scopes s JOIN assets a ON a.id=s.asset_id "
                           "WHERE a.target_locator IN (?, ?, ?)",
                           (PRIMARY_TARGET, PRIMARY_TARGET.rstrip('/'), 'https://empire.edu.vn:443/')).fetchall()
    if any(row[0] for row in rows):
        return "TARGET_EMERGENCY_STOP"
    for _, origin, ports, expires in rows:
        p = urlsplit(origin)
        if p.scheme != "https" or p.hostname != "empire.edu.vn" or p.port not in (None, 443):
            continue
        if p.path not in ("", "/") or p.query or p.fragment or p.username or p.password:
            continue
        if 443 not in json.loads(ports or "[]"):
            continue
        if expires:
            expiry = datetime.fromisoformat(expires)
            expiry = expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                continue
        return None
    return "NO_ACTIVE_EXACT_ROOT_SCOPE"


async def observe(database: Path, stop_file: Path, *, timeout: float = 12.0) -> dict:
    from backend.app.engines import tls_health
    reason = stop_reason(database, stop_file)
    if reason:
        return {"outcome": "BLOCKED", "reason": reason, "http_requests": 0, "measurement": None}
    task = asyncio.create_task(tls_health.measure(PRIMARY_TARGET, allow_private=False, timeout=5, method="HEAD"))
    deadline = asyncio.get_running_loop().time() + timeout
    try:
        while not task.done():
            done, _ = await asyncio.wait({task}, timeout=0.2)
            reason = stop_reason(database, stop_file)
            if reason:
                return {"outcome": "BLOCKED", "reason": reason, "http_requests": None,
                        "measurement": None, "cancellation_requested": True}
            if not done and asyncio.get_running_loop().time() >= deadline:
                return {"outcome": "ERROR", "reason": "TOTAL_TIMEOUT", "http_requests": None, "measurement": None}
        result = task.result()
        # Readiness is deliberately separate from TLS findings and HTTP status.
        return {"outcome": "OBSERVED" if result.http_status is not None else "ERROR",
                "reason": None if result.http_status is not None else "HTTP_NOT_OBSERVED",
                "http_requests": 1 if result.http_status is not None else None,
                "measurement": asdict(result)}
    except tls_health.EgressDenied:
        return {"outcome": "BLOCKED", "reason": "EGRESS_DENIED", "http_requests": 0, "measurement": None}
    except (OSError, ValueError, sqlite3.Error) as exc:
        return {"outcome": "ERROR", "reason": type(exc).__name__, "http_requests": None, "measurement": None}
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def build_report(result: dict) -> dict:
    from backend.app.engines import tls_health
    measurement = result.get("measurement") or {}
    http = measurement.get("http_status")
    cert_seen = measurement.get("cert_not_after") is not None
    checks = [
        {"id": "ROOT-REACHABILITY", "outcome": "PASS" if http and 200 <= http < 300 else "COVERAGE_GAP",
         "evidence": {"http_status": http}, "limitation": "A root-page response does not establish application health or route coverage."},
        {"id": "ROOT-TLS-VERIFY", "outcome": "PASS" if measurement.get("tls_verified") is True and cert_seen else
         "FINDING" if measurement.get("tls_verified") is False else "COVERAGE_GAP",
         "evidence": {"tls_verified": measurement.get("tls_verified"), "tls_version": measurement.get("tls_version")}},
        {"id": "ROOT-CERT-EXPIRY", "outcome": "PASS" if cert_seen and measurement.get("cert_days_remaining", -1) >= 14 else
         "FINDING" if cert_seen else "COVERAGE_GAP",
         "evidence": {"cert_not_after": measurement.get("cert_not_after"), "days_remaining": measurement.get("cert_days_remaining")}},
    ]
    gap = "AUTHENTICATED_COVERAGE_NOT_CONFIGURED" if http in (401, 403) else "ROUTE_REDIRECT_NOT_FOLLOWED" if http and 300 <= http < 400 else None
    return {"schema": "noosforge.root-observation/1", "environment": "PRODUCTION", "target": PRIMARY_TARGET,
            "recorded_at": datetime.now(timezone.utc).isoformat(), "profile": "root-metadata-head/1",
            "driver": tls_health.DRIVER_NAME, "driver_version": tls_health.DRIVER_VERSION,
            "scope_source": "Owner-designated primary target; no other inventory entries included",
            "limits": {"max_http_requests": 1, "concurrency": 1, "total_timeout_seconds": 12,
                       "response_body_retained": False, "follow_redirects": False, "credentials_sent": False},
            "observation": result, "checks": checks, "route_coverage_gap": gap,
            "automatic_stop": "HTTP_429" if http == 429 else "HTTP_5XX" if http and http >= 500 else result.get("reason"),
            "application_health_endpoint_verified": False, "full_assessment_complete": False,
            "limitations": ["No authenticated identities/test records provisioned: BOLA/BFLA/RBAC/tenant/session checks excluded.",
                            "No other hosts, paths, ports, login redirects or health endpoints tested.",
                            "No target CPU/memory/queue telemetry or pre-scan latency baseline available.",
                            "No external scanner run; this observation is not a vulnerability assessment of the application."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, default=ROOT / "storage/production-emergency-stop")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    database, output = args.database.resolve(), args.output.resolve()
    if output.suffix != ".json" or output == database or (output.exists() and output.samefile(database)):
        parser.error("output must be a JSON report distinct from the database")
    inventory = read_inventory(database)
    designated = [a for a in inventory["assets"] if a["owner_designation_matches"]]
    if not designated:
        parser.error("primary root is absent from the inventory; no target added or scanned")
    preview = {"environment": "PRODUCTION", "target": PRIMARY_TARGET, "method": "HEAD", "max_http_requests": 1,
               "database_modified": False, "execute": args.execute, "stop_file": str(args.stop_file)}
    print(json.dumps(preview), flush=True)
    if not args.execute:
        return 0
    # One local operator observation at a time; no child/scanner process is spawned.
    import fcntl
    lock_path = Path(tempfile.gettempdir()) / f"noosforge-root-observation-{os.getuid()}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("A root observation is already active; no request sent.", file=sys.stderr)
            return 2
        result = asyncio.run(observe(database, args.stop_file))
    finally:
        os.close(fd)
    report = build_report(result)
    report["evidence_sha256"] = hashlib.sha256(json.dumps(report["observation"], sort_keys=True).encode()).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(output), "outcome": result["outcome"], "full_assessment_complete": False}))
    return 0 if result["outcome"] == "OBSERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
