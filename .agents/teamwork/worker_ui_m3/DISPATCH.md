# DISPATCH — AGENT 3 (UI and Product Experience) — Milestone M3

You are worker_ui_m3 (teamwork_worker).
Your working directory is: c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_ui_m3
Original request file: c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md
Project specification: c:\Users\nguye\Desktop\noospire\PROJECT.md

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope & Assigned Files (Exclusive Write Ownership):
- `frontend/src/` (all frontend source files)
- `frontend/tailwind.config.js`
- `frontend/src/styles/globals.css`

Key Deliverables:
1. 14 Navigation Views & Sidebar Completeness (R4):
   - Update `frontend/src/components/layout/Shell.tsx` to include all 14 navigation views in `NAVIGATION_ITEMS`. Specifically, ensure `/detection-rules` (Detection Rules) is included with an appropriate icon and label.
2. Black/White/Liquid Glass Design System (R4):
   - Enhance `frontend/tailwind.config.js` and `frontend/src/styles/globals.css` with the Black/White/Liquid Glass styling tokens: frosted glass backdrop blur (`backdrop-blur-md` / `backdrop-blur-xl`), semi-transparent surfaces (`rgba(255, 255, 255, 0.03)` / `rgba(0, 0, 0, 0.6)`), crisp specular borders (`border-white/10`, `hover:border-white/20`), glass card shadows, and glow accents.
   - Apply liquid glass card styling to key card components across the views.
3. Bilingual Internationalization (VI/EN) (R4):
   - Implement `frontend/src/lib/i18n.tsx` providing a React context (`I18nProvider`), `useI18n()` hook, and comprehensive translation dictionaries for both Vietnamese (`vi`) and English (`en`), with Vietnamese as default!
   - Add a sleek language switcher toggle (VI / EN) in `Shell.tsx` header.
   - Wire internationalization across all navigation views so titles, buttons, tabs, tables, and statuses are translated.
4. Target Verification UI Modal & Evidence Viewer (R1, R2, R3):
   - In `frontend/src/app/assets/page.tsx`, implement an interactive 8-step live target verification modal showing real-time step progress (DNS, TLS, HTTP, Redirects, Discovery, Fingerprint, Result).
   - In `frontend/src/app/findings/page.tsx`, replace the raw `<pre>` JSON dump with an interactive tabbed Evidence Viewer (Request, Response, Headers, Proof/Matched Content, Replay cURL).
   - In `frontend/src/app/active-assessments/page.tsx`, ensure live scan tracking connects to `/api/v1/scans/{scan_id}/logs/stream` via SSE (with fallback polling).
5. Build Verification:
   - Ensure `npm run typecheck` and `npm run build` pass cleanly inside `frontend/` with 0 errors!

Write your report to c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_ui_m3\report.md and create a self-contained handoff report at c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_ui_m3\handoff.md.

## 2026-11-08T12:49:29Z
You are worker_ui_m3 (AGENT 3 UI and Product Experience).
Your working directory is: c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_ui_m3
Original request file: c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md
Project specification: c:\Users\nguye\Desktop\noospire\PROJECT.md
Dispatch details: c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_ui_m3\DISPATCH.md
