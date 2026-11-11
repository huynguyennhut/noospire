"""Gateway contract over real loopback processes: real FastAPI (throwaway DB), real gateway,
and a controlled misbehaving upstream. Covers origin-failure cases of Round A."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(url: str, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=1.0)
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"not up: {url}")


def _spawn(module: str, port: int, env: dict) -> subprocess.Popen:
    return subprocess.Popen(
        [PY, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT), env={**os.environ, **env}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )


@pytest.fixture(scope="module")
def stack():
    tmp = Path(tempfile.mkdtemp(prefix="noospire-gw-"))
    static = tmp / "out"
    (static / "dashboard").mkdir(parents=True)
    (static / "index.html").write_text("<html>console</html>", encoding="utf-8")
    (static / "dashboard" / "index.html").write_text("<html>dashboard</html>", encoding="utf-8")
    (static / "404.html").write_text("<html>not found</html>", encoding="utf-8")
    (static / "_worker.js").write_text("// must never be served", encoding="utf-8")

    api_port, gw_port, gw_bad_port, fake_port, dead_port = (_free_port() for _ in range(5))
    api_env = {
        "SENTINEL_DATABASE_URL": f"sqlite+aiosqlite:///{(tmp / 'api.db').as_posix()}",
        "SENTINEL_ENV": "test", "SENTINEL_PROCESS_ROLE": "api",
        "SENTINEL_SOLE_OWNER_EMAIL": "owner@pilot-test.invalid",
    }
    procs = [
        _spawn("backend.main:app", api_port, api_env),
        _spawn("tests_pilot.fake_upstream:app", fake_port, {}),
        _spawn("deploy.gateway.gateway:app", gw_port, {
            "NOOSPIRE_API_ORIGIN": f"http://127.0.0.1:{api_port}", "NOOSPIRE_STATIC_DIR": str(static)}),
        _spawn("deploy.gateway.gateway:app", gw_bad_port, {
            "NOOSPIRE_API_ORIGIN": f"http://127.0.0.1:{fake_port}", "NOOSPIRE_STATIC_DIR": str(static),
            "NOOSPIRE_GW_READ_TIMEOUT": "1"}),
    ]
    dead_gw_port = _free_port()
    procs.append(_spawn("deploy.gateway.gateway:app", dead_gw_port, {
        "NOOSPIRE_API_ORIGIN": f"http://127.0.0.1:{dead_port}", "NOOSPIRE_STATIC_DIR": str(static)}))
    try:
        for p in (api_port, fake_port, gw_port, gw_bad_port, dead_gw_port):
            _wait(f"http://127.0.0.1:{p}/healthz/live" if p == api_port else f"http://127.0.0.1:{p}/")
        yield {"gw": f"http://127.0.0.1:{gw_port}", "bad": f"http://127.0.0.1:{gw_bad_port}",
               "dead": f"http://127.0.0.1:{dead_gw_port}", "api_proc": procs[0]}
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


def test_static_routes_and_404(stack):
    gw = stack["gw"]
    assert httpx.get(f"{gw}/dashboard/").text == "<html>dashboard</html>"
    r = httpx.get(f"{gw}/no-such-page/")
    assert r.status_code == 404 and "not found" in r.text
    assert httpx.get(f"{gw}/_worker.js").status_code == 404


def test_api_passthrough_preserves_status_and_json(stack):
    gw = stack["gw"]
    r = httpx.get(f"{gw}/api/v1/findings")
    assert r.status_code == 401 and r.json()["code"] == "UNAUTHENTICATED"
    r = httpx.get(f"{gw}/api/v1/not-a-route")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")
    r = httpx.post(f"{gw}/api/v1/auth/login", json={})
    assert r.status_code == 422
    r = httpx.get(f"{gw}/healthz/ready")
    assert r.status_code == 200 and r.json()["status"] == "ready"
    assert r.headers["cache-control"] == "no-store"


def test_client_cannot_choose_upstream(stack):
    r = httpx.get(f"{stack['gw']}/api/v1/ok", headers={"x-backend-url": "http://127.0.0.1:1"})
    # Still the real API (404 JSON from FastAPI), never redirected by a client header.
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"


def test_upstream_unreachable_is_502_with_request_id(stack):
    r = httpx.get(f"{stack['dead']}/api/v1/assets", headers={"x-request-id": "pilot-req-0001"})
    assert r.status_code == 502
    body = r.json()
    assert body["code"] == "UPSTREAM_UNREACHABLE" and body["request_id"] == "pilot-req-0001"


def test_upstream_timeout_is_503(stack):
    r = httpx.get(f"{stack['bad']}/api/v1/slow", timeout=10)
    assert r.status_code == 503 and r.json()["code"] == "UPSTREAM_TIMEOUT" and r.json()["request_id"]


def test_upstream_html_on_api_path_is_misrouted(stack):
    r = httpx.get(f"{stack['bad']}/api/v1/html")
    assert r.status_code == 502 and r.json()["code"] == "MISROUTED"


@pytest.mark.parametrize("code", [502, 503, 504, 403, 422])
def test_upstream_error_codes_pass_through(stack, code):
    r = httpx.get(f"{stack['bad']}/api/v1/status/{code}")
    assert r.status_code == code and r.json()["detail"] == f"upstream {code}"


def test_origin_killed_mid_session_then_502(stack):
    gw = stack["gw"]
    assert httpx.get(f"{gw}/healthz/live").status_code == 200
    stack["api_proc"].terminate()
    stack["api_proc"].wait(timeout=10)
    r = httpx.get(f"{gw}/api/v1/assets")
    assert r.status_code == 502 and r.json()["code"] == "UPSTREAM_UNREACHABLE"
    # Static console keeps serving so the UI can render an explicit offline state.
    assert httpx.get(f"{gw}/dashboard/").status_code == 200


def test_repeated_set_cookie_headers_survive_proxy(stack):
    r = httpx.get(f"{stack['bad']}/api/v1/cookies")
    assert r.status_code == 200
    assert {c.split("=")[0] for c in r.headers.get_list("set-cookie")} == {"a_session", "b_csrf"}


def test_gateway_never_shares_one_users_session_with_another(stack):
    """P0 regression (found in Round B): the shared upstream client kept Set-Cookie in a jar and
    replayed the first user's session cookie on every later request through the gateway."""
    # Any login response carrying Set-Cookie (here: the fake upstream) must not be remembered.
    httpx.get(f"{stack['bad']}/api/v1/cookies")
    assert httpx.get(f"{stack['bad']}/api/v1/echo-cookies").json().get("cookie") in (None, "")
