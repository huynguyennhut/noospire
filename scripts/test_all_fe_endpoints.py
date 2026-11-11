import urllib.request
import json

BASE = "https://noosforge-soc.pages.dev"
UA = {"User-Agent": "Mozilla/5.0"}

endpoints = [
    "/api/v1/metrics/overview",
    "/api/v1/metrics/severity-distribution",
    "/api/v1/metrics/charts/risk-trend?days=14",
    "/api/v1/metrics/charts/vulnerability-trend?days=14",
    "/api/v1/metrics/charts/module-risk",
    "/api/v1/metrics/charts/coverage",
    "/api/v1/metrics/charts/remediation-progress",
    "/api/v1/metrics/charts/scanner-performance",
    "/api/v1/metrics/charts/intelligence-activity",
    "/api/v1/alerts",
    "/api/v1/intel/status",
    "/api/v1/scans/batches?page=1&size=5",
    "/api/v1/scans?size=100",
    "/api/v1/scans/trackcurrent",
    "/api/v1/engines/health",
    "/api/v1/engines",
    "/api/v1/rules",
    "/api/v1/baselines",
    "/api/v1/settings",
    "/api/v1/assets?size=100",
    "/api/v1/empire-modules",
    "/api/v1/schedules",
    "/api/v1/findings",
    "/api/v1/reports"
]

print("=== CHECKING ENDPOINTS AGAINST LIVE CLOUDFLARE PAGES ===")
missing = []
for ep in endpoints:
    url = BASE + ep
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            print(f"[200 OK] {ep}")
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        print(f"[{e.code} FAIL] {ep} -> {body}")
        missing.append(ep)
    except Exception as e:
        print(f"[ERR] {ep} -> {e}")
        missing.append(ep)

print(f"\nTotal Missing / Failing: {len(missing)} / {len(endpoints)}")
