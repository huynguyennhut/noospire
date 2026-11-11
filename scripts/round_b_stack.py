"""Milestone 7 · Round B environment without Docker: the same processes the compose file runs
(api, worker, scheduler, gateway) from the hand-over artifacts, on loopback, persistent file DB.

  python scripts/round_b_stack.py start  <run_dir>     # starts every process, waits for readiness
  python scripts/round_b_stack.py stop   <run_dir> [name ...]
  python scripts/round_b_stack.py restart <run_dir> name [...]

Ports: gateway 127.0.0.1:8080 (console), API 127.0.0.1:8000 (internal only).
The console export must exist at frontend/out (npm run build). Access is not configured on this
host (no Cloudflare credentials), so the gateway runs with NOOSPIRE_ACCESS_REQUIRED=false.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def _env(run: Path) -> dict:
    return {**os.environ,
            "SENTINEL_DATABASE_URL": f"sqlite+aiosqlite:///{(run / 'noospire.db').as_posix()}",
            "SENTINEL_STORAGE_DIR": str(run / "storage"),
            "SENTINEL_ENV": "test",
            "SENTINEL_SEED_DEMO_DATA": "false",
            "SENTINEL_SECRET_KEY": (run / "secret_key").read_text().strip(),
            "SENTINEL_SOLE_OWNER_EMAIL": "owner@pilot-test.invalid",
            "SENTINEL_SOLE_OWNER_ACCOUNT_ID": "0f0f0f0f-0000-4000-8000-0000000000b1",
            "SENTINEL_THROTTLE_MEM_PCT": "100", "SENTINEL_THROTTLE_CPU_PCT": "100",
            "NOOSPIRE_SCHEDULER_TICK_SECONDS": "5",
            "NOOSPIRE_BUILD_ID": (run / "build_id").read_text().strip()}


CMDS = {
    "api": [PY, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000"],
    "worker": [PY, "-m", "backend.app.worker"],
    "scheduler": [PY, "-m", "backend.app.scheduler_main"],
    "gateway": [PY, "-m", "uvicorn", "deploy.gateway.gateway:app", "--host", "127.0.0.1", "--port", "8080"],
}
ROLE = {"api": "api", "worker": "worker", "scheduler": "scheduler", "gateway": "api"}


def _pids(run: Path) -> dict:
    f = run / "pids.json"
    return json.loads(f.read_text()) if f.exists() else {}


def _save(run: Path, pids: dict) -> None:
    (run / "pids.json").write_text(json.dumps(pids))


def _wait(url: str, timeout: float = 40) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise SystemExit(f"not ready: {url}")


def start(run: Path, names) -> None:
    run.mkdir(parents=True, exist_ok=True)
    if not (run / "secret_key").exists():
        (run / "secret_key").write_text(os.urandom(32).hex())
    if not (run / "build_id").exists():
        (run / "build_id").write_text(run.name)
    env = _env(run)
    pids = _pids(run)
    for n in names:
        e = {**env, "SENTINEL_PROCESS_ROLE": ROLE[n]}
        if n == "gateway":
            e.update({"NOOSPIRE_API_ORIGIN": "http://127.0.0.1:8000",
                      "NOOSPIRE_STATIC_DIR": str(ROOT / "frontend" / "out"), "NOOSPIRE_ACCESS_REQUIRED": "false"})
        log = open(run / f"{n}.log", "ab")
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        p = subprocess.Popen(CMDS[n], cwd=str(ROOT), env=e, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=flags)
        pids[n] = p.pid
        _save(run, pids)
        if n == "api":
            _wait("http://127.0.0.1:8000/healthz/ready")
        if n == "gateway":
            _wait("http://127.0.0.1:8080/gateway/live")
    print(json.dumps(pids))


def stop(run: Path, names) -> None:
    pids = _pids(run)
    for n in names or list(pids):
        pid = pids.pop(n, None)
        if pid:
            if os.name == "nt":
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
            else:
                os.kill(pid, signal.SIGKILL)
    _save(run, pids)


if __name__ == "__main__":
    cmd, run = sys.argv[1], Path(sys.argv[2])
    names = sys.argv[3:] or ["api", "worker", "scheduler", "gateway"]
    if cmd == "start":
        start(run, names)
    elif cmd == "stop":
        stop(run, sys.argv[3:])
    elif cmd == "restart":
        stop(run, names)
        time.sleep(1)
        start(run, names)
