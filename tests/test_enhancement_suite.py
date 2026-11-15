"""Comprehensive test suite for NOOSFORGE Security Intelligence enhancements.
Covers:
1. Ultra Admin Seeding, Flexible Username/Email Authentication & Dev Tracking
2. Complete Log Lifecycle (Query with date/range filters, Export JSON/CSV, Purge) & System State Reset
3. Scan Scheduling Background Runner & Schedule Deletion
4. Scanner Engine Health, Versioning, Updates, & Live Integrity Testing
5. Multi-Engine Loop Testing & Security Alert Management
"""

import asyncio
from datetime import datetime, timedelta, timezone
import json
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal, init_db
from backend.app.core.scheduler import compute_next_run, get_scheduler_engine
from backend.app.core.security import decode_access_token
from backend.app.models.alert import SecurityAlert
from backend.app.models.asset import Asset
from backend.app.models.base import AdminAuditLog, User
from backend.app.models.scan import Scan, ScanLog
from backend.app.models.schedule import DailySchedule
from backend.app.schemas.common import ScanProfile, ScanStatus


# ============================================================================
# TASK 1: Ultra Admin Seeding & Flexible Authentication
# ============================================================================

from backend.app.core.security import create_access_token, get_password_hash

@pytest_asyncio.fixture(autouse=True)
async def authenticate_client(client: AsyncClient):
    async with AsyncSessionLocal() as session:
        user = await session.scalar(
            select(User).where(
                (User.username == "dangnhutnguyen0910@gmail.com")
                | (User.email == "dangnhutnguyen0910@gmail.com")
                | (User.id == uuid.UUID("00000000-0000-0000-0000-000000000001"))
            )
        )
        if not user:
            user = User(
                id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                username="dangnhutnguyen0910@gmail.com",
                email="dangnhutnguyen0910@gmail.com",
                hashed_password=get_password_hash("REDACTED-ROTATE-ME"),
                role="SUPER_ADMIN",
                is_superuser=True,
                is_active=True,
            )
            session.add(user)
            await session.commit()
        else:
            user.username = "dangnhutnguyen0910@gmail.com"
            user.email = "dangnhutnguyen0910@gmail.com"
            user.hashed_password = get_password_hash("REDACTED-ROTATE-ME")
            user.role = "SUPER_ADMIN"
            user.is_superuser = True
            user.is_active = True
            await session.commit()
    token = create_access_token("dangnhutnguyen0910@gmail.com", role="SUPER_ADMIN", is_superuser=True)
    client.headers["Authorization"] = f"Bearer {token}"


@pytest.mark.asyncio
async def test_ultra_admin_seeded_in_database(client: AsyncClient):
    """Verify that Ultra Admin user is seeded in database with SUPER_ADMIN role."""
    await init_db()
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(User).where(User.username == "dangnhutnguyen0910@gmail.com")
        )
        user = res.scalars().first()
        assert user is not None
        assert user.email == "dangnhutnguyen0910@gmail.com"
        assert user.role == "SUPER_ADMIN"
        assert user.is_superuser is True
        assert user.is_active is True


@pytest.mark.asyncio
async def test_ultra_admin_login_with_email_json(client: AsyncClient):
    """Verify login with Ultra Admin email/password JSON payload returns valid signed JWT with role claims."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "dangnhutnguyen0910@gmail.com",
            "password": "REDACTED-ROTATE-ME",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    user = data["user"]
    assert user["email"] == "dangnhutnguyen0910@gmail.com"
    assert user["role"] == "SUPER_ADMIN"
    assert user["is_superuser"] is True
    assert user["is_ultra_admin"] is True

    # Validate JWT claims
    token = data["access_token"]
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "dangnhutnguyen0910@gmail.com"
    assert payload["role"] == "SUPER_ADMIN"
    assert payload["is_superuser"] is True


@pytest.mark.asyncio
async def test_ultra_admin_login_with_username_field(client: AsyncClient):
    """Verify login works when email is provided in 'username' field (OAuth2 standard)."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={
            "username": "dangnhutnguyen0910@gmail.com",
            "password": "REDACTED-ROTATE-ME",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["is_ultra_admin"] is True


@pytest.mark.asyncio
async def test_auth_me_and_admin_audit_tracking(client: AsyncClient):
    """Verify /auth/me returns Ultra Admin profile and /auth/audit tracks admin actions."""
    # 1. Login
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "dangnhutnguyen0910@gmail.com", "password": "REDACTED-ROTATE-ME"},
    )
    token = login_resp.json()["access_token"]

    # 2. Get me
    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()
    assert me_data["username"] == "dangnhutnguyen0910@gmail.com"
    assert me_data["role"] == "SUPER_ADMIN"
    assert me_data["is_ultra_admin"] is True

    # 3. Check audit log
    audit_resp = await client.get("/api/v1/auth/audit")
    assert audit_resp.status_code == 200
    audit_items = audit_resp.json()
    assert len(audit_items) > 0
    assert any(item["username"] == "dangnhutnguyen0910@gmail.com" for item in audit_items)


# ============================================================================
# TASK 2: Complete Log Lifecycle & System State Reset
# ============================================================================

@pytest.mark.asyncio
async def test_logs_query_and_filtering(client: AsyncClient):
    """Verify querying /api/v1/logs with days, level, search, and scan_id filters."""
    # Seed a scan and several logs
    async with AsyncSessionLocal() as session:
        asset_res = await session.execute(select(Asset).limit(1))
        asset = asset_res.scalars().first()
        scan = Scan(
            id=uuid.uuid4(),
            asset_id=asset.id,
            engine="all",
            profile=ScanProfile.QUICK.value,
            status=ScanStatus.COMPLETED.value,
            target_locator=asset.target_locator,
        )
        session.add(scan)
        await session.flush()

        log1 = ScanLog(
            id=uuid.uuid4(),
            scan_id=scan.id,
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            source="nuclei",
            message="Target port discovery finished for empire.edu.vn",
        )
        log2 = ScanLog(
            id=uuid.uuid4(),
            scan_id=scan.id,
            timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            level="ERROR",
            source="system",
            message="SSL handshake exception simulated",
        )
        session.add_all([log1, log2])
        await session.commit()
        test_scan_id = str(scan.id)

    # 1. Query by scan_id
    resp = await client.get(f"/api/v1/logs?scan_id={test_scan_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2

    # 2. Query with days filter
    resp_days = await client.get(f"/api/v1/logs?scan_id={test_scan_id}&days=1")
    assert resp_days.status_code == 200
    assert resp_days.json()["total"] >= 2

    # 3. Query with level filter
    resp_level = await client.get(f"/api/v1/logs?scan_id={test_scan_id}&level=ERROR")
    assert resp_level.status_code == 200
    assert any("handshake" in item["message"] for item in resp_level.json()["items"])

    # 4. Query with search filter
    resp_search = await client.get(f"/api/v1/logs?scan_id={test_scan_id}&search=discovery")
    assert resp_search.status_code == 200
    assert len(resp_search.json()["items"]) >= 1

    # 5. Query scan-specific logs endpoint
    resp_scan_logs = await client.get(f"/api/v1/scans/{test_scan_id}/logs?days=7")
    assert resp_scan_logs.status_code == 200
    assert resp_scan_logs.json()["total"] >= 2


@pytest.mark.asyncio
async def test_logs_export_json_and_csv(client: AsyncClient):
    """Verify exporting logs in JSON and CSV formats."""
    # Export JSON
    resp_json = await client.get("/api/v1/logs/export?format=json")
    assert resp_json.status_code == 200
    assert resp_json.headers["content-type"].startswith("application/json")
    assert "attachment; filename=noosforge_logs.json" in resp_json.headers.get("content-disposition", "")
    json_data = resp_json.json()
    assert isinstance(json_data, list)

    # Export CSV
    resp_csv = await client.get("/api/v1/logs/export?format=csv")
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "attachment; filename=noosforge_logs.csv" in resp_csv.headers.get("content-disposition", "")
    assert "scan_id" in resp_csv.text


@pytest.mark.asyncio
async def test_logs_purge_and_scan_logs_deletion(client: AsyncClient):
    """Verify deleting logs for a specific scan and purging logs."""
    # Create temporary scan and log
    async with AsyncSessionLocal() as session:
        asset_res = await session.execute(select(Asset).limit(1))
        asset = asset_res.scalars().first()
        temp_scan = Scan(
            id=uuid.uuid4(),
            asset_id=asset.id,
            engine="all",
            profile=ScanProfile.QUICK.value,
            status=ScanStatus.COMPLETED.value,
            target_locator=asset.target_locator,
        )
        session.add(temp_scan)
        await session.flush()
        temp_log = ScanLog(
            id=uuid.uuid4(),
            scan_id=temp_scan.id,
            timestamp=datetime.now(timezone.utc),
            level="INFO",
            source="system",
            message="Ephemeral log for purge verification",
        )
        session.add(temp_log)
        await session.commit()
        scan_id_str = str(temp_scan.id)

    # Delete scan logs via DELETE /api/v1/scans/{scan_id}/logs
    del_resp = await client.delete(f"/api/v1/scans/{scan_id_str}/logs")
    assert del_resp.status_code == 200
    assert del_resp.json()["purged_count"] >= 1

    # Verify logs are gone for this scan
    check_resp = await client.get(f"/api/v1/scans/{scan_id_str}/logs")
    assert check_resp.json()["total"] == 0

    # Purge endpoint test
    purge_resp = await client.post("/api/v1/logs/purge", json={"days": 365})
    assert purge_resp.status_code == 200
    assert "purged_count" in purge_resp.json()


@pytest.mark.asyncio
async def test_system_state_reset_to_baseline(client: AsyncClient):
    """Verify POST /api/v1/system/reset restores platform to initial verified baseline."""
    resp = await client.post("/api/v1/system/reset")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "RESET_SUCCESSFUL"
    assert data["baseline_target"] == "https://empire.edu.vn/"

    # Check that primary target is re-seeded
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Asset).where(Asset.target_locator == "https://empire.edu.vn/"))
        primary = res.scalars().first()
        assert primary is not None
        assert str(getattr(primary.verification_status, "value", primary.verification_status)) == "VERIFIED"

    # Also test settings alias POST /api/v1/settings/reset-baseline
    alias_resp = await client.post("/api/v1/settings/reset-baseline")
    assert alias_resp.status_code == 200
    assert alias_resp.json()["status"] == "RESET_SUCCESSFUL"


# ============================================================================
# TASK 3: Scan Scheduling Background Runner & Deletion
# ============================================================================

@pytest.mark.asyncio
async def test_cron_next_run_calculation():
    """Verify compute_next_run correctly evaluates 5-part cron expressions."""
    now = datetime(2026, 11, 10, 1, 0, 0, tzinfo=timezone.utc)
    # Daily at 02:00
    next_run = compute_next_run("0 2 * * *", from_dt=now)
    assert next_run > now

    # Every 5 minutes
    next_5m = compute_next_run("*/5 * * * *", from_dt=now)
    assert next_5m > now
    assert (next_5m - now).total_seconds() <= 300


@pytest.mark.asyncio
async def test_schedule_crud_and_deletion(client: AsyncClient):
    """Verify creating schedule with next_run_at, triggering, and deleting schedule."""
    # 1. Create schedule
    create_resp = await client.post(
        "/api/v1/schedules",
        json={
            "name": "Automated Midnight Security Audit",
            "profile": "DAILY_SECURITY",
            "cron_expression": "0 0 * * *",
            "timezone": "Asia/Ho_Chi_Minh",
            "target_ids": ["ALL"],
            "is_active": True,
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    sched_data = create_resp.json()
    sched_id = sched_data["id"]
    assert sched_data["next_run_at"] is not None

    # 2. Get schedule by ID
    get_resp = await client.get(f"/api/v1/schedules/{sched_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Automated Midnight Security Audit"

    # 3. Trigger schedule
    trig_resp = await client.post(f"/api/v1/schedules/{sched_id}/trigger")
    assert trig_resp.status_code == 200
    assert "dispatched_scans" in trig_resp.json()

    # Cancel dispatched scans so background workers don't retain locks
    await client.post("/api/v1/scans/stop-all")

    # 4. Delete schedule
    del_resp = await client.delete(f"/api/v1/schedules/{sched_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["message"] == "Schedule deleted successfully"

    # 5. Confirm deletion
    get_after = await client.get(f"/api/v1/schedules/{sched_id}")
    assert get_after.status_code == 404


@pytest.mark.asyncio
async def test_scheduler_engine_tick():
    """Verify SchedulerEngine background tick evaluates schedules and calculates next_run_at."""
    engine = get_scheduler_engine()
    triggered = await engine.tick()
    assert isinstance(triggered, int)


# ============================================================================
# TASK 4: Engine Health, Updates & Live Integrity Testing
# ============================================================================

@pytest.mark.asyncio
async def test_engine_health_endpoint(client: AsyncClient):
    """Verify /api/v1/engines/health returns real runtime status for all 4 engines."""
    resp = await client.get("/api/v1/engines/health")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["all_healthy"] is True
    assert data["total_engines"] == 4
    assert data["online_engines"] == 4

    engines = {e["name"]: e for e in data["engines"]}
    assert "nuclei" in engines
    assert "zap" in engines
    assert "empire_engine" in engines
    assert "crawler" in engines

    # Check Nuclei real runtime info
    nuclei = engines["nuclei"]
    assert nuclei["status"] == "ONLINE"
    assert "cve-detection" in nuclei["capabilities"]

    # Check Empire engine
    empire = engines["empire_engine"]
    assert empire["mode"] == "IN_PROCESS"
    assert "module-a-auth" in empire["capabilities"]


@pytest.mark.asyncio
async def test_engine_check_updates_endpoint(client: AsyncClient):
    """Verify /api/v1/engines/check-updates checks template/version synchronization."""
    resp = await client.post("/api/v1/engines/check-updates")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "CHECK_COMPLETED"
    assert len(data["engines"]) == 4


@pytest.mark.asyncio
async def test_engine_test_live_integrity_probe(client: AsyncClient):
    """Verify /api/v1/engines/test executes live integrity probes on all engines."""
    resp = await client.post("/api/v1/engines/test")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "ALL_ENGINES_PASS"
    assert data["all_passed"] is True
    assert len(data["probes"]) == 4
    for probe in data["probes"]:
        assert probe["passed"] is True
        assert probe["latency_ms"] >= 0


# ============================================================================
# TASK 5: Multi-Engine Loop Testing & Alert Management
# ============================================================================

@pytest.mark.asyncio
async def test_multi_engine_loop_test_endpoint(client: AsyncClient):
    """Verify /api/v1/scans/loop-test executes multi-pass sequential assessment on primary target."""
    resp = await client.post(
        "/api/v1/scans/loop-test",
        json={
            "target_locator": "https://empire.edu.vn/",
            "loops": 2,
            "profile": "QUICK",
            "engines": ["empire_engine", "crawler"],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "COMPLETED"
    assert data["loops_requested"] == 2
    assert data["loops_completed"] == 2
    assert len(data["passes"]) == 2

    # Check passes result
    for pass_info in data["passes"]:
        assert pass_info["status"] in ("COMPLETED", "QUEUED", "RUNNING")
        assert pass_info["duration_seconds"] >= 0


@pytest.mark.asyncio
async def test_security_alert_lifecycle(client: AsyncClient):
    """Verify unread-count, read-all, and delete alert endpoints."""
    # Seed an alert
    async with AsyncSessionLocal() as session:
        alert = SecurityAlert(
            id=uuid.uuid4(),
            severity="HIGH",
            title="Test Vulnerability Notification",
            message="Transient high risk finding discovered during test.",
            category="VULN",
            is_read=False,
            metadata_json={"test": True},
        )
        session.add(alert)
        await session.commit()
        alert_id = str(alert.id)

    # 1. Check unread count
    count_resp = await client.get("/api/v1/alerts/unread-count")
    assert count_resp.status_code == 200
    assert count_resp.json()["unread_count"] >= 1

    # 2. Mark all read
    read_resp = await client.post("/api/v1/alerts/read-all")
    assert read_resp.status_code == 200
    assert read_resp.json()["marked_read"] >= 1

    # 3. Delete single alert
    del_resp = await client.delete(f"/api/v1/alerts/{alert_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["message"] == "Alert deleted successfully"

    # 4. Delete alerts in bulk
    del_all_resp = await client.delete("/api/v1/alerts?is_read=true")
    assert del_all_resp.status_code == 200
    assert "deleted_count" in del_all_resp.json()
