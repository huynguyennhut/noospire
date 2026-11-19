"""Worker-side execution of defensive engines (sbom, tls_health, public_web).

Lifecycle (all phases inside the RUNNING lease of the queue row `scans`):
  claim (queue.py, fencing token N) -> attempt row (phase=preflight) -> running -> reporting
  -> ONE transaction: UPDATE scans ... WHERE fencing_token = N  (+ findings, record, attempt)
If the conditional update matches 0 rows the attempt lost its lease (reaped, cancelled or
re-claimed): nothing from it is committed and the attempt is closed as `fenced`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy import func, select, update

from backend.app.core.inventory_reconciliation import execution_block_reasons
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.engines import sbom as sbom_engine
from backend.app.engines import tls_health, public_web
from backend.app.engines.advisories import AdvisoryFormatError, AdvisoryIndex, parse_snapshot
from backend.app.models.asset import Asset
from backend.app.models.defensive import (
    EXEC_CANCELLED,
    EXEC_FAILED,
    EXEC_RUNNING,
    EXEC_SKIPPED,
    EXEC_SUCCEEDED,
    EXEC_TIMED_OUT,
    EXEC_UNAVAILABLE,
    AdvisorySnapshot,
    Artifact,
    ExecutionAttempt,
    ExecutionRecord,
)
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan
from backend.app.scanners.base import compute_finding_fingerprint
from backend.app.schemas.common import OPEN_FINDING_STATES, RESOLVED_FINDING_STATES

log = logging.getLogger("noospire.engines")

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)((?:token|password|passwd|secret|api[_-]?key|cookie)=)[^&\s]+"), r"\1[REDACTED]"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"), "[REDACTED_JWT]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[REDACTED_EMAIL]"),
]


def redact(text: str, limit: int = 2000) -> str:
    out = text or ""
    for pat, rep in _SECRET_PATTERNS:
        out = pat.sub(rep, out)
    return out[:limit]


def storage_root() -> Path:
    p = Path(settings.STORAGE_DIR).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


class Outcome:
    def __init__(self, status: str, reason: Optional[str] = None, error_class: Optional[str] = None,
                 output: Optional[bytes] = None, findings: Optional[List[dict]] = None, summary: Optional[dict] = None,
                 rule_meta: Optional[dict] = None, evaluated_locations: Optional[set] = None,
                 known_rule_ids: Optional[set] = None, exit_code: int = 0, observed_at: Optional[datetime] = None,
                 evaluated_checks: Optional[dict] = None):
        self.status = status
        self.reason = reason
        self.error_class = error_class
        self.output = output
        self.findings = findings or []
        self.summary = summary or {}
        self.rule_meta = rule_meta or {}
        self.evaluated_locations = evaluated_locations or set()
        self.known_rule_ids = known_rule_ids
        self.exit_code = exit_code
        self.observed_at = observed_at
        self.evaluated_checks = evaluated_checks


# ------------------------------------------------------------------ engines

async def _active_snapshot(db) -> Optional[AdvisorySnapshot]:
    res = await db.execute(select(AdvisorySnapshot).where(AdvisorySnapshot.is_active == True)  # noqa: E712
                           .order_by(AdvisorySnapshot.imported_at.desc()).limit(1))
    return res.scalars().first()


async def _run_sbom(rec: ExecutionRecord, attempt: ExecutionAttempt, asset: Asset, timeout: float) -> Outcome:
    async with AsyncSessionLocal() as db:
        art = await db.get(Artifact, rec.artifact_id) if rec.artifact_id else None
        snap = await _active_snapshot(db)
    if art is None:
        return Outcome(EXEC_SKIPPED, "No SBOM artifact attached to this execution.", "INPUT_MISSING")
    try:
        raw = Path(art.storage_path).read_bytes()
    except OSError:
        return Outcome(EXEC_FAILED, "Stored SBOM artifact is missing from storage.", "INPUT_MISSING", exit_code=2)
    if sbom_engine.sha256_bytes(raw) != art.sha256:
        return Outcome(EXEC_FAILED, "SBOM artifact hash does not match its recorded sha256.", "INPUT_INTEGRITY",
                       exit_code=2)
    if snap is None:
        return Outcome(EXEC_UNAVAILABLE, "No active advisory snapshot imported; import one before analysis.",
                       "RULES_UNAVAILABLE", exit_code=3)
    try:
        records = parse_snapshot(Path(snap.storage_path).read_bytes())
        index = AdvisoryIndex.build(records)
    except (OSError, AdvisoryFormatError) as exc:
        return Outcome(EXEC_UNAVAILABLE, f"Advisory snapshot unreadable: {exc}", "RULES_UNAVAILABLE", exit_code=3)
    if index.digest != snap.digest:
        return Outcome(EXEC_UNAVAILABLE, "Advisory snapshot content does not match its recorded digest.",
                       "RULES_INTEGRITY", exit_code=3)

    rule_meta = {"source": snap.source, "version": snap.version_label, "digest": snap.digest,
                 "record_count": snap.record_count, "data_modified_max": snap.data_modified_max}
    try:
        result = await asyncio.wait_for(asyncio.to_thread(sbom_engine.analyze, raw, index), timeout)
    except sbom_engine.SbomParseError as exc:
        return Outcome(EXEC_FAILED, f"SBOM could not be parsed: {exc}", "INPUT_PARSE_ERROR", rule_meta=rule_meta,
                       exit_code=4)
    observed = datetime.now(timezone.utc)
    if result.components_total == 0:
        return Outcome(EXEC_SKIPPED, "SBOM lists no components; nothing to evaluate.", "INPUT_EMPTY",
                       rule_meta=rule_meta, summary={"components_total": 0}, observed_at=observed)
    if result.components_evaluated == 0:
        return Outcome(EXEC_SKIPPED, "No component had a supported purl and version; nothing evaluated.",
                       "INPUT_NOT_EVALUABLE", rule_meta=rule_meta, observed_at=observed,
                       summary={"components_total": result.components_total,
                                "components_not_evaluated": len(result.not_evaluated)})
    output = sbom_engine.result_document(result, execution_id=str(rec.id), attempt_id=str(attempt.id),
                                         input_sha256=art.sha256, snapshot=rule_meta)
    findings = []
    for m in result.matches:
        c, a = m["component"], m["advisory"]
        base_purl = c["purl"].split("@", 1)[0]
        cve = next((x for x in a["aliases"] if x.upper().startswith("CVE-")), None)
        findings.append({
            "rule": a["advisory_id"], "location": base_purl, "component": c["name"], "severity": a["severity"],
            "title": f"{a['advisory_id']}: {a['summary']} ({c['name']}@{c['version']})",
            "description": a["summary"], "cve": cve, "cvss": a["cvss_score"], "cvss_vector": a["cvss_vector"],
            "affected_version": c["version"], "fixed_version": ", ".join(a["fixed_versions"]) or None,
            "remediation": m["remediation"], "references": a["references"],
            "evidence": {"component": c, "advisory_id": a["advisory_id"], "aliases": a["aliases"],
                         "matched_by": a["matched_by"], "range_events": a["range_events"],
                         "severity_basis": a["severity_basis"], "advisory_modified": a["modified"]},
        })
    evaluated = {m_c.split("@", 1)[0] for m_c in _evaluated_purls(raw)}
    summary = {"components_total": result.components_total, "components_evaluated": result.components_evaluated,
               "components_not_evaluated": len(result.not_evaluated), "matches": len(result.matches),
               "sbom_format": result.format}
    return Outcome(EXEC_SUCCEEDED, None, None, output=output, findings=findings, summary=summary, rule_meta=rule_meta,
                   evaluated_locations=evaluated, known_rule_ids={r["id"] for r in records}, observed_at=observed)


def _evaluated_purls(raw: bytes) -> List[str]:
    _, _, comps = sbom_engine.parse_sbom(raw)
    return [c.purl for c in comps if c.purl and c.version and c.ecosystem]


async def _run_tls(rec: ExecutionRecord, attempt: ExecutionAttempt, asset: Asset, timeout: float) -> Outcome:
    async with AsyncSessionLocal() as scope_db:
        inventory_blocks = await execution_block_reasons(scope_db, [asset])
    if inventory_blocks:
        return Outcome(EXEC_SKIPPED, "Seed/test provenance is not a verified customer target.", inventory_blocks[str(asset.id)])
    hc = (asset.assessment_policy or {}).get("health_check") or {}
    rule_meta = {"source": "builtin", "version": tls_health.RULESET["version"],
                 "digest": sbom_engine.sha256_bytes(repr(sorted(tls_health.RULESET["rules"].items())).encode())}
    if not hc.get("url") or not hc.get("approved_by"):
        return Outcome(EXEC_SKIPPED, "No owner-approved health endpoint on this asset.", "NO_APPROVED_ENDPOINT",
                       rule_meta=rule_meta)
    if rec.input_descriptor.get("health_check_revision") != hc.get("revision"):
        return Outcome(EXEC_SKIPPED, "Approved endpoint changed after this execution was queued.", "SCOPE_CHANGED",
                       rule_meta=rule_meta)
    try:
        res = await asyncio.wait_for(
            tls_health.measure(hc["url"], allow_private=bool(hc.get("allow_private")), ca_file=hc.get("ca_file"),
                               timeout=min(10.0, timeout)), timeout)
    except tls_health.EgressDenied as exc:
        return Outcome(EXEC_SKIPPED, f"Egress denied: {exc}", "EGRESS_DENIED", rule_meta=rule_meta)
    import dataclasses
    import json as _json

    body = dataclasses.asdict(res)
    doc = {"schema": "noospire.engine-result/1", "engine_id": tls_health.ENGINE_ID, "driver": tls_health.DRIVER_NAME,
           "driver_version": tls_health.DRIVER_VERSION, "execution_mode": "native", "execution_id": str(rec.id),
           "attempt_id": str(attempt.id), "rules": rule_meta, "measurement": body}
    output = _json.dumps(doc, sort_keys=True, indent=2).encode()
    loc = hc["url"].split("?", 1)[0]
    fnds = [{"rule": f["rule"], "location": loc, "component": "tls", "severity": f["severity"], "title": f["title"],
             "description": f["detail"], "cve": None, "cvss": None, "cvss_vector": None, "affected_version": None,
             "fixed_version": None, "remediation": "Renew/replace the certificate and verify the full chain.",
             "references": [], "evidence": {"measurement": {k: body[k] for k in (
                 "observed_at", "connected_ip", "tls_verified", "tls_verify_error", "cert_not_after",
                 "cert_days_remaining", "cert_subject", "cert_issuer")}}} for f in tls_health.findings_from(res)]
    summary = {"service_status": res.service_status, "http_status": res.http_status, "latency_ms": res.latency_ms,
               "cert_not_after": res.cert_not_after, "cert_days_remaining": res.cert_days_remaining,
               "tls_verified": res.tls_verified, "missing": res.missing, "error": res.error,
               "measurement_type": "tls_handshake+http_get",
               "egress_bytes": res.bytes_sent + res.bytes_received}
    evaluated = {loc} if res.cert_not_after else set()
    return Outcome(EXEC_SUCCEEDED, None, None, output=output, findings=fnds, summary=summary, rule_meta=rule_meta,
                   evaluated_locations=evaluated, known_rule_ids=set(tls_health.RULESET["rules"]),
                   observed_at=datetime.fromisoformat(res.observed_at))


async def _run_public_web(rec: ExecutionRecord, attempt: ExecutionAttempt, asset: Asset, timeout: float) -> Outcome:
    import json
    rule_meta = {"source": "builtin", "version": public_web.RULESET["version"], "digest": public_web.rules_digest()}
    revision = (rec.input_descriptor or {}).get("public_web_revision")
    if not revision:
        return Outcome(EXEC_SKIPPED, "No pinned approval revision on the execution.", "SCOPE_CHANGED", rule_meta=rule_meta)

    async def check_scope(request_url=None):
        async with AsyncSessionLocal() as scope_db:
            current = await scope_db.get(Asset, asset.id)
            if current is None:
                raise public_web.PolicyDenied("ASSET_MISSING", "Asset no longer exists.")
            policy = await public_web.validate_approval(scope_db, current, revision)
            if request_url is not None:
                from backend.app.engines.web_surface import origin
                from backend.app.models.scope import AssetAssessmentScope
                grant = await scope_db.get(AssetAssessmentScope, uuid.UUID(policy["scope_id"]))
                if (origin(request_url) != origin(policy["url"]) or not grant or
                        not public_web.scope_allows(grant, request_url, datetime.now(timezone.utc),
                            max_requests=policy.get("max_requests", 1), byte_budget=policy.get("byte_budget", public_web.MAX_HEADER_BYTES+2048))):
                    raise public_web.PolicyDenied("REQUEST_OUT_OF_SCOPE", "Discovered URL is outside the configured origin/path scope.")
            return policy

    try:
        approval = await check_scope()
    except public_web.PolicyDenied as exc:
        return Outcome(EXEC_SKIPPED, exc.detail, exc.code, rule_meta=rule_meta)
    if approval["url"] != rec.input_descriptor.get("url"):
        return Outcome(EXEC_SKIPPED, "Pinned URL no longer matches approval.", "SCOPE_CHANGED", rule_meta=rule_meta)
    surface = approval.get("mode") == "surface"
    if surface:
        from backend.app.engines import web_surface
        rule_meta = {"source": "builtin", "version": web_surface.RULESET["version"], "digest": web_surface.rules_digest()}
        task = asyncio.create_task(web_surface.measure(approval, timeout=min(timeout, web_surface.MAX_SECONDS), before_request=check_scope, scan_id=rec.scan_id))
        rule_titles = web_surface.RULES
    else:
        task = asyncio.create_task(public_web.measure(approval["url"], timeout=min(timeout, public_web.MAX_SECONDS), before_request=check_scope))
        rule_titles = public_web.RULESET["rules"]
    try:
        # Poll persisted scope/stop state across processes; closing a pending task closes its socket.
        while not task.done():
            await asyncio.wait({task}, timeout=0.25)
            await check_scope()
        res = await task
    except public_web.PolicyDenied as exc:
        return Outcome(EXEC_CANCELLED, exc.detail, exc.code, rule_meta=rule_meta)
    except tls_health.EgressDenied:
        return Outcome(EXEC_SKIPPED, "Resolved addresses are outside public egress policy.", "EGRESS_DENIED", rule_meta=rule_meta)
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    checks = res["checks"]
    findings = []
    for check in checks:
        if check["status"] != "FAIL":
            continue
        findings.append({"rule": check["id"], "location": check.get("location", approval["url"]), "component": "public_web",
                         "severity": check["severity"], "title": rule_titles[check["id"]],
                         "description": check["detail"] + " Observation applies only to this captured public response.",
                         "cve": None, "cvss": None, "cvss_vector": None, "affected_version": None,
                         "fixed_version": None, "remediation": "Review this endpoint's TLS/response policy and recheck after a verified correction.",
                         "references": [], "evidence": {"check": check, "observed_at": res["observed_at"],
                                                        "http_status": next((p["status"] for p in res.get("pages", [])
                                                            if p["url"] == check.get("location")), res["http_status"]),
                                                        "method": "GET" if surface else "HEAD"}})
    summary = {**res, "egress_bytes": res["bytes_sent"] + res["bytes_received"],
               "checks_evaluated": len(checks), "checks_failed": len(findings)}
    document = {"schema": "noospire.engine-result/1", "engine_id": public_web.ENGINE_ID,
                "driver": public_web.DRIVER_NAME, "driver_version": public_web.DRIVER_VERSION,
                "execution_id": str(rec.id), "attempt_id": str(attempt.id), "execution_mode": "native",
                "rules": rule_meta, "measurement": summary}
    # A completed measurement can contain TLS findings despite no HTTP response. If absolutely
    # nothing was evaluated, preserve existing findings and report an unavailable observation.
    status = EXEC_SUCCEEDED if checks else EXEC_UNAVAILABLE
    return Outcome(status, res["error"], "OBSERVATION_INCOMPLETE" if not checks else None,
                   output=json.dumps(document, sort_keys=True, indent=2).encode(), findings=findings,
                   summary=summary, rule_meta=rule_meta, evaluated_locations={c.get("location", approval["url"]) for c in checks},
                   known_rule_ids={c["id"] for c in checks}, observed_at=datetime.fromisoformat(res["observed_at"]),
                   evaluated_checks=res.get("evaluated_checks"))


ENGINES = {public_web.ENGINE_ID: (_run_public_web, public_web.DRIVER_NAME, public_web.DRIVER_VERSION),
           sbom_engine.ENGINE_ID: (_run_sbom, sbom_engine.DRIVER_NAME, sbom_engine.DRIVER_VERSION),
           tls_health.ENGINE_ID: (_run_tls, tls_health.DRIVER_NAME, tls_health.DRIVER_VERSION)}

SCAN_STATUS_FOR = {
    EXEC_SUCCEEDED: ("COMPLETED", "SCANNED_SUCCESSFULLY"),
    EXEC_SKIPPED: ("COMPLETED", "PARTIAL_COVERAGE"),
    EXEC_UNAVAILABLE: ("FAILED", "SCANNER_FAILED"),
    EXEC_FAILED: ("FAILED", "SCANNER_FAILED"),
    EXEC_TIMED_OUT: ("TIMED_OUT", "SCANNER_FAILED"),
    EXEC_CANCELLED: ("CANCELLED", None),
}


# ------------------------------------------------------------------ lifecycle

async def has_execution(scan_id: uuid.UUID) -> bool:
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(ExecutionRecord.id).where(ExecutionRecord.scan_id == scan_id))
        return r.first() is not None


async def _set_phase(attempt_id: uuid.UUID, phase: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(update(ExecutionAttempt).where(ExecutionAttempt.id == attempt_id)
                         .values(phase=phase, heartbeat_at=datetime.now(timezone.utc)))
        await db.commit()


async def _execution_control(scan_id, fencing_token, cancel_token) -> Optional[Outcome]:
    """Re-read cross-process stop/cancel/lease state before and during engine I/O."""
    from backend.app.models.operations import CapacitySettings
    if cancel_token is not None and cancel_token.is_cancelled:
        return Outcome(EXEC_CANCELLED, "Execution cancellation requested.", "CANCELLED")
    async with AsyncSessionLocal() as db:
        cap = await db.get(CapacitySettings, 1)
        if ((cap and cap.emergency_stop_active)
                or (Path(settings.STORAGE_DIR) / "production-emergency-stop").exists()):
            return Outcome(EXEC_CANCELLED, "Global emergency stop is active.", "GLOBAL_STOP_ACTIVE")
        lease = (await db.execute(select(Scan.status, Scan.fencing_token).where(Scan.id == scan_id))).first()
        if lease is None or lease.status != "RUNNING" or lease.fencing_token != fencing_token:
            return Outcome(EXEC_CANCELLED, "Execution lease no longer held.", "LEASE_LOST")
    return None


async def _run_controlled(engine_fn, rec, attempt, asset, timeout, scan_id, fencing_token, cancel_token):
    stop = await _execution_control(scan_id, fencing_token, cancel_token)
    if stop is not None:
        return stop
    task = asyncio.create_task(engine_fn(rec, attempt, asset, timeout))
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.25)
            stop = await _execution_control(scan_id, fencing_token, cancel_token)
            if stop is not None:
                return stop
        return await task
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def run_execution(scan_id: uuid.UUID, fencing_token: int, worker_id: str, cancel_token) -> str:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        rec = (await db.execute(select(ExecutionRecord).where(ExecutionRecord.scan_id == scan_id))).scalars().first()
        if rec is None:
            return "not_defensive"
        # The lease may already be gone (cancelled, reaped, re-claimed) between claim and start:
        # then this worker must not touch the record or open an attempt at all.
        live = (await db.execute(select(Scan.id).where(Scan.id == scan_id, Scan.fencing_token == fencing_token,
                                                       Scan.status == "RUNNING"))).first()
        if live is None:
            log.info("execution %s: lease not held at start (token %s); skipping", rec.id, fencing_token)
            return "fenced"
        # Close attempts left open by a worker that died or lost its lease.
        await db.execute(update(ExecutionAttempt)
                         .where(ExecutionAttempt.execution_id == rec.id, ExecutionAttempt.status == EXEC_RUNNING)
                         .values(status="abandoned", error_class="LEASE_LOST", finished_at=now,
                                 error_detail="Superseded by a newer attempt after lease expiry or restart."))
        n = (await db.execute(select(func.count()).select_from(ExecutionAttempt)
                              .where(ExecutionAttempt.execution_id == rec.id))).scalar() or 0
        attempt = ExecutionAttempt(execution_id=rec.id, attempt_no=n + 1, fencing_token=fencing_token,
                                   worker_id=worker_id, phase="preflight", status=EXEC_RUNNING, started_at=now,
                                   heartbeat_at=now)
        db.add(attempt)
        engine_fn, driver, driver_version = ENGINES.get(rec.engine_id, (None, None, None))
        rec.status = EXEC_RUNNING
        rec.started_at = rec.started_at or now
        rec.worker_id = worker_id
        rec.driver, rec.driver_version = driver, driver_version
        scan = await db.get(Scan, scan_id)
        asset = await db.get(Asset, rec.asset_id)
        timeout = float(scan.timeout_seconds or settings.DEFAULT_SCAN_TIMEOUT) if scan else 60.0
        await db.commit()
        await db.refresh(attempt)
        db.expunge(rec)
        db.expunge(attempt)
        if asset is not None:
            db.expunge(asset)

    await _emit("EXECUTION_ATTEMPT_STARTED", f"attempt {attempt.attempt_no} started on {worker_id}", rec, attempt)

    hb_stop = asyncio.Event()

    async def attempt_heartbeat():
        while not hb_stop.is_set():
            try:
                await asyncio.wait_for(hb_stop.wait(), timeout=10)
            except asyncio.TimeoutError:
                async with AsyncSessionLocal() as hdb:
                    await hdb.execute(update(ExecutionAttempt).where(ExecutionAttempt.id == attempt.id)
                                      .values(heartbeat_at=datetime.now(timezone.utc)))
                    await hdb.commit()

    hb = asyncio.create_task(attempt_heartbeat())
    t0 = time.monotonic()
    cpu0 = time.process_time()
    try:
        # ---- preflight (before any I/O on inputs or network)
        if asset is None:
            outcome = Outcome(EXEC_SKIPPED, "Asset no longer exists.", "ASSET_MISSING")
        elif engine_fn is None:
            outcome = Outcome(EXEC_UNAVAILABLE, f"No adapter registered for engine '{rec.engine_id}'.",
                              "ENGINE_UNAVAILABLE", exit_code=3)
        elif cancel_token is not None and cancel_token.is_cancelled:
            outcome = Outcome(EXEC_CANCELLED, "Cancelled before start.", "CANCELLED")
        else:
            await _set_phase(attempt.id, "running")
            try:
                outcome = await asyncio.wait_for(_run_controlled(
                    engine_fn, rec, attempt, asset, timeout, scan_id, fencing_token, cancel_token), timeout)
            except asyncio.TimeoutError:
                outcome = Outcome(EXEC_TIMED_OUT, f"Engine exceeded its {timeout:.0f}s budget.", "TIMEOUT", exit_code=124)
            except Exception as exc:  # unexpected adapter error: keep a redacted trace
                log.exception("engine error execution=%s", rec.id)
                outcome = Outcome(EXEC_FAILED, redact(f"{type(exc).__name__}: {exc}"), "INTERNAL_ERROR", exit_code=1)
        if cancel_token is not None and cancel_token.is_cancelled and outcome.status == EXEC_SUCCEEDED:
            outcome = Outcome(EXEC_CANCELLED, "Cancelled while running; result discarded.", "CANCELLED")
        await _set_phase(attempt.id, "reporting")
        duration_ms = int((time.monotonic() - t0) * 1000)
        return await _commit(scan_id, fencing_token, rec, attempt, asset, outcome, duration_ms,
                             cpu_ms=(time.process_time() - cpu0) * 1000)
    finally:
        hb_stop.set()
        hb.cancel()


async def _commit(scan_id, token, rec, attempt, asset, outcome: Outcome, duration_ms: int,
                  cpu_ms: Optional[float] = None) -> str:
    now = datetime.now(timezone.utc)
    out_path = out_sha = None
    if outcome.output is not None:
        d = storage_root() / "executions" / str(rec.id)
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"attempt-{attempt.attempt_no}.json"
        p.write_bytes(outcome.output)
        out_path, out_sha = str(p), sbom_engine.sha256_bytes(outcome.output)

    scan_status, quality = SCAN_STATUS_FOR[outcome.status]
    async with AsyncSessionLocal() as db:
        res = await db.execute(
            update(Scan).where(Scan.id == scan_id, Scan.fencing_token == token, Scan.status == "RUNNING")
            .values(status=scan_status, quality_status=quality, completed_at=now, progress_percentage=100,
                    lease_expires_at=None, leased_by=None, error_message=outcome.reason))
        if res.rowcount != 1:
            await db.rollback()
            async with AsyncSessionLocal() as db2:
                await db2.execute(update(ExecutionAttempt).where(ExecutionAttempt.id == attempt.id).values(
                    status="fenced", finished_at=now, duration_ms=duration_ms, error_class="LEASE_LOST",
                    error_detail="Lease no longer held at commit (reaped, cancelled or re-claimed); result discarded."))
                await db2.commit()
            if out_path:
                try:
                    os.remove(out_path)
                except OSError:
                    pass
            await _emit("EXECUTION_ATTEMPT_FENCED", "commit rejected: lease lost", rec, attempt, level="WARNING")
            return "fenced"

        finding_ids = []
        if outcome.status == EXEC_SUCCEEDED:
            finding_ids = await _upsert_findings(db, scan_id, rec, attempt, asset, outcome, out_sha, now)
        elif outcome.status != EXEC_CANCELLED:
            await _observe_unavailable(db, rec, outcome, now)

        r = await db.get(ExecutionRecord, rec.id)
        r.status = outcome.status
        r.status_reason = outcome.reason
        r.error_class = outcome.error_class
        r.finding_count = len(outcome.findings) if outcome.status == EXEC_SUCCEEDED else None
        r.summary = outcome.summary
        r.output_path, r.output_sha256 = out_path, out_sha
        r.rule_source = outcome.rule_meta.get("source")
        r.rule_version = outcome.rule_meta.get("version")
        r.rule_digest = outcome.rule_meta.get("digest")
        r.observed_at = outcome.observed_at
        r.finished_at = now
        r.duration_ms = duration_ms
        a = await db.get(ExecutionAttempt, attempt.id)
        a.status = outcome.status
        a.finished_at = now
        a.duration_ms = duration_ms
        a.exit_code = outcome.exit_code
        a.error_class = outcome.error_class
        a.error_detail = redact(outcome.reason) if outcome.reason and outcome.status != EXEC_SUCCEEDED else None
        db.add(await _metric(db, scan_id, r, a, outcome, duration_ms, cpu_ms))
        from backend.app.core import lifecycle as _lc
        await _lc.notify_execution(db, r, outcome.status, outcome.reason)
        await db.commit()

    if rec.batch_id:
        try:
            from backend.app.core.dispatcher import get_dispatcher
            await get_dispatcher()._update_batch_progress(rec.batch_id)
        except Exception:
            log.debug("batch progress update failed", exc_info=True)
    await _emit("EXECUTION_FINISHED", f"{rec.engine_id} {outcome.status}: {outcome.reason or 'ok'}", rec, attempt,
                level="INFO" if outcome.status in (EXEC_SUCCEEDED, EXEC_SKIPPED) else "WARNING",
                details={"status": outcome.status, "finding_count": len(finding_ids), "output_sha256": out_sha})
    return outcome.status


async def _metric(db, scan_id, rec: ExecutionRecord, attempt: ExecutionAttempt, outcome: Outcome,
                  duration_ms: int, cpu_ms: Optional[float]):
    """Per-attempt resource row. Timings/bytes are exact; CPU/RSS are worker-process samples."""
    from backend.app.models.operations import ExecutionMetric

    scan = await db.get(Scan, scan_id)
    ready = rec.queued_at
    if scan is not None and scan.available_at is not None:
        ready = max(_aware(ready), _aware(scan.available_at))
    delay = int((_aware(attempt.started_at) - _aware(ready)).total_seconds() * 1000) if ready else None
    input_bytes = None
    if rec.artifact_id:
        art = await db.get(Artifact, rec.artifact_id)
        input_bytes = art.size_bytes if art else None
    try:
        import psutil
        rss = int(psutil.Process().memory_info().rss)
    except Exception:
        rss = None
    return ExecutionMetric(execution_id=rec.id, attempt_id=attempt.id, engine_id=rec.engine_id,
                           target_host=rec.target_host, status=outcome.status, attempt_no=attempt.attempt_no,
                           queue_delay_ms=max(0, delay) if delay is not None else None, duration_ms=duration_ms,
                           slot_ms=int((datetime.now(timezone.utc) - _aware(attempt.started_at)).total_seconds() * 1000),
                           cpu_ms=round(cpu_ms, 3) if cpu_ms is not None else None, rss_bytes=rss,
                           input_bytes=input_bytes, output_bytes=len(outcome.output) if outcome.output else 0,
                           egress_bytes=(outcome.summary or {}).get("egress_bytes"))


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


OPEN_STATES = OPEN_FINDING_STATES
SYSTEM_ACTOR = "noospire-engine"


async def _upsert_findings(db, scan_id, rec, attempt, asset, outcome: Outcome, out_sha, now) -> List[uuid.UUID]:
    """Apply one succeeded execution to findings. Every evaluated finding gets an observation
    (new | unchanged | reopened | fixed | changed_scope); status changes go to the change log."""
    from backend.app.core import lifecycle

    digest = outcome.rule_meta.get("digest")
    observed = outcome.observed_at or now
    ids, new_rows, reopened_rows = [], [], []
    seen_fps = set()
    for f in outcome.findings:
        fp = compute_finding_fingerprint(rec.asset_id, rec.engine_id, f["rule"], f["location"], f["component"])
        seen_fps.add(fp)
        evidence = dict(f["evidence"], execution_id=str(rec.id), attempt_id=str(attempt.id), output_sha256=out_sha,
                        input_sha256=rec.input_sha256, rule_digest=digest, observed_at=observed.isoformat(),
                        source={"engine": rec.engine_id, "driver": rec.driver, "driver_version": rec.driver_version},
                        confidence="high" if rec.engine_id in ("sbom", "tls_health", "public_web") else "medium",
                        last_verified=now.isoformat())
        existing = (await db.execute(select(NormalizedFinding).where(
            NormalizedFinding.asset_id == rec.asset_id, NormalizedFinding.fingerprint == fp))).scalars().first()
        if existing:
            before = existing.status
            existing.last_seen_at = now
            existing.occurrence_count = (existing.occurrence_count or 1) + 1
            existing.scan_id = scan_id
            existing.evidence = dict(evidence, triage_history=(existing.evidence or {}).get("triage_history", []))
            existing.affected_version = f["affected_version"]
            existing.fixed_version = f["fixed_version"]
            outcome_name = "unchanged"
            if existing.status in (*RESOLVED_FINDING_STATES, "FIXED_PENDING_RETEST", "FIXED"):
                existing.status = "REOPENED"
                outcome_name = "reopened"
                reopened_rows.append(existing)
                existing.remediation_notes = (existing.remediation_notes or "") + \
                    f"\n[{now.isoformat()}] Reopened: observed again in execution {rec.id}."
                lifecycle.record_change(db, existing.id, "status", before, "REOPENED", actor_id=None,
                                        actor_name=SYSTEM_ACTOR, reason="Observed again with equivalent evidence.",
                                        execution_id=rec.id)
            lifecycle.observe(db, finding_id=existing.id, rec=rec, outcome=outcome_name, before=before,
                              after=existing.status, output_sha=out_sha, rule_digest=digest, observed_at=now)
            ids.append(existing.id)
            continue
        nf = NormalizedFinding(
            id=uuid.uuid4(), scan_id=scan_id, asset_id=rec.asset_id, fingerprint=fp,
            empire_module=getattr(asset, "empire_module", None), scanner_engine=rec.engine_id,
            scanner_rule_id=f["rule"], title=f["title"][:512], description=f["description"] or f["title"],
            severity=f["severity"], original_severity=f["severity"], cve_id=f["cve"], cvss_score=f["cvss"],
            cvss_vector=f["cvss_vector"], target_location=f["location"], target_component=f["component"],
            affected_version=f["affected_version"], fixed_version=f["fixed_version"], evidence=evidence,
            remediation=f["remediation"], references=f["references"], status="NEW", first_seen_at=now,
            last_seen_at=now,
        )
        db.add(nf)
        new_rows.append(nf)
        lifecycle.record_change(db, nf.id, "status", None, "NEW", actor_id=None, actor_name=SYSTEM_ACTOR,
                                reason="First observation.", execution_id=rec.id)
        lifecycle.observe(db, finding_id=nf.id, rec=rec, outcome="new", before=None, after="NEW",
                          output_sha=out_sha, rule_digest=digest, observed_at=now)
        ids.append(nf.id)

    # Resolve only with equivalent new evidence: same engine and location evaluated in this
    # execution, the rule still exists in the rule set used, and it no longer matches.
    open_rows = (await db.execute(select(NormalizedFinding).where(
        NormalizedFinding.asset_id == rec.asset_id, NormalizedFinding.scanner_engine == rec.engine_id,
        NormalizedFinding.status.in_(OPEN_STATES)))).scalars().all()
    for row in open_rows:
        if row.fingerprint in seen_fps:
            continue
        if row.target_location not in outcome.evaluated_locations:
            lifecycle.observe(db, finding_id=row.id, rec=rec, outcome="changed_scope", before=row.status,
                              after=row.status, reason="Location not evaluated in this execution (input changed).",
                              output_sha=out_sha, rule_digest=digest, observed_at=now)
            continue
        if ((outcome.known_rule_ids is not None and row.scanner_rule_id not in outcome.known_rule_ids)
                or (outcome.evaluated_checks is not None and row.scanner_rule_id not in
                    outcome.evaluated_checks.get(row.target_location, []))):
            lifecycle.observe(db, finding_id=row.id, rec=rec, outcome="changed_scope", before=row.status,
                              after=row.status, reason="Rule absent from the rule set used; not equivalent evidence.",
                              output_sha=out_sha, rule_digest=digest, observed_at=now)
            continue
        before = row.status
        row.status = "RESOLVED"
        row.remediation_notes = (row.remediation_notes or "") + \
            f"\n[{now.isoformat()}] Fixed: evaluated in execution {rec.id} (rules {digest}) without a match."
        row.evidence = dict(row.evidence or {}, verified_fixed_by_execution=str(rec.id), last_verified=now.isoformat())
        lifecycle.record_change(db, row.id, "status", before, "RESOLVED", actor_id=None, actor_name=SYSTEM_ACTOR,
                                reason=f"Evaluated without a match (rules {digest}).", execution_id=rec.id)
        lifecycle.observe(db, finding_id=row.id, rec=rec, outcome="fixed", before=before, after="RESOLVED",
                          output_sha=out_sha, rule_digest=digest, observed_at=now)
    await db.flush()
    await lifecycle.notify_findings(db, rec, new_rows, reopened_rows)
    return ids


async def _observe_unavailable(db, rec, outcome: Outcome, now) -> None:
    """A run that produced no usable result keeps every open finding unchanged, but records that
    the check was attempted and why it could not verify anything."""
    from backend.app.core import lifecycle

    rows = (await db.execute(select(NormalizedFinding).where(
        NormalizedFinding.asset_id == rec.asset_id, NormalizedFinding.scanner_engine == rec.engine_id,
        NormalizedFinding.status.in_(OPEN_STATES)))).scalars().all()
    for row in rows:
        lifecycle.observe(db, finding_id=row.id, rec=rec, outcome="unavailable", before=row.status, after=row.status,
                          reason=f"{outcome.status}: {(outcome.reason or '')[:400]}", observed_at=now)


async def _emit(event_type: str, message: str, rec, attempt, level: str = "INFO", details: Optional[dict] = None):
    try:
        from backend.app.core.event_bus import emit_event
        await emit_event(event_type, message, scan_id=rec.scan_id, batch_id=rec.batch_id, target_id=rec.asset_id,
                         engine=rec.engine_id, attempt=attempt.attempt_no, level=level,
                         details=dict(details or {}, execution_id=str(rec.id), attempt_id=str(attempt.id),
                                      attempt_no=attempt.attempt_no,
                                      correlation_id=getattr(rec, "correlation_id", None)))
    except Exception:
        log.debug("event emission failed", exc_info=True)
