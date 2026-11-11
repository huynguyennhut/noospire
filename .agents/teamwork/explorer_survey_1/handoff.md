# Frontend Codebase Architecture, Implementation Gaps & Bug Survey

## 1. Observation

### 1.1 Silent Fallback & Local Simulation Machinery (`api.ts`, `scan-engine.ts`, `fallback-data.*`)
- **`frontend/src/lib/api.ts` Lines 83–836**: Contains a monolithic private method `handleFallback<T>(endpoint: string, options: RequestInit = {}): T` that intercepts every operational route:
  - Lines 87–105: Intercepts `POST /assets/:id/verify`, mutating local storage and returning synthetic `ADMIN_OVERRIDE` verification.
  - Lines 108–138: Intercepts `GET /assets` and `GET /assets/:id/summary`, querying in-memory arrays and calculating synthetic scan counts (`total_scans: 12`).
  - Lines 141–181: Intercepts `POST /findings/:id/triage` and `POST /findings/:id/retest`, mutating local storage and faking remediations (`status: 'PASSED'`).
  - Lines 208–220: Intercepts `POST /scans`, calling `dispatchNewScan()` from `scan-engine.ts` with fallback asset `ast-emp-01` and client-generated random scan IDs.
  - Lines 222–247: Intercepts `POST /scans/batch`, dispatching only 6 hardcoded scans (one per module: `['API_SERVICES', 'STUDENT_MANAGEMENT', 'WEB_APPLICATION', 'LEARNING_MATERIALS', 'SUPPORTING_TOOLS', 'SERVER_INFRASTRUCTURE']`) with random batch ID `batch-${Date.now().toString(36)}`.
  - Lines 288–298: Intercepts `GET /empire-modules`, returning 6 static modules with mismatched field names (`module_code`, `module_name`, `target_count`, `active_findings`).
  - Lines 301–413: Intercepts `/metrics/overview`, `/metrics/severity-distribution`, `/metrics/charts/module-risk`, `/metrics/charts/remediation-progress`, `/metrics/charts/vulnerability-trend`, `/metrics/charts/risk-trend`, returning hardcoded arrays of dates (`2026-10-27` to `2026-11-09`) and static scores (`overall_risk_score: 100.0`).
  - Lines 626–645: Intercepts `POST /auth/login`, generating client-side tokens `jwt_sentinel_ultra_admin_${Date.now()}` with synthetic user objects without contacting the backend.
  - Lines 660–663 & 1241–1246: Intercepts `POST /system/reset`, calling `resetSystemToBaseline()`.
- **`frontend/src/lib/api.ts` Lines 1241–1246**:
  ```typescript
  public async resetBaseline(): Promise<{ message: string; assets: number; findings: number; scans: number; schedules?: number }> {
    try {
      await this.fetchJson('/system/reset', { method: 'POST' });
    } catch (_) {}
    return resetSystemToBaseline();
  }
  ```
  `resetBaseline` wraps the API call in an empty `catch (_) {}` block and unconditionally falls back to client-side `resetSystemToBaseline()`.
- **`frontend/src/lib/scan-engine.ts` Lines 59–67 & 83–245**:
  - Defines `STORAGE_KEYS` (`sentinel_assets_v3`, `sentinel_findings_v3`, `sentinel_scans_v3`, `sentinel_logs_v3`, `sentinel_schedules_v3`).
  - Functions `getStoredAssets()`, `getStoredFindings()`, `getStoredScans()`, `getStoredLogs()`, `getStoredSchedules()` seed `localStorage` from `FALLBACK_ASSETS`, `FALLBACK_FINDINGS`, `FALLBACK_SCANS`, `FALLBACK_SCHEDULES` whenever storage is empty or fails parsing.
  - `dispatchNewScan()` (lines 320–351) generates client-side IDs `scan-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}` and prepends to `sentinel_scans_v3`.
  - `generateDefaultLogsForScan()` (lines 248–312) fabricates 9 synthetic operational logs for any historical scan ID with pre-scripted messages (`[PRE-FLIGHT] Initialized security inspection pipeline...`, `[DISCOVERY] Crawled 42 endpoints...`).
- **`frontend/src/components/evidence/EvidenceViewer.tsx` Lines 106–149**:
  - When `evidence.request` or `evidence.response` is empty, lines 106–149 synthesize fake HTTP requests (`GET ${targetLocation} HTTP/1.1...`), fake HTTP responses (`HTTP/1.1 200 OK\nServer: nginx/1.24 (Ubuntu)...`), and fake response bodies (`matched_pattern: evidence.matched_content || 'DETECTED_INDICATOR'`).
- **`frontend/src/components/layout/Shell.tsx` Lines 206–221**:
  - In `checkHealth()`:
    ```typescript
    try {
      await api.getSettings();
      ...
    } catch (_) {
      if (isMounted) {
        // Graceful fallback for static dev preview
        setBackendStatus('online');
        setLatencyMs(18);
      }
    }
    ```
    When the backend is down or unreachable, the shell catches the error and reports `backendStatus = 'online'` and `latencyMs = 18`.

### 1.2 503 & 200 SPA HTML Response Handling in `fetchJson`
- **`frontend/src/lib/api.ts` Lines 838–873**:
  ```typescript
  private async fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    ...
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errorMsg = `HTTP Error ${response.status}: ${response.statusText}`;
      let detail: any = null;
      try {
        const errorJson = await response.json();
        detail = errorJson.detail;
        if (errorJson.detail) {
          errorMsg = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
        }
      } catch (_) {}
      const err = new Error(errorMsg);
      (err as any).status = response.status;
      (err as any).detail = detail;
      throw err;
    }

    if (response.status === 204) {
      return {} as T;
    }

    return await response.json();
  }
  ```
  - **Handling of 503**: `response.ok` is false. When the 503 body is an HTML error page (e.g. from Cloudflare, Nginx, or an ASGI reverse proxy), `response.json()` throws a syntax error, caught by `catch (_) {}`. `detail` is left `null` and `errorMsg` defaults to `HTTP Error 503: Service Unavailable`.
  - **Handling of 200 SPA HTML**: When a reverse proxy, dev server, or Next.js rewrite redirects unknown `/api/v1/*` routes to the SPA index (`index.html`) returning HTTP 200 with `text/html`, `response.ok` is `true`. Line 872 executes `return await response.json()`, which fails with `SyntaxError: Unexpected token '<', "<!DOCTYPE "... is not valid JSON`.
  - **Header inspection**: `fetchJson` never checks `response.headers.get('content-type')` before attempting to parse JSON.
  - **Component error swallowing**:
    - `frontend/src/app/dashboard/page.tsx` Lines 133–155: Catches all failed calls with `.catch(() => null)`, `.catch(() => [])`, or `.catch(() => ({ ... }))`, masking 503 and HTML errors into empty/default arrays.
    - `frontend/src/app/scans/page.tsx` Lines 215–216: `api.listScans().catch(() => ({ items: [], total: 0 }))` swallows failures.
    - `frontend/src/app/active-assessments/page.tsx` Lines 214 & 225: `api.getScan(id).catch(() => null)` and `api.getScanLogs(id).catch(() => [])` swallow failures.

### 1.3 Active Assessments Event Truncation & SSE Streaming (`active-assessments/page.tsx`)
- **`frontend/src/app/active-assessments/page.tsx` Lines 268–300**:
  ```typescript
  if (typeof window !== 'undefined' && window.EventSource) {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }
    const sseUrl = `/api/v1/scans/${activeScanId}/logs/stream`;
    const es = new EventSource(sseUrl);
    ...
    es.onerror = () => {
      setSseConnected(false);
    };
  }
  ```
  - Native browser `EventSource` does NOT send custom HTTP headers (`Authorization: Bearer <token>`).
  - The JWT token is stored solely in `localStorage` (`sentinel_jwt_token`). No token is stored in browser cookies.
  - In `backend/app/api/scans.py` Lines 500–505:
    ```python
    @router.get("/{scan_id}/logs/stream")
    async def stream_scan_logs(
        scan_id: uuid.UUID,
        current_user: User = Depends(require_viewer),
    ) -> StreamingResponse:
    ```
    Endpoint requires `require_viewer`. Because `EventSource` passes no token in headers or cookies, `get_current_user` returns `None`, resulting in `HTTP 401 Unauthorized`.
  - The SSE connection immediately enters `es.onerror()`, sets `sseConnected = false`, and dies.
- **Fallback Polling Event Concealment (Events 101+)**:
  - When SSE fails, `active-assessments/page.tsx` relies on `fetchScanLogsFallback(activeScanId)` invoked every 2500ms (lines 302–305).
  - Lines 223–237:
    ```typescript
    const logsData = await api.getScanLogs(id).catch(() => []);
    ```
  - In `frontend/src/lib/api.ts` Lines 991–994:
    ```typescript
    public async getScanLogs(scanId: string): Promise<Array<{ timestamp: string; level: string; message: string; source: string }>> {
      const data = await this.fetchJson<any>(`/scans/${scanId}/logs?size=100`);
      return Array.isArray(data) ? data : (data.items || []);
    }
    ```
  - In `backend/app/api/scans.py` Lines 435–478:
    `get_scan_logs` endpoint accepts `page: int = Query(1)` and `size: int = Query(50, ge=1, le=200)`. It executes:
    `stmt = stmt.offset((page - 1) * size).limit(size)`
  - Because `api.getScanLogs` hardcodes `size=100` with default `page=1`, it returns at most the first 100 log entries.
  - The frontend never tracks the last received event ID (`Last-Event-ID`), never increments `page`, and never queries incremental logs. Consequently, all scan log events from index 101 onwards are permanently truncated and hidden from the operator.

### 1.4 Empire Modules Fields & Asset Drill-Down Routes
- **`frontend/src/app/empire-modules/page.tsx` Lines 184–197**:
  - Target drill-down link:
    ```typescript
    <Link href={`/assets?empire_module=${mod.module_key}`}>
      <span>Targets ({mod.asset_count})</span>
      <ArrowRight className="w-3 h-3" />
    </Link>
    ```
  - Findings drill-down link:
    ```typescript
    <Link href={`/findings?module=${mod.module_key}`}>
      <span>View Findings ({mod.total_findings})</span>
    </Link>
    ```
- **`frontend/src/app/assets/page.tsx` Line 479 & Lines 600–605**:
  - Line 479: `const [moduleFilter, setModuleFilter] = useState<string>('ALL');`
  - `assets/page.tsx` does NOT import or call `useSearchParams()`.
  - When an operator clicks `Targets (55)` from `/empire-modules`, navigating to `/assets?empire_module=API_SERVICES`, `moduleFilter` remains `'ALL'`, discarding the route state.
- **Inventory Pagination Cap in `assets/page.tsx` & `api.ts`**:
  - `api.listAssets(module)` (line 920 of `api.ts`) executes `/assets?size=100`.
  - `assets/page.tsx` line 602 executes `const res = await api.listAssets(); setAssets(res.items || []);` and filters in-memory over `assets`.
  - Backend `backend/app/api/assets.py` line 60 has `size: int = Query(50, ge=1, le=200)`.
  - Across the Empire ecosystem there are 379 inventory assets. Requesting `size=100` loads only the first 100 rows; the remaining 279 assets are invisible in the UI inventory grid.
- **Discrepancy in `handleFallback` field schemas**:
  - `api.ts` line 289 returned `module_code`, `module_name`, `target_count`, `active_findings`.
  - Real backend `backend/app/api/empire_modules.py` lines 112–129 and `types.ts` line 127 define `module_key`, `title`, `asset_count`, `total_findings`, `risk_score`, `risk_tier`.

### 1.5 Dashboard Metrics & Schedule Tracking (`dashboard/page.tsx`)
- **Default Time Horizon**:
  - `frontend/src/app/dashboard/page.tsx` Line 98: `const [timeRange, setTimeRange] = useState<TimeRangeDays>(14);` defaults to 14 days rather than 7 calendar days.
- **Hardcoded Baseline State**:
  - Lines 62–92: Initializes state with `EMPIRE_BASELINE_METRICS`, `EMPIRE_SEVERITY_DIST`, `EMPIRE_MODULE_RISK`. If network calls fail, the UI displays pre-scripted static metrics (379 total assets, 1 critical, 56 high, score 100.0) without indicating network disconnection.
- **Missing Service Reachability**:
  - R4 requires displaying Empire root (`https://empire.edu.vn`) and subservices reachability, HTTP latency, last measured time, freshness, and degraded/down/unknown status. `dashboard/page.tsx` contains no service reachability widget or endpoint bindings.
- **Missing Engine Queue & Worker Thread Telemetry**:
  - R4 requires displaying current workers/threads, queued/running/terminal engine jobs, open threats, and link to today's work. While `api.getTrackCurrent()` exists, it is called only in `active-assessments/page.tsx`, not on the Dashboard.
- **Missing 1-Second Countdown & Hourly Schedule Timer**:
  - R3 & R4 require a 1-second countdown to the next hourly scheduled scan (Asia/Ho_Chi_Minh timezone) with pause/resume controls and overdue status. `dashboard/page.tsx` has no countdown timer or schedule integration.

### 1.6 Findings Workflow, Tracker & Deletion Gaps
- **Findings Actions (`findings/page.tsx` & `EvidenceViewer.tsx`)**:
  - Contains "Retest" (`api.retestFinding(id)`), but lacks "Rescan target" (which must dispatch a fresh assessment for the parent asset).
  - Lacks tracking and display of operator-reported fix timestamps vs scanner-verified fix timestamps.
- **Terminal History Bulk Deletion**:
  - `scans/page.tsx` lines 860–926 renders a static 6-row table (`scans.slice(0, 6)`) without checkboxes, bulk selection, confirmation modal, affected-record counts, or delete endpoints.
  - Active running jobs cannot be distinguished from terminal jobs in bulk operations.
- **Batch-Grouped Notifications (`Shell.tsx`)**:
  - Lines 104–129 & 233–251: Renders a flat list of 5 alerts from `DEFAULT_ALERTS` or `api.listAlerts()`.
  - When an Ultra Scan runs (728 engine executions), notifications are not grouped under a parent batch header, causing notification flooding.
  - Read/unread state is stored globally in component state, not isolated per user in the database.
- **Reports Preview & Authenticated Downloads (`reports/page.tsx`)**:
  - Lines 216–248: Downloads use direct anchor tags `<a href={api.getDownloadUrl(rep.id, 'pdf')} target="_blank">`.
  - Backend `backend/app/api/reports.py` line 120 protects `/reports/{report_id}/download` with `require_viewer`.
  - Because `window.open` / `<a target="_blank">` navigation cannot supply `Authorization: Bearer <token>`, downloading reports fails with HTTP 401 Unauthorized.
  - No interactive report preview modal exists.

### 1.7 Sole Owner RBAC & Session Revocation (`Shell.tsx`, `settings/page.tsx`)
- **Sole Owner Restrictions (dangnhutnguyen0910@gmail.com)**:
  - "Run Ultra Scan" is not exposed on Scan Center or Dashboard.
  - `settings/page.tsx` (lines 35–39) has tabs for `baselines`, `synthetic`, `policy`, `ssrf`, `maintenance`, but completely lacks a User Management / Role Granting interface.
  - All 14 navigation items in `Shell.tsx` are visible to any logged-in user regardless of role (`VIEWER`, `OPERATOR`, `DEVELOPER`).
- **Session Revocation Handling**:
  - When an account is deactivated on the backend, API calls return `HTTP 401: Inactive or suspended user account`.
  - The frontend has no global 401 interceptor. The UI remains on the current page with stale `sentinel_user` and `sentinel_jwt_token` in `localStorage`.
  - `handleLogout` in `Shell.tsx` lines 170–177 simply clears `localStorage` without calling `POST /api/v1/auth/logout`, leaving the active JWT unrevoked in the backend database.

---

## 2. Logic Chain

1. **Premise 1**: Requirement R1 mandates the elimination of all silent fallback behavior where failed fetch, unsuccessful HTTP status, or HTML parsing failure triggers a local simulator or fallback data, ensuring 503 and 200 SPA HTML responses produce a visible launch error.
   - *Observation Reference*: 1.1 (`api.ts` lines 83–836, `scan-engine.ts`, `EvidenceViewer.tsx` lines 106–149) and 1.2 (`api.ts` lines 838–873).
   - *Inference*: As long as `handleFallback` and client-side simulator functions exist, any transient backend glitch or route mismatch causes the client to silently invent scan IDs and fake findings, violating Gate 1.
2. **Premise 2**: Gate 1 requires that logs and SSE streams deliver events beyond event 100 without truncation or event loss.
   - *Observation Reference*: 1.3 (`active-assessments/page.tsx` lines 268–300 & `api.ts` line 992).
   - *Inference*: Native `EventSource` cannot send the `Authorization` header, triggering a 401 error from `require_viewer`. When fallback polling runs, `api.getScanLogs` queries `?size=100` without pagination. Therefore, events 101+ are mathematically impossible to receive in the current frontend implementation.
3. **Premise 3**: Gate 1 requires that Empire module cards and asset drill-downs carry filter state without resetting to ALL.
   - *Observation Reference*: 1.4 (`empire-modules/page.tsx` lines 185–192 & `assets/page.tsx` line 479).
   - *Inference*: Because `assets/page.tsx` initializes `moduleFilter` with `useState('ALL')` without inspecting `useSearchParams()`, navigating from `/empire-modules` invariably resets the selection filter to `ALL`.
4. **Premise 4**: Gate 4 requires Dashboard metrics to display genuine measured data for 7 calendar days with service reachability, engine queue status, threat counts, and a 1-second countdown timer.
   - *Observation Reference*: 1.5 (`dashboard/page.tsx` line 98, lines 62–92, and lack of reachability/countdown components).
   - *Inference*: Setting `timeRange` to 14 days and lacking reachability probes or countdown timers causes immediate failure against Gate 4 acceptance criteria.
5. **Premise 5**: Gate 4 requires authenticated downloads and bulk history deletion with confirmation and record counts.
   - *Observation Reference*: 1.6 (`reports/page.tsx` lines 216–248 & `scans/page.tsx` lines 860–926).
   - *Inference*: Anchor tag downloads fail with 401 because `Authorization` headers are not passed. Static table rendering in `scans/page.tsx` lacks selection checkboxes, preventing bulk deletion.
6. **Premise 6**: Gate 5 requires binding owner authority to `dangnhutnguyen0910@gmail.com` and immediately invalidating active sessions upon account deactivation.
   - *Observation Reference*: 1.7 (`Shell.tsx` lines 170–177 & `settings/page.tsx`).
   - *Inference*: Lacking a 401 response interceptor and server-side logout call allows deactivated sessions to linger client-side.

---

## 3. Caveats

- **Scope Boundary**: This survey investigated the frontend codebase in `frontend/src` and its direct contract bindings with `backend/app/api`. Underlying scanner worker daemons and backend database schema migrations were reviewed only to verify frontend API contracts.
- **Third-Party Libraries**: Next.js 14 App Router and standard Web APIs (`fetch`, `EventSource`) were assumed as the foundational execution environment.
- **No Production Code Modified**: Per teamwork explorer constraints, this investigation is strictly read-only. All recommended code modifications are presented as actionable implementation blueprints.

---

## 4. Conclusion & Remediation Blueprints

### 4.1 Remediation Blueprint: `frontend/src/lib/api.ts` & `scan-engine.ts`
1. **Delete `handleFallback` and local simulation**:
   - Completely remove `handleFallback<T>` (lines 83–836) from `api.ts`.
   - Purge `scan-engine.ts` and `fallback-data.ts`/`fallback-data.json` from client build imports.
2. **Harden `fetchJson` against 503 and 200 SPA HTML**:
   - Check `response.headers.get('content-type')`: if it contains `text/html`, read text and throw:
     ```typescript
     const text = await response.text();
     throw new ApiError(
       `Unexpected HTML response from API endpoint ${endpoint} (Status: ${response.status}). Service may be unavailable or misrouted.`,
       response.status,
       text.slice(0, 300)
     );
     ```
   - For non-2xx status, extract structured JSON errors or throw explicit `ApiError(statusText, response.status)`.
3. **Add Global 401 Session Invalidation Interceptor**:
   - If `response.status === 401`, clear `localStorage.removeItem('sentinel_jwt_token')` and `localStorage.removeItem('sentinel_user')`, dispatch a custom `auth:revoked` event, and redirect to `/login`.
4. **Implement Authenticated Blob Downloader in `api.ts`**:
   ```typescript
   public async downloadReportFile(reportId: string, format: string, filename: string): Promise<void> {
     const headers = new Headers();
     const token = this.getToken();
     if (token) headers.set('Authorization', `Bearer ${token}`);
     const res = await fetch(`${API_BASE}/reports/${reportId}/download?format=${format}`, { headers });
     if (!res.ok) throw new Error(`Download failed with status ${res.status}`);
     const blob = await res.blob();
     const url = URL.createObjectURL(blob);
     const a = document.createElement('a');
     a.href = url;
     a.download = filename;
     document.body.appendChild(a);
     a.click();
     document.body.removeChild(a);
     URL.revokeObjectURL(url);
   }
   ```

### 4.2 Remediation Blueprint: `active-assessments/page.tsx`
1. **Authenticated SSE Streaming**:
   - Pass JWT access token via query parameter `/api/v1/scans/${activeScanId}/logs/stream?token=${encodeURIComponent(token)}` (and ensure backend dependency accepts token from query parameter for SSE).
   - Send `Last-Event-ID` header or query parameter `since_id` on reconnect.
2. **Incremental Bounded Fallback Polling (Events 101+)**:
   - Update `getScanLogs` in `api.ts` to accept `from_id?: string`, `page?: number`, and `size: number = 200`.
   - In `active-assessments/page.tsx`, track `highestLogId` or accumulated pages, polling until all available logs are ingested without truncating at 100 entries.

### 4.3 Remediation Blueprint: `assets/page.tsx` & `empire-modules/page.tsx`
1. **Synchronize Route Search Params**:
   - Wrap `TargetsPage` in `<Suspense>` and call `useSearchParams()`.
   - Read `searchParams.get('empire_module') || searchParams.get('module')`.
   - Initialize `moduleFilter` with `initialModule || 'ALL'`, updating filter state when the query parameter changes.
2. **Full Inventory Pagination Support**:
   - Expose page and size controls, or query all pages for full inventory views (`size=200` with pagination controls) so all 379 target assets can be inspected.

### 4.4 Remediation Blueprint: `dashboard/page.tsx`
1. **Default to 7 Calendar Days**:
   - Set `timeRange` initial state to `7` (`useState<TimeRangeDays>(7)`).
2. **Remove Hardcoded Static State**:
   - Initialize `metrics`, `severityDist`, and `moduleRisk` as `null` or loading skeletons. Display error banners on failure rather than fallback mocks.
3. **Add Empire Service Reachability Component**:
   - Query root endpoint `/health` or dedicated reachability endpoints, showing reachability status, latency in milliseconds, last checked timestamp, and freshness badges.
4. **Add Engine Queue & 1-Second Countdown**:
   - Poll `api.getTrackCurrent()` to display active worker process slots and thread metrics.
   - Fetch `/schedules` to calculate `next_run_at`, displaying a live 1-second countdown timer to the top-of-the-hour scan with pause/resume controls.

### 4.5 Remediation Blueprint: Operator Screens & Sole Owner RBAC
1. **Expose "Run Ultra Scan"**:
   - Add hero card button on Scan Center and Dashboard visible only when `currentUser?.email === 'dangnhutnguyen0910@gmail.com'`.
   - Include idempotency key (`crypto.randomUUID()`), initiator, scope `ALL`, and preserve exact engine selection.
2. **Bulk Scan History Deletion**:
   - Add row selection checkboxes in `scans/page.tsx` for terminal jobs (`COMPLETED`, `FAILED`, `CANCELLED`).
   - Implement confirmation modal showing affected scan and log record counts.
   - Connect to `DELETE /api/v1/scans/bulk` or iterative server deletion, disabling deletion for `RUNNING` or `QUEUED` jobs.
3. **Grouped Notifications**:
   - Group child scan completion alerts under parent batch headers in `Shell.tsx` to prevent 728-alert clutter.
4. **Reports Download**:
   - Replace `<a href=... target="_blank">` in `reports/page.tsx` with `api.downloadReportFile()` to ensure JWT headers are included.

---

## 5. Verification Method

To independently verify the frontend survey findings and validate remediation:

1. **Frontend Typecheck & Build**:
   ```powershell
   npm --prefix frontend run typecheck
   npm --prefix frontend run build
   ```
   *Expected Result*: Must compile cleanly without TypeScript or Next.js build errors.
2. **Verify Elimination of Fallback Data**:
   ```powershell
   Select-String -Path "frontend/src/lib/api.ts" -Pattern "handleFallback"
   Select-String -Path "frontend/src/lib/scan-engine.ts" -Pattern "STORAGE_KEYS"
   ```
   *Expected Result*: Zero occurrences of `handleFallback` and local storage mock seeding.
3. **Verify 503 & 200 HTML Error Handling**:
   - Run mock test hitting a dummy server returning 503 HTML and 200 HTML on `/api/v1/scans`.
   - Confirm `fetchJson` throws `ApiError` with clear description and does not parse HTML as JSON.
4. **Verify SSE & Events 101+ Delivery**:
   - Execute a scan generating >120 logs.
   - Verify in `active-assessments` that all 120+ events are received and rendered in the terminal container.
5. **Verify Empire Module Drill-Down**:
   - Open browser at `http://localhost:3000/empire-modules`.
   - Click "Targets (55)" under `API_SERVICES`.
   - Confirm route is `/assets?empire_module=API_SERVICES` and dropdown displays `API Services` (not reset to `ALL`).
6. **Verify Dashboard 7-Day Window & Countdown**:
   - Open `http://localhost:3000/dashboard`.
   - Confirm default tab is `7D`, reachability card displays live latency, and 1-second countdown ticks toward the top of the hour.
7. **Verify Authenticated Reports Download**:
   - Log in as `dangnhutnguyen0910@gmail.com`.
   - Navigate to `/reports`, click "PDF" download.
   - Confirm file downloads with HTTP 200 carrying `Authorization: Bearer` header.
