# Handoff Report: Frontend Architecture & Security Operations Gap Analysis

**Agent**: Survey Explorer (`teamwork_explorer_enh_2`)  
**Working Directory**: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\teamwork_explorer_enh_2\`  
**Target System**: NOOSFORGE Security Intelligence Command Center (`frontend/src/`)  
**Timestamp**: 2026-11-09T19:26:00Z  
**Handoff Type**: Hard (Task Complete)  

---

## 1. Observation

Direct observations and evidence collected across the codebase:

1. **Auto-seeding of Ultra Admin in `frontend/src/components/layout/Shell.tsx` (Lines 150–170)**:
   ```typescript
   useEffect(() => {
     if (typeof window !== 'undefined') {
       const raw = localStorage.getItem('sentinel_user');
       if (raw) {
         try {
           setCurrentUser(JSON.parse(raw));
         } catch (_) {}
       } else {
         // Default to Ultra Admin session for seamless experience
         const defaultAdmin = {
           email: 'dangnhutnguyen0910@gmail.com',
           name: 'Đại Ca Tú (Ultra Admin)',
           role: 'SUPER_ADMIN',
           is_ultra_admin: true,
         };
         localStorage.setItem('sentinel_user', JSON.stringify(defaultAdmin));
         setCurrentUser(defaultAdmin);
       }
     }
   }, []);
   ```
   - On cold visit (no localStorage `sentinel_user`), the Shell automatically creates an Ultra Admin session.
   - When `handleLogout()` (lines 172–179) deletes `sentinel_user` and navigates to `/login`, `Shell.tsx` mounts on `/login` and immediately executes the `else` branch, recreating the session instantly.

2. **Login Page Bypass & Mock JWT Generation in `frontend/src/app/login/page.tsx`**:
   - Lines 23–28: Hardcodes `ULTRA_ADMIN_CREDENTIALS` (`dangnhutnguyen0910@gmail.com` / `REDACTED-ROTATE-ME`).
   - Lines 55–95: `handleLogin` validates credentials via JavaScript comparison and sets `sentinel_jwt_token = "jwt_live_token_" + Date.now()`. It does not call backend `POST /api/v1/auth/login`.
   - Lines 97–123: `handleOneClickUltraAdmin` sets `sentinel_jwt_token = "jwt_ultra_admin_" + Date.now()` and redirects to `/dashboard`.
   - `frontend/src/app/page.tsx:6` renders `<DashboardPage />` directly without checking authentication or redirecting to `/login`.

3. **Backend Credential Mismatch in `backend/app/api/auth.py` & `backend/app/core/config.py`**:
   - `backend/app/core/config.py:30-31`:
     ```python
     ADMIN_USERNAME: str = os.getenv("SENTINEL_ADMIN_USER", "admin")
     ADMIN_PASSWORD: str = os.getenv("SENTINEL_ADMIN_PASS", "admin123")
     ```
   - `backend/app/core/security.py:79-88`:
     ```python
     payload = decode_access_token(token)
     if not payload:
         if settings.is_development:
             return DEV_MOCK_SUPERUSER
         raise HTTPException(
             status_code=status.HTTP_401_UNAUTHORIZED,
             detail="Could not validate credentials",
             headers={"WWW-Authenticate": "Bearer"},
         )
     return payload
     ```
   - Ultra Admin credentials (`dangnhutnguyen0910@gmail.com` / `REDACTED-ROTATE-ME`) are not registered in backend database or config. In production (`ENVIRONMENT=production`), client requests with dummy tokens (`jwt_live_token_...`) fail with `401 UNAUTHORIZED`.

4. **Window Viewport Hijacking in `frontend/src/app/active-assessments/page.tsx`**:
   - Line 84: `const [autoScroll, setAutoScroll] = useState(false);`
   - Lines 316–321:
     ```typescript
     // Auto-scroll anchor
     useEffect(() => {
       if (autoScroll) {
         terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
       }
     }, [logs, autoScroll]);
     ```
   - Line 1021: `<div ref={terminalEndRef} />` at the end of the log output.
   - Calling `scrollIntoView` moves the entire browser window/viewport downward whenever new logs arrive (every 2.5s via `fetchScanLogsFallback` or on SSE events), jerking the view away from user focus.
   - Line 1000: Log container has `className="h-[420px] overflow-y-auto ..."` but lacks a container reference to control `scrollTop`.

5. **Log History & Reset State Controls**:
   - `frontend/src/app/active-assessments/page.tsx`:
     - Lines 463–470: "Track by Days" filter (`timeFilter`) filters only the left sidebar scan queue (`1D`, `7D`, `14D`, `30D`), not system logs.
     - Lines 350–362: `handleClearTerminal` clears logs for the active scan.
     - Lines 364–384 & Lines 496–505: "Quay Về Ban Đầu" (`handleResetBaseline`) button resets database to verified baseline.
     - No central platform-wide system log inspection view exists.
     - Reset baseline button is missing from `frontend/src/app/settings/page.tsx`.

6. **Schedules Management in `frontend/src/app/schedules/page.tsx`**:
   - Lines 171–234: Displays cards for daily schedules with cron (`0 2 * * *`), target scope, timezone, status, and manual trigger button ("Run Daily Pipeline Now").
   - `frontend/src/lib/api.ts:850` defines `deleteSchedule(id)`, but there is no delete button or edit modal in `schedules/page.tsx`.

7. **Static Engine Diagnostics Matrix in `frontend/src/app/health/page.tsx`**:
   - Lines 122–132: Subsystem diagnostics rows (Nuclei CLI, Empire Engine, ZAP, Trivy, ReportLab) are static hardcoded JSON objects, not fetched from live scanner adapters.
   - No buttons exist for: "Verify All Engines", "Check Engine Updates", or "Update Nuclei Templates".

8. **Notification Tracking in `frontend/src/components/layout/Shell.tsx`**:
   - Lines 234–252: Fetches alerts once on mount (`api.listAlerts()`); no recurring polling or SSE connection.
   - Lines 295–297: `markAllAlertsRead` only mutates local React state; backend `POST /api/v1/alerts/read-all` is never called.
   - Lines 305–350: Mobile header lacks a notification bell icon.

---

## 2. Logic Chain

1. **Observation 1 & 2** show that visiting any page auto-creates an Ultra Admin user in `localStorage` when none is present, and `/login` is wrapped inside the standard layout.  
   $\rightarrow$ **Inference**: The login page cannot currently function as an authentic entry gate; users are never forced to authenticate, and logging out immediately re-creates the session.

2. **Observation 3** shows that backend token validation only passes because `is_development` triggers `DEV_MOCK_SUPERUSER`.  
   $\rightarrow$ **Inference**: The frontend token system is currently disconnected from the backend. Deploying in non-development mode will cause full API failure unless Ultra Admin credentials and proper JWT creation are synchronized.

3. **Observation 4** shows that `terminalEndRef.current?.scrollIntoView()` targets an element within an `overflow-y-auto` container, but `scrollIntoView()` scrolls the parent window by default.  
   $\rightarrow$ **Inference**: Whenever auto-scroll is triggered during active scans, the operator's entire browser window jerks to the bottom of the page every 2.5 seconds. The user's explicit mandate ("Không auto scroll, check UI") requires disabling auto-scroll by default and converting any scroll behavior to internal container `scrollTop = scrollHeight`.

4. **Observation 5** demonstrates that `handleResetBaseline` ("Quay Về Ban Đầu") and "Track by Days" exist in `/active-assessments`, but apply only to the scan queue.  
   $\rightarrow$ **Inference**: The platform lacks an administrative audit/log viewer for inspecting system-wide operational logs by calendar day, and baseline reset controls should be accessible in `/settings`.

5. **Observation 7** shows that `/health` presents static hardcoded engine paths and statuses.  
   $\rightarrow$ **Inference**: The user's requirement ("Kiểm tra tính toàn vẹn - dùng all engine. Test thật, kết quả thật - không fake kết quả... Update if engine got update") cannot be met until the health view queries real engine availability, checks for updates, and allows triggering live engine self-tests.

6. **Observation 8** shows the mobile topbar has no notification bell, alerts are fetched only once, and "Mark all read" does not persist.  
   $\rightarrow$ **Inference**: Real-time operational security alert tracking is broken on mobile devices and loses state upon desktop page reload.

---

## 3. Caveats

- **Scope Boundary**: This was a read-only investigation. No source files outside the agent's metadata directory (`.agents/teamwork/teamwork_explorer_enh_2/`) were modified.
- **Backend Runner Availability**: Binary CLI engines (`nuclei.exe`, `zap.sh`) depend on host OS environment paths. In environments where CLI binaries are not installed, the system cleanly defaults to high-fidelity embedded lab runners (`NucleiLabRunner`, `ZAPLabRunner`, `EmpireAssessmentEngine`).
- **Cloudflare Pages Context**: When frontend is hosted on Cloudflare Pages (`noosforge-soc.pages.dev`), API requests route through reverse proxy or CORS to the FastAPI backend. Authentication tokens must be valid JWTs to satisfy the backend gatekeeper.

---

## 4. Conclusion

The NOOSFORGE Security Intelligence frontend has established rich foundational interfaces (14 operational views, SVG charts, Liquid Glass styling, and batch scan orchestration), but exhibits 6 concrete architectural and operational gaps:
1. **Login & Session Management**: Login page is bypassed due to auto-seeding in `Shell.tsx`; Ultra Admin credentials are not synchronized with the backend.
2. **Auto-Scroll Behavior**: `scrollIntoView()` causes window-level viewport jumping; must be replaced by container-scoped `scrollTop` with default-disabled freeze toggle.
3. **Log & Reset Controls**: "Track by Days" is limited to scan queue; baseline reset should be centralized in `/settings` alongside system audit logs.
4. **Schedule Management**: Lacks schedule deletion and direct links to execution logs.
5. **Engine Health & Update UI**: Diagnostics matrix is static; lacks dynamic version detection, update checks, and engine self-test triggers.
6. **Notification Tracking**: Lacks mobile bell icon, polling/SSE synchronization, and persistent "Mark all read".

Detailed technical proposals and code references are compiled in `analysis.md`.

---

## 5. Verification Method

To independently verify these findings, execute the following commands and inspections:

1. **Verify Auto-Seeding & Double Shell Layout**:
   - Inspect `frontend/src/components/layout/Shell.tsx` lines 150–170 (`localStorage.setItem('sentinel_user', ...)`).
   - Inspect `frontend/src/app/layout.tsx` line 22 (`<Shell>{children}</Shell>` wrapping all routes without exception for `/login`).
2. **Verify Window Viewport Hijacking**:
   - Inspect `frontend/src/app/active-assessments/page.tsx` lines 316–321:
     `terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });`.
3. **Verify Static Diagnostics Matrix**:
   - Inspect `frontend/src/app/health/page.tsx` lines 122–146 to confirm static hardcoded component rows.
4. **Verify Backend Credentials & Token Auth**:
   - Run: `powershell -Command "Select-String -Path 'backend/app/core/config.py' -Pattern 'ADMIN_'"`
   - Inspect `backend/app/core/security.py` lines 74–88 (`get_current_user` checking `is_development`).
5. **Run Existing Frontend Quality Checks**:
   - In `frontend/`:
     - `npm run lint`
     - `npm run typecheck`
