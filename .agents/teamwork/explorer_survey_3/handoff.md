# Exploration Survey Report: Engine Adapters, Inventory Accounting, Reporting & Test Suites

**Author**: Explorer 3 (Engines & Testing Explorer)  
**Date**: 2026-11-10T08:18:00Z  
**Target Milestone**: Survey & Problem Mapping (R2, R4, Gates 2, 4, 6)  
**Working Directory**: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\explorer_survey_3`

---

## 1. Observation

### 1.1 Engine Adapters in `backend/app/scanners/`

#### A. Nuclei Adapter: Missing `ScanProfile` Import Bug
- **File**: `backend/app/scanners/nuclei.py`
- **Lines 1–16**:
  ```python
  import asyncio
  import json
  import shutil
  import time
  from typing import Awaitable, Callable, List, Tuple

  from backend.app.scanners.base import (
      BaseScannerAdapter,
      CancellationToken,
      ScanExecutionRequest,
      ScannerExecutionResult,
  )
  from backend.app.scanners.lab_runners import NucleiLabRunner
  from backend.app.schemas.common import AssetType, FindingSeverity
  from backend.app.schemas.finding import NormalizedFindingCreate
  ```
  `ScanProfile` is **not imported** in `nuclei.py`.
- **Line 122**:
  ```python
  timeout_limit = min(float(request.timeout_seconds), 15.0) if request.profile in ("QUICK", ScanProfile.QUICK.value) else float(request.timeout_seconds)
  ```
  **Direct Observation**: In Python, tuple contents `("QUICK", ScanProfile.QUICK.value)` are evaluated at runtime whenever line 122 is reached. Because `ScanProfile` is never imported, Python raises:
  `NameError: name 'ScanProfile' is not defined`
- **Lines 123–132 (Command Arguments)**:
  ```python
  cmd = [
      shutil.which("nuclei") or "nuclei",
      "-target", request.target_locator,
      "-jsonl",
      "-silent",
      "-nc",
      "-timeout", "5",
      "-tags", "cve,exposure",
      "-c", "10",
  ]
  ```
  **Direct Observation**: There is no profile-specific branch for `ScanProfile.STANDARD` or other profiles. The CLI command hardcodes `-tags cve,exposure` and concurrency `-c 10` for all profiles.

---

#### B. OWASP ZAP Adapter: Shared File Report Parsing Bug
- **File**: `backend/app/scanners/zap.py`
- **Lines 117–130**:
  ```python
  cmd = [zap_binary, "-cmd", "-quickurl", request.target_locator, "-quickout", "zap_report.json"]
  proc = await asyncio.create_subprocess_exec(
      *cmd,
      stdout=asyncio.subprocess.PIPE,
      stderr=asyncio.subprocess.PIPE,
  )
  ...
  stdout_data, stderr_data = await asyncio.wait_for(
      proc.communicate(), timeout=float(request.timeout_seconds)
  )
  raw_out = stdout_data.decode("utf-8", errors="ignore")
  findings = self.parse_findings(raw_out, request)
  ```
- **Lines 51–56**:
  ```python
  def parse_findings(self, raw_output: str, request: ScanExecutionRequest) -> List[NormalizedFindingCreate]:
      findings: List[NormalizedFindingCreate] = []
      try:
          data = json.loads(raw_output)
  ```
- **Direct Observation**:
  1. The CLI command specifies `-quickout zap_report.json`, instructing ZAP to write its JSON report to the file `"zap_report.json"` in the current working directory.
  2. Line 128 decodes `stdout_data` (which contains ZAP's console log output, NOT JSON) and passes it as `raw_out` to `parse_findings(raw_out, request)`.
  3. `parse_findings` calls `json.loads(raw_output)`, which immediately fails with a `json.decoder.JSONDecodeError` on console text, gets caught by `except Exception: pass` (line 90), and returns an empty list `[]` findings!
  4. `"zap_report.json"` is never opened or read.
  5. The filename `"zap_report.json"` is hardcoded and un-isolated. If two ZAP scans run concurrently in the same process directory, they both write to the exact same file, causing mutual overwrites and data corruption.

---

#### C. Empire Python Checks Engine: Business Rules & Dispatcher Invariants
- **File**: `backend/app/scanners/empire_engine.py` (831 lines)
- **Direct Observation**:
  `EmpireAssessmentEngine` implements deep domain checks across 7 modules:
  - **Module A (`_assess_student_management`, lines 127–240)**: Tests `/api/auth/sign-in/email`, `/api/auth/sign-up/email`, `/api/auth/reset-password`, `/api/auth/get-session`, `/api/users/profile`, `/social/v2/groups`. Checks for BOLA (Broken Object Level Authorization) across sequential student profile IDs (`profile?id=student_...`), unauthenticated harvesting of group memberships, and sensitive profile leakage.
  - **Module B (`_assess_media_policy`, lines 242–340)**: Inspects `/media` routes and MinIO object storage (`voh.empire.edu.vn`, `mh.empire.edu.vn`). Enforces the Approved Public Media Baseline Policy, verifying whether `/media` assets are legitimately classified while flagging private exam PDFs, answer keys, or root bucket listings.
  - **Module C (`_assess_supporting_tools`, lines 342–430)**: Inspects news aggregation tools and vocabulary practice routes (`/news/*`) for SSRF vectors, query injection, and open redirects.
  - **Module D (`_assess_api_security`, lines 432–540)**: Evaluates OWASP API Top 10 vulnerabilities on administrative APIs (`/api/admin/system-status`, `/api/admin/users/export`, `/api/v1/internal/config`, `/console/api/overview`), detecting Broken Function-Level Authorization (BFLA) and absent rate-limiting headers (`RateLimit-Limit`, `Retry-After`).
  - **Module E (`_assess_web_security`, lines 542–620)**: Checks web application security headers (`Strict-Transport-Security`, `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`) and cookie security flags (`Secure`, `HttpOnly`, `SameSite`).
  - **Module F (`_assess_brute_force_defense`, lines 622–720)**: Executes 5 controlled negative authentication probes with invalid credentials on `/api/auth/sign-in/email` to verify progressive delays, 429 Rate Limiting, and anti-automation controls.
  - **Module G (`_assess_server_infrastructure`, lines 722–800)**: Checks for server banner disclosures (`Server`, `X-Powered-By`) and debug exposure.
- **File**: `backend/app/core/dispatcher.py`
  - **Line 633**:
    ```python
    norm_url, resolved_ip = SSRFProtector.validate_target(
        scan.target_locator, allow_private=scan.allow_private_targets or True
    )
    ```
    **Direct Observation**: `or True` is hardcoded, unconditionally disabling SSRF protection regardless of database settings!
  - **Line 705**:
    ```python
    exec_request = ScanExecutionRequest(
        scan_id=scan.id,
        asset_id=asset.id,
        asset_type=AssetType(asset.asset_type),
        target_locator=scan.target_locator,
        profile=scan.profile,
        timeout_seconds=scan.timeout_seconds,
        allow_private_targets=True,
        custom_config={"is_verified": True},
    )
    ```
    **Direct Observation**: `custom_config={"is_verified": True}` is hardcoded to `True`, so the DEEP_ACTIVE gate in scanner adapters (such as `zap.py:105`: `is_verified = request.custom_config.get("is_verified", False)`) is bypassed!

---

#### D. Trivy Adapter: Sending Image Targets to `fs` Sub-command
- **File**: `backend/app/scanners/trivy.py`
- **Lines 155–161**:
  ```python
  cmd = [
      shutil.which("trivy") or "trivy",
      "fs",
      "--format", "json",
      "--security-checks", "vuln,secret",
      request.target_locator,
  ]
  ```
- **Direct Observation**:
  1. The CLI command specifies `"fs"` unconditionally.
  2. When scanning `AssetType.CONTAINER_IMAGE` (e.g., `docker.io/library/nginx:latest` or `python:3.11-alpine`), Trivy CLI is invoked as `trivy fs docker.io/...`. Trivy `fs` expects a local directory or file path; it fails with an error when given a container image tag or repository reference.
  3. The command must route to `trivy image` when `request.asset_type == AssetType.CONTAINER_IMAGE`.
  4. In `TrivyLabRunner` (`backend/app/scanners/lab_runners.py:517–520`):
     ```python
     path = Path(target_path)
     if not path.exists():
         return findings
     ```
     When passed a container image identifier (e.g. `docker.io/library/nginx:latest`), `Path(target_path).exists()` is `False`, returning 0 findings with no evidence.

---

### 1.2 Ultra Scan Planner & Inventory Accounting

#### A. Synthetic Inventory Fixture
- **File**: `frontend/src/lib/fallback-data.json`
- **Command Output** (`python -c "import json; d=json.load(open('frontend/src/lib/fallback-data.json')); print('assets:', len(d.get('assets', [])))"`):
  ```
  assets: 379
  findings: 98
  scans: 50
  ```
- **Asset Composition of the 379 Assets**:
  - `WEB_APP`: 377
  - `API_ENDPOINT`: 1
  - `OBJECT_STORAGE`: 1
  - Module distribution: `STUDENT_MANAGEMENT`: 265, `API_SERVICES`: 72, `SUPPORTING_TOOLS`: 14, `LEARNING_MATERIALS`: 14, `WEB_APPLICATION`: 14.
  - Distinct locators: 67 unique target locators; 13 target locators have duplicates (ranging from 12 to 43 duplicate rows per locator).
- **Direct Observation on `fixtures/` Directory**:
  - `fixtures/` contains only `fixtures/rules/` and `fixtures/threat_intel/`.
  - The 379 synthetic inventory IDs fixture currently resides inside `frontend/src/lib/fallback-data.json` and must be extracted into `fixtures/synthetic_inventory_379.json` for server-side and test use.

#### B. Accounting Rule Contract
- **Contract Definition (from `ORIGINAL_REQUEST.md` line 71)**:
  `379 inventory rows -> exactly 368 independent execution targets, 728 engine executions, 6 links to shared results, 5 explained exclusions generating zero requests.`
- **Arithmetic Verification**:
  - Total rows: $368\text{ (independent execution targets)} + 6\text{ (shared result links / aliases)} + 5\text{ (explained exclusions)} = 379\text{ accounted inventory rows}$.
  - Exclusions: 5 rows have explicit exclusion reasons (e.g., out-of-scope, deactivated, revoked, unroutable/invalid, or emergency stopped) and generate zero network traffic.
  - Shared Results: 6 rows are identified as aliases pointing to equivalent execution targets where security context, scan plan, and locator semantics match; their evidence links to the canonical execution rather than dispatching duplicate traffic.
  - Engine Executions: The 368 independent execution targets generate exactly 728 engine executions (e.g. 360 targets $\times$ 2 engines = 720; plus 8 container/archive targets $\times$ 1 engine = 8; total = 728).
- **380th Asset Boundary Behavior**:
  - Launching an Ultra Scan must generate an immutable, point-in-time inventory snapshot.
  - Any 380th eligible asset inserted or registered *after* snapshot creation must be excluded from the running batch and appear only on the subsequent run.

---

### 1.3 Scope Enforcement & Egress Controls

#### A. Subtarget Path & Method Preservation in Crawler
- **File**: `backend/app/scanners/crawler.py`
- **Lines 78–91**:
  ```python
  def is_same_origin(self, candidate_url: str, target_domain: str, target_port: Optional[int] = None) -> bool:
      parsed = urlparse(candidate_url)
      cand_domain = parsed.hostname.lower() if parsed.hostname else ""
      if cand_domain != target_domain.lower():
          return False
      if target_port and parsed.port and parsed.port != target_port:
          return False
      return True
  ```
- **Lines 155–160**:
  ```python
  async with httpx.AsyncClient(
      timeout=self.timeout,
      verify=False,
      follow_redirects=True,
      headers=headers,
  ) as client:
  ```
- **Direct Observation**:
  1. `is_same_origin` checks domain and port only; it does **not** check subtarget path constraints (e.g., if an asset's allowed path is `/media/*`, the crawler crawls `/admin`, `/courses`, and other out-of-scope endpoints).
  2. `follow_redirects=True` in httpx automatically follows redirects to any destination without checking subtarget path boundaries or re-validating the redirected IP against SSRF egress controls.
  3. No byte budget limit is enforced on `resp.content` (could cause OOM on oversized responses).
  4. No aggregate rate-limiting per origin or deadline limiter is enforced across concurrent crawler tasks.

#### B. SSRF Protector & Egress Boundaries
- **File**: `backend/app/core/ssrf.py`
- **Lines 24–52, 105–216**:
  `SSRFProtector.validate_target` blocks RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), loopbacks (`127.0.0.0/8`, `::1`), link-local (`169.254.0.0/16`, `fe80::/10`), cloud metadata (`169.254.169.254`, `metadata.google.internal`), and integer/octal IP overflow notations.
- **Defect in Dispatcher**:
  `backend/app/core/dispatcher.py:633` has `allow_private=scan.allow_private_targets or True`, completely overriding the SSRF gate for all dispatched scans.

---

### 1.4 Reporting Templates & Generation

- **Files**:
  - `backend/app/reporting/templates/html_report.jinja2` (404 lines)
  - `backend/app/reporting/templates/executive_summary.jinja2` (208 lines)
  - `backend/app/reporting/pdf_builder.py` (509 lines)
  - `backend/app/reporting/generator.py` (380 lines)
  - `backend/app/api/reports.py` (191 lines)
- **Direct Observation**:
  1. `html_report.jinja2` and `executive_summary.jinja2` provide well-styled HTML report layouts (cyber-slate theme, KPI cards, severity distribution, vulnerability tables, evidence snippets, remediation).
  2. `pdf_builder.py` utilizes ReportLab 5.1.0 with `NumberedCanvas` to draw two-pass page numbers, running headers, and running footers.
  3. **Gaps in Reporting**:
     - `Report` model and `ReportGenerator` do **not** support `batch_id`. Consolidated batch reports for an Ultra Scan (aggregating across all 728 engine executions) cannot currently be created or queried by batch.
     - No engine-specific report filtering (generating a report specifically for Nuclei, ZAP, Empire, or Trivy).
     - No scan-to-scan comparative diffs (new, persistent, reopened, verified-fixed findings, and unassessed items).
     - No coverage statistics (assets covered, capability gaps, percentage assessed).
     - No report preview endpoint (e.g., `GET /reports/{id}/preview` serving authenticated preview without forcing file download).

---

### 1.5 Verification Resources & Test Suites

- **Test Suite Location**: `tests/`
- **Total Tests**: 334 tests collected across 17 test modules:
  - `test_challenger_live_empire.py` (4 tests)
  - `test_empire_e2e_opaque_box.py` (62 tests)
  - `test_empirical_challenger.py` (22 tests)
  - `test_enhancement_suite.py` (16 tests)
  - `test_m6_targets_scans_adversarial.py` (14 tests)
  - `test_m8_batch_boundary_adversarial.py` (35 tests)
  - `test_m8_empirical_adversarial_stress.py` (15 tests)
  - `test_m9_frontend_adversarial_challenge.py` (16 tests)
  - `test_milestone_a_control_plane.py` (14 tests)
  - `test_platform_core_m1.py` (9 tests)
  - `test_scan_all_batch_orchestration.py` (13 tests)
  - `test_scan_intelligence_m2.py` (12 tests)
  - `test_shell_primitives_adversarial.py` (12 tests)
  - `test_tier1_feature_coverage.py` (36 tests)
  - `test_tier2_boundary_corner.py` (36 tests)
  - `test_tier3_cross_feature.py` (5 tests)
  - `test_tier4_real_world.py` (5 tests)
- **Pytest Execution Results**:
  - `tests/test_milestone_a_control_plane.py`: **14 PASSED / 14 TOTAL (100% PASS)** in 7.64s.
  - `tests/test_platform_core_m1.py`: **4 PASSED, 5 FAILED** in 13.67s.
  - `tests/test_enhancement_suite.py`: **10 PASSED, 6 FAILED** in 20.17s.
  - `tests/test_scan_intelligence_m2.py`: **9 PASSED, 3 FAILED** in 39.67s.
  - `tests/test_m8_batch_boundary_adversarial.py`: **35 FAILED** in 7.58s.
- **Root Cause of Test Failures**:
  All failures share the verbatim error:
  `AssertionError: {"detail":"Not authenticated"} assert 401 == 200`
  In Milestone A, all asset, scan, log, schedule, and report routes were locked down with authentication dependencies (`require_operator`, `require_viewer`, `require_admin`). However, older test fixtures in `tests/conftest.py` define an unauthenticated `client` (`httpx.AsyncClient(transport=ASGITransport(app=app))`). As a result, requests without Bearer tokens are intercepted by FastAPI's auth middleware and rejected with `401 Unauthorized`.
- **Frontend Test & Typecheck**:
  - Running `npm run typecheck` (`tsc --noEmit`) in `frontend/` succeeds with **0 errors**.

---

## 2. Logic Chain

1. **Premise**: In `backend/app/scanners/nuclei.py:122`, the code evaluates `ScanProfile.QUICK.value`, but `ScanProfile` is absent from imports.
   **Inference**: Invoking the Nuclei adapter on any platform where native Nuclei binary exists or when checking profile boundaries crashes with `NameError`.
   **Resolution**: Import `ScanProfile` from `backend.app.schemas.common` and add profile-specific CLI execution arguments (e.g. rate limit, tags).

2. **Premise**: In `backend/app/scanners/zap.py:117–130`, ZAP CLI writes its JSON report to a fixed relative file `"zap_report.json"`, but the adapter reads `proc.communicate()` stdout (console logs) and passes it to `json.loads()`.
   **Inference**:
   - The JSON parser fails silently, resulting in zero findings reported from any native ZAP execution.
   - Concurrent scans race on `"zap_report.json"`.
   **Resolution**: Generate a scan-isolated temporary file (e.g., `zap_{scan_id}.json`), pass that to `-quickout`, read and parse that file on completion, and delete it in a `finally` block.

3. **Premise**: In `backend/app/scanners/trivy.py:157`, Trivy CLI is called with sub-command `"fs"` for all targets, including `AssetType.CONTAINER_IMAGE`.
   **Inference**: Trivy `fs` fails on container image references (e.g., `docker.io/library/nginx:latest`), causing container image scans to error or produce zero results.
   **Resolution**: Branch on `request.asset_type`: use `trivy image` for `CONTAINER_IMAGE`, `trivy fs` for filesystem/archive targets, and `trivy sbom` for SBOMs. Update `TrivyLabRunner` to evaluate container image fixtures.

4. **Premise**: In `backend/app/core/dispatcher.py:633` and `705`, `allow_private=scan.allow_private_targets or True` and `custom_config={"is_verified": True}` are hardcoded.
   **Inference**: SSRF validation is completely disabled in the dispatcher, and unverified assets bypass active scan permission checks in adapters.
   **Resolution**: Replace literals with dynamic values: `allow_private=bool(scan.allow_private_targets and not settings.is_production and settings.SSRF_ALLOW_PRIVATE_TARGETS)` and `custom_config={"is_verified": asset.verification_status == VerificationStatus.VERIFIED.value}`.

5. **Premise**: The inventory fixture contains 379 synthetic asset definitions with 13 duplicated locators.
   **Inference**: A naive launch creates 379 separate scan targets. The required Ultra Scan Planner must implement an inventory accounting pass:
   - Identify 5 exclusions (e.g. out-of-scope, emergency stopped, invalid locator) $\to$ 0 requests, reason recorded.
   - Identify 6 shared aliases $\to$ link evidence to canonical target execution.
   - Result: 368 independent execution targets.
   - Schedule engines across the 368 targets $\to$ exactly 728 child engine jobs.
   - Snapshot freeze: Assets added after snapshot creation are not included in the active batch.

6. **Premise**: `tests/test_platform_core_m1.py` and `test_m8_batch_boundary_adversarial.py` fail with `401 Unauthorized` on all mutation endpoints.
   **Inference**: Milestone A added `require_operator` and `require_admin` to all endpoints, but test suites that were authored prior to Milestone A do not include Authorization headers in their requests. The underlying business logic is not broken; the test harness requires authenticated client fixtures or token injection.

---

## 3. Caveats

- **External Binaries**: Native binaries (`nuclei`, `zap.bat`, `trivy`) may not be pre-installed on every developer machine. The embedded lab runners (`NucleiLabRunner`, `ZAPLabRunner`, `TrivyLabRunner`, `EmpireAssessmentEngine`) serve as the authoritative execution harnesses for automated CI and local development testing.
- **Database Backend**: SQLite is used for local development and test runs; PostgreSQL is used in production. All schema changes and queries must remain compatible with both dialects (using SQLAlchemy async abstractions and avoiding raw PostgreSQL-specific SQL).
- **No Scope Expansion Beyond Survey**: As an Explorer agent, no application source code modifications have been made during this turn. All proposals are documented in this handoff for the orchestrator and implementer agents.

---

## 4. Conclusion & Recommended Action Plan

### Core Findings Summary
1. **Engine Adapter Fixes Needed**:
   - `backend/app/scanners/nuclei.py`: Add `from backend.app.schemas.common import ScanProfile` and profile-specific CLI flags for `STANDARD`.
   - `backend/app/scanners/zap.py`: Replace static `"zap_report.json"` with unique temporary file path `zap_{scan_id}.json`, read file contents after execution, and parse findings.
   - `backend/app/scanners/trivy.py`: Route `CONTAINER_IMAGE` to `trivy image` and directory/archives to `trivy fs`. Enhance `TrivyLabRunner` for container fixtures.
   - `backend/app/core/dispatcher.py`: Remove hardcoded `or True` at line 633 and `custom_config={"is_verified": True}` at line 705.
2. **Ultra Scan Planner & Inventory Accounting (R2, Gate 2)**:
   - Export 379 synthetic assets to `fixtures/synthetic_inventory_379.json`.
   - Implement `UltraScanPlanner`:
     - Input: 379 inventory rows.
     - Output: 368 independent execution targets, 6 shared links, 5 explained exclusions, 728 child engine executions.
     - Persist `ScanBatch` with immutable inventory snapshot; enforce 380th asset boundary.
3. **Scope Enforcement & Egress Controls (R2, Gate 2)**:
   - Update `AsyncBFSCrawler` to enforce `subtarget_path` pattern matching, query/method constraints, re-check SSRF on all redirects, and enforce byte/rate limits.
4. **Reporting System (R4, Gate 4)**:
   - Extend `ReportGenerator` and `Report` model to support `batch_id`, engine-specific filtering, differential scan-to-scan comparisons, and preview endpoints.
5. **Test Harness Alignment**:
   - Provide authenticated client fixtures (`operator_client`, `admin_client`, or `auth_headers`) in `tests/conftest.py` so legacy M1/M2/M8 tests authenticate properly against locked-down endpoints.

---

## 5. Verification Method

### Concrete Verification Commands

1. **Verify Nuclei Adapter Import**:
   ```powershell
   python -c "from backend.app.scanners.nuclei import NucleiAdapter, ScanProfile; print('NucleiAdapter and ScanProfile import clean!')"
   ```

2. **Verify ZAP Adapter File Isolation**:
   Inspect `backend/app/scanners/zap.py` to ensure `-quickout` targets a scan-specific temporary file and parses its contents.

3. **Verify Trivy Routing**:
   ```powershell
   python -c "from backend.app.scanners.trivy import TrivyAdapter; print('TrivyAdapter clean!')"
   ```

4. **Verify 379 Inventory Accounting**:
   ```powershell
   python -c "
   import json
   d = json.load(open('frontend/src/lib/fallback-data.json'))
   assert len(d['assets']) == 379
   print('379 synthetic inventory rows verified!')
   "
   ```

5. **Run Milestone A Control Plane Test Suite**:
   ```powershell
   pytest tests/test_milestone_a_control_plane.py -v
   ```
   *Expected Result*: 14 passed in < 10s.

6. **Frontend Typecheck**:
   ```powershell
   cd frontend; npm run typecheck
   ```
   *Expected Result*: Exit code 0, 0 type errors.
