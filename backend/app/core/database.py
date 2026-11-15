from typing import AsyncGenerator
from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.app.core.config import settings
from backend.app.core.security import get_password_hash
from backend.app.models.base import Base, User

# Configure engine arguments based on dialect
engine_kwargs = {"echo": False}
if settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": 30.0,
    }
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)

if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.close()

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    # Ensure all models are registered with Base metadata before creating tables
    import backend.app.models.user
    import backend.app.models.proof
    import backend.app.models.scope
    import backend.app.models.asset
    import backend.app.models.scan
    import backend.app.models.finding
    import backend.app.models.baseline
    import backend.app.models.schedule
    import backend.app.models.alert
    import backend.app.models.synthetic_identity
    import backend.app.models.rule
    import backend.app.models.intelligence
    import backend.app.models.event
    import backend.app.models.defensive
    import backend.app.models.operations  # noqa: F401
    import backend.app.models.lifecycle  # noqa: F401
    import backend.app.models.checklist  # noqa: F401
    import backend.app.reporting.generator
    from backend.app.core.empire_seeder import seed_empire_ecosystem
    from backend.app.core.checklist_seeder import seed_checklist_catalog

    async with engine.begin() as conn:
        if settings.DATABASE_URL.startswith("sqlite"):
            await conn.execute(text("PRAGMA journal_mode=WAL;"))
            await conn.execute(text("PRAGMA busy_timeout=30000;"))
        await conn.run_sync(Base.metadata.create_all)

        # Auto-migration for SQLite
        if settings.DATABASE_URL.startswith("sqlite"):
            try:
                res = await conn.execute(text("PRAGMA table_info(scans)"))
                cols = [row[1] for row in res.fetchall()]
                if cols:
                    if "batch_id" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN batch_id CHAR(36) REFERENCES scan_batches(id) ON DELETE SET NULL"))
                    if "leased_by" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN leased_by VARCHAR(128)"))
                    if "leased_at" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN leased_at TIMESTAMP"))
                    if "lease_expires_at" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN lease_expires_at TIMESTAMP"))
                    if "heartbeat_at" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN heartbeat_at TIMESTAMP"))
                    if "fencing_token" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN fencing_token INTEGER DEFAULT 0"))
                    if "attempts" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN attempts INTEGER DEFAULT 0"))
                    if "max_retries" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN max_retries INTEGER DEFAULT 3"))
                    if "available_at" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN available_at TIMESTAMP"))
                    if "cancelled_at" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN cancelled_at TIMESTAMP"))
                    if "cancellation_reason" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN cancellation_reason VARCHAR(256)"))
                    if "worker_pid" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN worker_pid INTEGER"))
                    if "idempotency_key" not in cols:
                        await conn.execute(text("ALTER TABLE scans ADD COLUMN idempotency_key VARCHAR(128)"))
            except Exception:
                pass

            try:
                res = await conn.execute(text("PRAGMA table_info(scan_batches)"))
                batch_cols = [row[1] for row in res.fetchall()]
                if batch_cols:
                    if "schedule_id" not in batch_cols:
                        await conn.execute(text("ALTER TABLE scan_batches ADD COLUMN schedule_id CHAR(36) REFERENCES daily_schedules(id) ON DELETE SET NULL"))
                    if "is_followup" not in batch_cols:
                        await conn.execute(text("ALTER TABLE scan_batches ADD COLUMN is_followup BOOLEAN DEFAULT 0"))
                    if "missed_slots_coalesced" not in batch_cols:
                        await conn.execute(text("ALTER TABLE scan_batches ADD COLUMN missed_slots_coalesced INTEGER DEFAULT 0"))
                    if "idempotency_key" not in batch_cols:
                        await conn.execute(text("ALTER TABLE scan_batches ADD COLUMN idempotency_key VARCHAR(128)"))
                    if "cancelled_at" not in batch_cols:
                        await conn.execute(text("ALTER TABLE scan_batches ADD COLUMN cancelled_at TIMESTAMP"))
                    if "cancellation_reason" not in batch_cols:
                        await conn.execute(text("ALTER TABLE scan_batches ADD COLUMN cancellation_reason VARCHAR(256)"))
            except Exception:
                pass

            try:
                res = await conn.execute(text("PRAGMA table_info(daily_schedules)"))
                sched_cols = [row[1] for row in res.fetchall()]
                if sched_cols:
                    if "last_completed_at" not in sched_cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN last_completed_at TIMESTAMP"))
                    if "active_batch_id" not in sched_cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN active_batch_id CHAR(36) REFERENCES scan_batches(id) ON DELETE SET NULL"))
                    if "pending_followup" not in sched_cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN pending_followup BOOLEAN DEFAULT 0"))
                    if "missed_slots_count" not in sched_cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN missed_slots_count INTEGER DEFAULT 0"))
                    if "overrun_active" not in sched_cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN overrun_active BOOLEAN DEFAULT 0"))
                    if "overdue_reason" not in sched_cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN overdue_reason VARCHAR(256)"))
                    if "concurrency_limit" not in sched_cols:
                        await conn.execute(text("ALTER TABLE daily_schedules ADD COLUMN concurrency_limit INTEGER DEFAULT 2"))
            except Exception:
                pass

            try:
                res = await conn.execute(text("PRAGMA table_info(users)"))
                user_cols = [row[1] for row in res.fetchall()]
                if user_cols:
                    if "email" not in user_cols:
                        await conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(256)"))
                    if "role" not in user_cols:
                        await conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(64) DEFAULT 'VIEWER'"))
                    if "tokens_valid_after" not in user_cols:
                        await conn.execute(text("ALTER TABLE users ADD COLUMN tokens_valid_after TIMESTAMP"))
            except Exception:
                pass

    # Invariant: boot NEVER creates users, assets, findings or schedules. An empty
    # production DB stays empty. Fixture/demo data only for an isolated demo env.
    if settings.SEED_DEMO_DATA and not settings.is_production:
        async with AsyncSessionLocal() as session:
            await seed_empire_ecosystem(session)

    # Checklist catalog definitions must be available for assessment runs
    async with AsyncSessionLocal() as session:
        await seed_checklist_catalog(session)
