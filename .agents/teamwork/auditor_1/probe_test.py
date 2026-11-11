import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.target_verifier import TargetVerifier

async def main():
    verifier = TargetVerifier(timeout=10.0)
    print("Executing 8-step live probe against https://empire.edu.vn/ ...")
    res = await verifier.verify_target("https://empire.edu.vn/")
    print("\n--- PROBE VERDICT ---")
    print(f"Status: {res['status']}")
    print(f"Verified: {res['verified']}")
    print(f"Message: {res['message']}")
    print("\n--- STEP DETAILS ---")
    for step in res["steps"]:
        print(f"Step {step['step']}: {step['name']} -> {step['status']}")
        print(f"   Detail: {step['detail']}")
        print(f"   Metadata: {step.get('metadata')}")
    print("\n--- FINGERPRINT ---")
    print(res["fingerprint"])

if __name__ == "__main__":
    asyncio.run(main())
