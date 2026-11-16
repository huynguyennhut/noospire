"""Measured diagnostics and real offline self-tests; no target or upstream requests."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from backend.app.core.database import AsyncSessionLocal
from backend.app.models.alert import SecurityAlert
from backend.app.models.defensive import AdvisorySnapshot, WorkerHeartbeat
from tests_pilot.conftest import csrf_headers, login, OWNER_PASSWORD
from backend.app.core.config import settings

API = "/api/v1/engines"


@pytest.mark.parametrize("age", [timedelta(minutes=2), timedelta(hours=-1)])
async def test_stale_or_future_worker_does_not_establish_readiness(client, owner, age):
    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    async with AsyncSessionLocal() as db:
        db.add(WorkerHeartbeat(worker_id="synthetic-worker", engines=["sbom", "tls_health"],
                               last_seen_at=datetime.now(timezone.utc) - age))
        await db.commit()
    response = (await client.get(f"{API}/health")).json()
    assert response["status"] == "UNAVAILABLE" and response["operational_count"] == 0
    assert all(e["last_success_at"] is None and e["workers_online"] == 0 for e in response["engines"])


async def test_advertised_engine_and_snapshot_freshness_are_required(client, owner):
    from tests_pilot.test_m3_sbom_flow import import_snapshot

    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    async with AsyncSessionLocal() as db:
        db.add(WorkerHeartbeat(worker_id="synthetic-worker", engines=["tls_health"],
                               last_seen_at=datetime.now(timezone.utc)))
        await db.commit()
    by = {e["id"]: e for e in (await client.get(f"{API}/health")).json()["engines"]}
    assert by["tls_health"]["status"] == "OPERATIONAL" and by["sbom"]["status"] == "UNAVAILABLE"
    await import_snapshot(client, csrf_headers(client))
    async with AsyncSessionLocal() as db:
        worker = await db.get(WorkerHeartbeat, "synthetic-worker")
        worker.engines = ["sbom", "tls_health"]
        snapshot = (await db.execute(select(AdvisorySnapshot))).scalars().one()
        snapshot.imported_at = datetime.now(timezone.utc) - timedelta(days=8)
        await db.commit()
    response = (await client.get(f"{API}/health")).json()
    by = {e["id"]: e for e in response["engines"]}
    assert response["status"] == "DEGRADED" and response["operational_count"] == 1
    assert by["sbom"]["status"] == "DEGRADED" and "7 days" in by["sbom"]["reason"]
    assert by["sbom"]["rules"]["digest"]
    assert by["sbom"]["last_success_at"] is None  # inputs/readiness are not an executed scan


async def test_selftest_reports_a_driver_failure_without_false_success_or_alert(client, owner, monkeypatch):
    from backend.app.engines import sbom

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic-secret-must-not-be-returned")

    monkeypatch.setattr(sbom, "analyze", broken)
    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    response = await client.post(f"{API}/test", headers=csrf_headers(client))
    assert response.status_code == 200 and response.json()["overall_status"] == "FAIL"
    by = {e["engine"]: e for e in response.json()["results"]}
    assert by["sbom"]["status"] == "FAIL" and by["tls_health"]["status"] == "PASS"
    assert "synthetic-secret" not in response.text
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(func.count()).select_from(SecurityAlert))).scalar_one() == 0


async def test_offline_selftest_and_version_report_make_no_network_calls(client, owner, monkeypatch):
    import socket

    def no_dns(*args, **kwargs):
        pytest.fail("offline diagnostics attempted network resolution")

    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    await login(client, settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    h = csrf_headers(client)
    response = await client.post(f"{API}/test", headers=h)
    assert response.json()["overall_status"] == "PASS"
    assert "not tested" in response.json()["scope"]
    update = (await client.post(f"{API}/check-updates", headers=h)).json()
    assert update["updates_checked"] is False
    assert all(e["latest_version"] is None and e["has_update"] is None and not e["templates_updated"]
               for e in update["engines"])
    assert "not queried" in update["note"]
