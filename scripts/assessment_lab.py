#!/usr/bin/env python3
"""Isolated UI acceptance lab: real API/worker/scheduler, no seeded findings or targets.

Uses the existing local supervisor with a separate SQLite DB and generated owner.
Credentials stay in a private local file. No customer DB, secret or target is copied.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def environment(directory: Path, *, create: bool) -> dict:
    # Reuse the inspected environment sanitizer without importing application settings.
    spec = importlib.util.spec_from_file_location("safe_checks", ROOT / ".agents/skills/noosforge-qa/scripts/run_checks.py")
    checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checks)
    marker = directory / "lab.json"
    if create and not marker.exists():
        if directory.exists() and any(directory.iterdir()):
            raise ValueError("Refusing a non-empty directory without an assessment-lab marker")
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
        directory.chmod(0o700)
        config = {"kind": "noosforge-isolated-ui-lab/1", "secret": secrets.token_urlsafe(48),
                  "password": secrets.token_urlsafe(24), "owner": "owner@pilot-test.invalid"}
        fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(config, handle)
    config = json.loads(marker.read_text())
    if config.get("kind") != "noosforge-isolated-ui-lab/1":
        raise ValueError("Not an isolated assessment lab")
    env = checks.isolated_env(directory)
    env.update(SENTINEL_SECRET_KEY=config["secret"],
               NOOSPIRE_LOCAL_STATE_DIR=str(directory / "processes"))
    # Pydantic also accepts unprefixed .env names. Override both forms so the
    # supervisor's repository cwd can never redirect the lab into customer data.
    for key in ("DATABASE_URL", "STORAGE_DIR", "SECRET_KEY", "SOLE_OWNER_EMAIL", "SOLE_OWNER_ACCOUNT_ID",
                "SEED_DEMO_DATA", "DEMO_MODE", "THROTTLE_CPU_PCT", "THROTTLE_MEM_PCT"):
        env[key] = env[f"SENTINEL_{key}"]
    env["BOOTSTRAP_TOKEN"] = ""
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "status", "stop"])
    parser.add_argument("--directory", type=Path, default=ROOT / "storage/assessment-lab")
    parser.add_argument("--port", type=int, default=8082)
    parser.add_argument("--api-port", type=int, default=8002)
    args = parser.parse_args()
    directory = args.directory.resolve()
    # Fixed lab basename is not required, but repository/customer data locations are forbidden.
    if directory == ROOT or directory == ROOT / "storage":
        parser.error("Choose a dedicated empty lab directory")
    try:
        env = environment(directory, create=args.action == "start")
        if args.action == "start" and not (directory / "checks.db").exists():
            config = json.loads((directory / "lab.json").read_text())
            boot = subprocess.run([sys.executable, "-m", "backend.app.cli", "bootstrap-owner",
                                   "--username", "lab-owner", "--password-stdin"],
                                  cwd=directory, env=env, input=config["password"] + "\n", text=True,
                                  capture_output=True)
            if boot.returncode:
                raise RuntimeError("Lab owner bootstrap failed; no customer database was used")
        command = [sys.executable, str(ROOT / "scripts/local_stack.py"), args.action]
        if args.action == "start":
            command += ["--enable-jobs", "--port", str(args.port), "--api-port", str(args.api_port)]
        code = subprocess.run(command, cwd=ROOT, env=env).returncode
        if args.action == "start" and code == 0:
            print(f"SYNTHETIC LOCAL LAB — no customer findings. Credentials (private): {directory / 'lab.json'}")
            print(f"Upload fixtures through UI from {ROOT / 'tests_pilot/data'}")
        return code
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Lab error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
