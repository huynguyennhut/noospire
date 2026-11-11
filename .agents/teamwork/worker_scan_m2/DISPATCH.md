# DISPATCH — AGENT 2 (Scanning and Intelligence) — Milestone M2

You are worker_scan_m2 (teamwork_worker).
Your working directory is: c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_scan_m2
Original request file: c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md
Project specification: c:\Users\nguye\Desktop\noospire\PROJECT.md
Test infrastructure: c:\Users\nguye\Desktop\noospire\TEST_INFRA.md and TEST_READY.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope & Assigned Files (Exclusive Write Ownership):
- `backend/app/scanners/` (including `nuclei.py`, `zap.py`, `empire_engine.py`, `crawler.py`, `base.py`)
- `backend/app/core/dispatcher.py`
- `backend/app/models/scan.py`
- `backend/app/schemas/scan.py`
- `backend/app/schemas/common.py`
- `backend/app/api/scans.py`
- `backend/app/api/findings.py` (for `flag_modified` fix on evidence mutation)

Key Deliverables:
1. Scanner Quality State Machine (R2):
   - In `backend/app/schemas/common.py`, `backend/app/models/scan.py`, and `backend/app/schemas/scan.py`, introduce `ScanQualityStatus` enum: `SCANNED_SUCCESSFULLY`, `PARTIAL_COVERAGE`, `AUTH_REQUIRED`, `SCANNER_FAILED`, `TARGET_UNAVAILABLE`.
   - Add `quality_status` column to `Scan` model and expose in `ScanRead` schema.
   - In `backend/app/core/dispatcher.py`, evaluate scanner adapter outcomes and transition to the correct explicit quality status instead of catching errors and silently returning `COMPLETED`.
   - Preserve backwards compatibility with `ScanStatus` (`status in ['QUEUED', 'INITIALIZING', 'RUNNING', 'COMPLETED']`).
2. Real Scanner Orchestration & Process Safety (R2):
   - In `backend/app/scanners/nuclei.py` and `backend/app/scanners/trivy.py`, register child process `proc.pid` with `process_safety.register_pid(request.scan_id, proc.pid)` so process tree termination cleanly kills external binaries on scan cancellation or timeout.
   - Implement `backend/app/scanners/crawler.py`: An asynchronous same-origin BFS web crawler (max_depth=3, max_pages=50, rate-limited, strictly matching target asset domain) that discovers and indexes endpoints on target assets prior to or during scan dispatch.
   - In `backend/app/scanners/zap.py`, ensure real HTTP requests are performed via `httpx.AsyncClient` or native ZAP process if available.
3. Empire Business Module Security & Finding Intelligence (R3):
   - In `backend/app/scanners/empire_engine.py`, ensure comprehensive coverage of the Empire business modules: Student Management, Learning Materials and `/media`, Supporting Tools, API Security, Web Security, Brute-force defense, Server and infrastructure starting from `https://empire.edu.vn/`.
   - In `backend/app/api/findings.py`, add `from sqlalchemy.orm.attributes import flag_modified; flag_modified(finding, "evidence")` so in-place triage history mutations are persisted cleanly.
4. Testing & Verification:
   - Run `python scripts/verify_empire_e2e.py` (ensure 10/10 tests PASS).
   - Run `pytest tests/ -v` (ensure all tests PASS).
   - Write unit tests for the quality state machine and crawler.

Write your report to c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_scan_m2\report.md and create a self-contained handoff report at c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_scan_m2\handoff.md. Send a completion message when done.


## 2026-11-08T13:16:17Z
[Message from orchestrator parent 29630e35-2325-48c7-a6c2-ca18347fdb37]
Milestone M2 (Scanning and Intelligence):
1. In backend/app/models/scan.py, backend/app/schemas/common.py, and backend/app/schemas/scan.py, implement the Scanner Quality State Machine: add ScanQualityStatus enum (SCANNED_SUCCESSFULLY, PARTIAL_COVERAGE, AUTH_REQUIRED, SCANNER_FAILED, TARGET_UNAVAILABLE) and quality_status field on Scan.
2. In backend/app/core/dispatcher.py, update state transitions to set explicit quality_status and fail or block cleanly rather than silently completing on errors.
3. In backend/app/scanners/nuclei.py and backend/app/scanners/trivy.py, register child process proc.pid with ProcessSafetyManager.
4. Implement backend/app/scanners/crawler.py: asynchronous BFS same-origin crawler (max_depth=3, max_pages=50, rate-limited) strictly matching target asset domain.
5. In backend/app/scanners/empire_engine.py, ensure coverage of Empire business modules starting from https://empire.edu.vn/.
6. In backend/app/api/findings.py, add flag_modified(finding, "evidence") for clean JSON mutation persistence.
7. Verify all tests pass: python scripts/verify_empire_e2e.py (10/10 PASS) and pytest tests/ -v (all PASS).
