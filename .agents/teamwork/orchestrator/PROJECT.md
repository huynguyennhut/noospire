# Project: Empire Security Pipeline & Hourly Dashboard

## Architecture
- **Control Plane & Auth**: FastAPI REST APIs with PostgreSQL / SQLite support via async SQLAlchemy. Sole owner RBAC bound to `dangnhutnguyen0910@gmail.com`. Server-derived audit actors, token revocation, clean first boot.
- **Durable Queue & Dispatcher**: Decoupled scanner/scheduler workers running alongside API. DB-backed queue with atomic leases, heartbeats, fencing tokens, cancellation cascades, and restart recovery.
- **Scheduling & Real-Time Eventing**: Cron scheduler at top of hour in Asia/Ho_Chi_Minh (UTC stored). Missed run coalescing (max 1 pending follow-up). Durable events with stable IDs, SSE streaming with cursor replay and bounded polling fallback.
- **Engine Adapters & Ultra Scan Planner**: Adapters for Nuclei, ZAP baseline, Empire Python checks, and Trivy. 379 synthetic inventory accounting with snapshot boundaries. Strict scope and egress controls.
- **Operator Frontend**: Next.js 14 / React dashboard, live tracker, findings management, bulk history deletion, batch-grouped notifications, authenticated report downloads.

---

## Feature Inventory
Every requirement from ORIGINAL_REQUEST.md is enumerated and assigned to a milestone.

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Silent Fallback Elimination | Remove fallback handlers in `api.ts` & `scan-engine.ts`; 503 & 200 SPA HTML return visible error, zero fake IDs/findings | M1 | R1 |
| 2 | Scan POST & Job Recovery | Valid scan POST commits DB job; refresh, tab close, second browser reopen recovers exact job & status | M1 | R1 |
| 3 | Unknown Asset Rejection | Unknown target locator returns 404 and generates zero network traffic | M1 | R1 |
| 4 | Three Paths Audit | Audit fallback data, UI asset pagination, backend ALL asset selection | M1 | R1 |
| 5 | Dispatcher Worker Claims | Replace hardcoded true constants in adapter permissions with dynamic permissions; trace worker claims | M1 | R1 |
| 6 | Sole Owner Bootstrap | Bootstrap `dangnhutnguyen0910@gmail.com` as immutable sole owner; fresh secrets; remove hardcoded credentials | M1 | R5 |
| 7 | Scoped RBAC & Session Revocation | Enforce permissions across APIs/DB/streams; immediate session revocation on account disablement; scoped developer isolation | M1 | R5 |
| 8 | Durable DB Job Queue | PostgreSQL / SQLite DB queue, SQLAlchemy models, separate worker/scheduler processes, leases, fencing, retries, restart recovery | M2 | R3 |
| 9 | Engine Lifespan & Cancellation | Decouple workers from ASGI boot; heartbeats; process tree termination with timestamp persistence; no startup blanket cancellation | M2 | R3 |
| 10 | Hourly Scheduler & Coalescing | Hourly cron at top of hour in Asia/Ho_Chi_Minh (UTC stored); runs >1h coalesce to max 1 follow-up; active run deduplication | M2 | R3 |
| 11 | Resumable Eventing & SSE | Durable ordered events table with stable IDs; SSE stream with Last-Event-ID, cursor replay, gap detection, bounded polling for events 101+ | M2 | R1, R3, R4 |
| 12 | Engine Adapters Remediation | Nuclei STANDARD branch ScanProfile import fix; ZAP report parsing fix; Trivy image vs fs fix; Empire checks false-positive fixes | M3 | R2 |
| 13 | Ultra Scan Planner & Accounting | 379 synthetic inventory accounting (379 rows -> 368 targets, 728 executions, 6 shared links, 5 exclusions); 380th asset boundary | M3 | R2 |
| 14 | Scope & Egress Enforcement | Preserved subtarget path/query/methods; egress boundaries denying private/loopback/link-local/metadata; rate/concurrency limits | M3 | R2 |
| 15 | Rule & Advisory Updates | Versioned update job with rollback, applicable assets, distinction between advisory vs exposure vs verified finding | M3 | R2 |
| 16 | Dashboard & Service Health | 7 calendar days measured data; root & subservices reachability/freshness; worker/threat counts; 1s countdown | M4 | R1, R4 |
| 17 | Live Tracker & Navigation | Searchable tree (Project -> module -> target -> run -> engine -> checks); deep linking; state preserved during events | M4 | R4 |
| 18 | Findings Workflow & Positive Controls | "Recheck finding" (verified fixed requires positive control) & "Rescan target"; finding vs observation separation; redacted evidence | M4 | R4 |
| 19 | Scan History & Bulk Deletion | History comparison to last comparable run; bulk terminal deletion with preview, confirmation, counts; running job protection | M4 | R4 |
| 20 | Notifications & Module Hub | Batch-grouped child notifications; per-user read/unread state; 6 catalog modules with accurate record counts | M4 | R4 |
| 21 | Immutable Reports & Downloads | Consolidated batch report & per-engine reports; coverage & scan-to-scan changes; PDF/HTML/JSON authenticated downloads | M4 | R4 |
| 22 | Full E2E Verification & Hardening | Pass 100% of Tiers 1-4 E2E tests, Tier 5 adversarial hardening, Dual-pass verification (Pass A & Pass B), clean/migrated deployment | M5 | Gates 1-6 |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Control Plane, RBAC & Failure Handling | Features 1, 2, 3, 4, 5, 6, 7 (R1 incident fix, Sole Owner bootstrap, RBAC enforcement, failure handling) | none | DONE |
| M2 | Durable Queue, Scheduling & Eventing | Features 8, 9, 10, 11 (Durable DB queue, leases, scheduler in Asia/Ho_Chi_Minh, SSE streaming events 101+) | M1 | IN_PROGRESS |
| M3 | Engine Adapters, Ultra Scan & Inventory | Features 12, 13, 14, 15 (Adapters fixes, 379 synthetic accounting, egress controls, rule updates) | M1, M2 | PLANNED |
| M4 | Operator UI, Findings & Reports | Features 16, 17, 18, 19, 20, 21 (Dashboard 7d, live tracker, findings positive control, bulk delete, reports) | M1, M2, M3 | PLANNED |
| M5 | Final E2E Suite, Hardening & Handover | Feature 22 (Pass 100% E2E tests Tiers 1-4, Tier 5 Adversarial hardening, Dual-pass verification, Handover) | M1, M2, M3, M4 | PLANNED |

---

## Interface Contracts

### M1 Control Plane ↔ M2 Queue & Workers
- **Authentication**: `get_current_active_user` returns validated `User` model with `role`, `id`, `is_active`.
- **Worker Claims**: Workers query pending jobs via `claim_next_job(worker_id: str, timeout_seconds: int) -> Optional[JobExecution]`.
- **Permissions**: Dynamic permissions resolved via `PermissionRegistry.get_allowed_adapters(user_role: str, scope: AssetScope) -> List[str]`.

### M2 Queue & Eventing ↔ M3 Engine Adapters
- **RunPlan & TargetExecution**: `TargetExecution(id: UUID, batch_id: UUID, target_locator: str, engine: str, profile: str, status: JobStatus)`.
- **Event Bus**: `emit_event(event_type: str, batch_id: UUID, target_id: Optional[UUID], engine: Optional[str], payload: dict) -> EventRecord`.
- **Cancellation**: `CancellationToken.is_cancelled(job_id: UUID) -> bool` checked before every external probe.

### M3 Engine Adapters ↔ M4 Findings & Reports
- **Observation Model**: `Observation(id: UUID, finding_id: UUID, run_id: UUID, check_id: str, status: str, evidence: dict, timestamp: datetime)`.
- **NormalizedFinding**: Does NOT overwrite `scan_id`; historical links stored in `Observation`.
- **Report Snapshot**: `generate_batch_report_snapshot(batch_id: UUID) -> ReportSnapshotRecord` containing frozen finding observations and engine coverage summaries.

---

## Code Layout
- `backend/app/core/`:
  - `config.py`: Dynamic settings, zero hardcoded secrets.
  - `database.py`: SQLAlchemy async engine, session factory, PostgreSQL / SQLite compatibility.
  - `security.py`: JWT encoding/decoding, password hashing, token revocation table.
  - `dispatcher.py`: DB-backed queue worker, lease heartbeats, cancellation manager.
  - `scheduler.py`: Hourly cron runner, Asia/Ho_Chi_Minh timezone, coalescing logic.
  - `ssrf.py`: Strict egress validator, socket binding, metadata / private network blocking.
- `backend/app/models/`:
  - `user.py`, `asset.py`, `scan.py`, `finding.py`, `observation.py`, `event.py`, `report.py`.
- `backend/app/scanners/`:
  - `nuclei.py`, `zap.py`, `trivy.py`, `empire_engine.py`.
- `backend/app/api/`:
  - `auth.py`, `assets.py`, `scans.py`, `findings.py`, `reports.py`, `metrics.py`, `schedules.py`.
- `frontend/src/`:
  - `lib/api.ts`, `lib/scan-engine.ts`.
  - `app/dashboard/page.tsx`, `app/active-assessments/page.tsx`, `app/empire-modules/page.tsx`, `app/assets/page.tsx`.
