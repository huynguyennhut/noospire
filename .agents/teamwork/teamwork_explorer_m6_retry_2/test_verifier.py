import asyncio
from backend.app.core.target_verifier import get_target_verifier

async def main():
    verifier = get_target_verifier()
    res = await verifier.verify_target("https://empire.edu.vn/")
    print("STATUS:", res["status"])
    print("VERIFIED:", res["verified"])
    for s in res["steps"]:
        print(f"Step {s['step']}: {s['name']} -> {s['status']}")
        print(f"  detail: {s['detail']}")
        print(f"  metadata: {s.get('metadata')}")

if __name__ == "__main__":
    asyncio.run(main())
