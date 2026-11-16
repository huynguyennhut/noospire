"""Database-Backed Queue Persistence with Worker Leases, Split-Brain Fencing, and Retries.

Implements IDBDurableQueue supporting atomic claims across PostgreSQL (FOR UPDATE SKIP LOCKED)
and SQLite (atomic CAS updates), lease heartbeats, bounded retries with exponential backoff,
and periodic recovery of abandoned/expired worker leases.
"""

from datetime import datetime, timedelta, timezone
import logging
import random
from typing import List, Optional
import uuid

from sqlalchemy import and_, func, or_, select, true, update
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan
from backend.app.core.config import settings
from backend.app.schemas.common import ScanQualityStatus, ScanStatus

logger = logging.getLogger("sentinel.queue")


class IDBDurableQueue:
    """Interface for database-backed queue operations across PostgreSQL and SQLite."""

    @staticmethod
    async def claim_next_job(
        session: AsyncSession,
        worker_id: str,
        lease_duration_seconds: int = 60,
        max_running: Optional[int] = None,
    ) -> Optional[Scan]:
        """Atomically claims the next eligible QUEUED job.

        Uses FOR UPDATE SKIP LOCKED on PostgreSQL, atomic CAS loop on SQLite.
        Increments fencing_token and sets lease_expires_at.
        """
        now = datetime.now(timezone.utc)
        from backend.app.models.defensive import ExecutionRecord
        from backend.app.models.operations import CapacitySettings
        capacity = await session.get(CapacitySettings, 1)
        if capacity and capacity.emergency_stop_active:
            return None
        not_paused = ~select(CapacitySettings.id).where(
            CapacitySettings.id == 1, CapacitySettings.emergency_stop_active.is_(True)
        ).exists()
        # Plan previews are advisory snapshots: concurrent requests can both plan
        # the same host. Reserve public-web concurrency and minimum spacing in
        # the SQLite claim itself, where writers are serialized.
        candidate_host = (select(ExecutionRecord.target_host)
                          .where(ExecutionRecord.scan_id == Scan.id,
                                 ExecutionRecord.engine_id == "public_web")
                          .correlate(Scan).scalar_subquery())
        public_ids = select(ExecutionRecord.scan_id).where(ExecutionRecord.engine_id == "public_web")
        other_scan, other_execution = aliased(Scan), aliased(ExecutionRecord)
        host_busy = (select(other_scan.id).join(other_execution, other_execution.scan_id == other_scan.id)
                     .where(other_scan.id != Scan.id,
                            other_execution.engine_id.in_(("public_web", "tls_health")),
                            other_execution.target_host == candidate_host,
                            or_(other_scan.started_at >= now - timedelta(seconds=20),
                                and_(other_scan.status.in_((ScanStatus.RUNNING.value, ScanStatus.INITIALIZING.value,
                                                           ScanStatus.COMPLETING.value)),
                                     other_scan.lease_expires_at > now)))
                     .correlate(Scan).exists())
        public_host_available = or_(Scan.id.not_in(public_ids),
                                    and_(candidate_host.is_not(None), ~host_busy))
        eligible = Scan.id.in_(select(ExecutionRecord.scan_id)) if settings.DEFENSIVE_ONLY else true()
        dialect = session.bind.dialect.name if session.bind else "sqlite"
        is_sqlite = dialect == "sqlite"
        # Estate-wide capacity: count live leases across every worker process.
        _live = aliased(Scan)
        running_now = (
            select(func.count()).select_from(_live)
            .where(_live.status.in_((ScanStatus.RUNNING.value, ScanStatus.INITIALIZING.value,
                                     ScanStatus.COMPLETING.value)),
                   _live.lease_expires_at != None, _live.lease_expires_at > now,
                   _live.id.in_(select(ExecutionRecord.scan_id)) if settings.DEFENSIVE_ONLY else true())
            .scalar_subquery()
        )
        if max_running is not None and not is_sqlite:
            if ((await session.execute(select(running_now))).scalar() or 0) >= max_running:
                return None

        if not is_sqlite:
            # PostgreSQL: lock-free FOR UPDATE SKIP LOCKED
            stmt = (
                select(Scan)
                .where(
                    (Scan.status == ScanStatus.QUEUED.value)
                    & ((Scan.available_at == None) | (Scan.available_at <= now))
                    & eligible
                    & not_paused
                    & public_host_available
                )
                .order_by(Scan.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            res = await session.execute(stmt)
            scan = res.scalars().first()
            if scan:
                scan.status = ScanStatus.RUNNING.value
                scan.leased_by = worker_id
                scan.leased_at = now
                scan.lease_expires_at = now + timedelta(seconds=lease_duration_seconds)
                scan.heartbeat_at = now
                scan.fencing_token = (scan.fencing_token or 0) + 1
                scan.attempts = (scan.attempts or 0) + 1
                if not scan.started_at:
                    scan.started_at = now
                await session.commit()
                return scan
            return None
        else:
            # SQLite: Optimistic CAS query loop
            stmt = (
                select(Scan.id, Scan.fencing_token)
                .where(
                    (Scan.status == ScanStatus.QUEUED.value)
                    & ((Scan.available_at == None) | (Scan.available_at <= now))
                    & eligible
                    & not_paused
                    & public_host_available
                )
                .order_by(Scan.created_at.asc())
                .limit(10)
            )
            res = await session.execute(stmt)
            candidates = res.all()

            for cand_id, old_token in candidates:
                old_tok = old_token if old_token is not None else 0
                new_token = old_tok + 1
                update_stmt = (
                    update(Scan)
                    .where(
                        (Scan.id == cand_id)
                        & (Scan.status == ScanStatus.QUEUED.value)
                        & (Scan.fencing_token == old_tok)
                        & eligible
                        & not_paused
                        & public_host_available
                        # SQLite serialises writers, so this cap check and the claim are one atomic step.
                        & ((running_now < max_running) if max_running is not None else true())
                    )
                    .values(
                        status=ScanStatus.RUNNING.value,
                        leased_by=worker_id,
                        leased_at=now,
                        lease_expires_at=now + timedelta(seconds=lease_duration_seconds),
                        heartbeat_at=now,
                        fencing_token=new_token,
                        attempts=Scan.attempts + 1,
                        started_at=func.coalesce(Scan.started_at, now),
                    )
                )
                result = await session.execute(update_stmt)
                if result.rowcount == 1:
                    await session.commit()
                    scan_res = await session.execute(select(Scan).where(Scan.id == cand_id))
                    return scan_res.scalars().first()
                await session.rollback()

            return None

    @staticmethod
    async def renew_lease_heartbeat(
        session: AsyncSession,
        scan_id: uuid.UUID,
        fencing_token: int,
        lease_duration_seconds: int = 60,
    ) -> bool:
        """Extends lease_expires_at conditioned on matching fencing_token.

        Returns False if lease was lost or revoked.
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=lease_duration_seconds)
        stmt = (
            update(Scan)
            .where(
                (Scan.id == scan_id)
                & (Scan.fencing_token == fencing_token)
                # Every phase that still holds the lease (legacy dispatcher moves
                # RUNNING -> INITIALIZING -> COMPLETING); otherwise long jobs self-cancel.
                & (Scan.status.in_((ScanStatus.RUNNING.value, ScanStatus.INITIALIZING.value,
                                    ScanStatus.COMPLETING.value)))
            )
            .values(
                heartbeat_at=now,
                lease_expires_at=expires,
            )
        )
        result = await session.execute(stmt)
        if result.rowcount == 1:
            await session.commit()
            return True
        await session.rollback()
        return False

    @staticmethod
    async def complete_job(
        session: AsyncSession,
        scan_id: uuid.UUID,
        fencing_token: int,
        final_status: str,
        final_quality: Optional[str] = None,
        findings_to_persist: Optional[List[NormalizedFinding]] = None,
        error_message: Optional[str] = None,
        progress_percentage: int = 100,
    ) -> bool:
        """Atomically persists findings and transitions job to terminal state,

        guarded strictly by fencing_token. Returns False if token was preempted.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            update(Scan)
            .where(
                (Scan.id == scan_id)
                & (Scan.fencing_token == fencing_token)
            )
            .values(
                status=final_status,
                quality_status=final_quality,
                error_message=error_message,
                progress_percentage=progress_percentage,
                completed_at=now,
                lease_expires_at=None,
                leased_by=None,
            )
        )
        result = await session.execute(stmt)
        if result.rowcount != 1:
            await session.rollback()
            return False

        if findings_to_persist:
            for finding in findings_to_persist:
                session.add(finding)

        await session.commit()
        return True

    @staticmethod
    async def fail_or_retry_job(
        session: AsyncSession,
        scan_id: uuid.UUID,
        fencing_token: int,
        error: Exception,
        is_transient: bool = True,
        base_backoff_seconds: int = 5,
        max_backoff_seconds: int = 60,
    ) -> str:
        """Evaluates retry budget. If transient and attempts < max_retries,

        schedules retry with exponential backoff; otherwise transitions to FAILED.
        """
        stmt = select(Scan).where((Scan.id == scan_id) & (Scan.fencing_token == fencing_token))
        res = await session.execute(stmt)
        scan = res.scalars().first()
        if not scan:
            await session.rollback()
            return "FENCING_REJECTED"

        now = datetime.now(timezone.utc)
        current_attempts = scan.attempts or 1
        max_retries = scan.max_retries if scan.max_retries is not None else 3

        if is_transient and current_attempts < max_retries:
            backoff = min(max_backoff_seconds, base_backoff_seconds * (2 ** (current_attempts - 1)))
            jitter = random.uniform(0.8, 1.2)
            delay = max(1.0, backoff * jitter)

            scan.status = ScanStatus.QUEUED.value
            scan.available_at = now + timedelta(seconds=delay)
            scan.leased_by = None
            scan.lease_expires_at = None
            scan.error_message = (
                f"Transient error: {str(error)} (retrying in {delay:.1f}s, attempt {current_attempts}/{max_retries})"
            )
            await session.commit()
            logger.info("Scan %s scheduled for retry in %.1fs (attempt %s/%s)", scan_id, delay, current_attempts, max_retries)
            return "RETRY_SCHEDULED"
        else:
            scan.status = ScanStatus.FAILED.value
            scan.quality_status = ScanQualityStatus.SCANNER_FAILED.value
            scan.completed_at = now
            scan.leased_by = None
            scan.lease_expires_at = None
            scan.error_message = str(error)
            await session.commit()
            logger.warning("Scan %s transitioned to terminal FAILED: %s", scan_id, error)
            return "FAILED"

    @staticmethod
    async def recover_expired_leases(
        session: AsyncSession,
        requeue_backoff_seconds: int = 5,
    ) -> int:
        """Periodic reaper scanning for jobs in RUNNING whose lease_expires_at < now.

        Increments fencing_token to fence off dead workers and requeues/fails them.
        """
        now = datetime.now(timezone.utc)
        from backend.app.models.defensive import ExecutionRecord
        stmt = (
            select(Scan)
            .where(
                (Scan.status.in_((ScanStatus.RUNNING.value, ScanStatus.INITIALIZING.value,
                                  ScanStatus.COMPLETING.value)))
                & (Scan.lease_expires_at != None)
                & (Scan.lease_expires_at < now)
                & (Scan.id.in_(select(ExecutionRecord.scan_id)) if settings.DEFENSIVE_ONLY else true())
            )
        )
        res = await session.execute(stmt)
        expired_scans = res.scalars().all()
        recovered_count = 0

        for scan in expired_scans:
            scan.fencing_token = (scan.fencing_token or 0) + 1
            current_attempts = scan.attempts or 1
            max_retries = scan.max_retries if scan.max_retries is not None else 3

            if current_attempts < max_retries:
                scan.status = ScanStatus.QUEUED.value
                scan.available_at = now + timedelta(seconds=requeue_backoff_seconds)
                scan.leased_by = None
                scan.lease_expires_at = None
                scan.error_message = (
                    f"Lease expired (worker abandoned or crashed). Requeued for attempt {current_attempts + 1}."
                )
                logger.info("Reaped expired lease for scan %s (requeued for retry)", scan.id)
            else:
                scan.status = ScanStatus.FAILED.value
                scan.quality_status = ScanQualityStatus.SCANNER_FAILED.value
                scan.completed_at = now
                scan.leased_by = None
                scan.lease_expires_at = None
                scan.error_message = "Scan abandoned: worker lease expired and maximum retry budget exceeded."
                logger.warning("Reaped expired lease for scan %s (max retries exceeded, marked FAILED)", scan.id)

            recovered_count += 1

        if recovered_count > 0:
            await session.commit()

        return recovered_count

    @staticmethod
    async def cancel_job(
        session: AsyncSession,
        scan_id: uuid.UUID,
        reason: str = "Scan cancelled by user.",
    ) -> bool:
        """Sets status=CANCELLED, records cancelled_at, increments fencing_token,

        and triggers process tree termination.
        """
        now = datetime.now(timezone.utc)
        stmt = select(Scan).where(Scan.id == scan_id)
        res = await session.execute(stmt)
        scan = res.scalars().first()
        if not scan:
            return False

        if scan.status in (ScanStatus.COMPLETED.value, ScanStatus.FAILED.value, ScanStatus.CANCELLED.value):
            return False

        scan.status = ScanStatus.CANCELLED.value
        scan.cancelled_at = now
        scan.cancellation_reason = reason
        scan.completed_at = now
        scan.fencing_token = (scan.fencing_token or 0) + 1
        scan.leased_by = None
        scan.lease_expires_at = None
        await session.commit()

        # Trigger process tree termination
        try:
            from backend.app.core.dispatcher import process_safety
            process_safety.terminate_process_tree(scan_id)
        except Exception as e:
            logger.debug("Process tree termination error: %s", e)

        return True
