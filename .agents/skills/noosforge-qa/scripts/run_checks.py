#!/usr/bin/env python3
"""Run inspected check presets with temporary data and truthful exit/result artifacts.

Not a network sandbox. No legacy tests, arbitrary commands, installation or deployment.
"""

import argparse
import ast
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[4]
PRESETS = {
    "backend": ["test_m1_identity_scope.py", "test_platform_access_security.py", "test_inventory_reconciliation.py", "test_root_observation.py", "test_verified_recheck_lifecycle.py", "test_m3_sbom_flow.py", "test_m5_console.py"],
    "security": ["test_m1_identity_scope.py", "test_platform_access_security.py", "test_inventory_reconciliation.py", "test_root_observation.py", "test_engine_diagnostics.py", "test_m3_engine_units.py", "test_m3_tls_health.py", "test_m6_contract.py"],
    "devops": ["test_m1_gateway.py", "test_m3_restart.py", "test_m6_smoke.py", "test_local_operations.py"],
    "pilot": [],
    "frontend": None,
    "contract": None,
}


def isolated_env(work):
    # BaseSettings accepts unprefixed field names as well as the SENTINEL defaults
    # read by config.py. Strip both forms without importing application settings.
    config = ast.parse((ROOT / "backend/app/core/config.py").read_text(encoding="utf-8"))
    fields = {node.target.id.upper() for cls in config.body
              if isinstance(cls, ast.ClassDef) and cls.name == "Settings"
              for node in cls.body if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)}
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith(("SENTINEL_", "NOOSPIRE_", "PYTEST_", "NEXT_PUBLIC_"))
           and k.upper() not in fields}
    env.update({
        "SENTINEL_DATABASE_URL": f"sqlite+aiosqlite:///{(work / 'checks.db').as_posix()}",
        "SENTINEL_STORAGE_DIR": str(work / "storage"),
        "SENTINEL_ENV": "test", "ENVIRONMENT": "test", "SENTINEL_DEBUG": "false",
        "SENTINEL_PROCESS_ROLE": "api", "SENTINEL_SEED_DEMO_DATA": "false",
        "SENTINEL_DEMO_MODE": "false", "SENTINEL_SSRF_ALLOW_PRIVATE": "false",
        "SENTINEL_SECRET_KEY": secrets.token_urlsafe(48),
        "SENTINEL_SOLE_OWNER_EMAIL": "owner@pilot-test.invalid",
        "SENTINEL_SOLE_OWNER_ACCOUNT_ID": "0f0f0f0f-0000-4000-8000-000000000001",
        "SENTINEL_THROTTLE_CPU_PCT": "100", "SENTINEL_THROTTLE_MEM_PCT": "100",
        "NOOSPIRE_ACCESS_REQUIRED": "false",  # test gateways bind loopback only
        "NEXT_TELEMETRY_DISABLED": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": str(ROOT),
    })
    return env


def commands(preset, work):
    py = sys.executable
    if preset == "frontend":
        return [(ROOT / "frontend", ["npm", "run", task]) for task in ("test:lifecycle", "typecheck", "lint", "build")]
    if preset == "contract":
        return [(ROOT, [py, "scripts/contract_audit.py"])]
    tests = [f"tests_pilot/{name}" for name in PRESETS[preset]] or ["tests_pilot"]
    cmd = [py, "-m", "pytest", "-p", "pytest_asyncio.plugin", "-q", *tests,
           "--deselect=tests_pilot/test_m7_round_a.py::test_legacy_database_upgrades_in_place_and_backup_restores",
           f"--junitxml={work / 'pytest.xml'}"]
    result = [(ROOT, cmd)]
    if preset == "devops":
        # Fresh schema only: no bootstrap, seed or copy of the repository DB.
        result.extend((ROOT, [py, "-m", "backend.app.cli", *args]) for args in (
            ["init-db"], ["backup", "--out", str(work / "backup.db")],
            ["restore-check", "--backup", str(work / "backup.db")],
        ))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preset", choices=PRESETS)
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix=f"noosforge-{args.preset}-"))
    env = isolated_env(work)
    results = []
    print(f"Artifacts: {work}", flush=True)
    for index, (cwd, cmd) in enumerate(commands(args.preset, work), 1):
        print(f"RUN {json.dumps(cmd)} (cwd={cwd})", flush=True)
        start = time.monotonic()
        log = work / f"{index:02d}.log"
        with log.open("w", encoding="utf-8") as output:
            try:
                code = subprocess.run(cmd, cwd=cwd, env=env, stdout=output,
                                      stderr=subprocess.STDOUT, check=False).returncode
                status = "PASS" if code == 0 else "FAIL"
            except FileNotFoundError as exc:
                output.write(str(exc) + "\n")
                code, status = 127, "BLOCKED"
        print(log.read_text(encoding="utf-8"), end="", flush=True)
        results.append({"command": cmd, "cwd": str(cwd), "exit_code": code,
                        "status": status, "seconds": round(time.monotonic() - start, 2), "log": str(log)})
        # Continue independent checks so one failure does not conceal other evidence.
        print(f"{status}: exit={code}", flush=True)
    (work / "results.json").write_text(json.dumps({"preset": args.preset, "checks": results}, indent=2) + "\n")
    print(f"Results: {work / 'results.json'}", flush=True)
    return 1 if any(r["status"] != "PASS" for r in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
