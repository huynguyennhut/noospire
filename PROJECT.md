# Project: NOOSFORGE Security Intelligence — Enterprise Cybersecurity SaaS Platform

## Architecture
NOOSFORGE Security Intelligence is a production-grade, enterprise cybersecurity SaaS platform and command center for the Empire Education Platform (`https://empire.edu.vn/`).

The architecture comprises:
- **Checklist Catalog & Result Engine**: Versioned checklist catalog containing 39 check definitions across 6 categories (Web WEB-001..010, API API-001..011, Files & Learning Materials FILE-001..005, Auth AUTH-001..005, Public Infra INFRA-001..004, Dependencies & Containers DEP-001..005). Immutable 7-state results (`PASS`, `FAIL`, `NEEDS_REVIEW`, `NOT_APPLICABLE`, `BLOCKED`, `NOT_RUN`, `ERROR`) with strict state invariants (never convert unrun/blocked/error to PASS), bilingual Vietnamese/English metadata, and honest coverage metrics.
- **Customer Scope & Authorization Gate**: Immutable backend gate requiring active, unexpired `AssetAssessmentScope` records before probe dispatch. Preflight validation verifying exact origin, ports, permitted checks, rate limits, request budgets, and byte budgets. SSRF protection blocking RFC 1918, loopbacks, and cloud metadata. 4-tier emergency stop (< 3s) at Platform, Batch, Target, and Worker levels.
- **Scanner Adapter Framework & Process Isolation**: Real scanner engine integrations (Nuclei CLI v3.11.1, OWASP ZAP, Trivy, Empire custom business checks) executing with structured argument arrays (`shell=False`), process group isolation (`os.setsid`), non-root execution, resource limits (`RLIMIT_AS`, `RLIMIT_CPU`, `RLIMIT_NOFILE`), complete process-tree termination, and normalized finding schema.
- **Custom Synthetic Test Harness & File Policy Engine**: API authorization testing (BOLA/IDOR, BFLA) using authenticated `SyntheticIdentity` test accounts (marking checks `BLOCKED` when credentials missing). File policy engine enforcing `/media` `PUBLIC_BY_DESIGN` baseline (evaluating legitimate public educational media to PASS and sensitive leaks to FAIL).
- **Live Assessment Monitor, Triage & Remediation Lifecycle**: Multi-worker concurrency telemetry HUD (`trackcurrent`), real-time SSE event streaming (`/scans/{id}/events/stream`) with Last-Event-ID replay and fallback polling, canonical 10-state finding lifecycle (`NEW`, `NEEDS_TRIAGE`, `CONFIRMED`, `FALSE_POSITIVE`, `ACCEPTED_RISK`, `ASSIGNED`, `IN_PROGRESS`, `FIXED_PENDING_RETEST`, `RESOLVED`, `REOPENED`), secret redaction, and targeted retesting.
- **Dual-Theme Liquid Glass UI & Reporting**: Next.js 14 App Router, TypeScript, Tailwind CSS, featuring the Black/White/Liquid Glass design system with seamless switching between Obsidian Dark Mode and Warm Invert Light Theme (`Theme: Invert (Light) / Light Theme: Warm`), bilingual VI/EN dictionary, checklist management view, interactive forensic evidence viewer, and ReportLab vector PDF, Jinja2 HTML, and JSON reports with honest coverage gap disclosure.
- **Documentation & Verification Suite**: Complete 8-document Empire documentation package (`EMPIRE_*.md`), end-to-end verification script (`scripts/verify_empire_e2e.py`), automated pytest suite, TypeScript compilation, and ESLint validation.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Empire Pentest Checklist Catalog | 39 check definitions across 6 categories (WEB-001..010, API-001..011, FILE-001..005, AUTH-001..005, INFRA-001..004, DEP-001..005) with bilingual VI/EN metadata | M11 | R1 |
| 2 | Immutable 7-State Result Engine | Check results stored as immutable records with strict 7 states (`PASS`, `FAIL`, `NEEDS_REVIEW`, `NOT_APPLICABLE`, `BLOCKED`, `NOT_RUN`, `ERROR`) and state invariant guards | M11 | R1 |
| 3 | Honest Coverage & Review Formulas | Automated coverage % and manual review completion % computed without score fabrication | M11 | R1 |
| 4 | Immutable Scope Authorization Gate | Preflight validation requiring active unexpired scope record; blocks ungranted scans by default | M11 | R2 |
| 5 | Network & SSRF Boundaries | Rejects unauthorized targets, private IPs without approval, and loopback/cloud metadata | M11 | R2 |
| 6 | 4-Tier Emergency Stop | Platform, Batch, Target, and Worker level emergency stop terminating scanner processes in < 3s | M11 | R2 |
| 7 | Synthetic Identity Test Harness | BOLA/BFLA test harness using `SyntheticIdentity` credentials, marking checks `BLOCKED` when missing | M11 | R4 |
| 8 | Public by Design File Policy Engine | `/media` policy engine evaluating educational media to `PASS` and unauthorized sensitive leaks to `FAIL` | M11 | R4 |
| 9 | Standalone Process Safety Manager | Extracted `process_safety.py` with process groups (`os.setsid`), non-root user execution, and resource limits (`RLIMIT_AS`, `RLIMIT_CPU`) | M12 | R3 |
| 10 | Scanner Adapter Framework & Normalization | Real adapters for OWASP ZAP, Nuclei, and Trivy with structured argument arrays (`shell=False`) and normalized finding output | M12 | R3 |
| 11 | Canonical 10-State Finding Lifecycle | Exact 10 states (`NEW`, `NEEDS_TRIAGE`, `CONFIRMED`, `FALSE_POSITIVE`, `ACCEPTED_RISK`, `ASSIGNED`, `IN_PROGRESS`, `FIXED_PENDING_RETEST`, `RESOLVED`, `REOPENED`) with immutable audit trail | M12 | R5 |
| 12 | Secret Redaction & Targeted Retesting | Multi-pattern secret redaction and affirmative defensive retesting pipeline | M12 | R5 |
| 13 | Reporting Engine & Coverage Gap Disclosure | ReportLab vector PDF, Jinja2 HTML, and JSON reports with honest coverage gaps & exclusions disclosure and Warm Light theme support | M12 | R6 |
| 14 | Dual-Theme Liquid Glass UI Tokens | CSS variables and Tailwind tokens supporting Obsidian Dark and Warm Invert Light (`Theme: Invert (Light) / Light Theme: Warm`) | M13 | R6 |
| 15 | Theme Switcher & Bilingual Persistence | Navigation bar theme toggle in `Shell.tsx`, `ThemeProvider` with localStorage persistence, and bilingual keys | M13 | R6 |
| 16 | Checklist Catalog & Assessment View | Dedicated frontend view `/checklist` for browsing check definitions, execution runs, and coverage statistics | M13 | R1, R6 |
| 17 | Live Assessment Monitor & Triage Polish | Real-time telemetry HUD (`trackcurrent`), SSE stream with Last-Event-ID replay, and triage drawer integration with dual themes | M13 | R5, R6 |
| 18 | Empire Documentation Package | Complete 8 markdown files (`EMPIRE_PENTEST_SCOPE.md`, `EMPIRE_PENTEST_CHECKLIST.md`, `EMPIRE_TOOL_COVERAGE_MATRIX.md`, `EMPIRE_ASSESSMENT_WORKFLOW.md`, `EMPIRE_TEST_ACCOUNT_SETUP.md`, `EMPIRE_REPORT_METHODOLOGY.md`, `EMPIRE_DEPLOYMENT_RUNBOOK.md`, `EMPIRE_ACCEPTANCE_REPORT.md`) | M14 | Docs |
| 19 | Verification Script & Auth Hardening | `scripts/verify_empire_e2e.py` authenticated owner token integration and demo data seeding | M14 | Verification |
| 20 | Programmatic Pytest Verification Suite | Comprehensive automated pytest suite testing checklist catalog, result invariants, scope gate, adapters, and file policy | M14 | Verification |
| 21 | Frontend Typecheck & Lint Cleanliness | Clean TypeScript compilation (`tsc --noEmit`) and ESLint (`npm run lint`) with zero errors and warnings across both themes | M14 | Verification |
| 22 | Final Dual-Track E2E & Victory Audit | 100% E2E test verification pass, live baseline scan execution on `https://empire.edu.vn/`, and Sentinel Victory Audit | M15 | Final |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M11 | Checklist Catalog, Scope Gate & Synthetic Test Harness (Agent B) | Models, schemas, catalog seeder (39 checks, 6 categories), 7-state result engine, scope authorization gate, 4-tier emergency stop, synthetic BOLA/BFLA harness, /media file policy engine, `/api/v1/checklist` and `/api/v1/scope` routes | none | DONE |
| M12 | Scanner Adapters, Process Safety, 10-State Lifecycle & Reporting (Agent B) | `process_safety.py` extraction, process group & resource limits, ZAP/Nuclei/Trivy adapter safety, 10-state finding lifecycle alignment, secret redaction, ReportLab PDF / HTML / JSON with coverage gap disclosure & warm light styling | M11 | DONE |
| M13 | Dual-Theme Liquid Glass UI & Checklist Experience (Agent C) | Warm Invert Light theme tokens, `ThemeProvider`, theme switcher in `Shell.tsx` and settings, `/checklist` view, triage drawer polish, dual-theme report preview, frontend node_modules setup | M11 | DONE |
| M14 | Documentation Package & Verification Hardening | Complete 8 `EMPIRE_*.md` documents, `scripts/verify_empire_e2e.py` auth fix, comprehensive pytest suite, TypeScript and ESLint verification | M11, M12, M13 | DONE |
| M15 | Final Dual-Track E2E & Victory Audit | Full E2E test pass (10/10 automated tests), live baseline on `https://empire.edu.vn/`, adversarial verification, and Sentinel Victory Audit | M14 | READY_FOR_VICTORY_AUDIT |

## Interface Contracts
### Checklist Engine ↔ Frontend (M11 ↔ M13)
- `GET /api/v1/checklist/definitions`: Query check catalog, optional category filter. Returns `List[ChecklistDefinitionRead]`.
- `GET /api/v1/checklist/runs`: List assessment runs with coverage statistics (`total_checks`, `automated_coverage_pct`, `manual_completion_pct`, counts per state).
- `POST /api/v1/checklist/runs`: Initiate checklist evaluation for an asset. Payload `{ "asset_id": UUID, "mode": "AUTOMATED" | "FULL" }`.
- `GET /api/v1/checklist/runs/{id}/results`: Query 7-state results with forensic evidence.

### Scope Authorization Gate ↔ Scanners (M11 ↔ M12)
- `ScopeValidator.validate_preflight(asset_id: UUID, requested_checks: list) -> ScopeValidationResult`:
  Raises `ScopeEnforcementError` if scope is missing, expired, emergency stop active, or origin mismatch.
- `ScopeValidator.check_rate_and_budget(asset_id: UUID, request_count: int, bytes_count: int) -> bool`.
- `POST /api/v1/assets/{id}/emergency-stop`: Immediately toggles `emergency_stop_active=True` and invokes `terminate_process_tree` on all active scans for the asset.

### Process Safety & Scanner Adapters (M12)
- `backend/app/core/process_safety.py`:
  - `ProcessSafetyManager.register_pid(scan_id: UUID, pid: int, pgid: Optional[int] = None)`
  - `ProcessSafetyManager.terminate_process_tree(scan_id: UUID, timeout: float = 3.0) -> bool`
  - `ProcessSafetyManager.get_safe_subprocess_kwargs() -> dict`: sets `preexec_fn` for `os.setsid` and `resource.setrlimit`.

### Finding Lifecycle ↔ Triage (M12 ↔ M13)
- `POST /api/v1/findings/{id}/triage`:
  Accepts `status` matching canonical 10 states: `NEW`, `NEEDS_TRIAGE`, `CONFIRMED`, `FALSE_POSITIVE`, `ACCEPTED_RISK`, `ASSIGNED`, `IN_PROGRESS`, `FIXED_PENDING_RETEST`, `RESOLVED`, `REOPENED`.
  Logs immutable `FindingChange` audit entry.

### Dual-Theme Styling (M13)
- `:root` (Dark Obsidian): `--bg-primary: #09090B`, `--bg-surface: #0C0C0E`, `--border-subtle: rgba(255, 255, 255, 0.07)`, `--text-primary: #FAFAFA`.
- `.theme-warm` / `[data-theme='warm']` (Warm Invert Light): `--bg-primary: #FAF8F5`, `--bg-surface: #FFFFFF`, `--border-subtle: rgba(0, 0, 0, 0.08)`, `--border-strong: rgba(0, 0, 0, 0.16)`, `--text-primary: #18181B`, `--text-secondary: #52525B`, `--text-muted: #71717A`.
- `ThemeProvider` manages active theme with `'obsidian-dark'` and `'warm-light'` keys, updating `document.documentElement` class and `data-theme` attribute.

## Code Layout
- `backend/app/api/`: FastAPI REST routers (`assets.py`, `scans.py`, `findings.py`, `checklist.py`, `scope.py`, etc.).
- `backend/app/core/`: Configuration, database session, `process_safety.py`, `ssrf.py`, `empire_seeder.py`, `dispatcher.py`.
- `backend/app/models/`: SQLAlchemy 2.0 ORM models (`checklist.py`, `scope.py`, `synthetic_identity.py`, `baseline.py`, `finding.py`, `asset.py`, `scan.py`).
- `backend/app/schemas/`: Pydantic V2 schemas (`checklist.py`, `scope.py`, `finding.py`, `scan.py`, `common.py`).
- `backend/app/scanners/`: Scanner adapters (`nuclei.py`, `zap.py`, `trivy.py`, `empire_engine.py`, `synthetic_harness.py`, `file_policy.py`).
- `backend/app/reporting/`: Multi-format reporting engine (`generator.py`, `pdf_builder.py`, `templates/html_report.jinja2`, `templates/executive_summary.jinja2`).
- `frontend/src/app/`: Next.js 14 App Router views (`dashboard`, `assets`, `scans`, `active-assessments`, `findings`, `remediation`, `checklist`, `settings`, `reports`).
- `frontend/src/components/`: Layout (`Shell.tsx`), theme switcher (`ThemeToggle.tsx`), checklist components, evidence viewer, verification modal.
- `frontend/src/providers/`: Context providers (`ThemeProvider.tsx`).
- `frontend/src/styles/`: `globals.css` with Black/White/Liquid Glass dark & warm-light tokens.
- `scripts/`: Verification scripts (`verify_empire_e2e.py`).
- `tests/`: Automated pytest test suites (`test_checklist_catalog.py`, `test_scope_gate.py`, `test_synthetic_harness.py`, `test_scanner_adapters.py`, etc.).
- Root Documentation: 8 `EMPIRE_*.md` files.
