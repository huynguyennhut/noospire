import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath("."))

import httpx
from backend.main import app

async def audit_endpoints():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # 1. Metrics Overview
        r1 = await client.get("/api/v1/metrics/overview")
        print("GET /metrics/overview:", r1.status_code, r1.json())
        assert r1.status_code == 200

        # 2. Scanner Performance
        r2 = await client.get("/api/v1/metrics/charts/scanner-performance")
        print("\nGET /metrics/charts/scanner-performance:", r2.status_code)
        for stat in r2.json():
            print(" ", stat)
        assert r2.status_code == 200

        # 3. Intelligence Activity
        r3 = await client.get("/api/v1/metrics/charts/intelligence-activity")
        print("\nGET /metrics/charts/intelligence-activity:", r3.status_code, r3.json())
        assert r3.status_code == 200

        # 4. Engine Health
        r4 = await client.get("/api/v1/engines/health")
        print("\nGET /engines/health:", r4.status_code)
        health = r4.json()
        print(f"  total: {health['total_engines']}, online: {health['online_engines']}")
        for eng in health['engines']:
            print(f"  - {eng['name']}: {eng['status']} ({eng['mode']}) ver: {eng['version']}")
        assert r4.status_code == 200
        assert health['all_healthy'] is True

        # 5. Engine Probes Test
        r5 = await client.post("/api/v1/engines/test")
        print("\nPOST /engines/test:", r5.status_code, r5.json())
        assert r5.status_code == 200
        assert r5.json()['status'] == 'ALL_ENGINES_PASS'

        # 6. Scans Track Current Telemetry
        r6 = await client.get("/api/v1/scans/trackcurrent")
        print("\nGET /scans/trackcurrent:", r6.status_code, r6.json())
        assert r6.status_code == 200

        # 7. Assets List
        r7 = await client.get("/api/v1/assets")
        print("\nGET /assets:", r7.status_code, f"count: {len(r7.json())}")
        assert r7.status_code == 200
        assert len(r7.json()) > 0

        # 8. Findings List
        r8 = await client.get("/api/v1/findings")
        print("\nGET /findings:", r8.status_code, f"count: {len(r8.json())}")
        assert r8.status_code == 200

        print("\nALL 8 LIVE ASGI ENDPOINT INTEGRITY CHECKS PASSED EMPIRICALLY!")

if __name__ == "__main__":
    asyncio.run(audit_endpoints())
