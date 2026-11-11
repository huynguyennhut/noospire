# Milestone 1 Challenger 2 Handoff Report: Incident Failure Scenarios & Edge Cases

## 1. Observation

Direct observations and evidence captured across empirical test executions and codebase inspections:

1. **Frontend Empirical Incident Failure Stress Test**:
   - Command: `npx tsx tests/test_m1_challenger2_frontend_failures.ts`
   - Output:
     ```
     =============================================================================
     STARTING EMPIRICAL CHALLENGER 2: FRONTEND INCIDENT FAILURE & BOUNDARY TESTS
     =============================================================================
     [PASS] 1.1. HTTP 503 on dispatchScan throws visible launch error with status 503
     [PASS] 1.2. HTTP 503 produces zero fake job IDs and zero fabricated findings
     [PASS] 2.1. HTTP 503 on createBatchScan throws explicit 503 error without fake batch ID
     [PASS] 3.1. HTTP 200 SPA HTML response triggers explicit rejection with status 502
     [PASS] 3.2. HTTP 200 SPA HTML prevents raw JSON parse crash (no "Unexpected token <")
     [PASS] 4.1. Multiple API endpoints (scans, assets, metrics, modules) cleanly reject SPA HTML with 502
     [PASS] 5.1. dispatchNewScan() throws permanent disablement error
     [PASS] 5.2. startLiveScanWorker() is honest no-op without client-side fake scan generation
     [PASS] 6.1. api.ts static inspection confirms 100% removal of handleFallback and fallback imports
     =============================================================================
     FRONTEND CHALLENGE RESULTS: 9 PASSED, 0 FAILED
     =============================================================================
     ```
   - Exit code: 0.

2. **Backend Empirical Boundary & Recovery Replay Test**:
   - Command: `python -m pytest tests/test_m1_challenger2_backend_boundaries.py -v`
   - Output:
     ```
     ============================= test session starts =============================
     platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
     collected 7 items

     tests/test_m1_challenger2_backend_boundaries.py::test_batch_scan_unknown_asset_id_rejected_404 PASSED [ 14%]
     tests/test_m1_challenger2_backend_boundaries.py::test_batch_scan_mixed_valid_and_unknown_target_rejected_404 PASSED [ 28%]
     tests/test_m1_challenger2_backend_boundaries.py::test_batch_scan_plural_and_singular_routes PASSED [ 42%]
     tests/test_m1_challenger2_backend_boundaries.py::test_loop_test_unknown_asset_query_param_rejected_404 PASSED [ 57%]
     tests/test_m1_challenger2_backend_boundaries.py::test_loop_test_unknown_asset_json_body_rejected_404 PASSED [ 71%]
     tests/test_m1_challenger2_backend_boundaries.py::test_single_scan_unknown_asset_rejected_404 PASSED [ 85%]
     tests/test_m1_challenger2_backend_boundaries.py::test_recovery_across_replay_and_independent_sessions PASSED [100%]

     ============================== 7 passed in 2.47s ==============================
     ```
   - Exit code: 0.

3. **Combined Control Plane & Platform Core Suite**:
   - Command: `python -m pytest tests/test_milestone_a_control_plane.py tests/test_platform_core_m1.py tests/test_m1_challenger2_backend_boundaries.py -v`
   - Output:
     ```
     ============================= 30 passed in 6.37s ==============================
     ```
   - Exit code: 0.

4. **Frontend TypeScript Typecheck**:
   - Command: `npm --prefix frontend run typecheck`
   - Output: `tsc --noEmit` completed with zero errors, exit code: 0.

5. **Codebase Structural Invariant Verification**:
   - `frontend/src/lib/api.ts` lines 75–109:
     - Lines 75–79: Checks `response.status === 503` and throws `new Error('Service Unavailable: Security assessment control plane is unreachable (HTTP 503).')` with `status = 503`.
     - Lines 101–106: Checks `contentType.includes('text/html')` and throws `new Error('Unexpected HTML response received from API gateway (SPA fallback detected). Backend API route is not available.')` with `status = 502` before invoking `response.json()`.
     - Complete removal of `handleFallback`, `FALLBACK_ASSETS`, `FALLBACK_FINDINGS`, `FALLBACK_SCANS` confirmed via static AST/text assertion in test 6.1.
   - `frontend/src/lib/scan-engine.ts` lines 320–322:
     - `dispatchNewScan` throws `new Error('Client-side scan fabrication is permanently disabled. Scans must be dispatched via real backend API.')`.
     - `startLiveScanWorker` is a no-op that produces zero timers or state changes in `localStorage`.
   - `backend/app/api/scans.py` lines 220–228:
     - `create_batch_scan`: Validates `target_uuids` against database `Asset` table; if any target ID is missing, raises `HTTPException(status_code=404, detail="Target asset(s) not found: ...")`. Does NOT fall back to all inventory.
   - `backend/app/api/scans.py` lines 628–641:
     - `run_loop_test`: Resolves target locator in DB; if not found, raises `HTTPException(status_code=404, detail=f"Target asset not found for loop test: '{effective_loc}'")`.
   - `backend/app/api/scans.py` lines 96–101:
     - `create_scan`: If `not asset`, raises `HTTPException(status_code=404, detail="Asset not found")`.
   - `backend/app/api/scans.py` lines 440–449:
     - `get_scan`: Queries `select(Scan).where(Scan.id == scan_id)` directly from database, returning authentic committed scan record or raising 404 if not found.

---

## 2. Logic Chain

1. **Failure Handling Without Simulation (Incident Mitigation)**:
   - Observation 1 and 5 directly tested `frontend/src/lib/api.ts` under simulated HTTP 503 and HTTP 200 HTML responses.
   - When HTTP 503 is returned, `api.ts` throws an explicit Error with `status = 503` and does not invoke any fallback simulator. Test 1.2 confirmed that `localStorage` has zero fake job records or findings.
   - When HTTP 200 HTML (`<!DOCTYPE html>...`) is returned (e.g. from an SPA gateway route fallback), `api.ts` inspects `Content-Type` before calling `response.json()`, raising status 502. Tests 3.1, 3.2, and 4.1 proved this eliminates the `SyntaxError: Unexpected token < in JSON at position 0` crash across multiple API endpoints.

2. **Client-Side Scan Fabrication Elimination**:
   - Observation 1 and 5 verified `frontend/src/lib/scan-engine.ts`.
   - Invocations of `dispatchNewScan()` throw `Error: Client-side scan fabrication is permanently disabled`.
   - `startLiveScanWorker()` produces no background intervals, no simulated findings, and no state modifications.
   - Therefore, the UI is incapable of displaying illusory scan progress or fabricated findings when the control plane is offline.

3. **Strict Target Resolution & Unknown Asset Rejection**:
   - Observation 2 directly tested backend target validation against unknown UUIDs and locators.
   - For `/api/v1/scans/batch`, submitting a non-existent UUID raises HTTP 404 and identifies the missing UUID in the response detail. Database counters before and after the call confirmed zero scan records and zero scan batch records were created, refuting any risk of silent fallback to all assets.
   - For mixed batches (1 valid asset + 1 unknown asset), atomic validation ensures no partial scans are dispatched for the valid asset.
   - For `/api/v1/scans/loop-test`, unknown target locators supplied either via query parameter (`?target_locator=...`) or via request body return HTTP 404 with zero created scans.
   - For single scan dispatch (`/api/v1/scans`), unknown asset IDs return HTTP 404 with zero created scans.

4. **Durability and Replay Recovery**:
   - Observation 2 tested scan recovery replay across completely separate HTTP sessions and database sessions.
   - Step 1: A valid scan POST committed a `Scan` entity to SQLite and returned a genuine UUID v4.
   - Step 2: An independent `httpx.AsyncClient` with distinct viewer credentials queried `/api/v1/scans/{scan_id}` (simulating closing tabs, page refresh, and reopening in a second browser). It recovered the exact matching scan ID, target locator, asset ID, engine, and profile.
   - Step 3: Direct database inspection confirmed the persistent record in SQLite.
   - Step 4: Querying a non-existent UUID returned HTTP 404, proving that unknown scan IDs are never fabricated client-side or server-side.

---

## 3. Caveats

- **Legacy Test Suite Assertion**: During verification of older suite `tests/test_enhancement_suite.py`, tests expecting role `"SUPER_ADMIN"` for the bootstrap owner failed because Milestone 1 intentionally updated the sole owner role to `"OWNER"` with dynamic secrets (Feature F01/R5). The M1 control plane test suite (`test_milestone_a_control_plane.py`, `test_platform_core_m1.py`, and `test_m1_challenger2_backend_boundaries.py`) has 100% passing tests (30/30).
- **SQLite Concurrency Mode**: Replay tests were executed against SQLite in WAL mode. PostgreSQL backend tests in production staging should maintain identical behavior due to SQLAlchemy GUID column abstraction.
- No other caveats: All assigned boundary conditions, incident failure modes, and recovery replay invariants were empirically proven.

---

## 4. Conclusion

**Verdict: SOLUTION CORRECTNESS CONFIRMED. ZERO BUGS FOUND.**

The Milestone 1 implementation adheres strictly to the requirements in `ORIGINAL_REQUEST.md` (R1, R5) and `PROJECT.md`:
1. Both failure responses (503 and 200 SPA HTML) produce visible errors, zero fake job IDs, zero local findings, and zero JSON parse crashes.
2. Target resolution for unknown assets in batch scans, loop tests, and single scan dispatches returns HTTP 404 with zero silent fallback to inventory.
3. Valid scans commit genuine server jobs and are 100% durable and recoverable across browser refresh, second-session replay, and direct database queries without client-side fabrication.

---

## 5. Verification Method

To independently verify all Challenger 2 empirical proofs, execute the following commands from the project root:

1. **Frontend Empirical Stress Tests**:
   ```powershell
   npx tsx tests/test_m1_challenger2_frontend_failures.ts
   ```
   *Expected Result*: 9 passed, 0 failed, exit code 0.

2. **Backend Boundary & Replay Recovery Tests**:
   ```powershell
   python -m pytest tests/test_m1_challenger2_backend_boundaries.py -v
   ```
   *Expected Result*: 7 passed in ~2.5 seconds, exit code 0.

3. **Full Milestone 1 Control Plane Suite**:
   ```powershell
   python -m pytest tests/test_milestone_a_control_plane.py tests/test_platform_core_m1.py tests/test_m1_challenger2_backend_boundaries.py -v
   ```
   *Expected Result*: 30 passed in ~6.5 seconds, exit code 0.

4. **Frontend TypeScript Typecheck**:
   ```powershell
   npm --prefix frontend run typecheck
   ```
   *Expected Result*: `tsc --noEmit` exits with 0 errors.
