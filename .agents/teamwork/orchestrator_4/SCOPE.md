# Scope: "Scan All" Batch Scan Orchestration, Modern Liquid Glass UI, Official Logo, Live Thread Tracking & Telemetry

## Architecture
NOOSFORGE Security Intelligence is extending its enterprise command center to support full-spectrum "Scan All" batch scan orchestration across all registered targets, available engines, and assessment profiles with active device resource optimization. The UI is upgraded to adhere strictly to the Black/White Modern Liquid Glass design language, integrating the official logo asset, live worker thread matrix ("trackcurrent"), real-time SSE log tracking, and lifecycle toast notifications.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 24 | Batch Domain Model & Migration | `ScanBatch` model (`scan_batches` table), `batch_id` on `Scan`, SQLite WAL mode & busy timeout | M8 | Survey (R1) |
| 25 | Batch Orchestration & Resource Throttling | `POST /api/v1/scans/batch`, `psutil` CPU/RAM throttling, concurrency bounds, cooperative batch cancel & master stop | M8 | Survey (R1) |
| 26 | Live Telemetry & "trackcurrent" Feed | `GET /api/v1/scans/trackcurrent`, active worker thread matrix, lifecycle alerts in `security_alerts` | M8 | Survey (R3) |
| 27 | Brand Asset & Liquid Glass Shell Header | Ingest official logo asset into `frontend/public/brand/`, replace `<Shield>` in `Shell.tsx` across desktop, tablet, and mobile | M9 | Survey (R2) |
| 28 | Liquid Glass Toast Notification System | `frontend/src/components/ui/toast.tsx` (`ToastProvider`, `useToast()`) with backdrop-blur, specular highlight, auto-dismiss | M9 | Survey (R3) |
| 29 | "Scan All" Batch Dispatch UI Hero Card | In `frontend/src/app/scans/page.tsx`, Hero Card / Modal for "Scan All" across all targets/engines/profiles with concurrency slider | M9 | Survey (R1, R2) |
| 30 | Multi-Worker Thread Tracking ("trackcurrent") HUD | In `frontend/src/app/active-assessments/page.tsx`, active worker matrix, focus switcher, batch progress bar, cooperative cancel | M9 | Survey (R3) |
| 31 | Dual-Track Test Suite & Full Regression Pass | Automated tests `tests/test_scan_all_batch_orchestration.py` (BAT-01..BAT-13), `pytest`, `verify_empire_e2e.py`, `npm run build`, `npm run lint` | M10 | Survey (R4) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M8 | "Scan All" Batch Scan & Resource Optimization | Backend: `ScanBatch` model, SQLite WAL, batch scan dispatch API, `psutil` CPU/RAM throttling, active thread telemetry, cooperative cancellation | none | DONE |
| M9 | Modern Liquid Glass UI, Brand Logo & Notifications | Frontend: Official logo integration in `Shell.tsx`, Liquid Glass toast notifications, "Scan All" batch UI, active thread matrix ("trackcurrent") HUD | M8 | DONE |
| M10 | Dual-Track Regression & Acceptance Verification | Verification: Run and verify BAT-01..BAT-13, full pytest suite (244 tests), E2E script (10/10 PASS), Next.js build and lint clean pass | M8, M9 | DONE |

## Interface Contracts
### Batch Scan Domain & Endpoints (M8 ↔ Frontend M9)
- `POST /api/v1/scans/batch` (alias `/api/v1/scans/scan-all`):
  - Request: `{ "targets": "ALL" | list[UUID], "profiles": list[str], "engines": list[str], "concurrency_limit": int, "description": str }`
  - Response: `BatchScanResponse`: `{ "batch_id": UUID, "total_scans": int, "target_count": int, "status": "QUEUED" | "RUNNING", "scans": list[ScanRead] }`
- `GET /api/v1/scans/batches`: Returns paginated list of batches.
- `GET /api/v1/scans/batch/{batch_id}`: Returns batch detail with aggregated progress percentage and constituent scan counts.
- `POST /api/v1/scans/batch/{batch_id}/cancel`: Cooperatively cancels running and queued scans in the batch.
- `POST /api/v1/scans/stop-all`: Emergency master stop.
- `GET /api/v1/scans/trackcurrent` (alias `/api/v1/scans/telemetry`):
  - Response: `{ "active_workers": int, "max_concurrency": int, "is_throttled": bool, "system_resources": { "cpu_percent": float, "memory_percent": float, "memory_available_mb": float }, "active_threads": [ { "thread_id": int, "scan_id": UUID, "target_locator": str, "profile": str, "engine": str, "stage": str, "progress_percentage": int, "elapsed_seconds": int, "last_log": str } ] }`

### Brand Assets & UI Components (M9)
- Official Logo: `frontend/public/brand/logo.jpg` & `frontend/public/brand/logo.png`
- Header brand: In `Shell.tsx`, replace placeholder `<Shield>` with `<Image src="/brand/logo.jpg" alt="NOOSFORGE Logo" ... />` inside specular liquid-glass wrapper.
- Toast Provider: `frontend/src/components/ui/toast.tsx` exporting `ToastProvider` and `useToast()` hook.
