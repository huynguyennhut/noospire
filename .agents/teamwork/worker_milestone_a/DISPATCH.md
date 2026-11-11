# Dispatch: Worker Milestone A (Safe Control Plane & Clean Deployment)

## Objective
Implement all code modifications and unit tests for Milestone A (Features F01–F16, Requirement R1, Gate A).

## Working Directory
`c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_milestone_a\`

## Mandatory References
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\ORIGINAL_REQUEST.md` (MUST read before starting work)
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\PROJECT.md` (Features F01–F16, Architecture, Contracts)
- `c:\Users\nguye\Desktop\noospire\.agents\teamwork\explorer_survey_1\handoff.md` (Detailed Survey 1 findings and line references)

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership Boundaries
You exclusively own:
- `backend/app/core/config.py`
- `backend/app/core/security.py`
- `backend/app/core/database.py`
- `backend/app/core/ssrf.py`
- `backend/app/core/target_verifier.py`
- `backend/app/core/empire_seeder.py`
- `backend/app/models/user.py`, `backend/app/models/proof.py`, `backend/app/models/scope.py`, `backend/app/models/asset.py`
- `backend/app/api/deps.py`, `backend/app/api/auth.py`, `backend/app/api/assets.py`, `backend/app/api/scans.py`, `backend/app/api/system.py`, `backend/app/api/settings.py`, `backend/app/api/reports.py`, `backend/app/api/findings.py`, `backend/app/api/rules.py`, `backend/app/api/baselines.py`, `backend/app/api/schedules.py`
- `backend/main.py` (clean minimal /health)
- `frontend/src/lib/api.ts`, `frontend/src/lib/scan-engine.ts`, `frontend/src/app/login/page.tsx`
- Unit/regression tests for Milestone A in `tests/test_milestone_a_control_plane.py`
DO NOT modify `tests/e2e/` (owned by E2E test writer).

## Features to Implement
1. F01: Eliminate hardcoded signing/admin/tunnel secrets, universal fallback passwords, synthetic superuser sessions, and accounts silently recreated or reset on boot. Require secrets via environment; fail fast in production if missing.
2. F02: Explicit one-time bootstrap (`POST /api/v1/auth/bootstrap` or CLI) locking permanently once initial admin is created.
3. F03: Active-user enforcement in DB, session expiry, token revocation/logout (`POST /api/v1/auth/logout`).
4. F04: Scoped RBAC (`admin`, `operator`, `viewer`) on all operational endpoints.
5. F05: Server-derived audit actors: bind triage/rule review/override actors to authenticated JWT subject, not client payload.
6. F06: Protect downloads (`/reports/{id}/download`) with same principal and scoping as report list.
7. F07: CSRF protection on mutations, secure cookie attributes (HttpOnly, Secure, SameSite=Lax).
8. F08: Remove destructive reset (`/system/reset`, `/settings/reset`) from production; store critical audit history in append-only tables outside reset path.
9. F09: Replace "reachable = verified" with `AssetOwnershipProof` (DNS TXT / HTTP challenge) and `AssetAssessmentScope` (origins, ports, allowed paths, methods, rate budgets).
10. F10: Target locator change automatically invalidates associated proof/grant.
11. F11: Strict network egress policy: socket IP binding, deny loopback/private/link-local/metadata (`169.254.169.254`, `metadata.google.internal`) in production, retain TLS/SNI.
12. F12: Reject unknown loop-test asset with HTTP 404 (eliminate fallback to first asset).
13. F13: Enforce configurable budgets (1 req/sec/origin, concurrency 1/origin, 100 req/asset/run), stop on kill switch or Retry-After.
14. F14: Clean first boot: no targets pre-verified, no active schedules, no invented successful runs.
15. F15: Distributable sanitization: purge stale reports from `storage/reports/`.
16. F16: Frontend honest error handling: remove silent fallbacks in `frontend/src/lib/api.ts`, remove fake timer simulation in `frontend/src/lib/scan-engine.ts`, remove fake JWT in `frontend/src/app/login/page.tsx`.

## Verification Instructions
1. Run pytest on existing test suite + new milestone A tests: `pytest tests/test_milestone_a_control_plane.py -v`.
2. Run frontend lint and build: `npm --prefix frontend run lint` and `npm --prefix frontend run build`.
3. Document all commands and results in `c:\Users\nguye\Desktop\noospire\.agents\teamwork\worker_milestone_a\handoff.md`.
Notify caller via `send_message` when done.

## 2026-11-10T05:55:23Z
**Context**: Milestone A Implementation & Progress Tracking
**Content**: Heartbeat check. Please update your `progress.md` with current status and let me know your current progress on Features F01–F16, test suite execution results, and when we can expect your completion handoff.
**Action**: Update `progress.md` and send a status update.
