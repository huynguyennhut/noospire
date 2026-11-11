import urllib.request
import json
import sys

BASE_URL = "https://noosforge-soc.pages.dev"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

headers = {
    "User-Agent": UA,
    "Content-Type": "application/json"
}

def run_test():
    print(f"=== TESTING LIVE DEPLOYMENT AT {BASE_URL} ===")
    
    # 1. Health
    req = urllib.request.Request(f"{BASE_URL}/api/v1/health", headers=headers)
    with urllib.request.urlopen(req) as r:
        data = json.loads(r.read().decode())
        print(f"[OK] Health: {data['status']} | POP: {data.get('edge_pop')} | Env: {data.get('environment')}")

    # 2. Login
    login_body = json.dumps({"username": "operator", "password": "password"}).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/v1/auth/login", data=login_body, headers=headers, method="POST")
    with urllib.request.urlopen(req) as r:
        login_res = json.loads(r.read().decode())
        token = login_res["access_token"]
        print(f"[OK] Auth Login: Token acquired for user='{login_res['user']['username']}' role='{login_res['user']['role']}'")

    auth_headers = dict(headers)
    auth_headers["Authorization"] = f"Bearer {token}"

    # 3. Overview Metrics
    req = urllib.request.Request(f"{BASE_URL}/api/v1/metrics/overview", headers=auth_headers)
    with urllib.request.urlopen(req) as r:
        metrics = json.loads(r.read().decode())
        print(f"[OK] Metrics Overview: total_assets={metrics['total_assets']} risk_posture={metrics['risk_posture']}")

    # 4. Ultra Scan 379 Fixture Accounting
    req = urllib.request.Request(f"{BASE_URL}/api/v1/scans/ultra/fixture-379", headers=auth_headers)
    with urllib.request.urlopen(req) as r:
        f379 = json.loads(r.read().decode())
        print(f"[OK] Ultra 379 Inventory: accounted={f379['accounted_inventory_rows']} targets={f379['independent_execution_targets']} executions={f379['engine_executions_count']}")

    # 5. Dispatch Ultra Scan
    ultra_body = json.dumps({
        "target_type": "all",
        "engines": ["zap", "nuclei", "empire_scanner"],
        "notes": "Live Production Verification from Antigravity"
    }).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/v1/scans/ultra", data=ultra_body, headers=auth_headers, method="POST")
    with urllib.request.urlopen(req) as r:
        ultra_res = json.loads(r.read().decode())
        print(f"[OK] Ultra Scan Dispatched: batch_id={ultra_res['batch_id']} targets={ultra_res['independent_execution_targets']} executions={ultra_res['engine_executions_count']} status={ultra_res['status']}")
        print(f"     Tracker Link: {ultra_res['tracker_link']}")

    # 6. Retest Finding
    retest_body = json.dumps({
        "notes": "Live Verified Patch on Student Records Access Control"
    }).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/v1/findings/find-vuln-001/retest", data=retest_body, headers=auth_headers, method="POST")
    with urllib.request.urlopen(req) as r:
        retest_res = json.loads(r.read().decode())
        print(f"[OK] Retest Finding: ID={retest_res.get('finding_id', 'find-vuln-001')} Status={retest_res.get('retest_status')}")

    # 7. Check UI Pages
    pages = ["/", "/dashboard/", "/scans/", "/active-assessments/", "/assets/", "/empire-modules/", "/reports/", "/login/"]
    for p in pages:
        req = urllib.request.Request(f"{BASE_URL}{p}", headers=headers)
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            assert r.status == 200
            print(f"[OK] UI Page {p:<20} -> HTTP 200 (len={len(body)})")

    print("\n>>> ALL CLOUDFLARE PAGES VERIFICATION TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    run_test()
