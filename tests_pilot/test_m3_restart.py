"""Milestone 3 · process-level run: real API, real worker process and the gateway on loopback,
persistent SQLite file. Launch through the gateway while no worker runs (job must wait in
the DB queue), start the worker, verify the result, then restart EVERY process and reopen
the same execution / findings / report by ID with identical hashes."""

from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).parent / "data"
PY = sys.executable
OWNER_EMAIL = "owner@pilot-test.invalid"


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(url: str, timeout: float = 25.0) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"not up: {url}")


class Stack:
    def __init__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="noospire-restart-"))
        self.env = {**os.environ,
                    "SENTINEL_DATABASE_URL": f"sqlite+aiosqlite:///{(self.tmp / 'pilot.db').as_posix()}",
                    "SENTINEL_STORAGE_DIR": str(self.tmp / "storage"),
                    "SENTINEL_ENV": "test",
                    "SENTINEL_SECRET_KEY": "pilot-test-" + uuid.uuid4().hex + uuid.uuid4().hex,
                    "SENTINEL_SOLE_OWNER_EMAIL": OWNER_EMAIL,
                    "SENTINEL_SOLE_OWNER_ACCOUNT_ID": "0f0f0f0f-0000-4000-8000-0000000000aa",
                    # The dev box runs near its RAM limit; host-load throttling is tested separately.
                    "SENTINEL_THROTTLE_MEM_PCT": "100", "SENTINEL_THROTTLE_CPU_PCT": "100"}
        self.api_port, self.gw_port = _port(), _port()
        self.procs: dict = {}
        static = self.tmp / "out"
        static.mkdir()
        (static / "index.html").write_text("<html>console</html>")

    def start(self, *names):
        for n in names:
            if n == "api":
                cmd = [PY, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(self.api_port)]
                env = {**self.env, "SENTINEL_PROCESS_ROLE": "api"}
            elif n == "worker":
                cmd, env = [PY, "-m", "backend.app.worker"], {**self.env, "SENTINEL_PROCESS_ROLE": "worker"}
            else:
                cmd = [PY, "-m", "uvicorn", "deploy.gateway.gateway:app", "--host", "127.0.0.1",
                       "--port", str(self.gw_port)]
                env = {**self.env, "NOOSPIRE_API_ORIGIN": f"http://127.0.0.1:{self.api_port}",
                       "NOOSPIRE_STATIC_DIR": str(self.tmp / "out")}
            log = open(self.tmp / f"{n}.log", "ab")
            self.procs[n] = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT)
        if "api" in names:
            _wait(f"http://127.0.0.1:{self.api_port}/healthz/ready")
        if "gateway" in names:
            _wait(f"http://127.0.0.1:{self.gw_port}/gateway/live")

    def stop(self, *names):
        for n in names or list(self.procs):
            p = self.procs.pop(n, None)
            if p:
                p.kill()  # hard kill: no graceful shutdown path
                p.wait(timeout=10)

    @property
    def base(self):
        return f"http://127.0.0.1:{self.gw_port}"


def _client(stack: Stack, password: str) -> httpx.Client:
    c = httpx.Client(base_url=stack.base, timeout=15)
    r = c.post("/api/v1/auth/login", json={"username": OWNER_EMAIL, "password": password})
    assert r.status_code == 200, r.text
    c.headers["X-CSRF-Token"] = c.cookies.get("noospire_csrf")
    return c


def _wait_terminal(c: httpx.Client, eid: str, timeout: float = 40) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        ex = c.get(f"/api/v1/executions/{eid}").json()
        if ex["status"] not in ("queued", "running"):
            return ex
        time.sleep(0.5)
    raise AssertionError(f"execution not terminal: {ex}")


def test_launch_without_worker_then_restart_everything():
    st = Stack()
    password = "pilot-owner-" + uuid.uuid4().hex
    try:
        boot = subprocess.run([PY, "-m", "backend.app.cli", "bootstrap-owner", "--username", "pilot-owner",
                               "--password-stdin"], cwd=str(ROOT), env=st.env, input=password + "\n",
                              capture_output=True, text=True, timeout=60)
        assert boot.returncode == 0, boot.stderr
        again = subprocess.run([PY, "-m", "backend.app.cli", "bootstrap-owner", "--username", "x",
                                "--password-stdin"], cwd=str(ROOT), env=st.env, input=password + "\n",
                               capture_output=True, text=True, timeout=60)
        assert again.returncode == 2 and "locked" in again.stderr

        st.start("api", "gateway")
        c = _client(st, password)
        assert c.get("/api/v1/assets").json()["total"] == 0  # fresh DB stays empty

        asset = c.post("/api/v1/assets", json={"name": "pilot-test-service",
                                               "target_locator": "https://svc.pilot-test.invalid/"})
        assert asset.status_code == 201, asset.text
        aid = asset.json()["id"]
        snap = c.post("/api/v1/threat-intel/advisory-snapshots",
                      params={"source": "pilot-test synthetic OSV", "version_label": "pilot-v1"},
                      content=(DATA / "advisories_pilot_v1.json").read_bytes(),
                      headers={"content-type": "application/json"}).json()
        art = c.post(f"/api/v1/assets/{aid}/artifacts", params={"filename": "bom.json"},
                     content=(DATA / "sbom_vulnerable.cdx.json").read_bytes(),
                     headers={"content-type": "application/json"}).json()
        r = c.post("/api/v1/executions", json={"asset_id": aid, "engine": "sbom", "artifact_id": art["id"]},
                   headers={"Idempotency-Key": "restart-test-1"})
        assert r.status_code == 202, r.text
        launch = r.json()
        eid = launch["execution_id"]
        assert launch["worker"]["ready"] is False

        # No worker yet: the job waits in the DB queue. Restart the API meanwhile.
        st.stop("api")
        st.start("api")
        assert c.get(f"/api/v1/executions/{eid}").json()["status"] == "queued"

        st.start("worker")
        ex = _wait_terminal(c, eid)
        assert ex["status"] == "succeeded" and ex["finding_count"] == 4, ex
        assert ex["rules"]["digest"] == snap["digest"] and ex["attempts"][0]["worker_id"].startswith("worker-")
        workers = c.get("/api/v1/engines/workers").json()
        assert workers["ready"] is True and workers["workers"][0]["state"] == "online"

        rep = c.post("/api/v1/reports/generate", json={"title": "restart pilot", "scan_id": ex["scan_id"],
                                                        "asset_id": aid, "formats": ["json", "pdf"]})
        assert rep.status_code == 201, rep.text
        rid = rep.json()["id"]
        before = {fmt: c.get(f"/api/v1/reports/{rid}/download", params={"format": fmt}).headers["x-content-sha256"]
                  for fmt in ("json", "pdf")}
        out_before = hashlib.sha256(c.get(f"/api/v1/executions/{eid}/output").content).hexdigest()
        assert out_before == ex["output"]["sha256"]

        # Hard-kill and restart every process; same IDs must resolve to the same data.
        st.stop()
        st.start("api", "gateway", "worker")
        c2 = _client(st, password)
        ex2 = c2.get(f"/api/v1/executions/{eid}").json()
        for k in ("status", "finding_count", "output", "rules", "input", "timestamps_utc", "attempts", "finding_ids"):
            assert ex2[k] == ex[k], k
        assert hashlib.sha256(c2.get(f"/api/v1/executions/{eid}/output").content).hexdigest() == out_before
        after = {fmt: c2.get(f"/api/v1/reports/{rid}/download", params={"format": fmt}).headers["x-content-sha256"]
                 for fmt in ("json", "pdf")}
        assert after == before
        f = c2.get(f"/api/v1/findings/{ex['finding_ids'][0]}").json()
        assert f["evidence"]["execution_id"] == eid
        # Replaying the same launch after restart returns the same execution (no duplicate job).
        rr = c2.post("/api/v1/executions", json={"asset_id": aid, "engine": "sbom", "artifact_id": art["id"]},
                     headers={"Idempotency-Key": "restart-test-1"})
        assert rr.status_code == 200 and rr.json()["execution_id"] == eid
        # Sessions survive a restart (same signing key from the secret store) ...
        assert c.get("/api/v1/auth/me").status_code == 200
        # ... and logout is server-side and global for that user: every earlier session dies.
        assert c.post("/api/v1/auth/logout").status_code == 200
        assert c2.get("/api/v1/auth/me").status_code == 401
        assert c2.get(f"/api/v1/executions/{eid}/output").status_code == 401
    finally:
        st.stop()
