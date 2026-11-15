# EMPIRE EDUCATIONAL PLATFORM — END-TO-END SECURITY ASSESSMENT WORKFLOW

**Workflow Version**: 2.4.0  
**Target Architecture**: 8-Stage Closed-Loop Vulnerability Management & Assessment Lifecycle  
**Governing Standard**: NIST SP 800-115 / OWASP ASVS 4.0 / ISO 27001  
**Platform**: NOOSFORGE Security Intelligence / Noospire  

```
+--------------------------------------------------------------------------------------------------------+
|                                    8-STAGE CLOSED-LOOP WORKFLOW                                        |
+--------------------------------------------------------------------------------------------------------+
| [1. Onboarding]  -->  [2. Scope Gate]  -->  [3. Preflight]   -->  [4. Dispatch & Execution]            |
|       |                                                                     |                          |
| [8. Report Export] <-- [7. Retest]    <--  [6. Triage]      <--  [5. Live Telemetry & SSE]             |
+--------------------------------------------------------------------------------------------------------+
```

---

## Stage 1: Target Asset Onboarding & Inventory Mapping

Every security assessment begins with explicit inventory registration and architectural classification:

### 1.1 Asset Registration & Deduplication
1. **Single Target Registration**: Target locator URL, asset type (`WEB_APP`, `API_ENDPOINT`, `OBJECT_STORAGE`), environment (`PRODUCTION`, `STAGING`), criticality (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), and Empire Business Module assignment.
2. **Bulk Inventory Import**: Supports CSV, JSON, and OpenAPI specifications (`POST /api/v1/assets/bulk-import`). Existing assets are identified by normalized locator (`target_locator.rstrip("/")`) and deduplicated without creating duplicate database rows.
3. **Module Assignment**: Targets are classified into one of the 6 canonical Empire modules:
   - `STUDENT_MANAGEMENT` (Better-Auth, Student IDs)
   - `LEARNING_MATERIALS` (MinIO S3, `/media` host)
   - `SUPPORTING_TOOLS` (News feed, vocabulary)
   - `API_SERVICES` (Central Gateway `gw.empire.edu.vn`)
   - `WEB_APPLICATION` (Primary portal, Admin SPA)
   - `SERVER_INFRASTRUCTURE` (Host OS, perimeter networks)

### 1.2 Asset Ownership Verification Gate
Active, intrusive, or high-intensity probes are strictly blocked until asset ownership is verified:
- **DNS TXT Record**: Verification token placed in `_noospire-challenge.<domain>`.
- **HTTP Well-Known**: Token served at `/.well-known/noospire-verification.txt`.
- **Admin Override**: Cryptographically signed by the Sole Owner.

---

## Stage 2: Immutable Scope Authorization Gate

Before any probe is scheduled, the target must pass the backend `ScopeValidator` (`backend/app/core/scope_gate.py`):

1. **Existence Verification**: Verifies the target asset exists in inventory.
2. **Scope Record Check**: Verifies an active `AssetAssessmentScope` record exists for the asset. Missing scope immediately raises `HTTP 403 SCOPE_MISSING`.
3. **Emergency Stop Intercept**: Verifies `emergency_stop_active == False`.
4. **Scope Expiry Check**: Compares `expires_at` against current UTC time; expired scope yields `HTTP 403 SCOPE_EXPIRED`.
5. **Ownership Status**: If active probes are requested, confirms `verification_status == VERIFIED`.
6. **Egress Boundary & SSRF Defense**: `SSRFProtector.validate_target()` verifies the locator does not resolve to RFC 1918 subnets, loopback, or cloud metadata.
7. **Origin & Port Lock**: Compares target scheme, host, and port against authorized boundaries (ports 80, 443).

---

## Stage 3: Preflight Validation & Resource Quotas

Once scope authorization passes, the system constructs an immutable `ScopeValidationResult`:
- **Rate Limit Assignment**: Clamps outbound rate to max 5 rps for production targets.
- **Worker Concurrency**: Restricts concurrent executions to 2 worker threads per target.
- **Byte Budget**: Sets maximum response accumulation budget (default 50 MB).
- **Check Permitted List**: Filters requested checklist IDs against `permitted_checks`. If the scope specifies an explicit check whitelist, disallowed checks are discarded.

---

## Stage 4: Scan Job Dispatch & Execution Engine

```
+-------------------------------------------------------------------------+
|                      DISPATCH & WORKER LEASE CYCLE                      |
+-------------------------------------------------------------------------+
| 1. Commit DB Job  --> 2. Worker Claim & Lease  --> 3. Guarded Subprocess|
| (status=QUEUED)       (lease_expires_at = +60s)    (shell=False, sandbox|
|       ^                                                    |            |
|       +---------------- Heartbeat Refresh -----------------+            |
+-------------------------------------------------------------------------+
```

1. **Transactional Queue Commit**: The assessment job is committed to the database queue (`scans` / `scan_batches`) with status `QUEUED`, returning a permanent job ID.
2. **Worker Lease & Fencing Tokens**:
   - The worker acquires a lease on the scan with a 60-second deadline (`lease_expires_at = now + 60s`).
   - The worker increments the scan's `fencing_token` to fence off stale workers.
   - A background heartbeat task refreshes `heartbeat_at` and `lease_expires_at` every 15 seconds.
3. **Scanner Subprocess Invocations**:
   - **OWASP ZAP**: Invoked with structured arguments (`zap-baseline.py -t <url>`).
   - **Nuclei**: Invoked with curated non-destructive templates (`nuclei -u <url> -t <template_dir>`).
   - **Trivy**: Invoked for container and dependency inspection (`trivy fs / trivy image`).
   - **Synthetic Test Harness**: Executes BOLA (`API-001`) and BFLA (`API-005`) in-process.
   - **File Policy Engine**: Evaluates `/media` against `PUBLIC_BY_DESIGN` (`FILE-001`, `FILE-002`).

---

## Stage 5: Live Telemetry Monitor & SSE Streaming

Real-time scan observability is delivered through Server-Sent Events (SSE) and live audit buffers:

1. **Durable Event Log**: Every check transition, worker claim, probe outcome, and finding discovery emits an immutable event record to `events` table with monotonic event IDs.
2. **Resumable SSE Stream** (`/api/v1/operations/stream`):
   - Supports `Last-Event-ID` cursor replay for reconnecting browsers.
   - Replays missed events beyond event 100+ without truncation.
   - Sub-second UI updates upon server-side event commit.
3. **Live Audit Console**: Displays live stdout/stderr log buffers with colorized status markers.
4. **Emergency Pause & Cancel**: Real-time cancellation stops worker subprocess trees cleanly within 3.0 seconds via process group `SIGTERM`/`SIGKILL`.

---

## Stage 6: The 10-State Vulnerability Triage Lifecycle

Discovered findings enter the standardized 10-state triage lifecycle (`backend/app/schemas/common.py`):

```
                       +-------------------+
                       |        NEW        |
                       +---------+---------+
                                 |
                                 v
                       +-------------------+
                       |   NEEDS_TRIAGE    |
                       +---------+---------+
                                 |
             +-------------------+-------------------+
             |                   |                   |
             v                   v                   v
      +--------------+    +--------------+    +--------------+
      |  CONFIRMED   |    |FALSE_POSITIVE|    |ACCEPTED_RISK |
      +------+-------+    +--------------+    +--------------+
             |
             v
      +--------------+
      |   ASSIGNED   |
      +------+-------+
             |
             v
      +--------------+
      | IN_PROGRESS  |
      +------+-------+
             |
             v
+---------------------------+
|   FIXED_PENDING_RETEST    | <-------- (Developer Fix Submitted)
+------------+--------------+
             |
      (Retest Engine)
             |
     +-------+-------+
     |               |
     v               v
+----------+   +----------+
| RESOLVED |   | REOPENED | (Regression Confirmed)
+----------+   +----+-----+
                    |
                    +--> Back to IN_PROGRESS
```

### 6.1 Triage Security & Evidence Sanitization
- **Secret Redaction**: All comments, assignees, and evidence payloads undergo automated regex filtering removing JWTs, passwords, session tokens, API keys, and sensitive email addresses.
- **Server-Derived Audit Actors**: Triage transitions record server-verified operator usernames and timestamps in the finding's audit log (`triage_history`).

---

## Stage 7: Targeted Retesting & Positive Controls

When a vulnerability is remediated by engineering, it must be validated through targeted retesting:

1. **Rerun Original Defensive Control**:
   - The retest engine reruns the exact scanner rule against the original target locator (`POST /api/v1/findings/{id}/retest` or `POST /api/v1/findings/{id}/recheck`).
2. **Positive Control Validation**:
   - A vulnerability is marked `VERIFIED_FIXED` only if:
     1. The reproduction probe confirms the flaw is closed (e.g. returns `401 Unauthorized` or `404 Not Found` on previously exposed files).
     2. A positive control probe verifies the route and service remain healthy and functional.
3. **Regression Detection**:
   - If a retest determines the flaw remains active, status transitions to `REOPENED`, occurrence count increments, and high-priority alerts are dispatched to the Sole Owner.

---

## Stage 8: Multi-Format Audit-Grade Report Generation

Upon assessment completion, forensic reports are compiled and published:

1. **Immutable Report Snapshot**: Findings, risk scores, coverage percentages, and methodology disclosures are frozen in a point-in-time snapshot.
2. **Tri-Format Generation**:
   - **Vector PDF**: High-resolution print-ready document with executive charts, severity breakdowns, and remediation playbooks (`backend/app/reporting/pdf_builder.py`).
   - **Interactive HTML**: Responsive Liquid Glass document supporting Obsidian Dark Mode and Warm Light Theme (`backend/app/reporting/templates/html_report.jinja2`).
   - **Machine-Readable JSON**: Complete structured data model for SIEM/SOAR ingestion.
3. **Integrity & Verification**: Every artifact generates a SHA-256 content checksum stored in the database and returned via `X-Content-SHA256` HTTP header.
4. **Download Security**: Downloads require authenticated bearer session with `REPORT:READ` grant; served with `Cache-Control: private, no-store`.
