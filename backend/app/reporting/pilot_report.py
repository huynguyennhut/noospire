"""Pilot report v1 (Milestone 5): build a frozen data snapshot, then render JSON/HTML/PDF from it.

The snapshot is canonical JSON; its SHA-256 is printed in every rendering. Rendered files are
stored with their own SHA-256 and re-verified on download, so a report reproduces exactly even
after findings change status later.

Sections: executive summary, scope, coverage, changes vs the previous report for the same scope,
findings with redacted evidence, remediation with owner/assignee, appendix of errors/exclusions.
The customer-approved Empire template has not been supplied: this is internal template
`noospire-pilot-report/1.0`; reconciliation items are listed in the M5 handover.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import unicodedata
import uuid
import zoneinfo
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.engines.runner import redact, storage_root
from backend.app.models.asset import Asset
from backend.app.models.defensive import ExecutionRecord
from backend.app.models.finding import NormalizedFinding
from backend.app.models.lifecycle import FindingObservation, ReportSnapshot

TEMPLATE_VERSION = "noospire-pilot-report/1.0"
TZ = zoneinfo.ZoneInfo(settings.DEFAULT_TIMEZONE)
OPEN_STATES = ("NEW", "OPEN", "CONFIRMED", "IN_REMEDIATION", "REOPENED")
SEV_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


def _iso(dt):
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


def _ict(dt) -> Optional[str]:
    if dt is None:
        return None
    d = dt if isinstance(dt, datetime) else datetime.fromisoformat(dt)
    d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return d.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S ICT")


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


async def build_snapshot(db, *, title: str, assets: List[Asset], batch_id: Optional[uuid.UUID], days: int,
                         generated_by: str, scope_kind: str) -> dict:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    asset_ids = [a.id for a in assets]
    names = {a.id: a.name for a in assets}
    owners = {a.id: (a.assessment_policy or {}).get("owner_contact") for a in assets}
    ids = asset_ids or [uuid.UUID(int=0)]

    exec_stmt = select(ExecutionRecord).where(ExecutionRecord.asset_id.in_(ids))
    exec_stmt = exec_stmt.where(ExecutionRecord.batch_id == batch_id) if batch_id else \
        exec_stmt.where(ExecutionRecord.queued_at >= since)
    execs = (await db.execute(exec_stmt.order_by(ExecutionRecord.queued_at))).scalars().all()

    findings = (await db.execute(select(NormalizedFinding).where(NormalizedFinding.asset_id.in_(ids))
                                 .order_by(NormalizedFinding.severity, NormalizedFinding.title))).scalars().all()
    findings = [f for f in findings if f.status in OPEN_STATES or (f.last_seen_at and
                                                                    _utc(f.last_seen_at) >= since)]
    last_verified: Dict[uuid.UUID, datetime] = {}
    for fid, at in (await db.execute(select(FindingObservation.finding_id, FindingObservation.observed_at)
                                     .where(FindingObservation.asset_id.in_(ids),
                                            FindingObservation.outcome.in_(("new", "unchanged", "reopened",
                                                                            "fixed"))))).all():
        if fid not in last_verified or _utc(at) > last_verified[fid]:
            last_verified[fid] = _utc(at)

    scope_key = {"kind": scope_kind, "asset_ids": sorted(str(a) for a in asset_ids),
                 "batch_id": str(batch_id) if batch_id else None}
    prev = next((r for r in (await db.execute(select(ReportSnapshot).order_by(ReportSnapshot.generated_at.desc())
                                               )).scalars() if (r.scope or {}) == scope_key), None)
    prev_states: Dict[str, str] = {}
    if prev is not None:
        p = Path(prev.files.get("snapshot", {}).get("path", ""))
        if p.is_file():
            prev_states = {x["fingerprint"]: x["status"] for x in json.loads(p.read_bytes())["findings"]}

    fx = []
    for f in sorted(findings, key=lambda f: (SEV_ORDER.get(f.severity, 9), f.title)):
        ev = f.evidence or {}
        fx.append({
            "id": str(f.id), "fingerprint": f.fingerprint, "title": redact(f.title, 300), "severity": f.severity,
            "status": f.status, "asset": names.get(f.asset_id), "asset_id": str(f.asset_id),
            "engine": f.scanner_engine, "rule": f.scanner_rule_id, "cve": f.cve_id,
            "location": redact(f.target_location.split("?", 1)[0], 300), "component": f.target_component,
            "affected_version": f.affected_version, "fixed_version": f.fixed_version,
            "first_seen_at": _iso(f.first_seen_at), "last_seen_at": _iso(f.last_seen_at),
            "last_verified_at": _iso(last_verified.get(f.id)),
            "evidence": {k: ev.get(k) for k in ("execution_id", "output_sha256", "input_sha256", "rule_digest",
                                                "observed_at", "confidence")},
            "remediation": redact(f.remediation or "", 1000), "owner": owners.get(f.asset_id),
            "assignee": f.assignee,
        })
    cur = {x["fingerprint"]: x["status"] for x in fx}
    changes = {
        "previous_snapshot_id": str(prev.id) if prev else None,
        "previous_generated_at": _iso(prev.generated_at) if prev else None,
        "new": sorted(k for k in cur if k not in prev_states) if prev else [],
        "fixed": sorted(k for k, s in cur.items() if s == "FIXED" and prev_states.get(k) not in (None, "FIXED")),
        "reopened": sorted(k for k, s in cur.items() if s == "REOPENED" and prev_states.get(k) == "FIXED"),
        "unchanged": sum(1 for k, s in cur.items() if prev_states.get(k) == s),
    }
    open_by_sev = {s: sum(1 for x in fx if x["severity"] == s and x["status"] in OPEN_STATES) for s in SEV_ORDER}
    coverage = []
    for a in assets:
        mine = [e for e in execs if e.asset_id == a.id]
        per_engine = {}
        for eng in ("sbom", "tls_health"):
            ok = [e for e in mine if e.engine_id == eng and e.status == "succeeded"]
            per_engine[eng] = {"runs": sum(1 for e in mine if e.engine_id == eng), "succeeded": len(ok),
                               "last_success_at": _iso(max((e.finished_at for e in ok), default=None))}
        coverage.append({"asset": a.name, "asset_id": str(a.id), "module": a.empire_module, "engines": per_engine})
    covered = sum(1 for c in coverage if any(v["succeeded"] for v in c["engines"].values()))
    appendix = [{"execution_id": str(e.id), "asset": names.get(e.asset_id), "engine": e.engine_id,
                 "status": e.status, "error_class": e.error_class,
                 "reason": redact(e.status_reason or e.plan_note or "", 500)}
                for e in execs if e.status not in ("succeeded", "queued", "running")]
    return {
        "template_version": TEMPLATE_VERSION, "title": title,
        "generated_at_utc": now.isoformat(), "generated_at_local": _ict(now), "display_timezone": str(TZ),
        "generated_by": generated_by,
        "scope": {**scope_key, "assets": [{"id": str(a.id), "name": a.name, "module": a.empire_module} for a in assets],
                  "window_days": None if batch_id else days, "window_from_utc": None if batch_id else since.isoformat()},
        "executive_summary": {
            "open_by_severity": open_by_sev, "open_total": sum(open_by_sev.values()),
            "new_since_previous": len(changes["new"]), "fixed_since_previous": len(changes["fixed"]),
            "reopened_since_previous": len(changes["reopened"]),
            "coverage": {"assets_with_successful_check": covered, "assets_in_scope": len(assets)},
            "errors_or_exclusions": len(appendix),
        },
        "coverage": coverage, "changes_vs_previous": changes, "findings": fx,
        "executions": [str(e.id) for e in execs],
        "correlation_ids": sorted({e.correlation_id for e in execs if e.correlation_id}),
        "appendix_errors_exclusions": appendix,
        "redaction": "Query strings, bearer tokens, secrets, cookies and e-mail addresses are removed; response "
                     "bodies and learner data are never stored.",
    }


def _utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def render_html(snap: dict, snap_sha: str) -> bytes:
    e = html.escape
    es = snap["executive_summary"]
    rows = "".join(
        f"<tr><td>{e(f['severity'])}</td><td>{e(f['status'])}</td><td>{e(f['title'])}</td><td>{e(f['asset'] or '')}</td>"
        f"<td>{e(f['location'] or '')}</td><td>{e(_ict(f['last_verified_at']) or '—')}</td>"
        f"<td>{e(f['remediation'] or '')}</td><td>{e(f['owner'] or '—')} / {e(f['assignee'] or '—')}</td>"
        f"<td><code>{e((f['evidence'].get('output_sha256') or '')[:16])}</code></td></tr>" for f in snap["findings"])
    cov = "".join(
        f"<tr><td>{e(c['asset'])}</td><td>{e(c['module'] or '')}</td>"
        + "".join(f"<td>{v['succeeded']}/{v['runs']} · {e(_ict(v['last_success_at']) or '—')}</td>"
                  for v in c["engines"].values()) + "</tr>" for c in snap["coverage"])
    app = "".join(f"<tr><td>{e(a['asset'] or '')}</td><td>{e(a['engine'])}</td><td>{e(a['status'])}</td>"
                  f"<td>{e(a['reason'])}</td></tr>" for a in snap["appendix_errors_exclusions"])
    ch = snap["changes_vs_previous"]
    sev = " · ".join(f"{k}: {v}" for k, v in es["open_by_severity"].items())
    doc = f"""<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>{e(snap['title'])}</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#111}}table{{border-collapse:collapse;width:100%;font-size:12px}}
td,th{{border:1px solid #ccc;padding:4px;vertical-align:top}}th{{background:#f3f3f3}}footer{{font-size:11px;color:#555;margin-top:24px}}</style>
</head><body>
<h1>{e(snap['title'])}</h1>
<p>Tạo lúc / Generated: {e(snap['generated_at_local'])} ({e(snap['generated_at_utc'])} UTC) · Timezone: {e(snap['display_timezone'])}</p>
<h2>Tóm tắt cho quản lý / Executive summary</h2>
<p>Finding đang mở / Open findings: <b>{es['open_total']}</b> ({e(sev)})</p>
<p>So với kỳ trước / Since previous report: mới/new {es['new_since_previous']} · đã sửa/fixed {es['fixed_since_previous']} · mở lại/reopened {es['reopened_since_previous']}
{(' · kỳ trước/previous ' + e(_ict(ch['previous_generated_at']) or '')) if ch['previous_snapshot_id'] else ' · chưa có kỳ trước/no previous report'}</p>
<p>Coverage: {es['coverage']['assets_with_successful_check']}/{es['coverage']['assets_in_scope']} asset có kiểm tra thành công · lỗi/loại trừ: {es['errors_or_exclusions']}</p>
<h2>Phạm vi / Scope</h2><p>{e(snap['scope']['kind'])} · {len(snap['scope']['assets'])} asset · batch {e(str(snap['scope']['batch_id']))} · window {e(str(snap['scope']['window_days']))} ngày/days</p>
<h2>Coverage</h2><table><tr><th>Asset</th><th>Module</th><th>sbom</th><th>tls_health</th></tr>{cov}</table>
<h2>Findings &amp; remediation</h2><table><tr><th>Severity</th><th>Status</th><th>Title</th><th>Asset</th><th>Location</th><th>Last verified</th><th>Remediation</th><th>Owner / assignee</th><th>Evidence sha</th></tr>{rows}</table>
<h2>Phụ lục lỗi / loại trừ · Appendix: errors &amp; exclusions</h2><table><tr><th>Asset</th><th>Engine</th><th>Status</th><th>Reason</th></tr>{app}</table>
<footer>{e(snap['redaction'])}<br>Template {e(snap['template_version'])} · snapshot sha256 {snap_sha} · executions {len(snap['executions'])} · correlation {e(', '.join(snap['correlation_ids'])[:300])}</footer>
</body></html>"""
    return doc.encode("utf-8")


def _font():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for path in (os.getenv("NOOSPIRE_PDF_FONT", ""), "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial Unicode.ttf"):
        if path and os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont("NoospireUnicode", path))
                return "NoospireUnicode", True
            except Exception:
                continue
    return "Helvetica", False


def _ascii(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def render_pdf(snap: dict, snap_sha: str) -> bytes:
    import io

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    font, unicode_ok = _font()
    txt = (lambda s: s) if unicode_ok else _ascii
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4, invariant=1)  # invariant: no timestamps/IDs in PDF bytes
    c.setTitle(_ascii(snap["title"]))
    w, h = A4
    y = h - 50

    def line(s: str, size: int = 9, gap: int = 13):
        nonlocal y
        if y < 60:
            c.showPage()
            y = h - 50
        c.setFont(font, size)
        c.drawString(40, y, txt(s)[:150])
        y -= gap

    es = snap["executive_summary"]
    line(snap["title"], 15, 22)
    line(f"Generated {snap['generated_at_local']} ({snap['generated_at_utc']} UTC)")
    line(f"Template {snap['template_version']} · snapshot sha256 {snap_sha}")
    line("")
    line("Executive summary", 12, 16)
    line(f"Open findings: {es['open_total']} · " + " · ".join(f"{k} {v}" for k, v in es['open_by_severity'].items()))
    line(f"Since previous: new {es['new_since_previous']} · fixed {es['fixed_since_previous']} · "
         f"reopened {es['reopened_since_previous']}")
    line(f"Coverage: {es['coverage']['assets_with_successful_check']}/{es['coverage']['assets_in_scope']} assets · "
         f"errors/exclusions {es['errors_or_exclusions']}")
    line("")
    line("Findings & remediation", 12, 16)
    for f in snap["findings"]:
        line(f"[{f['severity']}] {f['status']} · {f['title']}")
        line(f"   {f['asset']} · {f['location']} · last verified {_ict(f['last_verified_at']) or '-'}", 8, 11)
        line(f"   Fix: {(f['remediation'] or '-')[:130]} · owner {f['owner'] or '-'} / {f['assignee'] or '-'}", 8, 11)
    line("")
    line("Appendix: errors & exclusions", 12, 16)
    for a in snap["appendix_errors_exclusions"]:
        line(f"{a['asset']} · {a['engine']} · {a['status']} · {a['reason'][:100]}", 8, 11)
    line("")
    line(snap["redaction"][:150], 7, 10)
    if not unicode_ok:
        line("Note: no Unicode font found on this server; Vietnamese diacritics are transliterated in the PDF "
             "(HTML/JSON keep them).", 7, 10)
    c.save()
    return buf.getvalue()


async def create_snapshot(db, *, title: str, assets: List[Asset], batch_id, days: int, user_id: str,
                          scope_kind: str) -> ReportSnapshot:
    snap = await build_snapshot(db, title=title, assets=assets, batch_id=batch_id, days=days, generated_by=user_id,
                                scope_kind=scope_kind)
    raw = canonical(snap)
    sha = hashlib.sha256(raw).hexdigest()
    rid = uuid.uuid4()
    d = storage_root() / "report-snapshots" / str(rid)
    d.mkdir(parents=True, exist_ok=True)
    files = {}
    for fmt, data in (("snapshot", raw), ("json", json.dumps(snap, ensure_ascii=False, indent=2,
                                                               sort_keys=True).encode("utf-8")),
                      ("html", render_html(snap, sha)), ("pdf", render_pdf(snap, sha))):
        p = d / f"report.{ 'snapshot.json' if fmt == 'snapshot' else fmt}"
        p.write_bytes(data)
        files[fmt] = {"path": str(p), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
    prev = snap["changes_vs_previous"]["previous_snapshot_id"]
    rs = ReportSnapshot(id=rid, title=title, scope={k: snap["scope"][k] for k in ("kind", "asset_ids", "batch_id")},
                        asset_ids=snap["scope"]["asset_ids"], batch_id=batch_id, template_version=TEMPLATE_VERSION,
                        snapshot_sha256=sha, files=files, execution_ids=snap["executions"],
                        correlation_ids=snap["correlation_ids"], finding_count=len(snap["findings"]),
                        previous_snapshot_id=uuid.UUID(prev) if prev else None, created_by=user_id)
    db.add(rs)
    return rs
