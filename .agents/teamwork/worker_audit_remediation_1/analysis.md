# Technical Analysis: Audit Remediation of Metrics & Engine Alignment

**Worker**: `worker_audit_remediation_1`  
**Milestone**: AM-1 (Confirmed Defects Remediation)  
**Date**: 2026-11-10  
**Target Files Modified**:
- `backend/app/api/metrics.py`
- `frontend/src/lib/api.ts`

---

## 1. Executive Summary

During the Ultra Integrity Audit, two specific defects were identified regarding data authenticity and backend-frontend consistency:
1. **Static Metrics in Backend Telemetry**: `backend/app/api/metrics.py` returned hardcoded `avg_duration_seconds = 18.5` in `/charts/scanner-performance` and hardcoded `detection_rules_active = 12` in `/charts/intelligence-activity`.
2. **Unbacked Engine Claim in Frontend**: `frontend/src/lib/api.ts` included `Nmap Network & Port Recon` in its engine health and test responses despite the platform using in-process and lab runners (`nuclei`, `zap`, `trivy`, `empire_engine`, `crawler`) with no backend Nmap driver.

Both discrepancies have been genuinely resolved with dynamic database-backed logic and strict engine alignment.

---

## 2. Defect Analysis & Root Causes

### 2.1. Backend Metrics Discrepancy
- **Location**: `backend/app/api/metrics.py:277, 297`
- **Root Cause**: The endpoints `/charts/scanner-performance` and `/charts/intelligence-activity` previously returned static placeholder values (`18.5` seconds and `12` rules) instead of querying actual database state.
- **Database Schema Reality**:
  - `noospire.db` table `scans` contains `started_at` and `completed_at` timestamps. In addition, dynamic calculations must gracefully handle scans without recorded duration attributes by computing `(completed_at - started_at).total_seconds()`.
  - `noospire.db` table `detection_rules` maps to `DetectionRule` (aliased as `Rule`), where rule status is governed by `RuleStatus.ACTIVE.value` (`"active"`).

### 2.2. Frontend Engine Catalog Discrepancy
- **Location**: `frontend/src/lib/api.ts:388, 440, 721-732, 772`
- **Root Cause**: The fallback data client in `api.ts` advertised 7 engines including `Nmap Network & Port Recon`, but the backend engine architecture (`backend/app/api/engines.py` and `backend/app/scanners/`) provides 5 authentic assessment engines:
  1. `nuclei`: ProjectDiscovery Nuclei CLI (`nuclei.exe` v3.11.1 / NucleiLabRunner)
  2. `zap`: OWASP ZAP Runner (`zap.bat` / ZAPLabRunner DAST)
  3. `trivy`: Aqua Trivy Vulnerability Runner (`trivy.py` / TrivyLabRunner)
  4. `empire_engine`: Empire Specialized Assessment Engine (`empire_engine.py` in-process)
  5. `crawler`: Asynchronous Bounded BFS Web Crawler (`crawler.py` in-process)

---

## 3. Implementation Details

### 3.1. `backend/app/api/metrics.py`
1. **Dynamic Scan Duration Query & Calculation**:
   - Implemented dynamic query for `func.avg(Scan.duration_seconds)` if column exists.
   - Implemented dynamic calculation for completed scans:
     - For each engine in `["empire_consolidated_suite", "nuclei", "zap", "trivy"]`, collects all completed scans and computes duration from `(completed_at - started_at).total_seconds()` or `duration_seconds`.
     - Computes engine-specific average duration rounded to 1 decimal place.
     - Fallbacks to overall completed scans average if engine has no executions, or `0.0` if no durations recorded.
2. **Dynamic Active Detection Rules Query**:
   - Imported `DetectionRule, RuleStatus` and aliased `Rule = DetectionRule`.
   - Executed dynamic query `select(func.count(DetectionRule.id)).where((DetectionRule.status == RuleStatus.ACTIVE.value) | (DetectionRule.status == "active"))`.
   - Replaced static `12` with the actual database count (`detection_rules_active = active_rules_res.scalar() or 0`).

### 3.2. `frontend/src/lib/api.ts`
1. **Engine Health & Catalog Fallback Alignment**:
   - Aligned `/engines/health` and `/system/engines` fallback to 5 authentic engines:
     - `nuclei` (Nuclei CLI)
     - `zap` (OWASP ZAP Runner)
     - `trivy` (Trivy Vulnerability Runner)
     - `empire_engine` (Empire Specialized Assessment Engine)
     - `crawler` (Async BFS Web Crawler)
   - Updated `/engines` fallback to return the 5 authentic engines.
   - Updated `/engines/test` probe results to test the 5 authentic engines.
   - Updated `/engines/check-updates` to check updates across the 5 authentic engines.
   - Removed all `nmap` entries from scanner performance charts, health checks, and scan log streams.
2. **Added `api.getEngines()` Method**:
   - Added `public async getEngines(): Promise<EngineDiagnosticItem[]>` to `ApiClient`.
   - Normalizes both live backend `/engines/health` and fallback `/engines` responses into `EngineDiagnosticItem[]`.

---

## 4. Verification Evidence

### 4.1. Backend Test Suite
Command:
```bash
python -m pytest tests/test_platform_core_m1.py tests/test_scan_all_batch_orchestration.py -v
```
Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
collected 22 items

tests/test_platform_core_m1.py::test_primary_root_target_seeded PASSED   [  4%]
tests/test_platform_core_m1.py::test_seeder_idempotency PASSED           [  9%]
tests/test_platform_core_m1.py::test_target_verifier_live_probe_8_steps PASSED [ 13%]
tests/test_platform_core_m1.py::test_target_verifier_ssrf_rejection PASSED [ 18%]
tests/test_platform_core_m1.py::test_api_verify_asset_endpoint PASSED    [ 22%]
tests/test_platform_core_m1.py::test_bulk_preview_csv PASSED             [ 27%]
tests/test_platform_core_m1.py::test_bulk_preview_json_and_batch_dedup PASSED [ 31%]
tests/test_platform_core_m1.py::test_bulk_preview_openapi PASSED         [ 36%]
tests/test_platform_core_m1.py::test_bulk_preview_cidr_and_ips PASSED    [ 40%]
tests/test_scan_all_batch_orchestration.py::test_batch_dispatch_all_targets_default PASSED [ 45%]
tests/test_scan_all_batch_orchestration.py::test_batch_matrix_expansion_engines_profiles PASSED [ 50%]
tests/test_scan_all_batch_orchestration.py::test_batch_active_scan_security_gate PASSED [ 54%]
tests/test_scan_all_batch_orchestration.py::test_concurrency_throttling_strict_cap PASSED [ 59%]
tests/test_scan_all_batch_orchestration.py::test_per_asset_lock_mutual_exclusion PASSED [ 63%]
tests/test_scan_all_batch_orchestration.py::test_resource_optimization_queue_drain PASSED [ 68%]
tests/test_scan_all_batch_orchestration.py::test_cooperative_batch_cancellation PASSED [ 72%]
tests/test_scan_all_batch_orchestration.py::test_batch_cancel_process_tree_termination PASSED [ 77%]
tests/test_scan_all_batch_orchestration.py::test_batch_telemetry_active_threads_endpoint PASSED [ 81%]
tests/test_scan_all_batch_orchestration.py::test_scan_lifecycle_alert_notifications PASSED [ 86%]
tests/test_scan_all_batch_orchestration.py::test_frontend_logo_and_brand_contract PASSED [ 90%]
tests/test_scan_all_batch_orchestration.py::test_frontend_scan_all_ui_liquid_glass_contract PASSED [ 95%]
tests/test_scan_all_batch_orchestration.py::test_backward_compatibility_single_scan_api PASSED [100%]

============================= 22 passed in 12.51s =============================
```

### 4.2. Runtime Live Verification of Dynamic Metrics Endpoints
ASGI Endpoint Probe:
- `GET /api/v1/metrics/charts/scanner-performance` -> `HTTP 200`
  - Output: `[{'engine': 'Empire Consolidated Suite', 'total_executions': 1, 'completed': 1, 'failed': 0, 'success_rate': 100.0, 'avg_duration_seconds': 0.0}, {'engine': 'Nuclei', 'total_executions': 24, 'completed': 0, 'failed': 0, 'success_rate': 0.0, 'avg_duration_seconds': 0.0}, ...]`
- `GET /api/v1/metrics/charts/intelligence-activity` -> `HTTP 200`
  - Output: `{'total_cves_indexed': 15, 'cisa_kev_active': 6, 'high_epss_exploitable': 12, 'detection_rules_active': 0, 'last_sync': '2026-11-10 00:56 UTC'}`

### 4.3. Frontend TypeScript Typecheck
Command:
```bash
npm --prefix frontend run typecheck
```
Output:
```text
> noosforge-sentinel-frontend@1.0.0 typecheck
> tsc --noEmit
(Exit code: 0)
```

### 4.4. Frontend ESLint
Command:
```bash
npm --prefix frontend run lint
```
Output:
```text
> noosforge-sentinel-frontend@1.0.0 lint
> next lint

✔ No ESLint warnings or errors
(Exit code: 0)
```

### 4.5. Frontend Next.js Production Build
Command:
```bash
npm --prefix frontend run build
```
Output:
```text
> noosforge-sentinel-frontend@1.0.0 build
> next build

  ▲ Next.js 14.2.35
   Creating an optimized production build ...
 ✓ Compiled successfully
   Generating static pages (19/19) ...
 ✓ Generating static pages (19/19)
   Finalizing page optimization ...

Route (app)                              Size     First Load JS
┌ ○ /                                    14.1 kB         101 kB
├ ○ /_not-found                          871 B          87.8 kB
├ ○ /alerts                              4.8 kB         91.7 kB
├ ○ /analytics                           7.6 kB         94.5 kB
├ ○ /assets                              5.62 kB        92.5 kB
├ ○ /assets/[id]                         11.7 kB        98.6 kB
├ ○ /auth/login                          3.97 kB        90.9 kB
├ ○ /baselines                           5.77 kB        92.7 kB
├ ○ /findings                            8.05 kB        94.9 kB
├ ○ /findings/[id]                       10.7 kB        97.6 kB
├ ○ /health                              7.85 kB        94.7 kB
├ ○ /intel                               9.99 kB        96.9 kB
├ ○ /reports                             7.63 kB        94.5 kB
├ ○ /rules                               11 kB          97.9 kB
├ ○ /scans                               14.8 kB         102 kB
├ ○ /scans/batch                         12.1 kB        99.1 kB
├ ○ /scans/loop-test                     8.7 kB         95.6 kB
├ ○ /schedules                           6.33 kB        93.2 kB
└ ○ /settings                            5.84 kB        92.7 kB
+ First Load JS shared by all            86.9 kB
(Exit code: 0)
```
All 19 routes statically prerendered with 0 errors.
