# Dispatch: Sub-Orchestrator Milestone A (Safe Control Plane & Clean Deployment)

## Objective
Orchestrate the complete implementation and verification of Milestone A (Requirement R1, Gate A, Features F01–F16) for Noospire.

## Working Directory
`c:\Users\nguye\Desktop\noospire\.agents\teamwork\sub_orch_milestone_a\`

## Reference Documents
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md` (authoritative)
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\PROJECT.md` (Feature Inventory, Architecture, Contracts)
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\explorer_survey_1\handoff.md` (Detailed Survey 1 findings)

## Scope (Features F01–F16)
1. F01: Eliminate hardcoded secrets (`SECRET_KEY`, admin/ultra admin credentials), fail in prod on missing secrets.
2. F02: One-time bootstrap mechanism permanently locking after initial admin setup.
3. F03: Active-user enforcement in DB, session revocation (`/api/v1/auth/logout`), token invalidation.
4. F04: Scoped RBAC permissions (`admin`, `operator`, `viewer`) across all operational endpoints.
5. F05: Server-derived audit actors (triage, rule reviews, baseline overrides).
6. F06: Protected report downloads (`/reports/{id}/download`) with same principal & scoping as report list.
7. F07: CSRF protection on mutations, secure cookie settings.
8. F08: Remove destructive reset endpoints (`/system/reset`, `/settings/reset`) in production; preserve audit history.
9. F09: Replace "reachable = verified" with `AssetOwnershipProof` (DNS/HTTP challenge) and `AssetAssessmentScope`.
10. F10: Target locator change invalidates associated proof/grant.
11. F11: Strict network egress policy: socket IP binding, deny private/loopback/link-local/metadata, retain TLS/SNI.
12. F12: Reject unknown loop-test asset with HTTP 404 (eliminate silent fallback).
13. F13: Enforce request/byte budgets, respect Retry-After & emergency stop.
14. F14: Clean first boot: no pre-verified targets, no active schedules, no invented completed scans.
15. F15: Distributable sanitization: purge stale reports from `storage/reports/`.
16. F16: Frontend error transparency: remove silent fallback in `api.ts`, remove fake timer in `scan-engine.ts`, remove fake JWT in `login/page.tsx`.

## Verification Gate A
All Gate A acceptance criteria must be satisfied and verified by tests:
- Clean deploy cannot contact a real target and cannot start with missing production secrets.
- Cannot grant anonymous operational access; all operational routes require auth and scoped permissions.
- Protected downloads require same principal and scoping as report list.
- Failed requests surfaced honestly in UI.
- Strict egress validation: unknown loop-test asset rejected with 404; private/loopback/link-local/metadata denied in production; CLI containers blocked from direct egress and arbitrary DNS.

## Workflow
Apply the Project Pattern procedure:
Decompose into subtasks or run the iteration loop (Explorer -> Worker -> Reviewer -> Challenger -> Auditor -> Gate).
When Gate A passes, write `handoff.md` in your working directory and notify the parent orchestrator via `send_message`.
