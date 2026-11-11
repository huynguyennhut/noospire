import urllib.request
import json

BASE_URL = "https://noosforge-soc.pages.dev"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json"
}

endpoints_to_test = [
    # Auth
    ("POST", "/api/v1/auth/login", {"username": "admin", "password": "any"}),
    ("GET", "/api/v1/auth/me", None),
    # Scans
    ("POST", "/api/v1/scans", {"asset_id": "00000000-0000-0001-0000-000100000000", "engine": "zap", "profile": "QUICK"}),
    ("POST", "/api/v1/scans/ultra", {"scope": "ALL"}),
    ("POST", "/api/v1/scans/batch", {"targets": "ALL"}),
    ("POST", "/api/v1/scans/scan-001/cancel", {}),
    ("GET", "/api/v1/scans/scan-001/logs", None),
    ("GET", "/api/v1/scans/scan-001/events?after_id=0&limit=10", None),
    ("DELETE", "/api/v1/scans/scan-001/logs", None),
    # Assets
    ("POST", "/api/v1/assets", {"target_locator": "https://test.empire.edu.vn", "asset_type": "WEB_APP", "empire_module": "PORTAL"}),
    ("POST", "/api/v1/assets/bulk-import", {"targets": ["https://test.empire.edu.vn"]}),
    ("POST", "/api/v1/assets/00000000-0000-0001-0000-000100000000/verify", {"method": "DNS"}),
    ("DELETE", "/api/v1/assets/00000000-0000-0001-0000-000100000000", None),
    # Intel
    ("POST", "/api/v1/intel/sync", {}),
    ("GET", "/api/v1/intel/cve/CVE-2024-1234", None),
    ("GET", "/api/v1/intel/kev", None),
    # Rules
    ("POST", "/api/v1/rules/validate", {"raw_yaml": "id: test\nname: test"}),
    ("POST", "/api/v1/rules", {"id": "RULE-TEST", "name": "Test Rule", "raw_yaml": "id: test"}),
    ("POST", "/api/v1/rules/RULE-TEST/lifecycle", {"to_status": "ACTIVE", "comment": "test"}),
    ("POST", "/api/v1/rules/RULE-TEST/test", {}),
    # Reports
    ("POST", "/api/v1/reports/generate", {"title": "Test Report", "format": "HTML", "scan_batch_id": "test"}),
    ("DELETE", "/api/v1/reports/rep-001", None),
    # Schedules
    ("POST", "/api/v1/schedules/sched-hourly-001/trigger", {}),
    ("PUT", "/api/v1/schedules/sched-hourly-001/toggle", {}),
    ("DELETE", "/api/v1/schedules/sched-hourly-001", None),
    # Alerts
    ("POST", "/api/v1/alerts/alt-001/read", {}),
    ("POST", "/api/v1/alerts/read-all", {}),
    # Engines
    ("POST", "/api/v1/engines/test", {}),
    ("POST", "/api/v1/engines/check-updates", {}),
    # System & Logs
    ("POST", "/api/v1/logs/purge", {"days": 0}),
    ("POST", "/api/v1/system/reset", {})
]

print("=== TESTING ALL MUTATION & ACTION ENDPOINTS ON LIVE CLOUDFLARE PAGES ===")
failed = []
for method, ep, body in endpoints_to_test:
    url = BASE_URL + ep
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res_body = r.read().decode('utf-8', errors='replace')
            status = r.status
            print(f"[{status}] {method:<6} {ep:<45} -> OK ({len(res_body)} bytes)")
    except urllib.error.HTTPError as e:
        body_text = e.read().decode('utf-8', errors='replace')
        print(f"[{e.code}] {method:<6} {ep:<45} -> HTTP ERROR: {body_text[:100]}")
        failed.append((method, ep, e.code))
    except Exception as e:
        print(f"[ERR] {method:<6} {ep:<45} -> {e}")
        failed.append((method, ep, str(e)))

print(f"\nTOTAL FAILED: {len(failed)}")
if failed:
    for m, ep, err in failed:
        print(f"   -> {m} {ep}: {err}")
