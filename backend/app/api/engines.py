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
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps import get_current_active_user, require_operator
from backend.app.core.database import get_db
from backend.app.engines import sbom as sbom_engine
from backend.app.engines import tls_health
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
    now = datetime.now(timezone.utc)
    workers = [w for w in (await db.execute(select(WorkerHeartbeat))).scalars()
               if now - _utc(w.last_seen_at) <= WORKER_STALE]
    snap = (await db.execute(select(AdvisorySnapshot).where(AdvisorySnapshot.is_active == True))).scalars().first()  # noqa
    engines: List[Dict[str, Any]] = []
    for eid, meta in DEFENSIVE.items():
        online = [w for w in workers if eid in (w.engines or [])]
        last_ok = (await db.execute(select(func.max(ExecutionRecord.finished_at)).where(
            ExecutionRecord.engine_id == eid, ExecutionRecord.status == "succeeded"))).scalar()
        status, reason = "OPERATIONAL", None
        if not online:
            status, reason = "UNAVAILABLE", "no worker heartbeat listing this engine in the last 30 s"
        elif eid == "sbom" and snap is None:
            status, reason = "DEGRADED", "no active advisory snapshot; sbom runs end as 'unavailable'"
        elif eid == "sbom" and now - _utc(snap.imported_at) > FEED_STALE:
            status, reason = "DEGRADED", "active advisory snapshot is older than 7 days"
        elif any(w.throttle_reason for w in online) and len([w for w in online if not w.throttle_reason]) == 0:
            status, reason = "DEGRADED", online[0].throttle_reason
        engines.append({
            "id": eid, "name": meta["name"], "driver": meta["driver"], "version": meta["version"],
            "status": status, "reason": reason, "runtime_context": "worker process (native, no subprocess)",
            "workers_online": len(online), "last_success_at": _utc(last_ok).isoformat() if last_ok else None,
            "rules": ({"source": snap.source, "version": snap.version_label, "digest": snap.digest,
                       "imported_at": _utc(snap.imported_at).isoformat()} if eid == "sbom" and snap
                      else {"id": tls_health.RULESET["id"], "version": tls_health.RULESET["version"]}
                      if eid == "tls_health" else None),
            "capabilities": meta["capabilities"], "update_available": None,
        })
    for eid, name in LEGACY.items():
        engines.append({"id": eid, "name": name, "driver": None, "version": None, "status": "NOT_INTEGRATED",
                        "reason": "not wired into the fenced execution flow; not run in the pilot",
                        "runtime_context": None, "workers_online": 0, "last_success_at": None, "rules": None,
                        "capabilities": [], "update_available": None})
    defensive = [e for e in engines if e["id"] in DEFENSIVE]
    operational = sum(1 for e in defensive if e["status"] == "OPERATIONAL")
    overall = "HEALTHY" if operational == len(defensive) else ("DEGRADED" if operational or any(
        e["status"] == "DEGRADED" for e in defensive) else "UNAVAILABLE")
    return {
        "status": overall, "as_of": now.isoformat(), "timestamp": now.isoformat(),
        "engines_count": len(defensive), "operational_count": operational, "engines": engines,
        # compatibility keys of the former contract, now derived from measured state
        "all_healthy": overall == "HEALTHY", "total_engines": len(defensive), "online_engines": operational,
    }


_SELFTEST_SBOM = json.dumps({"bomFormat": "CycloneDX", "specVersion": "1.5", "components": [
    {"type": "library", "name": "noospire-selftest", "version": "1.0.0", "purl": "pkg:pypi/noospire-selftest@1.0.0"}]})
_SELFTEST_ADVISORY = [{"id": "NOOSPIRE-SELFTEST-0001", "modified": "2026-01-01T00:00:00Z",
                       "summary": "SYNTHETIC self-test advisory",
                       "affected": [{"package": {"ecosystem": "PyPI", "name": "noospire-selftest"},
                                     "ranges": [{"type": "ECOSYSTEM",
                                                 "events": [{"introduced": "0"}, {"fixed": "2.0.0"}]}]}]}]


@router.post("/test")
async def test_engines(current_user: User = Depends(require_operator)) -> Any:
    """In-process self-test with built-in synthetic inputs. No network, no subprocess, no target contact."""
    t_all = time.perf_counter()
    results = []

    t0 = time.perf_counter()
    try:
        res = sbom_engine.analyze(_SELFTEST_SBOM.encode(), AdvisoryIndex.build(_SELFTEST_ADVISORY))
        ok = len(res.matches) == 1 and res.components_evaluated == 1
        msg = "synthetic SBOM matched the synthetic advisory" if ok else f"unexpected result: {len(res.matches)} match(es)"
    except Exception as exc:  # pragma: no cover - reported, not raised
        ok, msg = False, f"{type(exc).__name__}: {exc}"
    results.append({"engine": "sbom", "status": "PASS" if ok else "FAIL",
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 2), "message": msg})

    t0 = time.perf_counter()
    try:
        await tls_health.resolve_vetted("169.254.169.254", 443, allow_private=True)
        ok, msg = False, "egress guard did NOT refuse the metadata address"
    except tls_health.EgressDenied:
        ok, msg = True, "egress guard refuses metadata addresses before any connection"
    except Exception as exc:  # pragma: no cover
        ok, msg = False, f"{type(exc).__name__}: {exc}"
    results.append({"engine": "tls_health", "status": "PASS" if ok else "FAIL",
                    "latency_ms": round((time.perf_counter() - t0) * 1000, 2), "message": msg})

    now = datetime.now(timezone.utc).isoformat()
    return {"overall_status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
            "duration_ms": round((time.perf_counter() - t_all) * 1000, 2), "timestamp": now, "results": results,
            "scope": "self-test of engine code paths with synthetic inputs; does not prove a worker is running"}


@router.post("/check-updates")
async def check_engine_updates(current_user: User = Depends(require_operator),
                               db: AsyncSession = Depends(get_db)) -> Any:
    """Reports what can be known offline: driver versions and the age of the rule data. The pilot has
    no update channel for drivers, so `latest_version` is unknown rather than claimed up to date."""
    now = datetime.now(timezone.utc)
    snap = (await db.execute(select(AdvisorySnapshot).where(AdvisorySnapshot.is_active == True))).scalars().first()  # noqa
    sbom_stale = snap is None or now - _utc(snap.imported_at) > FEED_STALE
    engines = [
        {"engine": "sbom", "current_version": sbom_engine.DRIVER_VERSION, "latest_version": None, "has_update": None,
         "templates_updated": not sbom_stale,
         "notes": ("no active advisory snapshot" if snap is None else
                   f"advisory snapshot {snap.version_label} imported {_utc(snap.imported_at).isoformat()}"
                   + (" (older than 7 days: import a newer snapshot)" if sbom_stale else ""))},
        {"engine": "tls_health", "current_version": tls_health.DRIVER_VERSION, "latest_version": None,
         "has_update": None, "templates_updated": True,
         "notes": f"built-in ruleset {tls_health.RULESET['id']} {tls_health.RULESET['version']}"},
    ]
    return {"timestamp": now.isoformat(), "updates_available": sbom_stale, "engines": engines,
            "note": "driver update channel not configured in the pilot; rule data freshness is reported"}
