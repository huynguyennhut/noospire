"""Milestone 6 · run deploy/smoke.py against real processes: API + gateway on loopback with a
file DB, signed in as a bootstrapped owner, including SSE through the gateway. A second gateway
with Cloudflare Access REQUIRED but unconfigured must fail closed.

The console export is a minimal stand-in (no Node on this host); everything else is the real app.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid

from tests_pilot.test_m3_restart import PY, ROOT, Stack, _port, _wait


def test_smoke_script_passes_through_gateway_and_access_fails_closed():
    st = Stack()
    (st.tmp / "out" / "health").mkdir(parents=True, exist_ok=True)
    (st.tmp / "out" / "health" / "index.html").write_text("<html>health page</html>")
    (st.tmp / "out" / "404.html").write_text("<html>not found</html>")
    (st.tmp / "out" / "_worker.js").write_text("// must not be served")
    password = "pilot-owner-" + uuid.uuid4().hex
    try:
        boot = subprocess.run([PY, "-m", "backend.app.cli", "bootstrap-owner", "--username", "pilot-owner",
                               "--password-stdin"], cwd=str(ROOT), env=st.env, input=password + "\n",
                              capture_output=True, text=True, timeout=60)
        assert boot.returncode == 0, boot.stderr
        st.start("api", "gateway")
        env = {**os.environ, "NOOSPIRE_SMOKE_USER": "owner@pilot-test.invalid", "NOOSPIRE_SMOKE_PASSWORD": password}
        r = subprocess.run([PY, "deploy/smoke.py", st.base], cwd=str(ROOT), env=env, capture_output=True,
                           text=True, timeout=120)
        print(r.stdout)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "PASS  SSE through gateway" in r.stdout and password not in r.stdout

        port = _port()
        log = open(st.tmp / "gw-access.log", "ab")
        st.procs["gw-access"] = subprocess.Popen(
            [PY, "-m", "uvicorn", "deploy.gateway.gateway:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
            env={**st.env, "NOOSPIRE_API_ORIGIN": f"http://127.0.0.1:{st.api_port}",
                 "NOOSPIRE_STATIC_DIR": str(st.tmp / "out"), "NOOSPIRE_ACCESS_REQUIRED": "true"})
        _wait(f"http://127.0.0.1:{port}/gateway/live")
        r = subprocess.run([PY, "deploy/smoke.py", f"http://127.0.0.1:{port}"], cwd=str(ROOT),
                           env={k: v for k, v in os.environ.items() if not k.startswith("NOOSPIRE_SMOKE")},
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 1 and "FAIL  console index" in r.stdout  # 503 ACCESS_NOT_CONFIGURED
        assert "PASS  gateway live" in r.stdout  # liveness stays available for the connector
    finally:
        st.stop()


def test_report_html_passes_gateway_but_other_html_is_misrouted():
    """Round B finding: report HTML downloads were turned into 502 MISROUTED by the gateway."""
    import httpx as _httpx
    import deploy.gateway.gateway as g

    assert g._REPORT_HTML.match("/api/v1/report-snapshots/c5c5da59-ba7e-4389-9b13-df1ead85a1ff/download")
    assert not g._REPORT_HTML.match("/api/v1/findings")
    assert not g._REPORT_HTML.match("/api/v1/report-snapshots/x/../../download")
