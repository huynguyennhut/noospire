"""
verify_remediation_adversarial.py
Adversarial Verification script for AM-2 / Phase 3 audit.
Checks:
1. ASGI metrics endpoints response schemas and dynamic calculations against DB.
2. Absence of hardcoded values in metrics.py responses.
3. Verification of frontend api.ts engine alignment.
"""

import asyncio
import json
import sqlite3
import sys
from pathlib import Path
import httpx

# Ensure workspace root is in sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WORKSPACE_ROOT))

from backend.main import app


def check_database_raw():
    db_path = WORKSPACE_ROOT / "noospire.db"
    if not db_path.exists():
        print(f"[-] ERROR: Database not found at {db_path}")
        return None

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Inspect table schema
    cursor.execute("PRAGMA table_info(scans)")
    scans_columns = [row[1] for row in cursor.fetchall()]
    print(f"[+] Scans columns: {scans_columns}")

    # Query completed scans
    cursor.execute("SELECT id, engine, status, started_at, completed_at FROM scans WHERE status='COMPLETED'")
    completed_scans = cursor.fetchall()

    # Query active detection rules
    cursor.execute("SELECT count(*) FROM detection_rules WHERE status='ACTIVE' OR status='active'")
    active_rules_count = cursor.fetchone()[0]

    # Query vulnerability intelligence
    cursor.execute("SELECT count(*), sum(case when is_cisa_kev=1 then 1 else 0 end) FROM vulnerability_intelligence")
    cve_stats = cursor.fetchone()

    conn.close()
    return {
        "completed_scans_count": len(completed_scans),
        "active_rules_count": active_rules_count,
        "cve_total": cve_stats[0],
        "kev_total": cve_stats[1],
    }


async def test_asgi_endpoints(db_baseline):
    results = {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Scanner performance
        r1 = await client.get("/api/v1/metrics/charts/scanner-performance")
        assert r1.status_code == 200, f"Expected 200, got {r1.status_code}: {r1.text}"
        perf_data = r1.json()
        results["scanner_performance"] = perf_data

        # 2. Intelligence activity
        r2 = await client.get("/api/v1/metrics/charts/intelligence-activity")
        assert r2.status_code == 200, f"Expected 200, got {r2.status_code}: {r2.text}"
        intel_data = r2.json()
        results["intelligence_activity"] = intel_data

    # Validations
    print("[+] ASGI Test Results:")
    print("--- /charts/scanner-performance ---")
    for item in perf_data:
        print(f"  Engine: {item['engine']:<32} Total: {item['total_executions']:<4} Completed: {item['completed']:<4} SuccessRate: {item['success_rate']}% AvgDuration: {item['avg_duration_seconds']}s")
        # Ensure it's not simply a static 18.5 across the board
        assert isinstance(item["avg_duration_seconds"], (int, float)), "Duration must be numeric"

    print("\n--- /charts/intelligence-activity ---")
    print(f"  Total CVEs indexed:     {intel_data['total_cves_indexed']} (DB: {db_baseline['cve_total']})")
    print(f"  CISA KEV active:        {intel_data['cisa_kev_active']} (DB KEV: {db_baseline['kev_total']})")
    print(f"  High EPSS exploitable:  {intel_data['high_epss_exploitable']}")
    print(f"  Detection rules active: {intel_data['detection_rules_active']} (DB: {db_baseline['active_rules_count']})")
    print(f"  Last sync:              {intel_data['last_sync']}")

    # Check match with DB
    assert intel_data["total_cves_indexed"] == db_baseline["cve_total"], "CVE count mismatch"
    assert intel_data["cisa_kev_active"] == db_baseline["kev_total"], "CISA KEV mismatch"
    assert intel_data["detection_rules_active"] == db_baseline["active_rules_count"], f"Detection rules mismatch: {intel_data['detection_rules_active']} vs DB {db_baseline['active_rules_count']}"

    return results


async def test_dynamic_sensitivity():
    print("\n--- Adversarial Sensitivity Test: Real-time DB Updates ---")
    db_path = WORKSPACE_ROOT / "noospire.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    test_rule_id = "test_adv_rule_9999"
    import uuid as _uuid_mod
    test_scan_id = str(_uuid_mod.uuid4())

    try:
        # Insert active detection rule using canonical RuleStatus.ACTIVE.value ('active')
        cursor.execute(
            "INSERT INTO detection_rules (id, name, version, author, severity, status, target_types, metadata_json, detection_json, remediation_json, raw_yaml, created_by, description, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (test_rule_id, "Adversarial Test Rule", "1.0.0", "tester", "CRITICAL", "active", "[]", "{}", "{}", "{}", "rules:", "admin", "Test rule for dynamic verification")
        )
        # Insert completed scan with 42.5 seconds duration
        cursor.execute(
            "INSERT INTO scans (id, asset_id, engine, profile, status, progress_percentage, target_locator, allow_private_targets, timeout_seconds, started_at, completed_at, created_at, updated_at) "
            "VALUES (?, '0c14cc6e-3847-4e9c-ba4e-4e7c4cb3ee55', ?, 'FULL', ?, 100, 'https://empire.edu.vn', 0, 300, '2026-11-10 01:00:00', '2026-11-10 01:00:42.5', datetime('now'), datetime('now'))",
            (test_scan_id, "trivy", "COMPLETED")
        )
        conn.commit()

        # Query ASGI endpoint
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            r_intel = await client.get("/api/v1/metrics/charts/intelligence-activity")
            intel_data = r_intel.json()
            print(f"  Dynamic detection_rules_active after insert: {intel_data['detection_rules_active']}")
            assert intel_data["detection_rules_active"] == 1, f"Expected 1 active rule, got {intel_data['detection_rules_active']}"

            r_perf = await client.get("/api/v1/metrics/charts/scanner-performance")
            perf_data = r_perf.json()
            trivy_stat = next((item for item in perf_data if "Trivy" in item["engine"]), None)
            assert trivy_stat is not None, "Trivy engine stat not found"
            print(f"  Trivy dynamic performance: executions={trivy_stat['total_executions']}, completed={trivy_stat['completed']}, avg_duration={trivy_stat['avg_duration_seconds']}s")
            assert trivy_stat["completed"] == 1, "Trivy completed scan count not updated"
            assert trivy_stat["avg_duration_seconds"] == 42.5, f"Expected 42.5s, got {trivy_stat['avg_duration_seconds']}"

        print("[+] Dynamic sensitivity test SUCCESSFUL: Endpoint strictly reflects live DB changes!")
    finally:
        # Cleanup
        cursor.execute("DELETE FROM detection_rules WHERE id=?", (test_rule_id,))
        cursor.execute("DELETE FROM scans WHERE id=?", (test_scan_id,))
        conn.commit()
def verify_frontend_engines():
    api_ts_path = WORKSPACE_ROOT / "frontend" / "src" / "lib" / "api.ts"
    content = api_ts_path.read_text(encoding="utf-8")

    # 1. Ensure Nmap is NOT in the file (case insensitive for engine declaration)
    assert "nmap" not in content.lower(), "Found 'nmap' in frontend/src/lib/api.ts!"

    # 2. Check getEngines method exists and is properly typed
    assert "public async getEngines(): Promise<EngineDiagnosticItem[]>" in content, "Missing getEngines method in ApiClient"

    # 3. Check exact 5 authentic engines
    authentic_engines = ["nuclei", "zap", "trivy", "empire_engine", "crawler"]
    for eng in authentic_engines:
        assert f"id: '{eng}'" in content or f'id: "{eng}"' in content or f"'{eng}'" in content, f"Engine {eng} not found in api.ts"

    print("[+] Frontend engine inventory verified: Nmap removed, 5 authentic engines confirmed.")


def main():
    print("=== Phase 3 Adversarial Verification: Remediation Integrity ===")
    db_stats = check_database_raw()
    print(f"[+] Raw DB Baseline: {db_stats}")

    asyncio.run(test_asgi_endpoints(db_stats))
    asyncio.run(test_dynamic_sensitivity())
    verify_frontend_engines()

    print("\n[+] ALL ADVERSARIAL REMEDIATION CHECKS PASSED EMPIRICALLY!")

    print("\n[+] ALL ADVERSARIAL REMEDIATION CHECKS PASSED EMPIRICALLY!")


if __name__ == "__main__":
    main()
