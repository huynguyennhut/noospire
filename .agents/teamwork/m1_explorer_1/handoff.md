# Handoff Report: Milestone 1 Frontend Incident Fix Strategy

**Author**: Explorer 1 (`m1_explorer_1`)  
**Target Milestone**: Milestone 1 (Frontend Incident Fix Strategy & Control Plane Integrity)  
**Date**: 2026-11-10T08:25:00Z  

---

## 1. Observation

Direct inspection of the frontend codebase identified critical design flaws, silent fallback behavior, and inventory pagination bugs across four core areas:

### 1.1 Silent Fallback & Simulator Debt in `frontend/src/lib/api.ts`
- **Lines 28–50**:
  Imports fallback datasets and client-side simulation functions:
  ```typescript
  import { FALLBACK_ASSETS, FALLBACK_FINDINGS, FALLBACK_SCANS } from './fallback-data';
  import {
    getStoredAssets, saveStoredAssets, getStoredFindings, saveStoredFindings,
    getStoredScans, saveStoredScans, getStoredLogs, dispatchNewScan,
    cancelScanJob, stopAllActiveScans, getLiveTelemetry, clearScanLogs,
    clearAllScanLogs, resetSystemToBaseline, getStoredSchedules,
    toggleStoredSchedule, triggerStoredSchedule, createStoredSchedule,
    deleteStoredSchedule,
  } from './scan-engine';
  ```
- **Lines 83–836**:
  `private handleFallback<T>(endpoint: string, options: RequestInit = {}): T` encompasses over 750 lines of mock response generators:
  - Generates fabricated scan IDs (`scan-${Date.now().toString(36)}-...`) via `dispatchNewScan`.
  - Generates fabricated batch IDs (`batch-${Date.now().toString(36)}`).
  - Generates fake JWT tokens (`jwt_sentinel_ultra_admin_${Date.now()}` on `/auth/login`).
  - Mutates browser `localStorage` to simulate scan cancellations, log purges, and finding triages.
  - Generates hardcoded static trend charts, risk scores, and intelligence stats.
- **Lines 838–873 (`fetchJson`)**:
  ```typescript
  private async fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers || {});
    headers.set('Content-Type', 'application/json');

    const token = this.getToken();
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }

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
  - **Vulnerability on 503 Service Unavailable**: If an Nginx, cloud load balancer, or FastAPI gateway returns 503 with an HTML error page, `response.json()` throws inside `try { ... } catch (_) {}`. While it does throw an Error, it lacks content-type validation and diagnostic body extraction.
  - **Vulnerability on 200 SPA HTML**: If Next.js, an edge router, or a misconfigured reverse proxy rewrites an API route to `index.html`, `response.ok` is `true` (status 200). `fetchJson` immediately calls `await response.json()`, causing an unhandled `SyntaxError: Unexpected token '<', "<!DOCTYPE "... is not valid JSON`. This throws an opaque runtime syntax error rather than a clear API failure, and does not surface the actual HTTP/HTML failure payload to the caller.
- **Lines 1241–1246 (`resetBaseline`)**:
  ```typescript
  public async resetBaseline(): Promise<{ message: string; assets: number; findings: number; scans: number; schedules?: number }> {
    try {
      await this.fetchJson('/system/reset', { method: 'POST' });
    } catch (_) {}
    return resetSystemToBaseline();
  }
  ```
  Silently suppresses backend failure and falls back to mutating client `localStorage` with `resetSystemToBaseline()`.
- **Lines 1233–1239 (`clearLogs` & `clearAllLogs`)**:
  Calls client-side `clearScanLogs(scanId)` and `clearAllScanLogs()` in `scan-engine.ts` instead of dispatching real API requests.

### 1.2 Client-Side Simulated Worker in `frontend/src/lib/scan-engine.ts`
- **Lines 314–318**:
  ```typescript
  export function startLiveScanWorker(_newScan: ScanJob, _targetAsset: Asset | undefined): void {
    // Honest telemetry: Scan execution, progress, and finding generation are driven by the real backend API.
  }
  ```
  `startLiveScanWorker` is currently an empty stub, but `scan-engine.ts` retains an entire in-memory/localStorage fake database (`STORAGE_KEYS`, `memoryAssets`, `memoryFindings`, `memoryScans`, `memoryLogs`, `activeTimers`, `generateDefaultLogsForScan`, `dispatchNewScan`, `getLiveTelemetry`, `createStoredSchedule`, etc.).
- When `api.ts` or any caller uses these functions, scan IDs and telemetry are fabricated on the client, violating the requirement that all state transitions and findings originate from genuine backend database commits and SSE streams.

### 1.3 Login Form & Mock Credentials in `frontend/src/app/login/page.tsx`
- **Lines 30–41**:
  Pre-populates the login email field from browser `localStorage.getItem('sentinel_user')`.
- **Lines 141–153**:
  Renders a misleading badge on the unauthenticated login screen:
  ```tsx
  <div className="flex items-center justify-between p-2.5 rounded-xl bg-white/[0.03] border border-white/10 text-xs mb-4">
    <div className="flex items-center gap-2">
      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
      <span className="font-mono text-[11px] text-slate-300">
        {locale === 'vi' ? 'Theo Dõi Quản Trị & Dev Track:' : 'Operator & Dev Tracking:'}{' '}
        <strong className="text-emerald-400">ACTIVE (SOVEREIGN)</strong>
      </span>
    </div>
    <Badge severity="critical" size="sm">
      ULTRA ADMIN
    </Badge>
  </div>
  ```
  This creates false confidence of an authenticated "ACTIVE (SOVEREIGN)" ultra admin session prior to providing credentials.
- **Line 182**: `placeholder="admin"` hints at default/hardcoded credentials.

### 1.4 Asset Inventory Pagination & Filter Drop in `frontend/src/app/assets/page.tsx`
- **Lines 478–481**:
  ```tsx
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [moduleFilter, setModuleFilter] = useState<string>('ALL');
  const [envFilter, setEnvFilter] = useState<string>('ALL');
  const [typeFilter, setTypeFilter] = useState<string>('ALL');
  ```
  `moduleFilter` defaults unconditionally to `'ALL'`. It completely ignores `useSearchParams()` from `next/navigation`.
- **Drill-down route in `frontend/src/app/empire-modules/page.tsx:185`**:
  ```tsx
  <Link href={`/assets?empire_module=${mod.module_key}`} ...>
  ```
  When an operator clicks "Targets (55)" on the Empire Module card, navigating to `/assets?empire_module=API_SERVICES`, `TargetsPage` ignores `?empire_module=API_SERVICES`, resetting the filter to `ALL`.
- **Lines 602–605 & `api.ts:919–922`**:
  ```typescript
  // frontend/src/lib/api.ts
  public async listAssets(module?: string): Promise<{ items: Asset[]; total: number }> {
    const url = module ? `/assets?empire_module=${module}&size=100` : '/assets?size=100';
    return this.fetchJson<{ items: Asset[]; total: number }>(url);
  }
  ```
  - Backend `backend/app/api/assets.py:57-108` supports `page`, `size` (up to 200), `empire_module`, `asset_type`, `environment`, `verification_status`, and `search`.
  - Frontend hardcodes `size=100` with NO pagination controls.
  - When 379 synthetic targets exist in the database (Gate 2 requirement), `listAssets()` retrieves only 100 targets. The remaining 279 targets are silently excluded from the operator view.
  - Filtering in `assets/page.tsx` is executed client-side over only the loaded 100 targets (`filteredAndSortedAssets`), meaning targets in other modules on pages 2-4 are unreachable.

---

## 2. Logic Chain

1. **Premise**: Requirement R1 and Gate 1 mandate that failed fetches, unsuccessful HTTP responses, or HTML parsing failures must never trigger a local simulator or fallback data. Both 503 and 200 SPA HTML at API paths must produce visible launch errors, zero fabricated job IDs, zero local findings, and zero success notifications.
   - **Observation Reference**: `api.ts:83–836` (`handleFallback`), `api.ts:838–873` (`fetchJson`), `scan-engine.ts:320–350` (`dispatchNewScan`).
   - **Inference**: If `handleFallback` is present, any caught exception or failed network call risks synthesizing fake scans or fake authentication. In addition, when an API route returns 200 SPA HTML, `fetchJson` crashes on `response.json()` without a structured error indicating that the server returned an HTML document instead of JSON. Adding strict content-type verification (`isJson`) and eliminating `handleFallback` guarantees that errors bubble up visibly to the UI without fabricating IDs or notifications.

2. **Premise**: Requirement R1 requires that a valid scan POST commits a server job and returns its server ID. Following the immediate tracker redirect, refreshing, closing all tabs, and reopening in a second browser must each recover the exact same job and output.
   - **Observation Reference**: `scans/page.tsx:260–275`, `active-assessments/page.tsx:62–74, 191–205, 212–221, 260–315`.
   - **Inference**: In `scans/page.tsx`, `api.dispatchScan` posts to `/api/v1/scans`, which commits a `Scan` row to the database and returns `scan.id`. The frontend redirects immediately to `/active-assessments?scan_id=${scan.id}`. In `active-assessments/page.tsx`, `initialScanId` is read from `useSearchParams()`. However, `activeScanId` could be overwritten if `fetchScans()` does not find the scan immediately in the first page of results. By ensuring `activeScanId` prioritizes `searchParams.get('scan_id')` and immediately loads the scan by ID via `api.getScan(scanId)`, the state is recovered identically across page reloads and secondary browsers.

3. **Premise**: Requirement R1 and Gate 1 require that Empire module cards and asset drill-downs match API schemas and carry filter state without resetting to ALL, and UI asset pagination must be audited.
   - **Observation Reference**: `empire-modules/page.tsx:185`, `assets/page.tsx:478–481, 602–605`, `api.ts:919–922`, `backend/app/api/assets.py:57–108`.
   - **Inference**: Because `assets/page.tsx` never reads `useSearchParams()`, any inbound link with query parameters (e.g. `?empire_module=API_SERVICES`) is dropped on mount. Furthermore, because `api.listAssets` requests `size=100` and `assets/page.tsx` performs purely in-memory filtering on those 100 items, 279 targets out of 379 are invisible. Updating `api.listAssets` to support query parameters, syncing `useSearchParams` to filter state on mount and update, and supporting server-side query filtering or multi-page fetching ensures complete inventory accounting and zero filter drop.

4. **Premise**: Requirement R1 mandates removing hardcoded credentials, synthetic auto-fill buttons, and premature superuser indicators on login.
   - **Observation Reference**: `login/page.tsx:141–153, 182`.
   - **Inference**: Displaying "ACTIVE (SOVEREIGN)" and "ULTRA ADMIN" on the unauthenticated login card is misleading. Removing this badge, changing the input placeholder from `admin` to a generic label, and ensuring the server's error message (e.g. 401 Unauthorized) is displayed without mock fallbacks guarantees compliance.

---

## 3. Caveats

1. **Backend Database Seeding State**:
   The frontend depends on the backend `/api/v1/assets` endpoint returning genuine seeded targets. In local SQLite dev environments where `noospire.db` is clean, the backend must seed the approved 379 inventory records or appropriate module targets.
2. **Next.js `useSearchParams()` Suspense Boundary**:
   In Next.js 14 App Router, any client component using `useSearchParams()` must be wrapped in a `<Suspense>` boundary to prevent de-opting into client-side rendering during static build. `active-assessments/page.tsx` already wraps `ActiveAssessmentsContent` in `Suspense`. When adding `useSearchParams()` to `assets/page.tsx`, a `Suspense` boundary must also be ensured.
3. **SSE Connection in Air-Gapped / Proxy Environments**:
   When EventSource connects to `/api/v1/scans/{id}/logs/stream`, some reverse proxies or edge buffers buffer SSE. The polling fallback in `active-assessments/page.tsx` (every 2.5s calling `api.getScanLogs`) provides necessary redundancy if the stream disconnects.

---

## 4. Conclusion & Concrete Implementation Plan

### 4.1 Plan for `frontend/src/lib/api.ts`

#### Step 1: Remove Fallback Imports and `handleFallback`
- **Delete** lines 28–50:
  Remove imports of `FALLBACK_ASSETS`, `FALLBACK_FINDINGS`, `FALLBACK_SCANS` from `./fallback-data` and all imported functions from `./scan-engine`.
- **Delete** lines 83–836:
  Completely remove the `private handleFallback<T>` method (~750 lines).

#### Step 2: Harden `fetchJson` against 503 and 200 SPA HTML
Replace lines 838–873 with the following drop-in implementation:

```typescript
  private async fetchJson<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers = new Headers(options.headers || {});
    if (!headers.has('Content-Type') && options.body && typeof options.body === 'string') {
      headers.set('Content-Type', 'application/json');
    }

    const token = this.getToken();
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }

    let response: Response;
    try {
      response = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
      });
    } catch (networkErr: any) {
      const err = new Error(`Network failure connecting to API at ${endpoint}: ${networkErr?.message || String(networkErr)}`);
      (err as any).status = 0;
      throw err;
    }

    const contentType = response.headers.get('content-type') || '';
    const isJson = contentType.toLowerCase().includes('application/json');

    // Handle non-2xx responses (including 503, 500, 401, 403, 404)
    if (!response.ok) {
      let errorMsg = `HTTP Error ${response.status}: ${response.statusText || 'Request Failed'}`;
      let detail: any = null;

      if (isJson) {
        try {
          const errorJson = await response.json();
          detail = errorJson.detail;
          if (errorJson.detail) {
            errorMsg = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail);
          }
        } catch (_) {}
      } else {
        try {
          const rawText = await response.text();
          if (rawText && rawText.length < 300 && !rawText.includes('<html') && !rawText.includes('<!DOCTYPE')) {
            errorMsg = `${errorMsg} — ${rawText.trim()}`;
          } else if (response.status === 503) {
            errorMsg = 'HTTP Error 503: Service Unavailable. Backend scan engine or API gateway is unreachable.';
          }
        } catch (_) {}
      }

      const err = new Error(errorMsg);
      (err as any).status = response.status;
      (err as any).detail = detail;
      throw err;
    }

    // 204 No Content
    if (response.status === 204) {
      return {} as T;
    }

    // Gate against 200 SPA HTML response at API paths
    if (!isJson) {
      const sampleText = await response.text().catch(() => '');
      const isHtml = sampleText.toLowerCase().includes('<!doctype') || sampleText.toLowerCase().includes('<html');
      const err = new Error(
        `Invalid API response at ${endpoint}: Expected application/json but received ${contentType || 'non-JSON payload'}` +
        (isHtml ? ' (SPA HTML fallback detected. API endpoint may not be routed properly).' : '.')
      );
      (err as any).status = response.status;
      throw err;
    }

    try {
      return await response.json();
    } catch (jsonErr: any) {
      const err = new Error(`Failed to parse JSON response from ${endpoint}: ${jsonErr?.message || String(jsonErr)}`);
      (err as any).status = response.status;
      throw err;
    }
  }
```

#### Step 3: Upgrade `listAssets` to Support Structured Query Params & Pagination
Replace lines 919–922:

```typescript
  export interface AssetListParams {
    page?: number;
    size?: number;
    empire_module?: string;
    asset_type?: string;
    environment?: string;
    verification_status?: string;
    search?: string;
  }

  public async listAssets(params?: AssetListParams | string): Promise<{ items: Asset[]; total: number; page?: number; size?: number; pages?: number }> {
    const query = new URLSearchParams();
    if (typeof params === 'string') {
      if (params && params !== 'ALL') query.append('empire_module', params);
      query.append('size', '200');
    } else if (params) {
      if (params.page) query.append('page', String(params.page));
      query.append('size', String(params.size || 200));
      if (params.empire_module && params.empire_module !== 'ALL') query.append('empire_module', params.empire_module);
      if (params.asset_type && params.asset_type !== 'ALL') query.append('asset_type', params.asset_type);
      if (params.environment && params.environment !== 'ALL') query.append('environment', params.environment);
      if (params.verification_status && params.verification_status !== 'ALL') query.append('verification_status', params.verification_status);
      if (params.search) query.append('search', params.search);
    } else {
      query.append('size', '200');
    }
    const queryString = query.toString();
    const url = queryString ? `/assets?${queryString}` : '/assets';
    return this.fetchJson<{ items: Asset[]; total: number; page?: number; size?: number; pages?: number }>(url);
  }
```

#### Step 4: Fix Log Clearing and System Reset
Replace lines 1233–1247:
```typescript
  public async clearLogs(scanId: string): Promise<void> {
    await this.fetchJson(`/scans/${scanId}/logs`, { method: 'DELETE' });
  }

  public async clearAllLogs(): Promise<void> {
    // Purge operational logs across all completed scans
    await this.fetchJson('/scans/logs/purge', { method: 'POST' }).catch(() => {});
  }

  public async resetBaseline(): Promise<{ message: string; assets: number; findings: number; scans: number; schedules?: number }> {
    return this.fetchJson<{ message: string; assets: number; findings: number; scans: number; schedules?: number }>(
      '/system/reset-baseline',
      { method: 'POST' }
    );
  }
```

---

### 4.2 Plan for `frontend/src/lib/scan-engine.ts`

1. **Remove simulated scan dispatch**:
   - In `dispatchNewScan`: mark deprecated or remove; ensure it does not fabricate synthetic jobs.
2. **Remove client-side timer simulation**:
   - `startLiveScanWorker`: leave as an explicit no-op or remove; document that all state transitions must come from backend SSE or `/api/v1/scans` polling.
3. **Decouple from `api.ts`**:
   - Ensure `api.ts` has zero imports from `scan-engine.ts`. All real data flows through `ApiClient` calling the backend.

---

### 4.3 Plan for `frontend/src/app/login/page.tsx`

1. **Remove misleading indicators**:
   - **Delete** lines 141–153 (the "Operator & Dev Tracking: ACTIVE (SOVEREIGN)" and "ULTRA ADMIN" badge).
2. **Update input placeholders**:
   - Replace line 182: `placeholder="admin"` → `placeholder="operator@empire.edu.vn"`.
3. **Ensure authentic error display**:
   - In `handleLogin`:
     ```typescript
     try {
       const res = await api.login(cleanEmail, password);
       ...
     } catch (err: any) {
       setError(
         err?.message ||
         (locale === 'vi'
           ? 'Xác thực thất bại. Vui lòng kiểm tra lại thông tin tài khoản.'
           : 'Authentication failed. Please verify your credentials.')
       );
       setLoading(false);
     }
     ```
     With `fetchJson` throwing explicit errors, 401 Unauthorized, 403 Forbidden, and 503 Service Unavailable will be displayed transparently in the red error alert banner.

---

### 4.4 Plan for Asset Pagination & Drill-Down in `frontend/src/app/assets/page.tsx`

1. **Read `useSearchParams` on load and preserve filters**:
   In `frontend/src/app/assets/page.tsx`:
   - Import `useSearchParams` from `'next/navigation'`.
   - Initialize `moduleFilter` from URL:
     ```tsx
     const searchParams = useSearchParams();
     const queryModule = searchParams?.get('empire_module');
     const [moduleFilter, setModuleFilter] = useState<string>(queryModule || 'ALL');

     // Keep moduleFilter synchronized if URL query parameter changes
     useEffect(() => {
       const m = searchParams?.get('empire_module');
       if (m && m !== moduleFilter) {
         setModuleFilter(m);
       }
     }, [searchParams]);
     ```
2. **Fetch all targets / pass filters to backend**:
   Update `fetchAssets` to request `size=200` (or multiple pages up to total):
   ```tsx
   const fetchAssets = useCallback(async () => {
     try {
       setLoading(true);
       // Fetch page 1 (up to 200)
       const res = await api.listAssets({ page: 1, size: 200, empire_module: moduleFilter !== 'ALL' ? moduleFilter : undefined });
       let allItems = res.items || [];

       // If total exceeds 200, fetch page 2
       if (res.total > 200 && res.pages && res.pages > 1) {
         const p2 = await api.listAssets({ page: 2, size: 200, empire_module: moduleFilter !== 'ALL' ? moduleFilter : undefined });
         allItems = [...allItems, ...(p2.items || [])];
       }

       setAssets(allItems);

       // Hydrate summary metrics for top assets
       allItems.slice(0, 25).forEach(async (a) => {
         try {
           const sum = await api.getAssetSummary(a.id);
           setSummaries((prev) => ({ ...prev, [a.id]: sum }));
         } catch (_) {}
       });
     } catch (err) {
       console.error('Failed to load targets', err);
     } finally {
       setLoading(false);
     }
   }, [moduleFilter]);
   ```
   This ensures that:
   - When an operator navigates from Empire Modules to `/assets?empire_module=STUDENT_MANAGEMENT`, the module filter is preserved and the table shows only Student Management assets.
   - If the estate has 379 inventory records, both page 1 and page 2 are fetched, ensuring all 379 assets are accounted for without truncation.

---

### 4.5 Plan for Valid Scan POST & Multi-Tab/Multi-Browser Recovery

1. **Dispatch Flow**:
   - In `frontend/src/app/scans/page.tsx`:
     ```tsx
     const scan = await api.dispatchScan({
       asset_id: selectedAssetId,
       engine: getSelectedEngineParam(),
       profile: selectedProfile,
       allow_private_targets: allowPrivate,
       timeout_seconds: timeoutSeconds,
     });
     // Redirect immediately to live tracker with server UUID
     window.location.href = `/active-assessments?scan_id=${scan.id}`;
     ```
2. **Tracker Recovery in `frontend/src/app/active-assessments/page.tsx`**:
   - `initialScanId` is read directly from `useSearchParams().get('scan_id')`.
   - On initial mount:
     ```tsx
     useEffect(() => {
       if (initialScanId) {
         setActiveScanId(initialScanId);
         fetchScanJobStatus(initialScanId);
         fetchScanLogsFallback(initialScanId);
       }
     }, [initialScanId, fetchScanJobStatus, fetchScanLogsFallback]);
     ```
   - In `fetchScans()`:
     ```tsx
     setActiveScanId((prev) => {
       if (prev) return prev; // Preserve current active selection across background polls!
       if (initialScanId) return initialScanId;
       ...
     });
     ```
   - **Recovery Verification**:
     - **Immediate Redirect**: Redirects to `/active-assessments?scan_id=<uuid>`, mounts tracker, establishes SSE and fallback polling.
     - **Page Refresh**: URL retains `?scan_id=<uuid>`, component reads `initialScanId`, fetches `/api/v1/scans/<uuid>` and displays exact server state.
     - **Tab Close & Reopen**: Reopening `http://localhost:3000/active-assessments?scan_id=<uuid>` in any tab loads the persistent DB job.
     - **Second Browser**: Opening `http://localhost:3000/active-assessments?scan_id=<uuid>` in another browser instance queries `/api/v1/scans/<uuid>`, connects to SSE `/api/v1/scans/<uuid>/logs/stream`, and renders the exact same running or terminal job without local storage dependencies.

---

## 5. Verification Method

To independently verify the implementation:

### 5.1 Automated Code & Build Verification
```bash
# 1. Verify frontend TypeScript compilation and lint
cd frontend && npm run lint

# 2. Verify frontend production static build
npm run build

# 3. Verify backend scan creation and contract tests
cd .. && pytest tests/test_platform_core_m1.py tests/test_enhancement_suite.py -v
```

### 5.2 Failure Response Probes (503 & 200 SPA HTML)
1. **503 Service Unavailable Probe**:
   - Mock `/api/v1/scans` to return HTTP 503 with an HTML error body `<html><body>503 Service Unavailable</body></html>`.
   - Dispatch a scan from UI.
   - **Expected Result**: An explicit error toast/banner is displayed: `"HTTP Error 503: Service Unavailable..."`. Zero job IDs generated in localStorage, zero fake notifications, zero navigation to fake tracker.
2. **200 SPA HTML Probe**:
   - Mock `/api/v1/scans` to return HTTP 200 with `Content-Type: text/html` and body `<!DOCTYPE html><html><body>SPA</body></html>`.
   - Dispatch a scan from UI.
   - **Expected Result**: An explicit error toast/banner is displayed: `"Invalid API response at /scans: Expected application/json but received text/html..."`. Zero fake jobs created.

### 5.3 Valid Scan POST & Recovery Replay
1. Dispatch scan from `/scans` against verified target `asset-emp-001`.
2. Verify browser immediately redirects to `/active-assessments?scan_id=<server-uuid>`.
3. Verify live logs and status appear via SSE.
4. Press `F5` (Refresh). Verify the scan job, progress, and logs reload from backend.
5. Close the browser tab entirely.
6. Open a separate browser (e.g. Incognito or secondary browser), navigate directly to `http://localhost:3000/active-assessments?scan_id=<server-uuid>`.
7. Verify the identical scan job and terminal output/logs are displayed.

### 5.4 Asset Drill-Down & Pagination Verification
1. Navigate to `/empire-modules`.
2. Click "Targets" on the "Student Management Portal" card (links to `/assets?empire_module=STUDENT_MANAGEMENT`).
3. Verify that `/assets` loads with `moduleFilter = 'STUDENT_MANAGEMENT'`, showing only Student Management targets.
4. Verify that total target inventory reflects all 379 synthetic targets across pages without truncation to 100.

### 5.5 Invalidation Conditions
- If any failed HTTP response (401, 403, 500, 503) generates a fake scan ID or fake finding in `localStorage`.
- If an HTML response to an API endpoint causes an unhandled `SyntaxError: Unexpected token '<'`.
- If refreshing `/active-assessments?scan_id=...` causes the active scan to switch to another scan or reset to null.
- If navigating to `/assets?empire_module=...` defaults to `'ALL'`.
- If the unauthenticated login page shows "ACTIVE (SOVEREIGN)" or "ULTRA ADMIN" before login.
