# Dispatch: Worker M9 — Modern Liquid Glass UI, Brand Logo, Live Telemetry & Notifications

## 2026-11-09T02:06:00Z
**Milestone**: M9: Modern Liquid Glass UI, Official Brand Logo, Live Thread Tracking ("trackcurrent") HUD & Toast Notifications
**Working Directory**: `C:\Users\nguye\desktop\noospire`
**State Folder**: `C:\Users\nguye\desktop\noospire\.agents\teamwork\worker_m9_1\`
**Original Request**: `C:\Users\nguye\desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md`
**Scope Document**: `C:\Users\nguye\desktop\noospire\.agents\teamwork\orchestrator_4\SCOPE.md`

### Mandatory Integrity Warning
> DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

### File Write Ownership (Exclusive)
- `frontend/public/brand/*` (official logo asset copy and format)
- `frontend/src/components/layout/Shell.tsx` (header brand, mobile/tablet/desktop navigation)
- `frontend/src/components/ui/toast.tsx` (liquid glass toast notification provider and hook)
- `frontend/src/lib/api.ts` (batch scan & telemetry API client methods)
- `frontend/src/app/layout.tsx` (ToastProvider root injection)
- `frontend/src/app/scans/page.tsx` ("Scan All" Hero Card / Modal with concurrency slider 1-4)
- `frontend/src/app/active-assessments/page.tsx` (active worker matrix HUD, focus switcher, resource telemetry)

### Requirements & Tasks
1. **Brand Asset Ingestion**:
   - Source image: `C:/Users/nguye/.gemini/antigravity-cli/brain/6fde3f07-9d36-4bda-a864-b53b67d53f2e/.user_uploaded/uploaded_media_1794171615086.jpg` (23.6 KB).
   - Ensure directory `frontend/public/brand/` exists. Copy source image to `frontend/public/brand/logo.jpg`. Also save as `frontend/public/brand/logo.png` (using python PIL/Pillow or raw copy).
   - In `frontend/src/components/layout/Shell.tsx`:
     - Replace the placeholder `<Shield>` icon with `<Image src="/brand/logo.jpg" alt="NOOSFORGE Logo" width={32} height={32} ... />` (or equivalent `<img>` tag) wrapped inside specular glass frame (`backdrop-blur-md bg-white/5 border border-white/10 rounded-lg p-1.5 shadow-[0_0_15px_rgba(255,255,255,0.05)]`).
     - Apply this brand presentation consistently across: Desktop Sidebar Header, Tablet/Mobile Top Navigation Bar, and Mobile Drawer Header.
     - Maintain the Black/White liquid glass aesthetic: deep black (`#000000`, `#09090b`), translucent white overlays (`bg-white/[0.03]`, `bg-white/[0.06]`), fine specular borders (`border-white/[0.08]`, `border-white/[0.15]`), backdrop blur (`backdrop-blur-xl`).

2. **Liquid Glass Toast Notification System**:
   - In `frontend/src/components/ui/toast.tsx`:
     - Implement React context provider `ToastProvider` and custom hook `useToast()`.
     - Toast methods: `toast({ title, description, variant: 'default' | 'success' | 'warning' | 'destructive', duration?: number })`.
     - Liquid glass design: `backdrop-blur-xl bg-black/80 border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.5)] rounded-xl text-white`, specular shine top border, subtle monochrome icons.
     - Inject `<ToastProvider>` into `frontend/src/app/layout.tsx`.

3. **API Client Integration**:
   - In `frontend/src/lib/api.ts`:
     - Add typescript interfaces: `ScanBatchCreate`, `ScanBatchRead`, `BatchScanResponse`, `TrackCurrentResponse`, `ActiveThreadInfo`, `SystemResourcesInfo`.
     - Add API methods:
       - `createBatchScan(data: ScanBatchCreate): Promise<BatchScanResponse>` -> `POST /api/v1/scans/batch` (or `/api/v1/scans/scan-all`).
       - `listBatches(page?: number, size?: number): Promise<PaginatedResponse<ScanBatchRead>>` -> `GET /api/v1/scans/batches`.
       - `getBatch(batchId: string): Promise<ScanBatchRead>` -> `GET /api/v1/scans/batch/${batchId}`.
       - `cancelBatch(batchId: string): Promise<{ batch_id: string, status: string, cancelled_count: number }>` -> `POST /api/v1/scans/batch/${batchId}/cancel`.
       - `stopAllScans(): Promise<{ status: string, halted_count: number }>` -> `POST /api/v1/scans/stop-all`.
       - `getTrackCurrent(): Promise<TrackCurrentResponse>` -> `GET /api/v1/scans/trackcurrent`.

4. **"Scan All" Hero Card & Batch Dispatch Controls**:
   - In `frontend/src/app/scans/page.tsx`:
     - Add prominent "Scan All" Hero Card / Batch Dispatch Modal at the top of the Scan Center:
       - Displays total registered target count badge (dynamic or fetched from `/assets`).
       - Concurrency slider (1 to 4, default 2, max 32) labeled "Worker Concurrency Throttle".
       - Engine selector checkboxes / pills (`Nuclei`, `OWASP ZAP`, `Trivy`, or `All Engines`).
       - Profile selector checkboxes / pills (`BASELINE`, `DEEP_ACTIVE`, `DAILY_SECURITY`, `STANDARD`, `INFRASTRUCTURE`, `LIGHT_PASSIVE`, `AUTHENTICATED`).
       - Noticeably warns if `DEEP_ACTIVE` is selected for unverified assets.
       - "Launch Full Sweep" button with liquid glass specular gradient (`bg-white text-black hover:bg-neutral-200 shadow-[0_0_20px_rgba(255,255,255,0.2)]`).
       - Connects to `api.createBatchScan()`, displays toast notification upon launch, and navigates / offers shortcut to Active Assessments tracking view.
     - ⚠️ CRITICAL REGRESSION ANCHOR: Preserve all existing individual scan form fields, profile labels, engine toggles, and buttons tested in `test_m6_targets_scans_adversarial.py` and `tests/test_scan_all_batch_orchestration.py`. DO NOT remove any pre-existing element or ID.

5. **Multi-Worker Live Thread Tracking ("trackcurrent") HUD**:
   - In `frontend/src/app/active-assessments/page.tsx`:
     - Integrate Active Worker Thread Matrix ("trackcurrent") HUD:
       - Queries `GET /api/v1/scans/trackcurrent` (polling interval ~2-3s or SSE integration).
       - Displays:
         - System Resource Bar: CPU %, Memory %, Memory Available, and "Throttling Active" alert badge when `is_throttled == true`.
         - Active Worker Slots Grid: Grid of active worker threads showing `Thread #N`, Target locator, Engine, Profile, Stage (`preflight`, `discovery`, `fingerprint`, `crawling`, `scoring`), progress percentage bar, and elapsed seconds.
         - Log Focus Switcher: Clicking on any active worker slot binds the live log feed panel to that specific `scan_id` via SSE (`/api/v1/scans/{scan_id}/logs/stream`), or allows viewing aggregated platform logs.
         - Controls: "Cancel Current Batch" and Emergency "Stop All Scans" (wired to `api.stopAllScans()` with confirm dialog).
     - ⚠️ CRITICAL REGRESSION ANCHOR: Preserve all existing stages (`preflight`, `discovery`, `fingerprint`, `crawling`, `scoring`), variables, and SSE handlers.

6. **Verification Requirements**:
   - Run `npm run lint` in `frontend/` -> Must pass with 0 errors.
   - Run `npm run build` in `frontend/` -> Must succeed with zero errors, generating all 18 static pages.
   - Run `pytest tests/test_scan_all_batch_orchestration.py -k "frontend" -v` -> Must pass.

Write your complete 5-component handoff report (`Observation`, `Logic Chain`, `Caveats`, `Conclusion`, `Verification Method`) to `C:\Users\nguye\desktop\noospire\.agents\teamwork\worker_m9_1\handoff.md`.
Use `send_message` to report your results back to caller.
