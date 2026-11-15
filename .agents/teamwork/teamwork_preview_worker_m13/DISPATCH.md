# Worker M13 Dispatch (Agent C - Frontend Product / UX Engineer)

## Assigned Working Directory
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m13

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Milestone Objective
Implement Milestone 13: Dual Theme (Dark Obsidian & Warm Invert Light) Liquid Glass UI & Checklist Experience (Agent C / Frontend).

## Reference Files to Read
- MANDATORY: `/home/nhut-nguyen/noospire/.agents/teamwork/ORIGINAL_REQUEST.md`
- Scope Document: `/home/nhut-nguyen/noospire/PROJECT.md`
- Survey 3 Explorer Report: `/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_explorer_survey_3/handoff.md`

## Write Ownership (Exclusively owned by Worker M13)
- `frontend/src/styles/globals.css`
- `frontend/src/providers/ThemeProvider.tsx`
- `frontend/src/components/ThemeToggle.tsx` (or inside `components/layout/`)
- `frontend/src/components/layout/Shell.tsx`
- `frontend/src/app/checklist/page.tsx`
- `frontend/src/app/settings/page.tsx`
- `frontend/src/lib/i18n.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/types.ts`
- `frontend/src/app/layout.tsx`

## Detailed Implementation Requirements
1. **R6: Dual Theme Liquid Glass System (Dark Obsidian & Warm Invert Light)**:
   - In `frontend/src/styles/globals.css`:
     - Maintain `:root` / `.dark` as the Dark Obsidian palette (`--bg-primary: #09090B`, `--bg-surface: #0C0C0E`, white specular highlights, cyan accents).
     - Add `.theme-warm`, `[data-theme='warm']`, and `.light` with the requested Warm Invert Light theme tokens:
       - `--bg-primary: #FAF8F5` (warm cream/linen)
       - `--bg-surface: #FFFFFF` (clean white card surface)
       - `--bg-surface-hover: #F4EFEA`
       - `--border-subtle: rgba(0, 0, 0, 0.08)`
       - `--border-strong: rgba(0, 0, 0, 0.16)`
       - `--text-primary: #18181B`
       - `--text-secondary: #52525B`
       - `--text-muted: #71717A`
       - Warm specular highlights and refined frosted glass borders for `.liquid-glass`, `.liquid-glass-card`, `.liquid-glass-modal`.
   - Create `frontend/src/providers/ThemeProvider.tsx`:
     - Manages active theme: `'obsidian-dark'` (default) vs `'warm-light'`.
     - Persists selection to `localStorage`.
     - Synchronizes `document.documentElement.classList` (`dark` vs `light theme-warm`) and `data-theme` attribute.
     - Provides `useTheme()` hook: `{ theme, setTheme, toggleTheme, isDark }`.
   - Update `frontend/src/app/layout.tsx` to wrap children in `ThemeProvider`.
   - Create theme toggle control in `frontend/src/components/layout/Shell.tsx`:
     - Position alongside the language switcher (`VI / EN`).
     - Includes icon (`Sun` / `Moon`), tooltip, and bilingual labels (`Giao diện: Sáng (Ấm) / Theme: Invert (Light) / Light Theme: Warm`).
   - In `frontend/src/app/settings/page.tsx`:
     - Add a "Giao diện & Chủ đề / Theme & Appearance" preference card with theme previews and radio/switch buttons.
   - In `frontend/src/lib/i18n.tsx`:
     - Add bilingual translations for all theme names and checklist UI terms.
2. **R1 / R6: Empire Pentest Checklist View**:
   - Create `frontend/src/app/checklist/page.tsx`:
     - Navigation item in `Shell.tsx` (`/checklist` with icon `ClipboardCheck` or `ShieldCheck`).
     - Displays all 39 checklist definitions grouped by the 6 categories (WEB, API, FILE, AUTH, INFRA, DEP).
     - Summary KPI cards at top: Total Checks (39), Automated Coverage %, Manual Review Completion %, State Counters (PASS, FAIL, NEEDS_REVIEW, NOT_APPLICABLE, BLOCKED, NOT_RUN, ERROR).
     - Filter tabs by category, search bar, and state badge indicators.
     - Modal / drawer showing detailed check metadata: Check ID, Bilingual Title & Description, Severity, Automation Type, Target Engine, and Remediation Guidance.
   - Update `frontend/src/lib/api.ts` and `frontend/src/lib/types.ts` to include checklist endpoints:
     - `getChecklistDefinitions()`, `getChecklistRuns()`, `getChecklistRunResults(id)`.
3. **Frontend Build Verification**:
   - Note: If `frontend/node_modules/` is missing in the local workspace, check if `/home/nhut-nguyen/Desktop/noosforge-sec/frontend/node_modules/` exists and symlink it, or run `npm install --prefer-offline` / `npm run build` / `npm run lint`.
   - Ensure `npm run lint` and `tsc --noEmit` succeed cleanly with zero errors.


## 2026-11-15T04:54:33Z
[Message] timestamp=2026-11-15T04:54:33Z sender=f5fb45da-8f40-4120-89d4-65f8ef960481 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_preview_worker_m13 (Agent C: Frontend Product / UX Engineer).
Your assigned working directory is:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m13

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY: Read /home/nhut-nguyen/noospire/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read your full instructions and write ownership boundaries in:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m13/DISPATCH.md
And reference Explorer 3 report in:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_explorer_survey_3/handoff.md

Your scope:
- R6: Dual Theme Liquid Glass UI system: Dark Obsidian + Warm Invert Light (`Theme: Invert (Light) / Light Theme: Warm`) in `frontend/src/styles/globals.css`, `frontend/src/providers/ThemeProvider.tsx`, theme toggle in `frontend/src/components/layout/Shell.tsx` and `frontend/src/app/settings/page.tsx`, bilingual keys in `frontend/src/lib/i18n.tsx`.
- R1/R6: New checklist catalog and assessment view in `frontend/src/app/checklist/page.tsx` with all 39 checks, categories, status badges, automated coverage vs manual review completion cards; updated `api.ts` and `types.ts`.
- Ensure node_modules are properly linked if needed, and run `npm run lint` / `tsc --noEmit` to verify 100% clean build.
Write your complete handoff report to:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m13/handoff.md
When done, notify orchestrator via send_message.
