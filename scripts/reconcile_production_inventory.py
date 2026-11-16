"""Reconcile an existing SQLite inventory without app startup, writes or network.

Use --database explicitly. Only the separately owner-designated primary target is
in the current production scope; legacy flags/documents never expand that scope.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.app.core.inventory_reconciliation import json_object, reconcile  # noqa: E402


def read_inventory(database: Path) -> dict:
    path = database.resolve(strict=True)
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assets = [dict(r) for r in con.execute(
            "SELECT id,target_locator,environment,verification_status,assessment_policy,auth_profile FROM assets")]
        for asset in assets:
            for key in ("assessment_policy", "auth_profile"):
                asset[key] = json_object(asset[key])
        proofs = ([dict(r) for r in con.execute(
            "SELECT asset_id,status,verified_at,expires_at,proof_data FROM asset_ownership_proofs")]
            if "asset_ownership_proofs" in tables else [])
        for proof in proofs:
            proof["proof_data"] = json_object(proof["proof_data"])
        scopes = ([dict(r) for r in con.execute(
            "SELECT asset_id,emergency_stop_active FROM asset_assessment_scopes")]
            if "asset_assessment_scopes" in tables else [])
        report = reconcile(assets, proofs, scopes)
        report["sqlite_connection_changes"] = con.total_changes
    report["database"] = str(path)
    report["external_tools"] = [{"name": name, "binary_on_path": bool(shutil.which(binary)),
                                  "version": None, "version_checked": False, "production_execution_verified": False}
                                 for name, binary in (("Nuclei", "nuclei"), ("ZAP", "zap.sh"), ("Trivy", "trivy"),
                                                      ("Nmap", "nmap"), ("Greenbone CLI", "gvm-cli"),
                                                      ("Semgrep", "semgrep"), ("Prowler", "prowler"),
                                                      ("MobSF", "mobsf"), ("Docker", "docker"))]
    report["evidence_sources"] = [
        {"path": "backend/app/core/ultra_planner.py", "meaning": "379-item synthetic fixture generator, not production inventory"},
        {"path": "backend/app/core/empire_seeder.py", "meaning": "Initial Empire seed; initial_seed proof is not ownership verification"},
        {"path": "EMPIRE_PENTEST_SCOPE.md", "meaning": "Historical seven-target scope document; no independent ownership corroboration"},
        {"path": "backend/app/api/assets.py", "meaning": "CSV/JSON/OpenAPI ingestion capability, not a designated inventory source"},
        {"path": "deploy/README_DEPLOY.md", "meaning": "NOOSFORGE platform health endpoints; not Empire customer health endpoints"},
        {"path": "deploy/.env.example", "meaning": "NOOSFORGE platform configuration; not a supplied customer secret store"}]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Prevent accidentally replacing the source database or its SQLite sidecars.
    source = args.database.resolve()
    dest = args.output.resolve()
    if (dest.suffix != ".json" or dest in {source, Path(str(source) + "-wal"), Path(str(source) + "-shm"), Path(str(source) + "-journal")}
            or (dest.exists() and source.exists() and dest.samefile(source))):
        parser.error("output must not replace the database or SQLite sidecars")
    try:
        report = read_inventory(source)
    except (OSError, sqlite3.Error) as exc:
        print(f"Inventory could not be read ({type(exc).__name__}); no database created or modified.", file=sys.stderr)
        return 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(dest), "counts": report["counts"], "database_modified": False,
                      "network_requests": 0, "customer_health_endpoints": len(report["customer_health_endpoints"]),
                      "credential_reference_locations": len(report["credential_reference_locations"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
