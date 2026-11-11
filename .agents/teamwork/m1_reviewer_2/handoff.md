# Milestone 1 Reviewer 2 Handoff Report: Frontend Incident Fix & UI Resilience Review

## 1. Observation

Direct observations and evidence captured across the frontend codebase and verification runs:

1. **Frontend Typecheck Execution**:
   - Command: `cd frontend && npm run typecheck`
   - Output:
     ```
     > noosforge-sentinel-frontend@1.0.0 typecheck
     > tsc --noEmit
     ```
   - Exit code: 0 (Zero TypeScript errors).

2. **Frontend Lint & Production Build Failure**:
   - Command: `cd frontend && npm run lint`
   - Output:
     ```
     > noosforge-sentinel-frontend@1.0.0 lint
     > next lint

     ./src/lib/api.ts
     163:7  Error: Do not assign to the variable `module`. See: https://nextjs.org/docs/messages/no-assign-module-variable  @next/next/no-assign-module-variable

     info  - Need to disable some ESLint rules? Learn more here: https://nextjs.org/docs/basic-features/eslint#disabling-rules
     ```
   - Exit code: 1.
   - Command: `cd frontend && npm run build`
   - Output:
     ```
     > noosforge-sentinel-frontend@1.0.0 build
     > next build

       ▲ Next.js 14.2.35

        Creating an optimized production build ...
      ✓ Compiled successfully
        Linting and checking validity of types ...

     Failed to compile.

     ./src/lib/api.ts
     163:7  Error: Do not assign to the variable `module`. See: https://nextjs.org/docs/messages/no-assign-module-variable  @next/next/no-assign-module-variable

     info  - Need to disable some ESLint rules? Learn more here: https://nextjs.org/docs/basic-features/eslint#disabling-rules
     ```
   - Exit code: 1.
   - Location: `frontend/src/lib/api.ts:163:7`:
     ```ts
     161:   } | string): Promise<{ items: Asset[]; total: number }> {
     162:     if (typeof params === 'string') {
     163:       const module = params;
     164:       const url = module && module !== 'ALL' ? `/assets?empire_module=${module}&size=200` : '/assets?size=200';
     165:       return this.fetchJson<{ items: Asset[]; total: number }>(url);
     166:     }
     ```

3. **Silent Fallback Elimination in `frontend/src/lib/api.ts`**:
   - The ~750-line `handleFallback` method has been completely removed from `api.ts`.
   - `fetchJson` has been hardened to reject 503 and HTML SPA fallbacks:
     ```ts
     75:     if (response.status === 503) {
     76:       const err = new Error('Service Unavailable: Security assessment control plane is unreachable (HTTP 503).');
     77:       (err as any).status = 503;
     78:       throw err;
     79:     }
     ...
     101:     const contentType = response.headers.get('content-type') || '';
     102:     if (contentType.includes('text/html')) {
     103:       const err = new Error('Unexpected HTML response received from API gateway (SPA fallback detected). Backend API route is not available.');
     104:       (err as any).status = 502;
     105:       throw err;
     106:     }
     ```
   - In callers (`frontend/src/app/scans/page.tsx:200, 271`, `frontend/src/app/assets/page.tsx:824`), dispatch failures trigger error toasts / alerts with zero fabricated job IDs, zero local findings, and zero success notifications.

4. **Neutralization of Simulated Scan Engine in `frontend/src/lib/scan-engine.ts`**:
   - `dispatchNewScan` has been disabled with an explicit throw:
     ```ts
     320: export function dispatchNewScan(_data?: any): never {
     321:   throw new Error('Client-side scan fabrication is permanently disabled. Scans must be dispatched via real backend API.');
     322: }
     ```
   - `startLiveScanWorker` is a no-op stub:
     ```ts
     315: export function startLiveScanWorker(_newScan: ScanJob, _targetAsset: Asset | undefined): void {
     316:   // Honest telemetry: Scan execution, progress, and finding generation are driven by the real backend API.
     317: }
     ```
   - Global repository search confirmed that `scan-engine.ts` is NOT imported by any page or component in `frontend/src/app`.

5. **Login Page Integrity in `frontend/src/app/login/page.tsx`**:
   - `email` and `password` state initialized to empty strings `''` (no hardcoded credentials pre-filled).
   - Removed fake `"ULTRA ADMIN / ACTIVE (SOVEREIGN)"` badges.
   - Renders authentic error message banner on authentication failure:
     ```tsx
     71:       const errorMsg =
     72:         err?.detail ||
     73:         err?.message ||
     74:         (locale === 'vi'
     75:           ? 'Tên đăng nhập hoặc mật khẩu không chính xác.'
     76:           : 'Invalid credentials. Please verify your username and password.');
     77:       setError(typeof errorMsg === 'string' ? errorMsg : JSON.stringify(errorMsg));
     ```
   - Stores genuine JWT token from `/api/v1/auth/login` in `localStorage.setItem('sentinel_jwt_token', res.access_token)`.

6. **Drill-down Filter Preservation & Pagination**:
   - `frontend/src/app/empire-modules/page.tsx` (lines 184–190) links to `/assets?empire_module=${mod.module_key}`.
   - `frontend/src/app/assets/page.tsx` reads `useSearchParams().get('empire_module')`, initializes `moduleFilter`, syncs on param changes, and wraps `TargetsContent` in `<Suspense>` (lines 2296–2300) preventing Next.js CSR de-opt warnings.
   - `frontend/src/app/assets/page.tsx` fetches `size: 200` (line 612), aligning with `backend/app/api/assets.py:33` where `size` query param is bounded by `Query(50, ge=1, le=200)`.

---

## 2. Logic Chain

1. **Integrity Assessment**:
   - The worker did not embed hardcoded test answers, dummy facades, or fabricated logs.
   - All critical features assigned to Milestone 1 Frontend (elimination of `handleFallback`, hardening of `fetchJson`, disabling of client-side scan generator, removal of hardcoded credentials, and filter preservation under Suspense) are correctly implemented.

2. **Build and Deployment Verification Failure**:
   - Observation 1 confirmed that `npm run typecheck` (`tsc --noEmit`) passes with zero errors because TypeScript allows `const module = params;` within block scope.
   - However, Observation 2 revealed that `npm run lint` and `npm run build` (`next build`) both fail with exit code 1.
   - In Next.js, `module` is a reserved CommonJS global. Assigning to a variable named `module` triggers the `@next/next/no-assign-module-variable` ESLint rule.
   - `frontend/next.config.js` sets `output: 'export'`. Next.js executes `next lint` as an integral step of `next build`. Because this rule triggers an error (not a warning), `next build` fails to produce the production export bundle.
   - Under the Quality Review and Build & Test guidelines, code changes must build cleanly on affected targets. Because `npm run build` fails, the frontend cannot be deployed to production.

---

## 3. Caveats

- **Dead Code in `scan-engine.ts`**: `scan-engine.ts` still contains inactive fallback helper functions (`resetSystemToBaseline`, `getStoredSchedules`, `getLiveTelemetry`, `FALLBACK_SCHEDULES`). While these are unreferenced by active application routes in `frontend/src/app`, they should be pruned or archived in future milestones to prevent dead-code confusion.
- **Single Line Fix**: The compilation failure is strictly caused by the variable identifier name on line 163 of `frontend/src/lib/api.ts`. Renaming `module` to `empireModule` or `moduleParam` immediately resolves the build failure.

---

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

### [Major] Finding 1: Production Next.js Build Failure via Reserved Identifier in `api.ts`
- **What**: `next build` fails to compile with exit code 1 due to ESLint error `@next/next/no-assign-module-variable`.
- **Where**: `frontend/src/lib/api.ts`, line 163:
  ```ts
  const module = params;
  ```
- **Why**: Next.js prohibits assigning to a variable named `module` because it conflicts with the CommonJS `module` object. Since Next.js runs ESLint during `next build`, this failure blocks production static export (`output: 'export'`).
- **Suggestion**: In `frontend/src/lib/api.ts` around line 163, rename the variable `module` to `empireModule`:
  ```ts
  if (typeof params === 'string') {
    const empireModule = params;
    const url = empireModule && empireModule !== 'ALL' ? `/assets?empire_module=${empireModule}&size=200` : '/assets?size=200';
    return this.fetchJson<{ items: Asset[]; total: number }>(url);
  }
  ```

---

## 5. Verification Method

To verify the finding and validate the required fix:

1. **Reproduce the build failure**:
   ```powershell
   cd frontend
   npm run build
   ```
   *Observed Result*: Build fails with `./src/lib/api.ts: 163:7 Error: Do not assign to the variable 'module'`.

2. **Verify Typecheck**:
   ```powershell
   cd frontend
   npm run typecheck
   ```
   *Observed Result*: Passes cleanly.

3. **Validation after renaming identifier**:
   Once `module` is renamed to `empireModule` in `frontend/src/lib/api.ts:163`, re-run:
   ```powershell
   cd frontend
   npm run lint
   npm run build
   ```
   *Expected Result*: `Compiled successfully`, lint passes, static export generates into `frontend/out/` with exit code 0.
