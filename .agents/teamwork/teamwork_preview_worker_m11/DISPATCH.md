# Worker M11 Dispatch

## Assigned Working Directory
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m11

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Milestone Objective
Implement Milestone 11: Checklist Catalog, Scope Gate & Synthetic Test Harness (Agent B / Backend).

## Reference Files to Read
- MANDATORY: `/home/nhut-nguyen/noospire/.agents/teamwork/ORIGINAL_REQUEST.md`
- Scope Document: `/home/nhut-nguyen/noospire/PROJECT.md`
- Survey 1 Explorer Report: `/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_explorer_survey_1/handoff.md`

## Detailed Implementation Requirements
1. **R1: Empire Pentest Checklist Catalog & Result Engine Data Model**:
   - Create `backend/app/models/checklist.py`:
     - Enum `ChecklistCategory`: `WEB`, `API`, `FILE`, `AUTH`, `INFRA`, `DEP`.
     - Enum `ChecklistResultState`: `PASS`, `FAIL`, `NEEDS_REVIEW`, `NOT_APPLICABLE`, `BLOCKED`, `NOT_RUN`, `ERROR`.
     - Invariant rule: Never convert unrun, blocked, or error states to PASS.
     - `ChecklistDefinition` model: `check_id` (e.g. WEB-001..010, API-001..011, FILE-001..005, AUTH-001..005, INFRA-001..004, DEP-001..005), `category`, `title_vi`, `title_en`, `description_vi`, `description_en`, `severity`, `automation_type` (`AUTOMATED`, `MANUAL`, `HYBRID`), `target_engine` (`ZAP`, `NUCLEI`, `TRIVY`, `EMPIRE_ENGINE`, `SYNTHETIC_HARNESS`, `FILE_POLICY`), `remediation_guidance_vi`, `remediation_guidance_en`.
     - `ChecklistAssessmentRun` model: `id`, `asset_id`, `created_at`, `completed_at`, `status`, `total_checks`, `automated_coverage_pct`, `manual_completion_pct`, `state_counts` (JSON).
     - `ChecklistResult` model: immutable check execution record with `run_id`, `check_id`, `state`, `evidence_payload` (JSON), `execution_duration_ms`, `evaluated_at`.
   - Create `backend/app/schemas/checklist.py` with Pydantic V2 schemas.
   - Create seeder `backend/app/core/checklist_seeder.py` seeding all 39 Empire check definitions with accurate Vietnamese and English metadata, and wire it into database initialization (`init_db()` in `backend/app/core/database.py`).
2. **R2: Customer Scope & Authorization Gate**:
   - In `backend/app/models/scope.py`, ensure `AssetAssessmentScope` fields support rate limits, request budgets, and byte budgets.
   - Create `backend/app/core/scope_gate.py`:
     - `ScopeValidator.validate_preflight(asset_id, requested_checks)`: Immutable backend gate. Must verify that an active, unexpired `AssetAssessmentScope` exists. Reject ungranted scans with HTTP 403 / `ScopeEnforcementError`. Block private IPs, loopbacks, and cloud metadata unless authorized. Block active/destructive probes by default unless verified.
     - Budget and rate limit tracking (`check_rate_and_budget`).
   - Add granular emergency stop endpoints in `backend/app/api/assets.py` or `backend/app/api/scope.py`:
     - `POST /api/v1/assets/{id}/emergency-stop`: Immediately toggles `emergency_stop_active=True` and terminates all active scanner processes for the asset in < 3s.
3. **R4: Custom Synthetic Test Harness & File Policy Engine**:
   - Create `backend/app/scanners/synthetic_harness.py`:
     - Dedicated test harness for API authorization (BOLA/IDOR on `API-001`, BFLA on `API-005`).
     - Queries `SyntheticIdentity` from the database.
     - If test account credentials are missing/inactive, marks checks `BLOCKED` (never `PASS`, never `NOT_APPLICABLE`).
     - When credentials are present, executes safe authorization probes and records evidence.
   - Create `backend/app/scanners/file_policy.py`:
     - Policy engine for `/media` `PUBLIC_BY_DESIGN` policy.
     - Approved public educational materials evaluate to `PASS` on `FILE-001`.
     - Unauthorized private leaks (CSV, .env, backups, keys) evaluate to `FAIL` on `FILE-002`.
4. **API Router**:
   - Create `backend/app/api/checklist.py` with endpoints:
     - `GET /api/v1/checklist/definitions`
     - `GET /api/v1/checklist/runs`
     - `POST /api/v1/checklist/runs` (launches or evaluates checklist)
     - `GET /api/v1/checklist/runs/{id}/results`
     - `GET /api/v1/checklist/runs/{id}/metrics` (honest automated coverage % and manual review completion %)
   - Mount router in `backend/main.py`.
5. **Tests & Verification**:
   - Create automated tests in `tests/test_checklist_catalog.py` and `tests/test_scope_gate.py` verifying all 39 checks, 7 states, invariants, scope rejection, and emergency stop.
   - Run tests and verify 100% pass.
   - Report test commands and outputs in your handoff report.


## 2026-11-15T04:54:33Z
You are teamwork_preview_worker_m11 (Agent B: Backend / Scanner / Data Engineer).
Your assigned working directory is:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m11

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY: Read /home/nhut-nguyen/noospire/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read your full instructions and file boundaries in:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m11/DISPATCH.md
And reference Explorer 1 report in:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_explorer_survey_1/handoff.md

Your scope:
- R1: Checklist catalog & 7-state result engine models (`backend/app/models/checklist.py`), Pydantic schemas (`backend/app/schemas/checklist.py`), seeder for all 39 Empire checks across 6 categories (`backend/app/core/checklist_seeder.py`).
- R2: Immutable scope authorization gate (`backend/app/core/scope_gate.py`), preflight validation, rate limits, request budgets, and 4-tier emergency stop (< 3s).
- R4: Custom synthetic test harness for BOLA/BFLA (`backend/app/scanners/synthetic_harness.py`), `/media` `PUBLIC_BY_DESIGN` file policy engine (`backend/app/scanners/file_policy.py`).
- API routes in `backend/app/api/checklist.py` and mount in `backend/main.py`.
- Write unit tests in `tests/test_checklist_catalog.py` and `tests/test_scope_gate.py`.
Run tests and report results.
Write your complete handoff report to:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m11/handoff.md
When done, notify orchestrator via send_message.
