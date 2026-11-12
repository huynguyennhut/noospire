"""Milestone 5 helpers: finding change log, observations and per-user notifications.

Everything here runs inside the caller's transaction so a result, its observations, its
change log and its notifications commit (or roll back) together.
"""

from __future__ import annotations

import uuid
from typing import Iterable, List, Optional, Sequence

from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.models.lifecycle import FindingChange, FindingObservation, Notification
from backend.app.models.user import User, UserAssetGrant

MAX_FINDING_NOTIFICATIONS = 5  # above this, one summary notification per execution


async def recipients_for_asset(db, asset_id: Optional[uuid.UUID]) -> List[str]:
    """Sole owner + active users holding any grant on the asset."""
    out = [str(settings.SOLE_OWNER_ACCOUNT_ID)]
    if asset_id is not None:
        rows = (await db.execute(select(UserAssetGrant.user_id).join(User, User.id == UserAssetGrant.user_id)
                                 .where(UserAssetGrant.asset_id == asset_id, User.is_active == True))  # noqa: E712
                ).scalars().all()
        out += [str(u) for u in rows]
    return list(dict.fromkeys(out))


async def notify(db, user_ids: Iterable[str], *, kind: str, title: str, message: str, object_type: str,
                 object_id: Optional[str], link: str, dedup_key: str, severity: str = "INFO") -> int:
    """Insert one notification per user unless (user, dedup_key) already exists."""
    users = list(dict.fromkeys(str(u) for u in user_ids if u))
    if not users:
        return 0
    have = set((await db.execute(select(Notification.user_id).where(Notification.dedup_key == dedup_key,
                                                                    Notification.user_id.in_(users)))).scalars())
    n = 0
    for u in users:
        if u in have:
            continue
        db.add(Notification(user_id=u, kind=kind, severity=severity, title=title[:255], message=message,
                            object_type=object_type, object_id=object_id, link=link[:512], dedup_key=dedup_key[:200]))
        n += 1
    return n


def record_change(db, finding_id: uuid.UUID, field: str, old, new, *, actor_id: Optional[str], actor_name: str,
                  reason: Optional[str] = None, execution_id: Optional[uuid.UUID] = None) -> None:
    if (old or None) == (new or None):
        return
    db.add(FindingChange(finding_id=finding_id, field=field, old_value=None if old is None else str(old),
                         new_value=None if new is None else str(new), actor_id=actor_id, actor_name=actor_name,
                         reason=reason, execution_id=execution_id))


def observe(db, *, finding_id: uuid.UUID, rec, outcome: str, before: Optional[str], after: Optional[str],
            reason: Optional[str] = None, output_sha: Optional[str] = None, rule_digest: Optional[str] = None,
            observed_at=None) -> None:
    kw = {"observed_at": observed_at} if observed_at else {}
    db.add(FindingObservation(finding_id=finding_id, execution_id=rec.id, batch_id=rec.batch_id, asset_id=rec.asset_id,
                              engine_id=rec.engine_id, outcome=outcome, status_before=before, status_after=after,
                              reason=reason, output_sha256=output_sha, input_sha256=rec.input_sha256,
                              rule_digest=rule_digest, **kw))


async def notify_findings(db, rec, new_rows: Sequence, reopened_rows: Sequence) -> None:
    users = await recipients_for_asset(db, rec.asset_id)
    groups = (("finding_new", "New finding", new_rows), ("finding_reopened", "Finding reopened", reopened_rows))
    for kind, label, rows in groups:
        if not rows:
            continue
        if len(rows) > MAX_FINDING_NOTIFICATIONS:
            worst = _worst(r.severity for r in rows)
            await notify(db, users, kind=kind, severity=worst, title=f"{len(rows)} × {label.lower()} ({rec.engine_id})",
                         message=f"{len(rows)} findings from execution {rec.id}.", object_type="execution",
                         object_id=str(rec.id), link=f"/findings/?scan_id={rec.scan_id}",
                         dedup_key=f"{kind}:exec:{rec.id}")
            continue
        for r in rows:
            await notify(db, users, kind=kind, severity=r.severity, title=f"{label}: {r.title}"[:255],
                         message=f"{r.scanner_rule_id} on {r.target_location} (execution {rec.id}).",
                         object_type="finding", object_id=str(r.id), link=f"/findings/?finding={r.id}",
                         dedup_key=f"{kind}:{r.id}:{rec.id}")


async def notify_execution(db, rec, status: str, reason: Optional[str]) -> None:
    failed = status in ("failed", "timed_out", "unavailable")
    if failed:
        users = [str(settings.SOLE_OWNER_ACCOUNT_ID)] + ([rec.actor_id] if rec.actor_id else [])
        await notify(db, users, kind="job_failed", severity="MEDIUM",
                     title=f"{rec.engine_id} {status}", message=reason or status, object_type="execution",
                     object_id=str(rec.id), link=f"/engine-runs/?execution={rec.id}",
                     dedup_key=f"job:{rec.id}")
    elif rec.trigger == "manual" and rec.actor_id:
        await notify(db, [rec.actor_id], kind="job_succeeded" if status == "succeeded" else "job_finished",
                     title=f"{rec.engine_id} {status}", message=reason or f"{rec.finding_count or 0} finding(s)",
                     object_type="execution", object_id=str(rec.id), link=f"/engine-runs/?execution={rec.id}",
                     dedup_key=f"job:{rec.id}")


_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]


def _worst(sevs: Iterable[str]) -> str:
    s = list(sevs)
    for x in _ORDER:
        if x in s:
            return x
    return "INFO"
