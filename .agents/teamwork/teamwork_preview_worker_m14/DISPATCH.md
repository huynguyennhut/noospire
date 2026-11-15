# Worker M14 Dispatch (Documentation Package & Verification Hardening)

## Assigned Working Directory
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m14

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objective
Author the complete 8-document Empire Documentation Package and harden `scripts/verify_empire_e2e.py`:

## Detailed Implementation Requirements:
1. **Empire Documentation Package (8 Root Markdown Files)**:
   Author comprehensive, professional, production-grade documentation files at the project root `/home/nhut-nguyen/noospire/`:
   - **`EMPIRE_PENTEST_SCOPE.md`**: Target domains (`https://empire.edu.vn/`), subdomains, CIDRs, allowed ports (80, 443), path constraints, rate limits (rps, concurrency, byte budget), out-of-scope boundaries, emergency stop procedures, and authorization sign-offs.
   - **`EMPIRE_PENTEST_CHECKLIST.md`**: Full versioned catalog of all 39 Empire checks across 6 categories (WEB-001..010, API-001..010, FILE-001..005, AUTH-001..005, INFRA-001..004, DEP-001..005) with bilingual VI/EN titles, descriptions, severities, automation types, and invariant rules (never convert unrun/blocked/error to PASS).
   - **`EMPIRE_TOOL_COVERAGE_MATRIX.md`**: Detailed mapping of each of the 39 checks to detection tools (OWASP ZAP, Nuclei, Trivy, Empire Engine, Synthetic Harness, File Policy Engine), execution parameters (`shell=False`), and coverage classification.
   - **`EMPIRE_ASSESSMENT_WORKFLOW.md`**: End-to-end operational workflow: target onboarding -> immutable scope gate -> preflight validation -> scan dispatch -> live telemetry monitor -> 10-state triage lifecycle -> targeted retesting -> report export.
   - **`EMPIRE_TEST_ACCOUNT_SETUP.md`**: Synthetic identity provisioning for BOLA/BFLA testing (`SyntheticIdentity`), credential seeding, canary tokens, and safety bounds.
   - **`EMPIRE_REPORT_METHODOLOGY.md`**: Risk scoring methodology ($SRS$), calculation formulas for automated coverage and manual review completion, honest coverage gap disclosure, and dual-theme reporting (Obsidian Dark & Warm Invert Light).
   - **`EMPIRE_DEPLOYMENT_RUNBOOK.md`**: Installation, Docker deployment, non-root execution, resource limits, environment variables, SQLite/PostgreSQL configuration, backup, and rollback runbook.
   - **`EMPIRE_ACCEPTANCE_REPORT.md`**: Formal acceptance ledger documenting complete satisfaction of R1 through R6, gate verification results, and operational handover.
2. **Harden `scripts/verify_empire_e2e.py`**:
   - Fix Step 2 authentication: Mint an owner access token via `create_access_token(subject=settings.SOLE_OWNER_ACCOUNT_ID, role="OWNER")` and attach `Authorization: Bearer <token>` to client requests.
   - Ensure `SEED_DEMO_DATA=true` is set when running the verification script so the 7 Empire demo assets and policies are loaded.
   - Execute `scripts/verify_empire_e2e.py` and verify all checks pass 100%.
3. **Report**:
   - Write handoff report to `handoff.md` and notify orchestrator via `send_message`.


## 2026-11-15T05:25:47Z
[Message] timestamp=2026-11-15T05:25:47Z sender=f5fb45da-8f40-4120-89d4-65f8ef960481 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_preview_worker_m14 (Documentation & E2E Hardening).
Your assigned working directory is:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m14

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY: Read /home/nhut-nguyen/noospire/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read your full instructions and file boundaries in:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m14/DISPATCH.md

Your scope:
1. Author the 8 root documentation files:
   - `EMPIRE_PENTEST_SCOPE.md`
   - `EMPIRE_PENTEST_CHECKLIST.md`
   - `EMPIRE_TOOL_COVERAGE_MATRIX.md`
   - `EMPIRE_ASSESSMENT_WORKFLOW.md`
   - `EMPIRE_TEST_ACCOUNT_SETUP.md`
   - `EMPIRE_REPORT_METHODOLOGY.md`
   - `EMPIRE_DEPLOYMENT_RUNBOOK.md`
   - `EMPIRE_ACCEPTANCE_REPORT.md`
2. Fix authentication in `scripts/verify_empire_e2e.py` by minting an owner token (`create_access_token(subject=settings.SOLE_OWNER_ACCOUNT_ID, role="OWNER")`) and passing `Authorization: Bearer <token>`, and ensure demo seeding is enabled.
3. Execute `scripts/verify_empire_e2e.py` and verify all checks pass 100%.
Write complete handoff report to `handoff.md` and notify orchestrator via send_message.
