# DISPATCH — AGENT 1 (Platform Core) — Milestone M1

You are worker_core_m1 (teamwork_worker).
Your working directory is: c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_core_m1
Original request file: c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md
Project specification: c:\Users\nguye\Desktop\noospire\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope & Assigned Files (Exclusive Write Ownership):
- `backend/app/core/empire_seeder.py`
- `backend/app/core/target_verifier.py` (new or updated 8-step live verification engine)
- `backend/app/api/assets.py`
- `backend/app/schemas/asset.py`

Key Deliverables:
1. Primary Target Registration:
   - In `backend/app/core/empire_seeder.py`, register `https://empire.edu.vn/` as the primary root target with same-origin scope (`*.empire.edu.vn`), production-safe baseline assessment policy, and verified status. Ensure idempotent seeding.
2. 8-Step Live Target Verification Engine:
   - Implement `TargetVerifier` in `backend/app/core/target_verifier.py` executing the 8 distinct steps:
     Step 1: Input validation (URL syntax, scheme http/https, SSRF check)
     Step 2: DNS resolution (A/AAAA records, IP extraction)
     Step 3: TLS verification (SSL certificate validity, expiry, SAN)
     Step 4: HTTP connectivity (status code, latency, headers)
     Step 5: Redirect inspection (tracing redirect chain, final URL, protocol downgrade prevention)
     Step 6: Web discovery (robots.txt, sitemap.xml, common endpoint accessibility)
     Step 7: Target fingerprint (Server header, WAF/Proxy detection e.g. Envoy/Cloudflare, framework detection e.g. Next.js)
     Step 8: Verification result (determination, metadata aggregation, status update)
   - Wire this into `POST /api/v1/assets/{id}/verify` and return the structured 8-step diagnostic result and fingerprint.
3. Bulk Import & Preview API:
   - Implement `POST /api/v1/assets/bulk-preview` in `backend/app/api/assets.py` to support previewing bulk inputs (URL, domain, IP, CIDR, OpenAPI, CSV, JSON) with duplicate detection before committing to the database.
4. Testing & Verification:
   - Run `python scripts/verify_empire_e2e.py` to ensure all 10 existing tests pass without regression!
   - Write unit/integration tests for the 8-step verification engine and bulk preview.

Write your report to c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_core_m1\report.md and create a self-contained handoff report at c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_core_m1\handoff.md.
