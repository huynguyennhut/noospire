"""Engine health contract (Milestone 6) — the single source for "is this engine usable now".

Only engines registered in the defensive runner are reported as operational, and only from
measured state: a worker heartbeat that lists the engine, the inputs it needs (e.g. an active
advisory snapshot for sbom), and its last committed success. Legacy integrations (nuclei, ZAP,
crawler, "empire engine") are listed as NOT_INTEGRATED: they are not wired into the fenced
execution flow and the pilot does not run them.

The former implementation reported every engine ONLINE / UP_TO_DATE / all_healthy=true even when
no binary existed (a "lab runner" stood in). That contract was removed.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_active_user, require_operator
from backend.app.core.database import get_db
from backend.app.engines import sbom as sbom_engine
from backend.app.engines import tls_health, public_web
from backend.app.engines.advisories import AdvisoryIndex
from backend.app.models.defensive import AdvisorySnapshot, ExecutionRecord, WorkerHeartbeat
from backend.app.models.user import User

router = APIRouter(prefix="/engines", tags=["Engine health"], dependencies=[Depends(get_current_active_user)])

WORKER_STALE = timedelta(seconds=30)
FEED_STALE = timedelta(days=7)
LEGACY = {
    "nuclei": "ProjectDiscovery Nuclei",
    "zap": "OWASP ZAP",
    "trivy": "Aqua Trivy",
    "crawler": "BFS web crawler",
    "empire_engine": "Empire assessment engine",
}
DEFENSIVE = {
    "public_web": {"name": "Public web response baseline", "driver": public_web.DRIVER_NAME,
                   "version": public_web.DRIVER_VERSION,
                   "capabilities": ["single-head", "bounded-same-origin-get", "tls-verification", "certificate-expiry", "response-header-policy", "cookie-secure-attribute", "html-policy-checks", "network-isolated-native-nuclei-passive-when-provisioned"]},
    "sbom": {"name": "SBOM vs versioned advisories", "driver": sbom_engine.DRIVER_NAME,
             "version": sbom_engine.DRIVER_VERSION, "capabilities": ["cyclonedx", "spdx", "pypi", "semver", "maven"]},
    "tls_health": {"name": "Read-only TLS / health measurement", "driver": tls_health.DRIVER_NAME,
                   "version": tls_health.DRIVER_VERSION,
                   "capabilities": ["tls-certificate-expiry", "tls-verification", "http-status", "latency"]},
}


def _utc(dt):
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/health")
async def get_engines_health(db: AsyncSession = Depends(get_db)) -> Any:
    from backend.app.engines.runner import ENGINES

    now = datetime.now(timezone.utc)
    workers = (await db.execute(select(WorkerHeartbeat).where(
        WorkerHeartbeat.last_seen_at >= now - WORKER_STALE,
        WorkerHeartbeat.last_seen_at <= now + timedelta(seconds=5),
    ))).scalars().all()
    snapshot = (await db.execute(select(AdvisorySnapshot).where(AdvisorySnapshot.is_active == True)
                                .order_by(AdvisorySnapshot.imported_at.desc()).limit(1))).scalars().first()
    successes = dict((await db.execute(select(ExecutionRecord.engine_id, func.max(ExecutionRecord.finished_at))
                                      .where(ExecutionRecord.status == "succeeded")
                                      .group_by(ExecutionRecord.engine_id))).all())
    engines = []
    for engine_id, info in DEFENSIVE.items():
        online = sum(engine_id in (w.engines or []) for w in workers)
        reason = None
        engine_status = "OPERATIONAL"
        if engine_id not in ENGINES:
            engine_status, reason = "UNAVAILABLE", "no registered defensive driver"
        elif not online:
            engine_status, reason = "UNAVAILABLE", "no worker heartbeat advertising this engine within 30 seconds"
        elif engine_id == "sbom" and snapshot is None:
            engine_status, reason = "DEGRADED", "no active advisory snapshot imported"
        elif engine_id == "sbom" and now - _utc(snapshot.imported_at) > FEED_STALE:
            engine_status, reason = "DEGRADED", "active advisory snapshot imported more than 7 days ago"
        rules = ({"source": snapshot.source, "version": snapshot.version_label, "digest": snapshot.digest}
                 if snapshot is not None else None) if engine_id == "sbom" else {
                     "id": (public_web if engine_id == "public_web" else tls_health).RULESET["id"],
                     "version": (public_web if engine_id == "public_web" else tls_health).RULESET["version"]}
        last_success = _utc(successes.get(engine_id))
        engines.append({
            "id": engine_id, "name": info["name"], "driver": info["driver"], "version": info["version"],
            "status": engine_status, "reason": reason, "runtime_context": "defensive worker",
            "workers_online": online, "last_success_at": last_success.isoformat() if last_success else None,
            "rules": rules, "capabilities": info["capabilities"], "update_available": None,
        })
    operational = sum(e["status"] == "OPERATIONAL" for e in engines)
    all_healthy = operational == len(DEFENSIVE)
    overall = "HEALTHY" if all_healthy else "DEGRADED" if any(
        e["status"] in ("OPERATIONAL", "DEGRADED") for e in engines) else "UNAVAILABLE"
    for engine_id, name in LEGACY.items():
        engines.append({
            "id": engine_id, "name": name, "driver": None, "version": None,
            "status": "NOT_INTEGRATED", "reason": "not registered in the fenced defensive execution flow",
            "runtime_context": None, "workers_online": 0, "last_success_at": None,
            "rules": None, "capabilities": [], "update_available": None,
        })
    return {"status": overall, "as_of": now.isoformat(), "timestamp": now.isoformat(),
            "engines_count": len(engines), "operational_count": operational,
            "all_healthy": all_healthy, "engines": engines}


def _self_test_sbom() -> None:
    from backend.app.engines.advisories import parse_snapshot

    records = [{"id": "NOOSFORGE-SELFTEST-1", "affected": [{
        "package": {"ecosystem": "PyPI", "name": "noosforge-selftest"}, "versions": ["1.0.0"]}]}]
    index = AdvisoryIndex.build(parse_snapshot(json.dumps(records).encode()))
    document = {"bomFormat": "CycloneDX", "specVersion": "1.5", "components": [{
        "type": "library", "name": "noosforge-selftest", "version": "1.0.0",
        "purl": "pkg:pypi/noosforge-selftest@1.0.0"}]}
    affected = sbom_engine.analyze(json.dumps(document).encode(), index)
    if affected.components_evaluated != 1 or len(affected.matches) != 1:
        raise ValueError("synthetic vulnerable component was not matched")
    document["components"][0].update(version="2.0.0", purl="pkg:pypi/noosforge-selftest@2.0.0")
    patched = sbom_engine.analyze(json.dumps(document).encode(), index)
    if patched.components_evaluated != 1 or patched.matches:
        raise ValueError("synthetic patched component did not evaluate cleanly")


async def _self_test_tls_policy() -> None:
    # A metadata hostname is rejected before DNS or a socket can be opened.
    try:
        await tls_health.resolve_vetted("metadata.google.internal", 443, False)
    except tls_health.EgressDenied:
        pass
    else:
        raise ValueError("metadata hostname was not rejected")
    if tls_health._allowed_ip("127.0.0.1", False) or tls_health._allowed_ip("169.254.169.254", True):
        raise ValueError("private/metadata address policy failed")


@router.post("/test")
async def test_engines(current_user: User = Depends(require_operator)) -> Any:
    """Exercise actual code paths on synthetic inputs, without targets or persistence."""
    started = time.perf_counter()
    results = []
    for engine_id in DEFENSIVE:
        t0 = time.perf_counter()
        try:
            if engine_id == "sbom":
                _self_test_sbom()
                detail = "Synthetic vulnerable and patched CycloneDX components evaluated."
            elif engine_id == "public_web":
                await _self_test_tls_policy()
                checks, _ = public_web.assess_headers(200, [("strict-transport-security", "max-age=31536000")])
                if checks != [public_web._check("PUBLIC-HSTS", True, "Positive HSTS max-age on the observed HEAD response.", "MEDIUM")]:
                    raise ValueError("synthetic header policy check failed")
                detail = "Synthetic response-header policy and metadata egress rejection evaluated; no target request."
            else:
                await _self_test_tls_policy()
                detail = "Private/metadata egress rejection evaluated; no network TLS handshake performed."
            result_status = "PASS"
        except Exception as exc:
            result_status, detail = "FAIL", f"Synthetic code-path test failed ({type(exc).__name__})."
        results.append({"engine": engine_id, "status": result_status,
                        "latency_ms": round((time.perf_counter() - t0) * 1000, 3), "message": detail})
    passed = all(r["status"] == "PASS" for r in results)
    return {"overall_status": "PASS" if passed else "FAIL", "results": results,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scope": "Local synthetic SBOM matching and TLS egress policy only; worker readiness and network handshakes are not tested."}


@router.post("/check-updates")
async def check_engine_updates(current_user: User = Depends(require_operator)) -> Any:
    """Report installed driver versions; upstream versions are unknown without a check."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(), "updates_available": False,
        "updates_checked": False,
        "note": "Upstream versions were not queried. No updates were applied; current versions do not establish freshness.",
        "engines": [{"engine": engine_id, "current_version": info["version"], "latest_version": None,
                     "has_update": None, "templates_updated": False,
                     "notes": "No upstream comparison or template update performed."}
                    for engine_id, info in DEFENSIVE.items()],
    }
