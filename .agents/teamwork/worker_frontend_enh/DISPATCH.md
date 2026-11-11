## 2026-11-09T19:27:50Z

You are the Frontend Implementation Worker in the NOOSFORGE Security Intelligence enhancement phase.
Your working directory: c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_frontend_enh\
You MUST read:
- c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md
- c:\Users\nguye\Desktop\noospire\PROJECT.md
- c:\Users\nguye\Desktop\noospire\.agents\teamwork\teamwork_explorer_enh_2\analysis.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

EXCLUSIVE WRITE OWNERSHIP:
You exclusively own and may modify:
- `frontend/src/`
DO NOT modify any files in `backend/` or `tests/`.

YOUR IMPLEMENTATION TASKS:
1. Login Page & Ultra Admin Authentication:
   - In `frontend/src/components/layout/Shell.tsx`:
     * Eliminate the auto-seeding bug on initial mount: Do not automatically write a dummy admin session to localStorage when no user is logged in.
     * When route is `/login`, render a clean unauthenticated layout without the main sidebar/topbar navigation.
     * Ensure logout (`handleLogout`) clears `sentinel_user` and `sentinel_jwt_token` and redirects cleanly to `/login` without re-seeding.
   - In `frontend/src/app/login/page.tsx`:
     * Support Ultra Admin credentials: `dangnhutnguyen0910@gmail.com` / `Hahanguyen09@`.
     * On login / One-Click Ultra Admin, call backend `POST /api/v1/auth/login` (via `api.login` in `frontend/src/lib/api.ts`), store the real token and user profile in `localStorage`, and redirect to `/dashboard`.
     * Display Ultra Admin role badge and dev tracking indicator.
2. Auto-scroll Control in Log Terminals ("Không auto scroll, check UI"):
   - In `frontend/src/app/active-assessments/page.tsx`:
     * Completely remove `terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' })` which was jumping the entire window viewport down every 2.5s!
     * Implement container-scoped scrolling using a ref on the scrollable terminal container (`terminalContainerRef.current.scrollTop = terminalContainerRef.current.scrollHeight`).
     * Set `autoScroll = false` by default (Logs Frozen by default).
     * Provide a clear, styled toggle switch / button ("Auto-scroll: ON / OFF") and an explicit "Scroll to Bottom" button so users have full control and can inspect logs comfortably without any jumps.
3. System Logs, Date Tracking & State Reset UI:
   - In `frontend/src/app/active-assessments/page.tsx` and `frontend/src/app/settings/page.tsx`:
     * Provide day filtering (1D, 7D, 14D, 30D, ALL), Export Logs (JSON/CSV), and Clear/Purge Logs wired to backend `api.ts`.
     * Connect "Quay Về Ban Đầu" (Reset to Baseline) to the backend reset endpoint (`POST /api/v1/system/reset`) with confirmation modal and toast notification.
4. Schedules UI:
   - In `frontend/src/app/schedules/page.tsx`:
     * Add "Delete Schedule" button wired to `api.deleteSchedule(id)`.
     * Add link / button to view logs of scheduled runs.
5. Engine Health & Updates UI:
   - In `frontend/src/app/health/page.tsx` (and `settings/page.tsx`):
     * Wire subsystem diagnostics to live dynamic data from `GET /api/v1/engines/health`.
     * Add "Test All Engines" button calling `POST /api/v1/engines/test`.
     * Add "Check Updates" button calling `POST /api/v1/engines/check-updates`.
6. Notifications Tracking:
   - In `frontend/src/components/layout/Shell.tsx`:
     * Add notification bell to the mobile header (`Shell.tsx:305-350`).
     * Wire "Mark all read" to backend `POST /api/v1/alerts/read-all`.
7. Build & Lint Verification:
   - In `frontend/`:
     * Run `npm run lint` and verify 0 errors, 0 warnings.
     * Run `npm run build` and verify all routes compile cleanly.
