# Milestone M2 Report: Scanning and Intelligence

**Agent**: `worker_scan_m2`  
**Date**: 2026-11-08  
**Scope**: Milestone M2 (Scanning and Intelligence Subsystem)  
**Verification**: 92/92 `pytest` PASS, 10/10 `scripts/verify_empire_e2e.py` PASS  

---

## 1. Executive Summary

Milestone M2 delivers the core scanning and intelligence capabilities of NOOSFORGE Security Intelligence, fulfilling all requirements specified in `ORIGINAL_REQUEST.md`, `PROJECT.md`, and `DISPATCH.md`:

1. **Scanner Quality State Machine (R2)**: Implemented `ScanQualityStatus` with explicit quality states (`SCANNED_SUCCESSFULLY`, `PARTIAL_COVERAGE`, `AUTH_REQUIRED`, `SCANNER_FAILED`, `TARGET_UNAVAILABLE`), integrated into database models, API schemas, and dispatcher execution transitions while preserving strict backwards compatibility with `ScanStatus`.
2. **Scanner Process Safety & Orchestration (R2)**: Registered child process PIDs (`proc.pid`) across Nuclei, Trivy, and ZAP scanner adapters with `ProcessSafetyManager` for clean recursive process tree termination.
3. **Asynchronous Same-Origin Web Crawler (R2)**: Built `backend/app/scanners/crawler.py` delivering a high-performance asynchronous Breadth-First Search (BFS) crawler constrained strictly to target asset origin, bounded by `max_depth=3`, `max_pages=50`, with rate-limiting delay and robust HTML link discovery.
4. **Empire Business Module Security & Intelligence (R3)**: Extended `backend/app/scanners/empire_engine.py` to guarantee comprehensive coverage across all Empire operational modules starting from `https://empire.edu.vn/`, including Web Application security (CSP, clickjacking, cookie security) and Server Infrastructure (version banner disclosure, HSTS, status probe detection).
5. **Finding Evidence JSON Persistence**: Implemented `flag_modified(finding, "evidence")` in `backend/app/api/findings.py` to ensure in-place JSON mutations (`triage_history`, `last_retest`) persist cleanly without stale ORM caching.

---

## 2. Deliverables & Implementation Details

### 2.1 Scanner Quality State Machine
- **Schemas (`backend/app/schemas/common.py`)**:
  ```python
  class ScanQualityStatus(str, Enum):
      SCANNED_SUCCESSFULLY = "SCANNED_SUCCESSFULLY"
      PARTIAL_COVERAGE = "PARTIAL_COVERAGE"
      AUTH_REQUIRED = "AUTH_REQUIRED"
      SCANNER_FAILED = "SCANNER_FAILED"
      TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"
  ```
- **ORM Model (`backend/app/models/scan.py`)**:
  Added `quality_status: Mapped[Optional[str]] = mapped_column(String(32), default=None, nullable=True, index=True)` and initialized default in `__init__`.
- **API Schema (`backend/app/schemas/scan.py`)**:
  Added `quality_status: Optional[ScanQualityStatus] = None` to `ScanResponse`, and exported alias `ScanRead = ScanResponse`.
- **Dispatcher Transitions (`backend/app/core/dispatcher.py`)**:
  - Target unavailable (asset missing or SSRF validation failure): Sets `quality_status = TARGET_UNAVAILABLE`, `status = FAILED`.
  - Authentication / authorization required (e.g. `DEEP_ACTIVE` profile on unverified target): Sets `quality_status = AUTH_REQUIRED`, `status = FAILED`.
  - Scanner crash or total adapter failure: Sets `quality_status = SCANNER_FAILED`, `status = FAILED`.
  - Partial adapter failure (some succeeded, some failed/timed out): Sets `quality_status = PARTIAL_COVERAGE`, `status = COMPLETED`.
  - All adapters clean: Sets `quality_status = SCANNED_SUCCESSFULLY`, `status = COMPLETED`.

### 2.2 Scanner Process Safety & Orchestration
- In `backend/app/scanners/nuclei.py`:
  ```python
  proc = await asyncio.create_subprocess_exec(*cmd, ...)
  from backend.app.core.dispatcher import process_safety
  await process_safety.register_pid(request.scan_id, proc.pid)
  ```
- In `backend/app/scanners/trivy.py`:
  ```python
  proc = await asyncio.create_subprocess_exec(*cmd, ...)
  from backend.app.core.dispatcher import process_safety
  await process_safety.register_pid(request.scan_id, proc.pid)
  ```
- In `backend/app/scanners/zap.py`:
  Added native CLI execution with `proc.pid` registration and seamless fallback to `httpx.AsyncClient` lab runner.

### 2.3 Asynchronous Same-Origin BFS Crawler
- File: `backend/app/scanners/crawler.py`
- Class: `AsyncBFSCrawler`
- Capabilities:
  - `is_same_origin`: Parses candidate URL and checks domain hostname and port against target origin.
  - `extract_links`: Discovers URLs from `href`, `src`, and `action` HTML attributes, resolves relative paths, strips URL fragments (`#...`), and filters out static media/binary files (`.png`, `.jpg`, `.pdf`, `.zip`, etc.).
  - `crawl`: Queue-based BFS traversal enforcing `max_depth` (default 3), `max_pages` (default 50), and rate-limiting delay between requests (`rate_limit_delay`).
  - Cooperative cancellation via `CancellationToken`.
  - Produces structured `CrawlResult` containing visited endpoint metrics (status code, content type, content length, title, discovered links).

### 2.4 Empire Business Module Security
- File: `backend/app/scanners/empire_engine.py`
- Added methods:
  - `_assess_web_security`: Audits Web Application security (Module E) for Content-Security-Policy (CSP), Clickjacking defense (`X-Frame-Options` and `frame-ancestors`), and cookie security attributes (`Secure`, `HttpOnly`, `SameSite`).
  - `_assess_server_infrastructure`: Audits Server & Infrastructure security (Module G) for web server software version banner disclosure, HTTPS Strict-Transport-Security (HSTS), and exposed diagnostic interfaces (`/server-status`).
- Updated `execute_empire_assessment`:
  When assessing `https://empire.edu.vn/` or root ecosystem targets, comprehensively covers all business modules (Modules A through G).

### 2.5 Finding Evidence JSON Persistence (`flag_modified`)
- File: `backend/app/api/findings.py`
- Implemented:
  ```python
  from sqlalchemy.orm.attributes import flag_modified
  ...
  evidence["triage_history"] = triage_history
  finding.evidence = evidence
  flag_modified(finding, "evidence")
  ```
  Applied in both `triage_finding` and `retest_finding` to guarantee database persistence across SQLAlchemy async sessions.

---

## 3. Verification & Test Results

### 3.1 Automated Test Suite (`pytest tests/ -v`)
- **Total Test Cases**: 92 tests (80 existing platform tests + 12 new M2 tests).
- **Result**: 🟢 **92/92 PASSED (100%)**
- New test file: `tests/test_scan_intelligence_m2.py`:
  - `test_m2_01_scan_quality_status_enum`: PASS
  - `test_m2_02_scan_model_and_schema_quality_status`: PASS
  - `test_m2_03_crawler_same_origin_enforcement`: PASS
  - `test_m2_04_crawler_link_extraction`: PASS
  - `test_m2_05_crawler_execution_bounded`: PASS
  - `test_m2_06_process_safety_manager_registration`: PASS
  - `test_m2_07_finding_flag_modified_persistence`: PASS
  - `test_m2_08_empire_assessment_engine_module_coverage`: PASS
  - `test_m2_09_dispatcher_auth_required_state_machine`: PASS
  - `test_m2_10_dispatcher_target_unavailable_state_machine`: PASS
  - `test_m2_11_scan_dispatch_quality_status_lifecycle`: PASS
  - `test_m2_12_direct_dispatcher_quality_state_machine`: PASS

### 3.2 Empire E2E Verification Harness (`scripts/verify_empire_e2e.py`)
- **Total Steps**: 10 capability checks
- **Result**: 🟢 **10/10 PASS (100% XANH MƯỢT)**
  - Step 1: Database Initialization & Empire Seed Verification -> PASS
  - Step 2: Dashboard Overview KPIs & Analytics -> PASS
  - Step 3: Empire Business Architecture Modules -> PASS
  - Step 4: Asset Inventory & Bulk Import Deduplication -> PASS
  - Step 5: Approved Public Media Baseline Policy -> PASS
  - Step 6: Scan Dispatch & Empire Assessment Engine Execution -> PASS
  - Step 7: Vulnerability Triage Lifecycle & Live Retest -> PASS
  - Step 8: Multi-Format Report Generation (Zero Fabrication PDF/HTML/JSON) -> PASS
  - Step 9: Daily Assessment Scheduler Trigger -> PASS
  - Step 10: Security Alerts & Notification System -> PASS
