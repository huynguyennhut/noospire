# Worker M12 Dispatch (Backend Scanners, Process Safety, 10-State Lifecycle & Reporting)

## Assigned Working Directory
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m12

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Objective
Implement Milestone 12 (Scanner Adapters, Process Safety, 10-State Lifecycle & Reporting):

## Detailed Implementation Requirements:
1. **R3: Standalone Process Safety Manager (`backend/app/core/process_safety.py`)**:
   - Create `backend/app/core/process_safety.py` containing `ProcessSafetyManager`.
   - Implement `get_safe_subprocess_kwargs()` providing POSIX process group isolation (`preexec_fn=os.setsid`), non-root execution checks, and OS resource limits via `resource.setrlimit` (`RLIMIT_AS` memory limits, `RLIMIT_CPU` cpu time limits, `RLIMIT_NOFILE`).
   - Implement `terminate_process_tree(scan_id, timeout=3.0)` terminating all child and descendant processes recursively via `psutil` within 3 seconds, killing any stubborn processes with `SIGKILL`.
   - Wire `ProcessSafetyManager` into `backend/app/core/dispatcher.py` and scanner adapters.
2. **R3: Scanner Adapter Framework & Unified Finding Schema**:
   - In `backend/app/scanners/base.py`, `nuclei.py`, `zap.py`, `trivy.py`:
     - Ensure structured argument arrays with `shell=False`.
     - Register spawned PIDs in `ProcessSafetyManager`.
     - Standardize findings into `NormalizedFindingCreate` with deterministic SHA-256 fingerprinting.
     - Fallback cleanly to embedded lab runners (`NucleiLabRunner`, `ZAPLabRunner`, `TrivyLabRunner`) when binaries are absent.
3. **R5: Canonical 10-State Finding Lifecycle**:
   - In `backend/app/schemas/common.py`:
     - Update `FindingStatus` enum to exactly the 10 canonical states:
       `NEW`, `NEEDS_TRIAGE`, `CONFIRMED`, `FALSE_POSITIVE`, `ACCEPTED_RISK`, `ASSIGNED`, `IN_PROGRESS`, `FIXED_PENDING_RETEST`, `RESOLVED`, `REOPENED`.
     - Add backward-compatibility alias mapping for legacy state names.
   - In `backend/app/api/findings.py`:
     - Ensure `POST /findings/{id}/triage` supports the 10 canonical states.
     - Append immutable `FindingChange` records to audit trail.
     - Redact secrets (Bearer tokens, cookies, passwords, JWTs) from evidence.
     - Ensure `POST /findings/{id}/retest` triggers affirmative rule rechecks.
4. **R6 / R5 Reporting: Honest Coverage Gap Disclosure & Dual-Theme Exports**:
   - In `backend/app/reporting/generator.py` and `backend/app/reporting/pdf_builder.py`:
     - Incorporate an explicit "Coverage Gaps & Exclusions" section detailing targets or checks that could not be executed or failed.
     - Add support for Warm Light theme CSS styling in `backend/app/reporting/templates/html_report.jinja2`.
     - Ensure PDF, HTML, and JSON reports export with honest coverage metrics.
5. **Testing & Verification**:
   - Create unit tests in `tests/test_process_safety.py` and `tests/test_finding_lifecycle.py`.
   - Run tests via pytest and verify 100% pass.
   - Write handoff report to `handoff.md` and notify orchestrator via `send_message`.


## 2026-11-15T05:25:47Z
[Message] timestamp=2026-11-15T05:25:47Z sender=f5fb45da-8f40-4120-89d4-65f8ef960481 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_preview_worker_m12 (Agent B: Backend / Scanner / Data Engineer).
Your assigned working directory is:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m12

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY: Read /home/nhut-nguyen/noospire/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read your full instructions and file boundaries in:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_worker_m12/DISPATCH.md
And reference Explorer 2 report:
/home/nhut-nguyen/noospire/.agents/teamwork/teamwork_preview_explorer_survey_2/handoff.md

Your scope:
1. Create standalone `backend/app/core/process_safety.py` with `os.setsid`, resource limits, non-root execution, and < 3s tree termination via psutil.
2. Ensure scanner adapters (`nuclei.py`, `zap.py`, `trivy.py`) use `process_safety` and structured argument arrays (`shell=False`).
3. Update `backend/app/schemas/common.py` to canonical 10 states: `NEW`, `NEEDS_TRIAGE`, `CONFIRMED`, `FALSE_POSITIVE`, `ACCEPTED_RISK`, `ASSIGNED`, `IN_PROGRESS`, `FIXED_PENDING_RETEST`, `RESOLVED`, `REOPENED`.
4. Ensure `POST /findings/{id}/triage` supports the 10 states and records audit changes.
5. In `backend/app/reporting/generator.py` and `pdf_builder.py`, add explicit "Coverage Gaps & Exclusions" section and Warm Light styling in HTML template.
6. Write tests in `tests/test_process_safety.py` and `tests/test_finding_lifecycle.py`, run pytest and verify 100% pass.
Write complete handoff report to `handoff.md` and notify orchestrator via send_message.
