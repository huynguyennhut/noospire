# Original User Request

## Initial Request — 2026-11-10T07:23:10Z

Repair the scan pipeline and deliver an hourly security dashboard for Empire in the Noospire repository, running the product through its normal entry points and handing over the code with test evidence.

Integrity mode: development

## Verification Resources
Rely on existing repository code, fixtures (`fixtures/`), templates (`backend/app/reporting/templates/`), and local tests (`tests/`).

## Requirements

### R1. Fix the three-line incident first
- Eliminate silent fallback behavior in `frontend/src/lib/api.ts` and `frontend/src/lib/scan-engine.ts` where failed fetch, unsuccessful HTTP response, or HTML parsing failure triggers a local simulator or fallback data.
- Ensure both failure responses (503 and 200 SPA HTML at API path) produce a visible launch error, zero fabricated job IDs, zero local findings, and zero success notifications.
- A valid scan POST must commit a server job and return its ID. Following the immediate tracker redirect, refreshing, closing all tabs, and reopening in a second browser each recover that same job, including its engine output or a specific terminal failure.
- An unknown asset returns a clear rejection and generates zero traffic.
- Audit the three paths independently: fallback data, UI asset pagination, and backend ALL asset selection.
- Fix worker claim and dispatcher invocation in `backend/main.py` and `backend/app/core/dispatcher.py`, replacing true constants in adapter permissions with real dynamic permissions and tracing jobs through actual worker claims and engine invocations.
- Fix active assessments logging and SSE streaming (`frontend/src/app/active-assessments/page.tsx`, `backend/app/api/scans.py`) so later work (events 101+) is not concealed.
- Align Empire module fields and drill-down routes (`frontend/src/lib/api.ts`, `frontend/src/app/empire-modules/page.tsx`, `frontend/src/app/assets/page.tsx`) between API data, field names, and selection filters.
- Correct dashboard metrics and trend series in `frontend/src/app/dashboard/page.tsx` and `backend/app/api/metrics.py`, replacing inferred history and constant intel metrics with genuine measured data, defaulting to the last 7 calendar days.

### R2. Make an Ultra Scan account for the whole inventory
- Expose "Run Ultra Scan" at the top of Scan Center and on Dashboard for the owner. Submissions include scope, requested profile, chosen engines, initiator, and idempotency key, returning the committed batch ID, snapshot count, and tracker link. If the response is lost after commit, recover the original batch via idempotency key, showing "launch unconfirmed" while reconciling. Single-target launch follows the same planner with one asset ID. Preserve the exact chosen subset of engines.
- Snapshot the entire in-scope project inventory at launch across pages, retaining exact chosen subtarget, path, method, tenant, identity, environment, and policy revision. Account for each row as an execution target, alias referencing equivalent target execution, or an exclusion with an explained reason. Share evidence only when security context, scan plan, and locator semantics match.
- Plan every applicable approved engine for each eligible target. Persist a child execution per target, profile, and engine with attempt history, actual version and rule digest, worker, timestamps, coverage, result, and link to the engine report. Distinguish planned, queued, running, succeeded, failed, timed out, cancelled, unavailable, and skipped/inapplicable. Make unavailable capabilities affect coverage. Preserve separate counts for inventory entries, execution targets, engine jobs, checks, and distinct findings.
- Keep the existing adapter interface: Nuclei with versioned approved templates, scoped ZAP baseline for web, Empire's Python checks for agreed business rules, and Trivy for supplied filesystem/image/SBOM inputs. Store measured DNS/TLS/HTTP answers, latency, and certificate metadata. Fix the native Nuclei STANDARD branch missing ScanProfile import, ZAP adapter shared file report parsing, and Trivy adapter sending image targets to fs. Every operational engine must execute a known local target and produce parseable evidence.
- Enforce asset ownership, allowed origin/port/path/method, permitted probes, expiry, and revocation at dispatch and execution. Keep approved subpath throughout crawl/redirects. Enforce aggregate per-origin rate, concurrency, byte, retry, and deadline limits, TLS validation, DNS/redirect egress controls, backoff, and a working stop button. Slower, more thorough profile within approved limits. Use test identities and disposable canaries. Keep public learning materials under `/media` classified per Empire policy; compare private canaries separately.
- Refresh security advisories and approved rule packs through a versioned update job, recording last attempt, last successful update, source, version, rollback, and applicable assets. Keep new advisory, potential exposure, and verified finding distinct. Include informational through critical findings. Export covered checks and unresolved gaps.

### R3. Run hourly, survive interruption, and record real time
- Implement durable DB-backed job queue with PostgreSQL for deployed stack (and SQLite supported for local dev), keeping FastAPI/SQLAlchemy. Separate scheduler and scanner workers from API processes. Transactionally commit due occurrences and job plans; use leases, bounded retries, fencing, and idempotent result writes. Recover abandoned work after restart. Capture process exit and parsing errors separately. Heartbeats and deadlines for slow/silent engines. Disconnected browser has no effect on scan execution.
- Configure one hourly schedule for the approved Empire scope at the top of each hour in Asia/Ho_Chi_Minh as the initial setting. Persist time in UTC. API provides server time, next due instant, last scheduled run, last completed run, and scheduler health. UI shows local time, 1-second countdown, pause/resume, and reason if overdue.
- If a run takes longer than one hour, keep the current run intact, record due slots, coalesce missed work into at most one pending follow-up for the same scope, and display delay without unbounded backlog, duplicate sweeps, or fabricated completion.
- If owner clicks Run during active work, show matching active batch and offer one fresh follow-up or start independent non-overlapping work within global budget; repeated clicks reuse the request.
- On service restart, cancellation, or quiet engine: second API instance leaves leased work intact; watcher exposes status with reason. Cancellation confirmed after worker/process tree stops and persists timestamp. Do not replay potentially side-effecting probes whose execution is uncertain.
- When batch becomes terminal, tracker displays "View results" and "Today's work". Completion notification deep-links to snapshot; failed/partial runs also produce a report.
- Emit durable, ordered events with stable event ID, project, batch/target/engine/attempt, actor/service identity, occurrence time, and sanitized details. Distinct timestamps for operator-reported vs scanner-verified fixes; null for unknown times; track queue wait and runtime separately.

### R4. Deliver the operator screens
- Dashboard and service health: Default to last 7 local calendar days including today. For Empire root and subservices show reachability, latency/status, last measured time, freshness, and degraded/down/unknown states. Separate service availability from scan coverage and security findings. Show current workers/threads, queued/running/terminal engine jobs, open threats, new/reopened/verified-fixed findings, scheduled countdown, and link to today's work. Drill down from time buckets, series, severity, or status. Support keyboard, touch, table equivalents, tooltips.
- Live tracker and navigation: Searchable tree (Project → module → target → run → engine → checks/evidence) supporting direct links, breadcrumbs, browser navigation, preserved filters/scroll/selection under pagination/virtualization and incoming events.
- Findings, evidence, and tasks: "Recheck finding" (reruns original rule on original target with matching identity and controls) and "Rescan target" (launches fresh target assessment). Track first/last seen, latest observation, last recheck, assignee, task status, fix submitted, and verified time. Redacted evidence and attempt history. Mark verified fixed only when original reproduction yields expected denial/corrected result and positive control proves route/session still works; reopen on verified recurrence.
- Scan history and comparisons: Show manual, scheduled, rescan, and retest work with full metadata. Compare selected run to last comparable run (new, persistent, reopened, verified fixed, new/removed targets, unassessed items). Checkbox bulk deletion of selected terminal history with preview, confirmation, affected-record count, and server authorization. Define retention; preserve references; record deletion audits; prevent running jobs from being deleted.
- Notifications: Distinguish work threads/jobs from security threats. Group child job events under their batch (preventing 728-job flood). Persist per-user unread/read state; mark one/all read; dismiss/delete. Scrollable overlay, modal layering, Escape/outside click, keyboard focus, mobile layout, full history. Multi-user isolation.
- Empire Business Module Hub: Render all 6 catalog modules (including empty, never assessed, unavailable, restricted states) and configured additional modules. Validate response fields; link complete targets, findings, active runs, reports; ensure counts agree with records.
- Reports and downloads: Preserve established report structure (`backend/app/reporting/templates/html_report.jinja2`, `executive_summary.jinja2`, `pdf_builder.py`). Add coverage, scan-to-scan changes, and per-engine results. Provide engine-specific reports and consolidated batch report. Serve preview and authenticated PDF/HTML/JSON downloads from immutable snapshot.
- Live updates: Authenticated resumable SSE stream backed by durable events with stable SSE IDs, Last-Event-ID/cursor replay, gap detection, bounded incremental polling fallback (including events 101+). Sub-second visible updates upon event commit. 1-second countdown/elapsed time ticks.

### R5. Enforce the sole owner's authority
- Bind owner authority to dangnhutnguyen0910@gmail.com with verified, immutable server-side account ID via one-time deployment bootstrap.
- Fresh credentials via deployment secret mechanism; remove hardcoded literals from source, compiled assets, scripts, tests, logs, docs, and prompts.
- Only the owner can create/invite users and developers, activate/deactivate accounts, grant/revoke capabilities, view cross-user activity, and configure or manually launch an estate-wide Ultra Scan.
- Scoped developers see only explicitly granted assets, actions, and assigned work.
- Enforce permissions across API, DB queries, downloads, and stream subscriptions; reject client role overrides; immediately invalidate disabled accounts and revoke sessions/stream access. Scheduler uses scoped service identity.

## Acceptance Criteria

### Gate 1: Three-Line Incident & Failure Handling
- [ ] Both failure responses (503 and 200 SPA HTML at API path) produce a visible launch error, zero fabricated job IDs, zero local findings, and zero success notifications.
- [ ] Valid scan POST commits server job, returns server ID; immediate tracker redirect, refresh, tab close, and second browser reopen recover the exact same job and engine output / terminal failure.
- [ ] Unknown asset returns clear rejection (404) and generates zero network traffic.
- [ ] Dispatcher invokes genuine worker claims and actual engine execution without hardcoded true constants in adapter permissions.
- [ ] Logs and SSE stream deliver events beyond event 100 without truncation or cross-process event loss.
- [ ] Empire module cards and asset drill-downs match API schemas and carry filter state without resetting to ALL.
- [ ] Dashboard metrics display genuine measured data for the 7-day window without fabricated trend curves or static constants.

### Gate 2: Ultra Scan Orchestration & Inventory Accounting
- [ ] 379 synthetic inventory IDs fixture produces exactly 379 accounted inventory rows, 368 independent execution targets, 728 engine executions, 6 links to shared results, and 5 explained exclusions generating zero requests.
- [ ] Adding a 380th eligible asset after snapshot creation appears only on the subsequent run.
- [ ] Each operational engine adapter (Nuclei, ZAP, Empire checks, Trivy) executes against known local fixtures and produces parseable evidence.
- [ ] Subtarget path, query, and method constraints are strictly preserved across crawl and redirects.
- [ ] Egress boundaries prevent private/loopback/link-local/metadata access.

### Gate 3: Hourly Scheduling, Durability & Real-Time Eventing
- [ ] Hourly schedule triggers at the top of the hour (Asia/Ho_Chi_Minh initial setting), recording UTC timestamps.
- [ ] Runs exceeding 1 hour keep active execution intact, record due slots, and coalesce missed work into at most one pending follow-up.
- [ ] Manual launch during an active run displays the active batch, prevents duplicate sweep, and allows at most one queued follow-up.
- [ ] Service restart recovers abandoned leased work; cancellation stops worker process tree cleanly and persists terminal status with reason.
- [ ] SSE stream supports cursor replay and bounded polling for events 101+; UI reflects committed events within 1 second on local stack.

### Gate 4: Operator UI, Findings Workflow & Reports
- [ ] Dashboard displays 7 calendar days with accurate service reachability, engine queue status, threat counts, and 1-second countdown timer.
- [ ] Live tracker renders hierarchical tree with search, deep linking, and intact selection during live event delivery.
- [ ] Recheck finding reruns original rule on original target with verified fixed requiring positive control; rescan target runs fresh assessment.
- [ ] Checkbox bulk deletion of terminal history requires confirmation, updates record counts, and prevents deletion of running jobs or audit logs.
- [ ] Notifications deduplicate job events under batch headers, isolate read/unread state per user, and link to affected objects.
- [ ] All 6 catalog modules render accurately with zero-asset and error handling.
- [ ] Engine-specific and consolidated batch reports generate preview and authenticated PDF/HTML/JSON downloads from immutable snapshot.

### Gate 5: Sole Owner RBAC & Privileged Enforcement
- [ ] Bootstrap securely establishes dangnhutnguyen0910@gmail.com as sole owner.
- [ ] Privileged actions (user management, role granting, estate-wide scan launch) strictly reject unauthenticated, deactivated, forged-role, or scoped-developer requests.
- [ ] Disabling a user account immediately invalidates active sessions, stream connections, and API tokens.
- [ ] Zero secrets in source, config, test output, or client-accessible payloads.

### Gate 6: Dual-Pass Verification (Pass A & Pass B)
- [ ] Every feature in the verification agreement matrix has independently recorded Pass A (API/worker/contract) and Pass B (built UI/browser replay) evidence on isolated local targets.
- [ ] Full smoke verification flow passes on clean deployment and migrated deployment.
- [ ] Handover documentation delivered with verification ledger, tested startup/upgrade/rollback commands, and sanitized sample report.
