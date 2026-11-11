# BRIEFING — 2026-11-10T08:21:00Z

## Mission
Formulate the exact, concrete implementation plan with line-by-line fix proposals for Milestone 1 frontend incident fixes (`frontend/src/lib/api.ts`, `frontend/src/lib/scan-engine.ts`, `frontend/src/app/login/page.tsx`, and asset pagination).

## 🔒 My Identity
- Archetype: explorer
- Roles: frontend investigator, incident fix planner
- Working directory: c:\Users\nguye\Desktop\noospire\.agents\teamwork\m1_explorer_1
- Original parent: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb
- Milestone: Milestone 1 (Frontend Incident Fix Strategy)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement changes in source code directly
- Formulate concrete line-by-line diff proposals and exact logic in handoff.md
- Ensure 503 / 200 SPA HTML errors surface explicitly with zero fake data, fake IDs, or fake findings
- Remove client-side simulation completely
- Ensure real server job IDs and multi-tab/multi-browser recovery via tracker redirect

## Current Parent
- Conversation ID: eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb
- Updated: 2026-11-10T08:21:00Z

## Investigation State
- **Explored paths**:
  - `frontend/src/lib/api.ts` (lines 1-1251)
  - `frontend/src/lib/scan-engine.ts` (lines 1-548)
  - `frontend/src/app/login/page.tsx` (lines 1-225)
  - `frontend/src/app/assets/page.tsx` (lines 1-2282)
  - `frontend/src/app/empire-modules/page.tsx` (lines 1-204)
  - `frontend/src/app/scans/page.tsx` (lines 1-300)
  - `frontend/src/app/active-assessments/page.tsx` (lines 1-370)
  - `backend/app/api/assets.py` (lines 1-110)
  - `backend/app/api/scans.py` (lines 95-155, 440-540)
- **Key findings**:
  - `api.ts`: Contains ~750 lines of dead/fallback simulator logic in `handleFallback`. `fetchJson` lacks content-type validation, causing 200 SPA HTML responses to throw unhelpful SyntaxErrors or be masked. `listAssets` lacks query parameter mapping for pagination/filtering.
  - `scan-engine.ts`: Generates fake scan IDs, fake logs, fake findings, and stores state in localStorage. Must be decoupled from `api.ts`.
  - `login/page.tsx`: Contains premature "ULTRA ADMIN / ACTIVE (SOVEREIGN)" indicator and default placeholder hints. Real error display needs transparent server message rendering.
  - Asset pagination / filtering: `assets/page.tsx` ignores `searchParams` on initial load (defaults `moduleFilter` to `'ALL'`), dropping the `?empire_module=` filter passed from `empire-modules/page.tsx`. `api.listAssets()` defaults to `size=100`, hiding 279 of 379 inventory targets.
- **Unexplored areas**: None for M1 frontend scope. Ready to formulate final handoff report.

## Key Decisions Made
- Formulate exact replacement code for `fetchJson` with content-type checking and detailed error generation.
- Eliminate `handleFallback` and decouple `api.ts` from `scan-engine.ts` and `fallback-data.ts`.
- Update `api.listAssets` signature to accept typed parameters (`page`, `size`, `empire_module`, `asset_type`, `environment`, `verification_status`, `search`).
- Update `assets/page.tsx` to read `useSearchParams()` on initial load and keep `moduleFilter` in sync with URL.
- Update `login/page.tsx` to remove misleading badges, neutral placeholders, and direct error display.

## Artifact Index
- `DISPATCH.md` — Inbound instructions from orchestrator
- `progress.md` — Liveness and status heartbeat
- `BRIEFING.md` — Situational awareness and working memory
- `handoff.md` — Final structured report and concrete fix proposal
