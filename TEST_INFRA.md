# NOOSFORGE Security Intelligence — Test Infrastructure & Quality Assurance Specification

## 1. Testing Philosophy & Quality Engineering Principles

NOOSFORGE Security Intelligence operates under a mission-critical, enterprise cybersecurity mandate for assessing the Empire education ecosystem (`*.empire.edu.vn`). The testing infrastructure is designed around strict, non-negotiable engineering principles that eliminate false confidence, prevent regressions, and guarantee defensive robustness:

### 1.1. Opaque-Box & Requirement-Driven Architecture
- **Black-Box / Opaque-Box Contracts**: Every test interacts with the platform strictly across public API interfaces (`/api/v1/*`), CLI harnesses, and client contracts without mocking internal business logic, database transactions, or scanner engines.
- **Requirement-Driven Traceability**: Every test case directly derives from requirements established in `PROJECT.md` and `ORIGINAL_REQUEST.md`, forming an unbroken chain from business capability to technical assertion.
- **Zero-Mock & Zero-Fabrication Invariant**: Tests never synthesize artificial findings, fake scan records, or hardcoded mock responses. Real HTTP local transport harnesses (`httpx.AsyncClient` with `ASGITransport`) exercise full request routing, middleware validation, database transactions, and JSON serialization.

### 1.2. Methodological Testing Disciplines
- **Category-Partition Method**: Systematic decomposition of input domains (locators, scan profiles, triage states, export formats, search queries) into orthogonal equivalence classes, ensuring every operational partition is exercised.
- **Boundary Value Analysis (BVA)**: Exhaustive probing of extremal limits, including empty strings, 4096-character locators, zero-day time bounds, negative page indices, max batch sizes, and edge-case status transitions.
- **Pairwise & Combinatorial Testing**: Combinations of asset types (`DOMAIN`, `IP`, `CIDR`, `URL`, `API`), environments (`PRODUCTION`, `STAGING`, `DEVELOPMENT`), modules (`A` through `G`), and scanner profiles (`QUICK_DISCOVERY`, `DAILY_SECURITY`, `FULL_AUDIT`, `DEEP_EXPLOIT`).
- **Workload & Stress Testing**: Concurrent scan job dispatch, SSE log stream backpressure verification, multi-format report generation under load, and database connection pool saturation resilience.

---

## 2. Four-Tier Test Architecture & Directory Layout

The automated testing architecture is organized into four hierarchical verification tiers, anchored by the primary opaque-box suite `tests/test_empire_e2e_opaque_box.py` and complemented by specialized adversarial and live capability suites:

```
noospire/
├── tests/
│   ├── conftest.py                             # Async fixtures, database session lifecycle, HTTP client harness
│   ├── test_empire_e2e_opaque_box.py           # Primary 4-Tier Opaque-Box E2E Suite (60 tests, 100% PASS)
│   │   ├── Tier 1: Feature Coverage            # >=5 tests per core feature (28 tests)
│   │   ├── Tier 2: Boundary & Corner Cases     # >=5 tests per edge category (22 tests)
│   │   ├── Tier 3: Cross-Feature Combinations  # Pairwise lifecycle interactions (5 tests)
│   │   └── Tier 4: Real-World Scenarios        # Production-grade operational workflows (5 tests)
│   ├── test_platform_core_m1.py                # Core M1: Target ingestion, 8-step verification engine
│   ├── test_scan_intelligence_m2.py            # Core M2: Scanner state machine, process safety, finding deduplication
│   ├── test_shell_primitives_adversarial.py    # Shell & UI: Primitives contracts, responsive breakpoints, 14 views
│   ├── test_m6_targets_scans_adversarial.py    # M6 SaaS: Modal probes, triage transitions, SSE telemetry
│   ├── test_empirical_challenger.py            # Empirical: SSRF filter bypasses, IPv6/IPv4 normalization
│   └── test_challenger_live_empire.py          # Live Target: Empire live ecosystem integration & verification
├── scripts/
│   └── verify_empire_e2e.py                    # Dual-Track E2E Verifier: 10 vertical slice subsystem capabilities
└── frontend/
    ├── package.json                            # Scripts: lint, typecheck, build
    └── .eslintrc.json                          # Non-interactive ESLint config extending next/core-web-vitals
```

---

## 3. Tier Classification & Methodological Scope

### Tier 1: Comprehensive Feature Coverage (>=5 per Feature)
- **Objective**: Validate 100% of core security, operational, and assessment capabilities across all critical domains.
- **Feature 1.1 — Student Access Control & BOLA Detection (6 tests)**:
  - `test_t1_student_access_a_accesses_a_profile`: Student A successfully accesses own profile (`/api/v1/auth/me`).
  - `test_t1_student_access_b_accesses_b_profile`: Student B successfully accesses own profile.
  - `test_t1_student_access_b_denied_a_learning_records`: Student B access to Student A's records is forbidden/isolated.
  - `test_t1_student_access_anon_denied_a_learning_records`: Anonymous access to student records is rejected with 401.
  - `test_t1_student_access_bola_assessment_engine_detection`: BOLA security engine detection capability flags broken object level access.
  - `test_t1_student_access_symmetric_isolation`: Student A is symmetrically isolated from Student B's records.
- **Feature 1.2 — Public Materials vs Private Canary Media (5 tests)**:
  - `test_t1_media_public_course_material_allowed`: Public course assets accessible without leakage warnings.
  - `test_t1_media_private_canary_csv_leak_detection`: Sensitive student canary records trigger immediate high-severity leak detection.
  - `test_t1_media_baseline_policy_registration`: Approved media baseline policy (`/media PUBLIC_BY_DESIGN`) registers successfully.
  - `test_t1_media_directory_indexing_defense_contract`: Directory indexing defense verifies scanner flags index disclosures.
  - `test_t1_media_env_file_probe_contract`: Environment file probe verification ensures `.env` leak attempts generate critical alerts.
- **Feature 1.3 — Login Defense & Anti-Automation (5 tests)**:
  - `test_t1_login_defense_five_404s_produce_zero_bruteforce`: Five consecutive 404 responses trigger zero brute-force false positives.
  - `test_t1_login_defense_sacrificial_identity_bounded`: Sacrificial probe identity requests are bounded to safe evaluation limits.
  - `test_t1_login_defense_stops_on_429`: Scanner immediately halts and respects HTTP 429 Too Many Requests backoff.
  - `test_t1_login_defense_valid_credentials_succeed`: Valid credentials authenticate cleanly yielding JWT access token.
  - `test_t1_login_defense_invalid_credentials_rejected`: Invalid credentials rejected with 400/401 and generic security message.
- **Feature 1.4 — Operational Route Authentication & RBAC (6 tests)**:
  - `test_t1_auth_anonymous_rejected_on_asset_creation`: Anonymous POST to `/api/v1/assets` returns 401.
  - `test_t1_auth_anonymous_rejected_on_scan_dispatch`: Anonymous POST to `/api/v1/scans` returns 401.
  - `test_t1_auth_student_forbidden_on_operator_routes`: Student role accessing operator routes is blocked with 403 Forbidden.
  - `test_t1_auth_refresh_rejected_without_credentials`: Refresh endpoint rejects unauthenticated requests.
  - `test_t1_auth_invalid_token_rejected_with_401`: Malformed/tampered JWT tokens rejected with 401.
  - `test_t1_auth_public_health_minimal_and_accessible`: Public `/health` endpoint accessible without credentials.
- **Feature 1.5 — Protected Report Downloads (6 tests)**:
  - `test_t1_report_download_pdf_success`: Authorized PDF download verifies binary `%PDF-` file header.
  - `test_t1_report_download_html_success`: Authorized HTML download verifies `<!DOCTYPE html` or `<html>` tag.
  - `test_t1_report_download_json_success`: Authorized JSON download verifies valid parseable JSON structure.
  - `test_t1_report_download_nonexistent_returns_404`: Nonexistent report ID returns 404 Not Found.
  - `test_t1_report_download_invalid_format_returns_404`: Unsupported download format returns 404/422.
  - `test_t1_report_download_anonymous_rejected_with_401`: Anonymous download attempt rejected with 401.

### Tier 2: Boundary Value & Corner Cases (>=5 per Feature)
- **Feature 2.1 — Locators & Special Characters (6 tests)**:
  - `test_t2_locator_empty_string_rejected`: Empty/whitespace locator rejected with 422.
  - `test_t2_locator_max_length_url_boundary`: 2048+ character locator handled safely at schema boundary.
  - `test_t2_locator_crlf_injection_rejected`: Header CRLF injection characters (`\r\n`) rejected or sanitized.
  - `test_t2_locator_unicode_homoglyph_handling`: Cyrillic/homoglyph domain characters rejected or normalized.
  - `test_t2_locator_disallowed_schemes_rejected`: Dangerous schemes (`file://`, `gopher://`, `ftp://`) blocked with 400/422.
  - `test_t2_locator_boundary_port_validation`: Port boundaries (0, 65535, 65536) strictly validated.
- **Feature 2.2 — Rate, Page, and Budget Limits (5 tests)**:
  - `test_t2_budget_negative_page_rejected`: Negative pagination query params (`page=-1`) rejected with 422.
  - `test_t2_budget_zero_page_size_rejected`: Zero page size (`size=0`) rejected with 422.
  - `test_t2_budget_excessive_page_size_rejected`: Page size exceeding max limit (`size=10000`) rejected with 422.
  - `test_t2_budget_invalid_enum_rejected`: Non-existent enum values for filters rejected with 422.
  - `test_t2_budget_negative_limit_on_audit_logs`: Negative limit on audit logs rejected with 422.
- **Feature 2.3 — Egress Boundaries & SSRF Defense (6 tests)**:
  - `test_t2_egress_ipv4_loopback_blocked`: IPv4 loopback (`127.0.0.1`, `127.0.0.2`) blocked by SSRFProtector.
  - `test_t2_egress_ipv6_loopback_blocked`: IPv6 loopback (`::1`, `[::1]`) blocked by SSRFProtector.
  - `test_t2_egress_aws_metadata_blocked`: AWS/cloud link-local metadata (`169.254.169.254`) strictly blocked.
  - `test_t2_egress_gcp_metadata_blocked`: GCP metadata hostname (`metadata.google.internal`) strictly blocked.
  - `test_t2_egress_rfc1918_private_ranges_blocked`: RFC 1918 private subnets (`10.0.0.1`, `172.16.0.1`, `192.168.1.1`) blocked.
  - `test_t2_egress_obfuscated_decimal_ip_blocked`: Decimal IP integer encoding (`2130706433` -> `127.0.0.1`) blocked.
- **Feature 2.4 — Unknown Loop-Test Assets & 404 Rejections (5 tests)**:
  - `test_t2_unknown_asset_detail_query_404`: Nonexistent asset ID query returns 404.
  - `test_t2_unknown_asset_scan_dispatch_404`: Scan dispatch against nonexistent asset returns 404.
  - `test_t2_unknown_asset_verification_trigger_404`: Verification trigger against nonexistent asset returns 404.
  - `test_t2_unknown_finding_retest_404`: Retest trigger against nonexistent finding returns 404.
  - `test_t2_unknown_asset_update_404`: Update against nonexistent asset returns 404.

### Tier 3: Cross-Feature Interactions & Multi-Stage Lifecycles (5 Pairwise Combinations)
- **Lifecycle 3.1 — Schedule → Batch → Worker Claim → Observation → Report Snapshot**:
  - `test_t3_pairwise_schedule_to_batch_to_claim_to_report`: Verifies end-to-end pipeline from assessment schedule creation to batch task dispatch, finding generation, and multi-format report persistence.
- **Lifecycle 3.2 — Asset Verification Gate → Scan Dispatch**:
  - `test_t3_pairwise_asset_verification_gate_to_scan`: Verifies that unverified assets are blocked from active scans until verified, after which scan dispatch succeeds.
- **Lifecycle 3.3 — Finding Detection → Triage → Regression Retest**:
  - `test_t3_pairwise_finding_triage_to_retest`: Verifies transition from OPEN finding to IN_PROGRESS triage, triggering live retest and audit trail logging.
- **Lifecycle 3.4 — Scan Execution → SSE Telemetry Streaming**:
  - `test_t3_pairwise_scan_sse_telemetry_flow`: Verifies real-time event streaming (`text/event-stream`), step logs, progress updates, and terminal state transitions.
- **Lifecycle 3.5 — Schedule Occurrence Idempotency**:
  - `test_t3_pairwise_schedule_occurrence_idempotency`: Verifies that recurring cron schedule triggers do not generate duplicate overlapping scan jobs for identical execution windows.

### Tier 4: Real-World Application Scenarios (5 Comprehensive Workflows)
- **Scenario 4.1 — Dual Synthetic Students Scheduled Assessment**:
  - `test_t4_real_world_dual_synthetic_students_scheduled_assessment`: Deploys two synthetic student personas (Student Alpha and Student Beta) with distinct identities, runs a scheduled assessment against `id.empire.edu.vn`, and validates BOLA isolation and authorization boundaries.
- **Scenario 4.2 — Empire Full 7-Module Architecture Discovery**:
  - `test_t4_real_world_empire_modules_a_through_g_discovery`: Validates ecosystem architecture mapping across all Empire modules: Student Management, Learning Materials, Supporting Tools, API Services, Web Applications, Server Infrastructure, and Identity Provider.
- **Scenario 4.3 — Approved Public Media Baseline Policy Enforcement**:
  - `test_t4_real_world_approved_media_baseline_policy`: Enforces security baseline on `media.empire.edu.vn` (`/media PUBLIC_BY_DESIGN`), ensuring legitimate public educational assets are never misclassified as vulnerabilities while private canary tokens are flagged.
- **Scenario 4.4 — Login Defense Bounded Anti-Automation**:
  - `test_t4_real_world_login_defense_bounded_anti_automation`: Simulates credential evaluation workflow with bounded sacrificial probes, verifying automated scanners respect rate-limiting cooldowns without locking genuine student accounts.
- **Scenario 4.5 — Audit-Grade Executive & Technical Report Generation**:
  - `test_t4_real_world_audit_grade_report_generation`: Generates comprehensive audit-grade security assessments in JSON, HTML, and PDF formats, verifying non-empty disk persistence and header compliance.

---

## 4. Test Execution Runners & Invocation Commands

### 4.1. Primary Opaque-Box E2E Suite (Pytest)
```bash
# Execute the full 4-tier opaque-box test suite (60 tests):
python -m pytest tests/test_empire_e2e_opaque_box.py -v

# Execute specific tiers:
python -m pytest tests/test_empire_e2e_opaque_box.py -k "test_t1" -v  # Tier 1 (28 tests)
python -m pytest tests/test_empire_e2e_opaque_box.py -k "test_t2" -v  # Tier 2 (22 tests)
python -m pytest tests/test_empire_e2e_opaque_box.py -k "test_t3" -v  # Tier 3 (5 tests)
python -m pytest tests/test_empire_e2e_opaque_box.py -k "test_t4" -v  # Tier 4 (5 tests)
```

### 4.2. Dual-Track E2E Verifier & Live Engine
```bash
# Execute 10 vertical slice subsystem capabilities:
python scripts/verify_empire_e2e.py
```

### 4.3. Frontend Static Analysis & Build
```bash
cd frontend && npm run lint        # Non-interactive ESLint check
cd frontend && npm run typecheck   # TypeScript compiler check
cd frontend && npm run build       # Next.js 14 App Router production build
```

---

## 5. Coverage Thresholds & Acceptance Criteria

1. **Pass Rate Gate**: 100% of all automated tests in `tests/test_empire_e2e_opaque_box.py` (60/60) must PASS with zero failures, zero errors, and zero unhandled exceptions.
2. **Feature Coverage Gate**: Every required feature (Student Access Control, Canary Media, Login Defense, Operational Auth, Report Downloads) must have >=5 dedicated tests.
3. **Boundary Gate**: Boundary conditions (Locators, Budgets, Egress/SSRF, Unknown Assets) must have >=5 dedicated tests.
4. **SSRF Defense Gate**: 100% rejection rate for private RFC 1918 subnets, IPv4/IPv6 loopbacks, AWS/GCP cloud metadata addresses, and malformed URL schemes.
5. **Report Artifact Gate**: Multi-format report generation must persist valid, non-empty JSON, HTML, and PDF artifacts with proper magic bytes (`%PDF-`).
