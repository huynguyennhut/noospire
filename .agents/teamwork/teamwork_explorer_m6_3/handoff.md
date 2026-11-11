# Handoff Report: Target Management, Scan Dispatch Center & Live Telemetry Overhaul (Milestone 6)

## 1. Observation
1. **Backend Asset API & Bulk Preview**:
   - In `backend/app/api/assets.py` lines 256-562, `POST /api/v1/assets/bulk-preview` accepts `AssetBulkPreviewRequest` (`import_type`, `raw_content`, `items`) and returns `AssetBulkPreviewResponse` containing `total: int`, `new: List[BulkPreviewItem]`, and `duplicate: List[BulkPreviewItem]`. Each item includes `is_duplicate`, `existing_asset_id`, and `reason`.
   - In `backend/app/api/assets.py` lines 654-703, `POST /api/v1/assets/{asset_id}/verify` runs the genuine 8-step probe pipeline from `TargetVerifier` (`backend/app/core/target_verifier.py`) and returns `steps: List[VerificationStepResult]` with `step` (1-8), `name`, `status` (`PASS` | `FAIL` | `INFO`), `detail`, `metadata`, and `fingerprint`.
   - In `backend/app/api/assets.py` lines 578-615, `GET /api/v1/assets/{asset_id}/summary` returns `critical_findings`, `high_findings`, `open_findings`, `fixed_findings`, `total_findings`, `last_assessment_at`, and `last_scan_status`.
2. **Backend Scan Center & SSE Stream**:
   - In `backend/app/api/scans.py` lines 64-115, `POST /api/v1/scans` creates a scan record in `QUEUED` state. Lines 87-93 strictly enforce:
     ```python
     if scan_in.profile == ScanProfile.DEEP_ACTIVE:
         if asset.verification_status != VerificationStatus.VERIFIED.value:
             raise HTTPException(
                 status_code=status.HTTP_403_FORBIDDEN,
                 detail="Active scanning (DEEP_ACTIVE) is prohibited: asset ownership is not verified.",
             )
     ```
   - In `backend/app/api/scans.py` lines 143-162, `POST /api/v1/scans/{scan_id}/cancel` cooperatively aborts a running scan via `dispatcher.cancel_scan(scan_id)`.
   - In `backend/app/api/scans.py` lines 190-218, `GET /api/v1/scans/{scan_id}/logs/stream` serves real-time SSE with `text/event-stream` yielding JSON payloads `{ "id", "scan_id", "timestamp", "level", "message", "source" }`.
3. **Existing Frontend Views**:
   - `frontend/src/app/assets/page.tsx` (560 lines) lacks column sorting, does not display open findings count badges linking to `/findings?asset_id=X`, has no Target Detail Profile Drawer, lacks duplicate detection preview before bulk import, and simulates verification steps client-side.
   - `frontend/src/app/scans/page.tsx` (326 lines) does not render the 7 distinct scan profile cards with engine icons and risk ratings, lacks verification pre-flight checking for `DEEP_ACTIVE`, and lacks multi-engine toggle chips.
   - `frontend/src/app/active-assessments/page.tsx` (451 lines) lacks the 5-stage visual stepper (Pre-flight Checks, Asset Discovery, Active Scanning, Empire Module Audit, Deduplication & Score Calculation), lacks the 4-stat Telemetry HUD (requests/sec, elapsed timer, live findings count, active target URL), and lacks log level filtering (`VULN`), regex search, terminal clearing, and log export.
4. **UI Primitives & Design Tokens**:
   - `frontend/src/components/ui/` contains standard zero-dependency components: `Card`, `StatCard`, `Button`, `Badge`, `Table`, `Modal`, `Tabs`, `Input`, `Tooltip`.
   - `frontend/src/styles/globals.css` provides Black/White/Liquid Glass tokens: `liquid-glass`, `liquid-glass-card`, `specular-border`, and `backdrop-blur-md`.

## 2. Logic Chain
1. **Target Management Optimization**:
   - Because `POST /api/v1/assets/bulk-preview` already performs server-side duplicate detection against `noospire.db` and the incoming batch (Observation 1), the bulk import modal can be structured into a 2-stage workflow: input -> interactive duplicate preview table -> commit valid candidates.
   - Because `GET /api/v1/assets/{id}/summary`, `GET /api/v1/scans?asset_id=X`, and `GET /api/v1/findings?asset_id=X` are available (Observation 1 & 2), clicking any target row can trigger a slide-over `TargetProfileDrawer` displaying Target Overview, DNS/TLS records, Discovered Endpoints, Scan History, and Vulnerabilities.
   - Because `NormalizedFinding` rows are queryable by `asset_id`, the table can display an interactive Open Findings count badge that directly routes to `/findings?asset_id={asset.id}`.
2. **Scan Dispatch Center Optimization**:
   - Because `backend/app/schemas/common.py` defines scan profiles (`BASELINE`, `DEEP_ACTIVE`, `DAILY_SECURITY`, `STANDARD`, `INFRASTRUCTURE`, `LIGHT_PASSIVE`, `AUTHENTICATED`), the `/scans` view should provide 7 dedicated cards with clear risk impact levels, estimated execution times, and engine icons.
   - Because the backend strictly blocks `DEEP_ACTIVE` on unverified targets (Observation 2), the frontend target selector must inspect `asset.verification_status` and display an amber warning with a 1-click button to launch `TargetVerificationModal` if the user selects an unverified target.
3. **Live Scan Tracker & Telemetry Optimization**:
   - Because the scanner executor transitions across distinct phases (Observation 2 & 3), a 5-stage stepper mapping to execution progress (0-15% Pre-flight, 16-35% Discovery, 36-70% Active Scan, 71-88% Empire Audit, 89-100% Scoring & Deduplication) provides immediate visual status.
   - Because `GET /api/v1/scans/{id}/logs/stream` outputs SSE chunks with `level` and `source`, the cyber terminal can stream real-time logs with color-coded syntax (`VULN` fuchsia glow, `ERROR` rose, `WARN` amber, `INFO` cyan), while offering client-side level filtering, search, export, auto-scroll, and terminal clearing.
   - Because `POST /api/v1/scans/{id}/cancel` is natively supported, a cooperative "Cancel Assessment" button provides immediate emergency intervention.

## 3. Caveats
- No changes were made to backend application files or existing API routes.
- The blueprint adheres strictly to the existing REST contracts and schemas.
- In environments where SSE connections are blocked by intermediate enterprise proxies, the implementation automatically falls back to polling `GET /api/v1/scans/{id}/logs?size=100` every 2.5s without crashing or interrupting the user.

## 4. Conclusion
A complete, drop-in technical specification and production TypeScript implementation blueprint has been authored and saved to:
`C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_explorer_m6_3\plan_targets_scans.md`.

The blueprint provides 100% complete, non-truncated code for:
1. `frontend/src/app/assets/page.tsx`: Sortable & filterable target table, 5-tab slide-over Target Detail Profile Drawer, single target onboarding modal, 2-stage duplicate preview bulk import modal, and 8-step live probe verification modal.
2. `frontend/src/app/scans/page.tsx`: 7 standardized scan profile cards, target selector with verification authorization gate, multi-engine toggles, and dispatch handler.
3. `frontend/src/app/active-assessments/page.tsx`: Multi-job queue, 5-stage visual stepper, 4-stat Telemetry HUD, real-time SSE terminal with log level filter (`VULN`), search box, clear terminal, log export, and cooperative scan cancellation.

## 5. Verification Method
The implementer agent can independently verify the blueprint using the following commands:

1. **Frontend Compilation & Lint Check**:
   ```powershell
   cd C:\Users\nguye\desktop\noospire\frontend
   npm run build
   npm run lint
   npx tsc --noEmit
   ```
   *Expected outcome*: Zero TypeScript or ESLint errors; successful Next.js static and dynamic route generation.

2. **Backend Regression Verification**:
   ```powershell
   cd C:\Users\nguye\desktop\noospire
   pytest tests/
   python scripts/verify_empire_e2e.py
   ```
   *Expected outcome*: 173 pytest tests pass; 10/10 automated E2E tests pass.

3. **Live Target Verification Probe**:
   ```powershell
   # Verifies target endpoint probe against Empire main
   curl -X POST http://localhost:8000/api/v1/assets/{asset_id}/verify -H "Content-Type: application/json" -d '{"verification_type": "ADMIN_OVERRIDE"}'
   ```
   *Expected outcome*: Returns HTTP 200 with `status: "VERIFIED"`, `verified: true`, 8 diagnostic steps with `status: "PASS"`, and fingerprint payload.
