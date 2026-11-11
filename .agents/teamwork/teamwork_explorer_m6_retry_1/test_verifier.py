import asyncio
import json
from backend.app.core.target_verifier import TargetVerifier

async def main():
    verifier = TargetVerifier()
    res = await verifier.verify_target('https://empire.edu.vn/', allow_private=True)
    print("STATUS:", res["status"])
    print("VERIFIED:", res["verified"])
    print("MESSAGE:", res["message"])
    print("STEPS COUNT:", len(res["steps"]))
    for s in res["steps"]:
        print(f"Step {s['step']}: {s['name']} -> {s['status']} ({s['detail'][:70]})")
    print("\nFINGERPRINT:")
    print(json.dumps(res["fingerprint"], indent=2))

if __name__ == "__main__":
    asyncio.run(main())
