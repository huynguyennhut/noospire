import urllib.request
import json

BASE = "https://noosforge-soc.pages.dev"
UA = {"User-Agent": "Mozilla/5.0"}

extra_endpoints = [
    "/api/v1/alerts/unread-count",
    "/api/v1/auth/me",
    "/api/v1/auth/audit",
    "/api/v1/auth/users",
    "/api/v1/engines/check-updates",
    "/api/v1/intel/kev",
    "/api/v1/intel/cve/CVE-2024-21413",
    "/api/v1/rules/validate",
    "/api/v1/settings/ssrf-config",
    "/api/v1/assets/summary",
    "/api/v1/assets/bulk-preview",
    "/api/v1/logs",
    "/api/v1/logs/export",
    "/reports/download/99999999-0000-0000-0000-000000000001.pdf",
    "/reports/download/99999999-0000-0000-0000-000000000001.html",
    "/reports/download/99999999-0000-0000-0000-000000000001.json"
]

print("=== TESTING EXTENDED ENDPOINTS ===")
all_ok = True
for ep in extra_endpoints:
    req = urllib.request.Request(f"{BASE}{ep}", headers=UA)
    try:
        with urllib.request.urlopen(req) as resp:
            ct = resp.headers.get("Content-Type", "").split(";")[0]
            print(f"[200 OK] {ep:<60} ({ct})")
    except Exception as e:
        print(f"[FAIL] {ep:<60} -> {e}")
        all_ok = False

print("\nALL EXTENDED ENDPOINTS PASS:", all_ok)
assert all_ok
