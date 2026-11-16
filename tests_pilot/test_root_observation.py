"""Operator observation tested only against owned local TLS or mocks."""
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.engines import tls_health
from scripts.observe_empire_root import build_report, observe, stop_reason
from tests_pilot.test_m3_tls_health import HttpsService


async def test_head_measurement_uses_real_tls_and_retains_no_response_body():
    service = HttpsService(30)
    try:
        result = await tls_health.measure(f"https://localhost:{service.port}/", allow_private=True,
                                          ca_file=str(service.cert), method="HEAD")
        assert result.http_status == 200 and result.tls_verified is True
        assert len(service.requests) == 1 and service.requests[0].startswith(b"HEAD / HTTP/1.1\r\n")
        assert b"Authorization:" not in service.requests[0] and b"Cookie:" not in service.requests[0]
        assert result.bytes_received < 150  # headers only; service deliberately sends a body
    finally:
        service._stop = True
        service.sock.close()


def make_db(tmp_path, stop=False, expires=None, origin="https://empire.edu.vn"):
    path = tmp_path / "root.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE assets(id TEXT,target_locator TEXT)")
        db.execute("CREATE TABLE asset_assessment_scopes(asset_id TEXT,emergency_stop_active INT,exact_origin TEXT,ports TEXT,expires_at TEXT)")
        db.execute("INSERT INTO assets VALUES('root','https://empire.edu.vn/')")
        db.execute("INSERT INTO asset_assessment_scopes VALUES('root',?,?,?,?)", (stop, origin, '[443]', expires))
    return path


async def test_stop_before_start_never_calls_network(tmp_path, monkeypatch):
    def unexpected(*a, **k):
        pytest.fail("stopped target reached network")
    monkeypatch.setattr(tls_health, "measure", unexpected)
    db = make_db(tmp_path, stop=True)
    result = await observe(db, tmp_path / "global-stop")
    assert result["reason"] == "TARGET_EMERGENCY_STOP" and result["http_requests"] == 0


async def test_global_stop_cancels_in_flight_socket_task(tmp_path, monkeypatch):
    db = make_db(tmp_path)
    stop = tmp_path / "global-stop"
    cleanup = []
    async def pending(*a, **k):
        try:
            stop.touch()
            await asyncio.sleep(20)
        finally:
            cleanup.append(True)
    monkeypatch.setattr(tls_health, "measure", pending)
    result = await observe(db, stop, timeout=1)
    assert result["reason"] == "GLOBAL_STOP_FILE" and cleanup == [True]


async def test_total_deadline_cancels_without_retry(tmp_path, monkeypatch):
    db = make_db(tmp_path)
    calls = []
    async def pending(url, **kwargs):
        calls.append((url, kwargs))
        await asyncio.sleep(20)
    monkeypatch.setattr(tls_health, "measure", pending)
    result = await observe(db, tmp_path / "global-stop", timeout=0.01)
    assert result["reason"] == "TOTAL_TIMEOUT"
    assert calls == [("https://empire.edu.vn/", {"allow_private": False, "timeout": 5, "method": "HEAD"})]


@pytest.mark.parametrize("kind", ["expired", "other_origin"])
def test_scope_expiry_and_origin_are_enforced_before_observation(tmp_path, kind):
    db = make_db(tmp_path, expires=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat() if kind == "expired" else None,
                 origin="https://other.pilot-test.invalid" if kind == "other_origin" else "https://empire.edu.vn")
    assert stop_reason(db, tmp_path / "global-stop") == "NO_ACTIVE_EXACT_ROOT_SCOPE"


@pytest.mark.parametrize("http,expected_gap", [(401, "AUTHENTICATED_COVERAGE_NOT_CONFIGURED"), (403, "AUTHENTICATED_COVERAGE_NOT_CONFIGURED"), (302, "ROUTE_REDIRECT_NOT_FOLLOWED"), (429, None), (503, None)])
def test_challenge_redirect_and_health_errors_are_not_fake_passes_or_findings(http, expected_gap):
    report = build_report({"outcome": "OBSERVED", "measurement": {"http_status": http}})
    assert report["checks"][0]["outcome"] == "COVERAGE_GAP"
    assert report["route_coverage_gap"] == expected_gap
    assert report["full_assessment_complete"] is False and report["application_health_endpoint_verified"] is False
    assert all(c["outcome"] != "FINDING" for c in report["checks"])


def test_unexecuted_checks_cannot_be_reported_passed():
    report = build_report({"outcome": "BLOCKED", "reason": "TARGET_EMERGENCY_STOP", "measurement": None})
    assert all(c["outcome"] == "COVERAGE_GAP" for c in report["checks"])
