#!/usr/bin/env python3
"""Loopback local process supervisor. No customer inventory or database is seeded."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import uuid

import psutil
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = Path(__file__).resolve()
STATE_DIR = Path(os.environ.get("NOOSPIRE_LOCAL_STATE_DIR", ROOT / "storage/local-stack")).resolve()
STATE_FILE = STATE_DIR / "state.json"
STATIC_DIR = Path(os.environ.get("NOOSPIRE_STATIC_DIR", ROOT / "frontend/out")).resolve()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def prepare_dir():
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE_DIR.chmod(0o700)


@contextmanager
def lock():
    prepare_dir()
    with (STATE_DIR / "control.lock").open("a") as handle:
        os.chmod(handle.name, 0o600)
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def read_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def write_state(state):
    tmp = STATE_DIR / f"state-{os.getpid()}.tmp"
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(STATE_FILE)


def identity(pid):
    p = psutil.Process(pid)
    return {"pid": pid, "created": p.create_time()}


def matching_process(info):
    try:
        p = psutil.Process(info["pid"])
        if abs(p.create_time() - info["created"]) < 0.01 and p.status() != psutil.STATUS_ZOMBIE:
            return p
    except (KeyError, psutil.Error):
        pass
    return None


def supervisor(state):
    p = matching_process(state.get("supervisor", {}))
    if p:
        try:
            args = p.cmdline()
            if str(SCRIPT) in args and "__supervise" in args and state.get("token") in args:
                return p
        except psutil.Error:
            pass
    return None


def healthy(port, path):
    try:
        # Loopback operational checks must never follow a redirect off this process.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(
            f"http://127.0.0.1:{port}{path}", timeout=1
        ) as response:
            return response.status == 200
    except Exception:
        return False


def wait_ready(process, port, path, timeout=30):
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError("service exited during startup; inspect its local log")
        if healthy(port, path):
            return
        time.sleep(0.2)
    raise RuntimeError("service readiness timed out; inspect its local log")


def local_env():
    env = os.environ.copy()
    # Set prefixed and unprefixed keys: Pydantic also reads legacy .env names.
    forced = {"ENVIRONMENT": "development", "DEFENSIVE_ONLY": "true",
              "SEED_DEMO_DATA": "false", "SSRF_ALLOW_PRIVATE_TARGETS": "false",
              "DISPATCHER_MODE": "async_worker", "DEBUG": "false",
              "SESSION_COOKIE_SECURE": "false"}
    for key, value in forced.items():
        env[key] = value
        env[f"SENTINEL_{key}"] = value
    env.update(SENTINEL_ENV="development", SENTINEL_SSRF_ALLOW_PRIVATE="false",
               NOOSPIRE_ACCESS_REQUIRED="false", PYTHONUNBUFFERED="1",
               NOOSPIRE_STATIC_DIR=str(STATIC_DIR))
    configured = dotenv_values(ROOT / ".env")
    key = (env.get("SECRET_KEY") or env.get("SENTINEL_SECRET_KEY")
           or configured.get("SECRET_KEY") or configured.get("SENTINEL_SECRET_KEY"))
    if not key or len(key) < 32 or key in {"noospire-super-secret-key-change-in-production-2026",
                                         "dev_insecure_default_secret_key_change_in_production"}:
        key_path = STATE_DIR / "session.key"
        if not key_path.exists():
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(secrets.token_urlsafe(48))
        key_path.chmod(0o600)
        key = key_path.read_text().strip()
        if len(key) < 32:
            raise RuntimeError("invalid local session key; retain it and repair configuration")
    env["SENTINEL_SECRET_KEY"] = env["SECRET_KEY"] = key
    return env


def start(args):
    with lock():
        state = read_state()
        if supervisor(state):
            print(json.dumps(status_data(state), indent=2))
            return 0 if state.get("phase") == "ready" and state.get("jobs_enabled") == args.enable_jobs else 1
        if any(matching_process(info) for info in state.get("services", {}).values()):
            raise RuntimeError("recorded child services are still running; use stop before start")
        if args.api_port == args.port:
            raise RuntimeError("API and gateway ports must be different")
        for port in (args.api_port, args.port):
            with socket.socket() as sock:
                # Match uvicorn's listener behavior: a recently stopped connection's
                # TIME_WAIT must not prevent restart; an active listener still fails.
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(("127.0.0.1", port))
                except OSError as exc:
                    raise RuntimeError(f"loopback port {port} is already in use; existing services were left untouched") from exc
        if args.build_console:
            subprocess.run(["npm", "run", "build"], cwd=ROOT / "frontend", check=True)
        if not (STATIC_DIR / "index.html").is_file():
            raise RuntimeError("console export is missing; run ./run.sh start --build-console")
        token = uuid.uuid4().hex
        cmd = [sys.executable, str(SCRIPT), "__supervise", "--token", token,
               "--api-port", str(args.api_port), "--port", str(args.port)]
        if args.enable_jobs:
            cmd.append("--enable-jobs")
        log_path = STATE_DIR / "supervisor.log"
        with log_path.open("a") as log:
            log_path.chmod(0o600)
            child = subprocess.Popen(cmd, cwd=ROOT, env=local_env(), stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        until = time.monotonic() + 65
        while time.monotonic() < until:
            state = read_state()
            if state.get("token") == token and state.get("phase") in {"ready", "failed", "stopped"}:
                print(json.dumps(status_data(state), indent=2))
                return 0 if state["phase"] == "ready" else 1
            if child.poll() is not None:
                raise RuntimeError("supervisor exited; inspect storage/local-stack/supervisor.log")
            time.sleep(0.2)
        child.terminate()
        raise RuntimeError("local startup timed out; stop requested, inspect supervisor.log")


def supervise(args):
    prepare_dir()
    pid_file = STATE_DIR / "supervisor.pid"
    pid_file.write_text(str(os.getpid()) + "\n")
    pid_file.chmod(0o600)
    state = {"token": args.token, "supervisor": identity(os.getpid()), "phase": "starting",
             "started_at": timestamp(), "jobs_enabled": args.enable_jobs,
             "defensive_only": True, "api_port": args.api_port, "gateway_port": args.port,
             "console_url": f"http://localhost:{args.port}/", "services": {}}
    write_state(state)
    stop_requested = False
    def request_stop(*_):
        nonlocal stop_requested
        stop_requested = True
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    env = local_env()
    env["NOOSPIRE_API_ORIGIN"] = f"http://127.0.0.1:{args.api_port}"
    definitions = {
        "api": ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(args.api_port)],
        "gateway": ["-m", "uvicorn", "deploy.gateway.gateway:app", "--host", "127.0.0.1", "--port", str(args.port)],
    }
    if args.enable_jobs:
        definitions.update(worker=["-m", "backend.app.worker"], scheduler=["-m", "backend.app.scheduler_main"])
    children, log_handles, restarts = {}, [], {}
    def spawn(name):
        child_env = {**env, "PROCESS_ROLE": name if name in {"worker", "scheduler"} else "api",
                     "SENTINEL_PROCESS_ROLE": name if name in {"worker", "scheduler"} else "api"}
        path = STATE_DIR / f"{name}.log"
        log = path.open("a")
        path.chmod(0o600)
        log_handles.append(log)
        log.write(f"\n--- {timestamp()} supervisor starting {name} ---\n")
        log.flush()
        child = subprocess.Popen([sys.executable, *definitions[name]], cwd=ROOT, env=child_env,
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        children[name] = child
        state["services"][name] = {**identity(child.pid), "log": str(path), "restarts": len(restarts.get(name, []))}
        write_state(state)
        return child
    try:
        wait_ready(spawn("api"), args.api_port, "/healthz/ready")
        wait_ready(spawn("gateway"), args.port, "/gateway/live")
        for name in ("worker", "scheduler"):
            if name in definitions:
                spawn(name)
        state["phase"] = "ready"
        write_state(state)
        while not stop_requested:
            for name, child in list(children.items()):
                if child.poll() is None:
                    continue
                now = time.monotonic()
                restarts[name] = [t for t in restarts.get(name, []) if now - t < 60]
                if len(restarts[name]) >= 3:
                    raise RuntimeError(f"{name} repeatedly exited; automatic restart stopped")
                restarts[name].append(now)
                print(f"{timestamp()} restarting {name}; exit={child.returncode}", flush=True)
                spawn(name)
            time.sleep(0.5)
    except Exception as exc:
        state["phase"] = "failed"
        state["error"] = str(exc)
        print(f"{timestamp()} local supervisor failed: {exc}", flush=True)
    finally:
        for name in reversed(list(children)):
            child = children[name]
            if child.poll() is None:
                child.terminate()
        until = time.monotonic() + 15
        for child in children.values():
            try:
                child.wait(timeout=max(0.1, until - time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        for handle in log_handles:
            handle.close()
        if state["phase"] != "failed":
            state["phase"] = "stopped"
        state["stopped_at"] = timestamp()
        write_state(state)
        if pid_file.read_text().strip() == str(os.getpid()):
            pid_file.unlink()
    return 1 if state["phase"] == "failed" else 0


def status_data(state):
    running = supervisor(state) is not None
    services = {name: {**info, "running": matching_process(info) is not None}
                for name, info in state.get("services", {}).items()}
    return {"phase": state.get("phase", "not_started") if running else
            ("stopped" if state.get("phase") == "ready" else state.get("phase", "not_started")),
            "supervisor_running": running, "jobs_enabled": state.get("jobs_enabled", False),
            "defensive_only": True, "console_url": state.get("console_url"),
            "api_ready": healthy(state.get("api_port", 8000), "/healthz/ready") if running else False,
            "gateway_ready": healthy(state.get("gateway_port", 8080), "/gateway/live") if running else False,
            "services": services, "log_directory": str(STATE_DIR), "error": state.get("error")}


def stop():
    with lock():
        state = read_state()
        process = supervisor(state)
        if process:
            process.terminate()
            try:
                process.wait(timeout=22)
            except psutil.TimeoutExpired:
                raise RuntimeError("supervisor did not stop in time; inspect service state before retrying")
        else:
            # A dead supervisor may leave children. Signal only the exact recorded
            # PID/create-time identities, never a port owner or a guessed process.
            processes = [p for info in state.get("services", {}).values() if (p := matching_process(info))]
            for p in processes:
                p.terminate()
            _, alive = psutil.wait_procs(processes, timeout=15)
            if alive:
                raise RuntimeError("recorded child services have not stopped; inspect their logs")
            if state:
                state.update(phase="stopped", stopped_at=timestamp())
                write_state(state)
        print(json.dumps(status_data(read_state()), indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("start", "__supervise"):
        p = sub.add_parser(command)
        p.add_argument("--enable-jobs", action="store_true", help="start defensive worker and monitor scheduler")
        p.add_argument("--api-port", type=int, default=int(os.environ.get("NOOSPIRE_API_PORT", "8000")))
        p.add_argument("--port", type=int, default=int(os.environ.get("NOOSPIRE_GW_PORT", "8080")))
        if command == "start":
            p.add_argument("--build-console", action="store_true")
        else:
            p.add_argument("--token", required=True)
    sub.add_parser("stop")
    sub.add_parser("status")
    p = sub.add_parser("logs")
    p.add_argument("service", choices=["supervisor", "api", "gateway", "worker", "scheduler"], default="supervisor", nargs="?")
    p.add_argument("--lines", type=int, default=80)
    p.add_argument("--follow", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "start":
            return start(args)
        if args.command == "__supervise":
            return supervise(args)
        if args.command == "stop":
            return stop()
        if args.command == "status":
            data = status_data(read_state())
            print(json.dumps(data, indent=2))
            return 0 if data["supervisor_running"] and data["api_ready"] and data["gateway_ready"] else 1
        path = STATE_DIR / f"{args.service}.log"
        if not path.is_file():
            raise RuntimeError(f"no log for {args.service}; it may not have been started")
        return subprocess.call(["tail", "-n", str(max(1, min(args.lines, 10000))), *( ["-F"] if args.follow else []), str(path)])
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Local stack: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
