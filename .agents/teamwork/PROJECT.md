# Project: Noospire - Authorized Continuous Security Assessment Platform (Empire)

## Architecture
- **Control Plane**: FastAPI async web application (`backend/app/main.py`) exposing REST APIs (`/api/v1/`) and Server-Sent Events (SSE).
- **Security & RBAC**: JWT bearer tokens, active-user enforcement, permission scopes (`admin`, `operator`, `viewer`), server-derived audit actors, CSRF protection, and minimal public health probe (`/health`).
- **Target Verification & Egress**: Dedicated `AssetOwnershipProof` (DNS TXT, HTTP well-known token challenges) and `AssetAssessmentScope` models replacing "reachable = verified"; strict egress proxy / socket IP binding denying loopback, private, link-local, and metadata destinations.
- **Dispatcher & Persistence**: Durable PostgreSQL and SQLite dispatcher with atomic job claims, leases (`lease_expires_at`), heartbeats, fencing tokens, and idempotent occurrence tracking (`ScheduleOccurrence`).
- **Data Models**: Clear separation of `RunPlan`, `CheckExecution`, `Observation`, stable `NormalizedFinding` (un-mutated across runs), `RetestExecution`, and frozen `ReportSnapshot`.
- **Check Engines**:
  - Empire Business Checks (Python/httpx): BOLA/IDOR learning records, public vs private media, login brute-force defense, English/news SSRF & XSS sinks.
  - Scanner Adapters: Nuclei (repaired `ScanProfile`, pinned templates), ZAP (baseline passive plan, multi-instance parser), Trivy (typed input, sandboxed extraction), and Native Mobile/Server (`NOT_ASSESSED`).
- **Local Synthetic Staging**: Self-contained synthetic Empire endpoints in `fixtures/` for deterministic offline integration testing.
- **Engine Updates & Rule Manifests**: Dynamic status tracking in `api/engines.py`, immutable rule manifests with SHA-256 digests, and staging -> canary -> daily promotion pipeline.
- **Reporting**: Project-scoped daily report snapshots rendered in JSON, HTML, and PDF, with change detection (new, persistent, reopened, remediated) and zero numeric posture scores under partial coverage.
- **Frontend**: Next.js 14 SPA (`frontend/`) communicating via same-origin proxy to `/api/v1/`, honest error handling (zero fake tokens/timers), and real-time SSE telemetry HUD.

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | F01_EliminateHardcodedSecrets | Remove hardcoded SECRET_KEY, admin, and ultra admin passwords; fail on missing secrets in prod | Milestone A | R1, Survey 1 |
| 2 | F02_OneTimeBootstrap | Explicit one-time bootstrap command/route permanently locking after initial admin creation | Milestone A | R1, Survey 1 |
| 3 | F03_ActiveUserSessionEnforce | Active-user verification in DB, session revocation/logout endpoint (`/auth/logout`) | Milestone A | R1, Survey 1 |
| 4 | F04_ScopedRBAC | Scoped RBAC permissions (`admin`, `operator`, `viewer`) on all operational endpoints | Milestone A | R1, Survey 1 |
| 5 | F05_ServerDerivedAuditActors | Derive audit actors for triage, rule review, and overrides from authenticated token, not client payload | Milestone A | R1, Survey 1 |
| 6 | F06_ProtectedReportDownloads | Protect `/reports/{id}/download` with same principal and scoping as report list | Milestone A | R1, Survey 1 |
| 7 | F07_CSRFAndCookieProtection | Enforce CSRF protection on mutations and secure cookie settings (HttpOnly, Secure, SameSite) | Milestone A | R1, Survey 1 |
| 8 | F08_RemoveDestructiveReset | Remove destructive `/system/reset` and `/settings/reset` in production; preserve append-only audit history | Milestone A | R1, Survey 1 |
| 9 | F09_OwnershipProofNotReachable | Replace "reachable = verified" with `AssetOwnershipProof` (DNS/HTTP challenge) and `AssetAssessmentScope` | Milestone A | R1, Survey 1 |
| 10 | F10_LocatorChangeInvalidation | Target locator changes automatically revoke existing proofs and reset verification status | Milestone A | R1, Survey 1 |
| 11 | F11_StrictNetworkEgressPolicy | Enforce socket IP binding, deny loopback/private/link-local/metadata in production, retain TLS/SNI | Milestone A | R1, Survey 1 |
| 12 | F12_RejectUnknownLoopTestAsset | Reject unknown loop-test asset locator with HTTP 404 (eliminate silent fallback) | Milestone A | R1, Survey 1 |
| 13 | F13_EnforceScanBudgets | Rate limits (1 req/s/origin), concurrency 1/origin, 100 req/asset/run, respect Retry-After & emergency stop | Milestone A | R1, Survey 1 |
| 14 | F14_CleanFirstBoot | Initial boot has no pre-verified targets, no active schedules, no invented completed scans | Milestone A | R1, Survey 1 |
| 15 | F15_DistributableSanitization | Clean historical reports from `storage/reports/`, exclude fixtures/node_modules/bloat from dist | Milestone A | R1, Survey 1 |
| 16 | F16_FrontendHonestErrorHandling | Remove silent fallback in `api.ts`, remove fake timer simulation in `scan-engine.ts`, remove fake JWT in login | Milestone A | R1, Survey 1 |
| 17 | F17_DecoupleWorkerLifespan | Decouple dispatcher/scheduler from ASGI lifespan; remove startup blanket job cancellation | Milestone B | R2, Survey 2 |
| 18 | F18_MultiReplicaSafeExecution | A second API replica boot must never cancel live jobs running on another instance | Milestone B | R2, Survey 2 |
| 19 | F19_DurableDatabaseDispatcher | Implement durable PostgreSQL/SQLite dispatcher; reject or remove inert Celery adapter | Milestone B | R2, Survey 2 |
| 20 | F20_DeterministicScheduleOccurrence| Record named timezone due occurrences (`ScheduleOccurrence`) and planned scans in one committed transaction | Milestone B | R2, Survey 2 |
| 21 | F22_JobLeasesAndFencing | Atomic job claims with lease expiry, worker heartbeat, fencing token, and bounded retries | Milestone B | R2, Survey 2 |
| 22 | F23_CrossReplicaCancellation | Propagate cancellation via DB status checks in worker execution loops; terminate process trees cleanly | Milestone B | R2, Survey 2 |
| 23 | F24_SeparatedExecutionModels | Introduce `RunPlan`, `CheckExecution`, `Observation`, and `RetestExecution` models | Milestone B | R2, Survey 2 |
| 24 | F26_StableFindingIdentity | Preserve historical finding membership; link scans via `Observation` records without mutating `scan_id` | Milestone B | R2, Survey 2 |
| 25 | F27_CaseSensitiveRouteNorm | Normalize URLs by lowercasing scheme/host only; preserve case of URL paths and mask sensitive params | Milestone B | R2, Survey 2 |
| 26 | F28_RetestNegativeSafety | 401/403/404 or network timeout on retest records INCONCLUSIVE/RETEST_ERROR and never auto-closes findings | Milestone B | R2, Survey 2 |
| 27 | F29_FrozenReportSnapshots | Re-exporting Day 1 report queries historical frozen snapshot or observations, producing unchanged content | Milestone B | R2, Survey 2 |
| 28 | F30_DatabaseMigrationsAndRollback | Structured additive migrations, backup, forward migration, and tested restore/rollback procedures | Milestone B | R2, Survey 2 |
| 29 | F31_EmpireBusinessCheckContracts | Pass policy-enforcing client, synthetic identities, time budgets, and cancellation tokens to every check | Milestone C | R3, Survey 3 |
| 30 | F32_EmpireBOLALearningRecords | BOLA check: A accesses A, B accesses B, B denied A, anon denied A; verify schema + marker (zero FP on catch-all) | Milestone C | R3, Survey 3 |
| 31 | F33_EmpirePublicMaterialsCheck | Approved published PDF returns public access without vulnerability; check private canaries & cache headers | Milestone C | R3, Survey 3 |
| 32 | F34_EmpireLoginDefenseCheck | Stage sacrificial identity, agreed threshold, known cooldown; stop on 429/lock; 5 404s produce 0 brute-force | Milestone C | R3, Survey 3 |
| 33 | F35_EmpireEnglishNewsCheck | Inert canary for reflection; SSRF against lab-owned sink with per-run correlation; redirect rejection | Milestone C | R3, Survey 3 |
| 34 | F36_NucleiAdapterRepair | Import `ScanProfile`, execute pinned/signed template bundle, cap rate/concurrency, record version/digest | Milestone C | R3, Survey 3 |
| 35 | F37_ZAPAdapterRepair | Tightly scoped baseline/passive plan, per-job report storage, parse all sites/instances, handle exit codes | Milestone C | R3, Survey 3 |
| 36 | F38_TrivyAdapterRepair | Typed input (`fs`/`image`/`sbom`), sandboxed extraction, reject traversal/symlinks, redact secret matches | Milestone C | R3, Survey 3 |
| 37 | F39_NativeMobileServerHandling | Expose `NOT_ASSESSED` explicitly when mobile/server inputs are missing | Milestone C | R3, Survey 3 |
| 38 | F40_SyntheticStagingEnvironment | Self-contained local synthetic Empire staging fixture endpoints for automated CI/regression testing | Milestone C | R3, Survey 3 |
| 39 | F41_DynamicEngineStatusAPI | Replace constant statuses in `api/engines.py`; track binary version, rule pack, advisory DB, upstream sync | Milestone D | R4, Survey 3 |
| 40 | F42_RuleLifecycleManifests | Immutable manifests with pinned SHA-256 digests, permission classes, staging -> canary -> daily promotion | Milestone D | R4, Survey 3 |
| 41 | F43_ProjectScopedDailyReport | Single project-scoped daily report snapshot (JSON, HTML, PDF) generated on batch terminal state | Milestone D | R4, Survey 3 |
| 42 | F44_ReportSchemaAndCompleteness | Planned vs executed vs conclusive checks, coverage gaps with reasons, approved public exposures | Milestone D | R4, Survey 3 |
| 43 | F45_ChangeDetectionEngine | Accurate change detection tracking new, persistent, reopened, and verified remediated findings | Milestone D | R4, Survey 3 |
| 44 | F46_IdempotentMinimalAlerts | Minimal-content idempotent notifications for scan completions and critical triage updates | Milestone D | R4, Survey 3 |
| 45 | F47_PackagingAndCleanBuild | Locked backend manifests, DB env alignment, Next.js static build behind reverse proxy with SSE | Milestone D | R4, Survey 3 |
| 46 | F48_VietnameseHandoverDocs | Full handover in Vietnamese preserving English code symbols; operator quickstart, test evidence table | Milestone D | R4, Survey 3 |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| E2E | E2E Testing Track | Design 4-tier opaque-box test suite (Tiers 1-4) & publish `TEST_READY.md` | none | PLANNED |
| 1 | Milestone A | Safe Control Plane & Clean Deployment (F01–F16, Gate A) | none | PLANNED |
| 2 | Milestone B | Repeatable Daily Work & Durable Observations (F17–F30, Gate B) | Milestone A | PLANNED |
| 3 | Milestone C | Reliable Check Engines & Synthetic Staging (F31–F40, Gate C) | Milestone A, B | PLANNED |
| 4 | Milestone D | Engine Updates, Reports & Handover Delivery (F41–F48, Gate D) | Milestone C, E2E | PLANNED |

---

## Interface Contracts

### Control Plane Auth ↔ Operational Endpoints
- Dependency: `get_current_active_user(security_scopes: SecurityScopes, token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)) -> User`
- Token format: JWT Bearer with claims: `{"sub": user_id, "username": username, "role": role, "scopes": [...], "exp": ...}`
- Active check: `User.is_active is True` and `User.tokens_valid_after <= token_issued_at`.
- Unauthorized response: HTTP 401 `{"detail": "Could not validate credentials"}`. Forbidden: HTTP 403 `{"detail": "Not enough permissions"}`.

### Target Ownership & Scope ↔ Check Engines
- `AssetOwnershipProof`: `(asset_id, challenge_token, method, status, expires_at)`
- `AssetAssessmentScope`: `(asset_id, exact_origin, allowed_path_patterns, permitted_checks, rate_limit_rps, byte_budget, emergency_stop_active)`
- Engine Preflight: Before executing active probes against `target_locator`, verify:
  1. `asset.verification_status == VerificationStatus.VERIFIED`
  2. `scope.emergency_stop_active is False`
  3. Destination IP resolved via DNS does not belong to private/loopback/link-local/metadata ranges.

### Scheduler ↔ Durable Dispatcher
- Occurrence model: `ScheduleOccurrence(id, schedule_id, due_instant, status, idempotency_key)`
- Scan claim transaction:
  ```sql
  UPDATE scans
  SET status = 'RUNNING', claimed_by = :worker_id, lease_expires_at = :lease_exp, fencing_token = fencing_token + 1
  WHERE id = :scan_id AND status = 'QUEUED';
  ```
- Worker Heartbeat: Every 30s updates `heartbeat_at = now, lease_expires_at = now + 300s`. Checks if `status == 'CANCELLED'` in DB to self-terminate.

### Check Engines ↔ Observations ↔ Findings
- Check execution record: `CheckExecution(id, scan_id, check_id, rule_digest, status, coverage_reason, confidence)`
- Normalized Finding: `NormalizedFinding(id, fingerprint, title, severity, status, first_seen_at, last_seen_at)`
  *Note*: Finding identity is stable and NOT tied to a single mutable `scan_id`.
- Observation link: `Observation(id, finding_id, scan_id, check_execution_id, observed_at, rule_digest, evidence_ref)`

### Daily Report Snapshot ↔ Output Formats
- Generation: Triggered automatically upon completion of batch or schedule occurrence.
- Schema: `ReportSnapshot(id, batch_id, project_id, snapshot_json, sha256_digest, created_at)`
- Renderers: Reads frozen `snapshot_json` to produce identical JSON, HTML (`jinja2`), and PDF (`weasyprint` / reportlab).

---

## Code Layout
- Backend Source: `backend/app/`
  - Core & Config: `backend/app/core/` (`config.py`, `security.py`, `database.py`, `dispatcher.py`, `scheduler.py`, `ssrf.py`, `target_verifier.py`)
  - API Routes: `backend/app/api/` (`auth.py`, `assets.py`, `scans.py`, `findings.py`, `reports.py`, `schedules.py`, `rules.py`, `engines.py`, `system.py`)
  - Models: `backend/app/models/` (`user.py`, `asset.py`, `proof.py`, `scope.py`, `scan.py`, `execution.py`, `finding.py`, `observation.py`, `report.py`, `schedule.py`)
  - Scanners & Checks: `backend/app/scanners/` (`empire_engine.py`, `nuclei.py`, `zap.py`, `trivy.py`, `crawler.py`)
  - Rules & Manifests: `backend/app/rules/` (`manifest.py`, `lifecycle.py`)
  - Reporting: `backend/app/reporting/` (`generator.py`, `snapshot.py`, `renderers/`)
- Fixtures & Staging: `fixtures/` (`synthetic_empire/`, `rules/`, `threat_intel/`)
- Tests: `tests/` (`e2e/`, `unit/`, `adversarial/`)
- Frontend: `frontend/` (`src/app/`, `src/components/`, `src/lib/api.ts`, `src/lib/scan-engine.ts`)
- Handover Docs: `HANDOVER_VI.md` (root)
