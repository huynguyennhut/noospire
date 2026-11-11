# Dispatch: E2E Test Writer

## Objective
Design and implement the 4-tier opaque-box E2E test suite for Noospire (Empire security assessment platform) according to:
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md` (read verbatim)
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\PROJECT.md` (Feature Inventory, Architecture, Contracts)

## Working Directory
`c:\Users\nguye\Desktop\noospire\.agents\teamwork\test_writer_e2e\`

## Write Boundaries
You exclusively own:
- `TEST_INFRA.md` at project root
- `TEST_READY.md` at project root
- `tests/e2e/` and any new E2E test files (e.g. `tests/test_empire_e2e_opaque_box.py`)
DO NOT modify `backend/app/` or `frontend/` source code.

## 4-Tier Test Requirements
1. Tier 1 - Feature Coverage (>=5 tests per feature):
   - Student access control (verify A accesses A, B accesses B, B denied A, anon denied A).
   - Public materials vs private canary media.
   - Login defense (rate limit / threshold / cooldown; 5 404s produce 0 brute-force).
   - Operational route auth (anonymous access rejected with 401).
   - Protected report download.
2. Tier 2 - Boundary & Corner Cases (>=5 tests per feature):
   - Empty locators, max-length URLs, special characters, unicode, boundary ports.
   - Zero/negative rate budgets, timeout limits.
   - Egress boundaries: loopback (127.0.0.1, ::1), AWS metadata (169.254.169.254), GCP metadata.
   - Unknown loop-test asset (HTTP 404 rejection).
3. Tier 3 - Cross-Feature Combinations:
   - Pairwise interactions: schedule trigger -> batch creation -> worker claim -> observation recording -> report snapshot.
4. Tier 4 - Real-World Application Scenarios:
   - Realistic workflows: 2 synthetic students, verified lab asset, daily scheduled assessment, report generation in JSON/HTML/PDF.

## Deliverables
1. `TEST_INFRA.md` at project root describing methodology, architecture, and runner commands.
2. Complete test suite file(s) in `tests/`. Run pytest to verify all tests pass.
3. `TEST_READY.md` at project root with test summary and tier counts.
4. Handoff report in `c:\Users\nguye\Desktop\noospire\.agents\teamwork\test_writer_e2e\handoff.md`.
Notify caller via `send_message` when done.


## 2026-11-10T04:26:36Z
Design and implement the 4-tier opaque-box E2E test suite (Tiers 1-4) for Noospire:
- Tier 1: Feature coverage (>=5 per feature)
- Tier 2: Boundary & corner cases (>=5 per feature)
- Tier 3: Cross-feature combinations (pairwise)
- Tier 4: Real-world application scenarios (>=5)
Create TEST_INFRA.md, write executable test files in tests/, run pytest to verify, and create TEST_READY.md.
Document your complete results in c:\Users\nguye\Desktop\noospire\.agents\teamwork\test_writer_e2e\handoff.md and notify me via send_message when done.
