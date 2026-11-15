# Worker M13 Remediation Dispatch

## Assigned Working Directory
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m13_fix

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objective
Remediate the specific issues identified by Reviewer 2 and Challenger 2 on Milestone 13 Frontend:

### Mandatory Remediation Tasks:
1. **Eliminate Mock Simulator**:
   In `frontend/src/app/checklist/page.tsx`:
   - Replace the `setTimeout` 1500ms block in `handleRunAllEvaluations` with genuine backend API invocation:
     `await api.createChecklistRun({ asset_id: selectedAssetId, mode: 'AUTOMATED' })`.
   - On success, reload the checklist run results via `api.getChecklistRunResults(run.id)` and update `resultsMap` and metrics dynamically.
   - On failure, show error toast without fabricated completion message.
2. **Wire Manual Review Persistence**:
   In `frontend/src/app/checklist/page.tsx`:
   - In `handleSaveReview`, call `await api.reviewChecklistResult(activeRunId, activeModalCheck.check_id, { status: modalSelectedState, review_notes: modalNotes.trim() })`.
   - Update `resultsMap` and `reviewNotesMap` from the API response so reviews persist across refreshes.
3. **Live Run Loading on Mount**:
   - In `useEffect` on page mount, call `api.getChecklistRuns()` to get the latest run for the active asset, then call `api.getChecklistRunResults(latestRun.id)` to populate `resultsMap`. Only fall back to empty/unrun state if no runs exist. Remove static `DEFAULT_INITIAL_RESULTS`.
4. **Fix White Text CSS Override**:
   - In `frontend/src/styles/globals.css`, remove or refine `.light .text-white { color: #18181B !important; }`. It causes white text inside `bg-rose-500 text-white` (like red badges, notifications, danger buttons) to become unreadable dark gray on red!
5. **Catalog Count Alignment (Exact 39 Checks)**:
   - In `frontend/src/app/checklist/page.tsx`: Ensure `EMPIRE_CHECKLIST_CATALOG` contains exactly 39 checks (WEB: 10, API: 10, FILE: 5, AUTH: 5, INFRA: 4, DEP: 5), matching `backend/app/core/checklist_seeder.py`.
   - Consolidate API-009 & API-011 so API has exactly 10 checks: `API-001` (BOLA), `API-002` (Broken Auth), `API-003` (Mass Assignment), `API-004` (Rate Limiting), `API-005` (BFLA), `API-006` (API SSRF), `API-007` (Gateway Misconfig), `API-008` (Automated Threats), `API-009` (Shadow APIs & Introspection), `API-010` (Third-Party APIs).
6. **NaN Guard on Metrics**:
   - In `automatedCoveragePct`, guard against division by zero:
     `const automatedCoveragePct = total > 0 ? Math.round((automatedCount / total) * 100) : 0;`
7. **Strict State Invariant in Modal**:
   - Enforce that transitioning from `NOT_RUN`, `BLOCKED`, or `ERROR` directly to `PASS` is forbidden in the UI modal (matching backend `validate_state_transition`).
8. **Verification**:
   - Run `npm run typecheck`, `npm run lint`, and `npm run build` in `frontend/`. Ensure 100% clean exit code 0.
   - Write handoff report to `handoff.md` and notify orchestrator via `send_message`.


## 2026-11-15T05:25:47Z
[Message] timestamp=2026-11-15T05:25:47Z sender=f5fb45da-8f40-4120-89d4-65f8ef960481 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_preview_worker_m13_fix (Agent C: Frontend Product / UX Engineer).
Your assigned working directory is:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m13_fix

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY: Read /home/nhut-nguyen/noospire/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read your full instructions and remediation tasks in:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m13_fix/DISPATCH.md
And reference Reviewer 2 and Challenger 2 feedback:
- /home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_reviewer_m11_m13_2/handoff.md
- /home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_challenger_m11_m13_2/handoff.md

Your scope:
1. Eliminate setTimeout mock simulator in `checklist/page.tsx` and wire up `api.createChecklistRun`.
2. Wire up `api.reviewChecklistResult` in `handleSaveReview`.
3. Load live runs on mount via `api.getChecklistRuns` and `api.getChecklistRunResults`.
4. Remove `.light .text-white { color: #18181B !important; }` in `globals.css`.
5. Align catalog to exactly 39 checks matching backend (consolidate API to 10 items).
6. Fix NaN in `automatedCoveragePct`.
7. Enforce strict invariant in review modal.
8. Verify with `npm run typecheck`, `npm run lint`, and `npm run build`.
Write complete handoff report to `handoff.md` and notify orchestrator via send_message.
