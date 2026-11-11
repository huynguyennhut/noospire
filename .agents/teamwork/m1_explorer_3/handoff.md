# Implementation Plan & Handoff Report: Dispatcher, Worker Claims & Egress Strategy

**Author**: Explorer 3 (Milestone 1 — Backend Dispatcher, Worker Claims & Egress Strategy)  
**Target Recipient**: Parent Orchestrator (`eeb1d800-7d4f-4c4f-ad8c-53143c0be2cb`) & M1 Worker  
**Working Directory**: `c:\Users\nguye\Desktop\noospire\.agents\teamwork\m1_explorer_3`  
**Date**: 2026-11-10T08:22:00Z  
**Status**: Complete Implementation Plan with Line-by-Line Code Proposals  

---

## 1. Observation

### 1.1 Backend Dispatcher & Startup Cancellation (`backend/main.py` & `backend/app/core/dispatcher.py`)

1. **Cluster-Wide Unconditional Scan Cancellation on Startup**:
   - Location: `backend/main.py:41-52`
   - Verbatim Code:
     ```python
     # 1.1 Startup: Recover stale unfinished jobs from previous sessions
     from backend.app.models.scan import Scan
     from backend.app.schemas.common import ScanStatus
     from sqlalchemy import update
     from backend.app.core.database import AsyncSessionLocal
     async with AsyncSessionLocal() as session:
         await session.execute(
             update(Scan)
             .where(Scan.status.in_([ScanStatus.QUEUED.value, ScanStatus.INITIALIZING.value, ScanStatus.RUNNING.value]))
             .values(status=ScanStatus.CANCELLED.value, error_message="Session interrupted / server restarted.")
         )
         await session.commit()
     ```
   - *Direct Impact*: Any API replica restart or second instance boot executes a blanket SQL update that cancels **all** live jobs across the cluster, even if actively executing on a surviving worker replica.

2. **Hardcoded SSRF Bypass Constant in Dispatcher**:
   - Location: `backend/app/core/dispatcher.py:632-634`
   - Verbatim Code:
     ```python
     norm_url, resolved_ip = SSRFProtector.validate_target(
         scan.target_locator, allow_private=scan.allow_private_targets or True
     )
     ```
   - *Direct Impact*: `allow_private` evaluates to `True` unconditionally, bypassing RFC 1918 and loopback address blocking regardless of target ownership or scan settings.

3. **Hardcoded Adapter Permissions and Custom Config**:
   - Location: `backend/app/core/dispatcher.py:697-706`
   - Verbatim Code:
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
   - *Direct Impact*: `allow_private_targets=True` and `custom_config={"is_verified": True}` are hardcoded constants. Unverified assets are falsely treated as verified by scanner adapters (e.g. `backend/app/scanners/zap.py:105`: `is_verified = request.custom_config.get("is_verified", False)`), completely bypassing active probe authorization checks. Target scope parameters (`rate_limit_rps`, `byte_budget`, `allowed_path_patterns`, `emergency_stop_active` in `AssetAssessmentScope`) are never loaded or passed down.

4. **Missing Worker Claim Identity & Claim Tracing**:
   - Location: `backend/app/core/dispatcher.py:228-237`, `446-496`, `570-582`
   - Current Behavior: Jobs are enqueued into an in-memory `asyncio.Queue` without a persistent claim identity. When a worker thread claims a job, it executes `thread_id = (self._thread_counter % self.max_concurrent) + 1` in memory. The database row for `Scan` remains in `QUEUED` until `_run_scan` acquires an asset lock. No worker identifier (`worker_id`) or claim timestamp is committed to the database or logged in `ScanLog`.

---

### 1.2 Target Validation & Rejection (`backend/app/api/scans.py`)

1. **Silent Fallback to ALL Assets in Batch Scan Dispatch**:
   - Location: `backend/app/api/scans.py:168-181`
   - Verbatim Code:
     ```python
     # 1. Resolve Target Assets
     if batch_in.targets == "ALL" or (
         isinstance(batch_in.targets, str) and batch_in.targets.strip().upper() == "ALL"
     ):
         asset_res = await db.execute(select(Asset))
         assets = asset_res.scalars().all()
     elif isinstance(batch_in.targets, list):
         target_uuids = [uuid.UUID(str(t)) for t in batch_in.targets]
         asset_res = await db.execute(select(Asset).where(Asset.id.in_(target_uuids)))
         assets = asset_res.scalars().all()
     else:
         asset_res = await db.execute(select(Asset))
         assets = asset_res.scalars().all()
     ```
   - *Direct Impact*:
     - If `batch_in.targets` is an unexpected string, invalid specifier, or empty, the `else:` branch silently executes `select(Asset)` without filtering, launching an unrequested platform-wide scan.
     - If `batch_in.targets` is a list of IDs where one or more targets do NOT exist (e.g., `[id_valid, id_unknown]`), `Asset.id.in_(target_uuids)` silently returns only the valid asset and drops the unknown ID without raising an error or notifying the caller.
     - If `batch_in.targets` contains non-UUID strings (e.g. target locators), `uuid.UUID(str(t))` raises an unhandled `ValueError` returning HTTP 500 instead of a clean HTTP 400 or HTTP 404.

2. **Loop-Test Target Locator Handling & Crash on None Payload**:
   - Location: `backend/app/api/scans.py:561-608`
   - Verbatim Code:
     ```python
     @router.post("/loop-test", response_model=LoopTestResponse)
     async def run_loop_test(
         payload: Optional[LoopTestRequest] = None,
         target_locator: Optional[str] = Query(None),
         current_user: User = Depends(require_operator),
         db: AsyncSession = Depends(get_db),
     ) -> Any:
         effective_loc = payload.target_locator if payload and payload.target_locator else target_locator
         ...
         for pass_idx in range(1, payload.loops + 1):  # <-- Crashes if payload is None!
             ...
             scan = Scan(
                 ...
                 allow_private_targets=True,  # <-- Hardcoded True!
                 ...
             )
     ```
   - *Direct Impact*:
     - When invoked via query parameter `/api/v1/scans/loop-test?target_locator=...` without a JSON body, `payload` is `None`, causing `AttributeError: 'NoneType' object has no attribute 'loops'` on line 595.
     - `allow_private_targets=True` is hardcoded on line 606.

---

### 1.3 Egress Controls & SSRF Protection (`backend/app/core/ssrf.py` & `backend/app/core/target_verifier.py`)

1. **Link-Local & Cloud Metadata Bypass Risk in Non-Production Mode**:
   - Location: `backend/app/core/ssrf.py:210-217`
   - Verbatim Code:
     ```python
     if cls._is_ip_blocked(ip_obj):
         if allow_private and not settings.is_production and (ip_obj.is_private or ip_obj.is_loopback):
             # Authorized private lab target bypass
             continue
         raise SSRFValidationError(
             f"Target '{hostname}' resolves to blocked network address '{ip_obj}' (SSRF security violation)."
         )
     ```
   - *Direct Impact*: In Python's `ipaddress` module, `ipaddress.IPv4Address("169.254.169.254").is_private` evaluates to `True`! Furthermore, any link-local address in `169.254.0.0/16` that is not explicitly in `CLOUD_METADATA_IPS` (e.g. `169.254.1.1`) is bypassed when `allow_private=True`.
   - *Requirement*: Cloud metadata (`169.254.169.254`, `metadata.google.internal`) and link-local (`169.254.0.0/16`, `fe80::/10`) MUST be unconditionally blocked under all environments, including development and lab modes.

2. **Absence of Socket Binding to Pre-Validated IP (DNS Rebinding Vulnerability)**:
   - Location: `backend/app/core/target_verifier.py:328-330`
   - Verbatim Code:
     ```python
     context = ssl.create_default_context()
     with socket.create_connection((hostname, port), timeout=self.timeout) as raw_sock:
         with context.wrap_socket(raw_sock, server_hostname=hostname) as ssl_sock:
     ```
   - *Direct Impact*: The raw socket connects using `(hostname, port)`. The OS resolver resolves the hostname a second time. An attacker using DNS rebinding can return a public IP on the first resolution (passing `validate_target`), and then return `127.0.0.1` or `169.254.169.254` during socket connection.
   - *Requirement*: Sockets MUST be bound directly to the pre-validated IP address (`socket.create_connection((resolved_ip, port))`) while passing `server_hostname=hostname` for TLS SNI.

---

### 1.4 Active Assessments Logging & SSE Streaming Truncation (Events 101+)

1. **Frontend Hardcoded Limit (`size=100`) and Zero Pagination**:
   - Location: `frontend/src/lib/api.ts:991-994`
   - Verbatim Code:
     ```typescript
     public async getScanLogs(scanId: string): Promise<Array<{ timestamp: string; level: string; message: string; source: string }>> {
       const data = await this.fetchJson<any>(`/scans/${scanId}/logs?size=100`);
       return Array.isArray(data) ? data : (data.items || []);
     }
     ```
   - *Direct Impact*: `getScanLogs` queries exclusively page 1 with `size=100`. Any logs beyond 100 (events 101+) are strictly concealed on page 2 and never fetched.

2. **Frontend Fallback Polling Only Uses First Page**:
   - Location: `frontend/src/app/active-assessments/page.tsx:223-237`
   - Verbatim Code:
     ```typescript
     const fetchScanLogsFallback = useCallback(async (id: string) => {
       try {
         const logsData = await api.getScanLogs(id).catch(() => []);
         if (logsData && logsData.length > 0) {
           setLogs((prev) => {
             const map = new Map<string, LogEntry>();
             prev.forEach((l) => map.set(`${l.timestamp}-${l.message}`, l));
             logsData.forEach((l: LogEntry) => map.set(`${l.timestamp}-${l.message}`, l));
             return Array.from(map.values());
           });
         }
       } catch (err) {
         console.error(err);
       }
     }, []);
     ```
   - *Direct Impact*: The fallback polling loop calls `api.getScanLogs(id)`, receiving at most 100 entries.

3. **Backend API Query Hard Ceiling**:
   - Location: `backend/app/api/scans.py:444`
   - Verbatim Code:
     ```python
     size: int = Query(50, ge=1, le=200),
     ```
   - *Direct Impact*: Even if the client passed `size=1000`, FastAPI would reject it with a validation error (`le=200`).

4. **SSE Stream In-Memory Loss Across Replicas & Late Subscribers**:
   - Location: `backend/app/api/scans.py:500-530` & `backend/app/core/dispatcher.py:126-146`
   - *Direct Impact*: `stream_scan_logs` only yields from `log_buffer.subscribe(scan_id)`. If the client connects after a scan has begun on another replica or after buffer rotation, historical logs from the `scan_logs` database table are not replayed to initialize the stream.

---

## 2. Logic Chain

```
[Observation 1.1.1: main.py lines 46-52 cancels all active/queued scans on boot]
   │
   ▼
(Step 1) In any multi-worker or multi-replica setup, when an API worker starts/restarts, it cancels active jobs across all other workers.
   │
   ▼
[Observation 1.1.2 & 1.1.3: dispatcher.py lines 633, 704-705 hardcodes allow_private or True, allow_private_targets=True, is_verified=True]
   │
   ▼
(Step 2) Scanner adapters rely on request.custom_config["is_verified"] to authorize active attacks. Hardcoding is_verified=True allows unauthorized DEEP_ACTIVE attacks on unverified hosts.
   │
   ▼
(Step 3) Hardcoding allow_private or True disables SSRF blocking inside the dispatcher worker loop, allowing scan engines to hit 127.0.0.1 or local network services.
   │
   ▼
[Observation 1.2.1: scans.py line 178-180 else: select(Asset) falls back to ALL assets]
   │
   ▼
(Step 4) If an operator sends a malformed target or non-existent list ID, the system silently falls back to scanning the entire estate instead of rejecting with HTTP 404, generating unexpected load and unauthorized traffic.
   │
   ▼
[Observation 1.3.1 & 1.3.2: 169.254.169.254 has is_private=True; sockets connect to hostname]
   │
   ▼
(Step 5) Link-local addresses could slip through when allow_private is active, and DNS rebinding allows an attacker to resolve to a benign IP during validation but connect to loopback/metadata during socket creation.
   │
   ▼
[Observation 1.4.1 - 1.4.3: api.ts line 992 requests ?size=100 with no pagination; scans.py caps at le=200]
   │
   ▼
(Step 6) When an active scan generates 105 log events, logs 101 to 105 are placed on page 2. Because frontend only polls page 1 with size=100 and backend caps at 200 without cursor replay, events 101+ are truncated and hidden from the operator console.
```

---

## 3. Caveats

1. **Backwards Compatibility with Existing Tests**: Existing tests in `tests/test_scan_all_batch_orchestration.py` test `targets="ALL"` and specific batch profiles. Changes to target validation must support `"ALL"` (case-insensitive) for authorized users while rejecting unknown individual IDs with HTTP 404.
2. **Lab Environment Private Target Support**: In non-production environments (`settings.is_production == False`), private RFC 1918 addresses (e.g. `10.0.0.0/8`, `192.168.0.0/16`) may be permitted for testing **only** when `scan.allow_private_targets` is explicitly requested **and** `settings.SSRF_ALLOW_PRIVATE_TARGETS` is enabled. Cloud metadata (`169.254.169.254`, `metadata.google.internal`) and link-local (`169.254.0.0/16`, `fe80::/10`) must **never** be permitted under any circumstances.
3. **SSE Connection Lifecycles**: A streaming SSE endpoint must yield a heartbeat comment (`: ping\n\n`) every 15 seconds to prevent intermediate reverse proxies (Nginx, AWS ALB, Cloudflare) from terminating idle connections.

---

## 4. Conclusion & Actionable Recommendations

To fully fulfill Milestone 1 requirements, the worker must implement the following concrete changes:

1. **Eliminate Startup Blanket Cancellation**: Remove the unconditional `ScanStatus.CANCELLED` update in `backend/main.py:41-52`.
2. **Implement Worker Claim Logging & Dynamic Permissions in Dispatcher**:
   - In `backend/app/core/dispatcher.py`: remove `or True`, dynamically derive `allow_private`, load `AssetAssessmentScope` to enforce rate limits and byte budgets, and derive `is_verified` dynamically from `asset.verification_status`.
   - Log explicit worker claim identities (`worker_id = f"worker-{os.getpid()}-th{thread_id}"`) and update `Scan.started_at`.
3. **Strict Target Validation & Zero Traffic on Unknown Assets**:
   - In `backend/app/api/scans.py:168-186`: if `batch_in.targets` is a list, verify every target exists; if any are missing, return HTTP 404 and create zero scans. Replace `else:` silent fallback with an explicit HTTP 400 rejection.
   - In `backend/app/api/scans.py:561-610` (`run_loop_test`): provide fallback defaults when `payload` is `None` to prevent 500 crashes, and use dynamic `allow_private_targets`.
4. **Harden SSRF Egress & Pin Sockets to Validated IP**:
   - In `backend/app/core/ssrf.py`: ensure link-local (`169.254.0.0/16`, `fe80::/10`) and cloud metadata are strictly blocked even when `allow_private=True`.
   - In `backend/app/core/target_verifier.py`: bind raw sockets to `(resolved_ip, port)` rather than `(hostname, port)`.
5. **Fix Active Assessments Logging & SSE Streaming Beyond Event 100**:
   - In `backend/app/api/scans.py`: increase `size` limit in `get_scan_logs` to `le=1000` (default 100), and add DB replay on SSE stream initiation.
   - In `frontend/src/lib/api.ts`: update `getScanLogs` to request `size=500` or paginate until all logs are collected.
   - In `frontend/src/app/active-assessments/page.tsx`: ensure fallback polling accumulates all available pages without truncating at 100.

---

## 5. Verification Method

### 5.1 Verification Commands

1. **Run Milestone 1 Control Plane Test Suite**:
   ```powershell
   pytest tests/test_milestone_a_control_plane.py -v
   ```
2. **Run Scan All Batch Orchestration Suite**:
   ```powershell
   pytest tests/test_scan_all_batch_orchestration.py -v
   ```
3. **Run E2E Opaque Box Test Suite**:
   ```powershell
   pytest tests/test_empire_e2e_opaque_box.py -k "unknown or ssrf or loop_test or stream" -v
   ```

### 5.2 Specific Assertions to Verify

1. **Unknown Asset Rejection**:
   - `POST /api/v1/scans` with non-existent `asset_id` -> Returns `404 Not Found`.
   - `POST /api/v1/scans/batch` with `targets: ["00000000-0000-0000-0000-000000000000"]` -> Returns `404 Not Found`.
   - `POST /api/v1/scans/loop-test?target_locator=https://nonexistent.example.com` -> Returns `404 Not Found`.
2. **SSRF Blocking**:
   - Target `http://169.254.169.254/latest/meta-data/` -> Fails SSRF validation with HTTP 400.
   - Target `http://127.0.0.1:8000` in production -> Fails SSRF validation with HTTP 400.
3. **Logging Beyond 100 Events**:
   - A scan generating 120 log entries -> `GET /api/v1/scans/{id}/logs?size=200` returns `total: 120` and `items` count = 120.
   - UI Active Assessments terminal displays `Displaying 120 of 120 logged entries`.

---

## 6. Exact Line-by-Line Code Proposals

### Proposal 1: `backend/main.py`
**File**: `backend/main.py`  
**Lines**: 41–53  
**Change Description**: Remove cluster-wide scan cancellation on boot. Only clean up in local development mode if explicitly enabled, preserving multi-replica live scan safety.

```diff
--- a/backend/main.py
+++ b/backend/main.py
@@ -41,12 +41,14 @@ async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
-    # 1.1 Startup: Recover stale unfinished jobs from previous sessions
-    from backend.app.models.scan import Scan
-    from backend.app.schemas.common import ScanStatus
-    from sqlalchemy import update
-    from backend.app.core.database import AsyncSessionLocal
-    async with AsyncSessionLocal() as session:
-        await session.execute(
-            update(Scan)
-            .where(Scan.status.in_([ScanStatus.QUEUED.value, ScanStatus.INITIALIZING.value, ScanStatus.RUNNING.value]))
-            .values(status=ScanStatus.CANCELLED.value, error_message="Session interrupted / server restarted.")
-        )
-        await session.commit()
+    # 1.1 Startup: Multi-replica safe initialization
+    # Do NOT execute cluster-wide scan cancellation on startup.
+    # Live scans leased or executing on other workers/replicas must remain untouched.
+    pass
```

---

### Proposal 2: `backend/app/core/dispatcher.py`
**File**: `backend/app/core/dispatcher.py`  
**Lines**: 629–649 and 697–710  
**Change Description**: Remove `or True` in SSRF validation; replace hardcoded `allow_private_targets=True` and `custom_config={"is_verified": True}` with real dynamic permissions derived from `Asset`, `AssetAssessmentScope`, and platform settings; record worker claim identity in logs.

```diff
--- a/backend/app/core/dispatcher.py
+++ b/backend/app/core/dispatcher.py
@@ -629,9 +629,14 @@ class AsyncWorkerDispatcher(ITaskDispatcher):
             # 1. SSRF Pre-flight Validation (with lab override support)
             if asset.asset_type in (AssetType.WEB_APP.value, AssetType.DOMAIN.value, AssetType.API_ENDPOINT.value):
                 try:
+                    # Dynamic permission: allow_private strictly forbidden in production
+                    effective_allow_private = bool(
+                        scan.allow_private_targets
+                        and not settings.is_production
+                        and settings.SSRF_ALLOW_PRIVATE_TARGETS
+                    )
                     norm_url, resolved_ip = SSRFProtector.validate_target(
-                        scan.target_locator, allow_private=scan.allow_private_targets or True
+                        scan.target_locator, allow_private=effective_allow_private
                     )
                     await log_cb("system", f"Target validation PASSED for {norm_url} (Resolved: {resolved_ip})")
                 except SSRFValidationError as e:
@@ -697,14 +702,32 @@ class AsyncWorkerDispatcher(ITaskDispatcher):
+            # Load dynamic scope boundaries and verification permissions
+            from backend.app.models.scope import AssetAssessmentScope
+            scope_res = await session.execute(select(AssetAssessmentScope).where(AssetAssessmentScope.asset_id == asset.id))
+            asset_scope = scope_res.scalars().first()
+            is_asset_verified = (asset.verification_status == VerificationStatus.VERIFIED.value)
+            effective_allow_private = bool(
+                scan.allow_private_targets
+                and not settings.is_production
+                and settings.SSRF_ALLOW_PRIVATE_TARGETS
+            )
+
             exec_request = ScanExecutionRequest(
                 scan_id=scan.id,
                 asset_id=asset.id,
                 asset_type=AssetType(asset.asset_type),
                 target_locator=scan.target_locator,
                 profile=scan.profile,
                 timeout_seconds=scan.timeout_seconds,
-                allow_private_targets=True,
-                custom_config={"is_verified": True},
+                allow_private_targets=effective_allow_private,
+                custom_config={
+                    "is_verified": is_asset_verified,
+                    "worker_id": f"worker-{os.getpid()}-th{thread_id}",
+                    "rate_limit_rps": asset_scope.rate_limit_rps if asset_scope else 2,
+                    "byte_budget": asset_scope.byte_budget if asset_scope else 10485760,
+                    "concurrency_limit": asset_scope.concurrency_limit if asset_scope else 1,
+                    "permitted_checks": asset_scope.permitted_checks if asset_scope else [],
+                },
             )
+            await log_cb("dispatcher", f"Worker claimed scan execution [Worker: worker-{os.getpid()}-th{thread_id}, Verified: {is_asset_verified}, PrivateAllowed: {effective_allow_private}]")
```

---

### Proposal 3: `backend/app/api/scans.py`
**File**: `backend/app/api/scans.py`  
**Lines**: 168–186, 444, 563–608  
**Change Description**: Fix batch target resolution to reject unknown targets with HTTP 404, remove silent fallback, handle None payload in `run_loop_test`, and support log querying up to 1000 items.

```diff
--- a/backend/app/api/scans.py
+++ b/backend/app/api/scans.py
@@ -168,17 +168,36 @@ async def create_batch_scan(
     # 1. Resolve Target Assets
     if batch_in.targets == "ALL" or (
         isinstance(batch_in.targets, str) and batch_in.targets.strip().upper() == "ALL"
     ):
         asset_res = await db.execute(select(Asset))
         assets = asset_res.scalars().all()
     elif isinstance(batch_in.targets, list):
-        target_uuids = [uuid.UUID(str(t)) for t in batch_in.targets]
+        if not batch_in.targets:
+            raise HTTPException(
+                status_code=status.HTTP_400_BAD_REQUEST,
+                detail="Target list cannot be empty.",
+            )
+        try:
+            target_uuids = [uuid.UUID(str(t)) for t in batch_in.targets]
+        except (ValueError, TypeError) as ve:
+            raise HTTPException(
+                status_code=status.HTTP_400_BAD_REQUEST,
+                detail=f"Invalid target UUID format in target list: {ve}",
+            )
         asset_res = await db.execute(select(Asset).where(Asset.id.in_(target_uuids)))
         assets = asset_res.scalars().all()
+        found_ids = {a.id for a in assets}
+        missing_ids = [str(tid) for tid in target_uuids if tid not in found_ids]
+        if missing_ids:
+            raise HTTPException(
+                status_code=status.HTTP_404_NOT_FOUND,
+                detail=f"Target asset(s) not found: {', '.join(missing_ids)}",
+            )
     else:
-        asset_res = await db.execute(select(Asset))
-        assets = asset_res.scalars().all()
+        raise HTTPException(
+            status_code=status.HTTP_400_BAD_REQUEST,
+            detail=f"Invalid targets parameter: '{batch_in.targets}'. Expected 'ALL' or a non-empty list of UUIDs.",
+        )
@@ -444,3 +463,3 @@ async def get_scan_logs(
-    size: int = Query(50, ge=1, le=200),
+    size: int = Query(50, ge=1, le=1000),
@@ -563,3 +582,6 @@ async def run_loop_test(
     payload: Optional[LoopTestRequest] = None,
     target_locator: Optional[str] = Query(None),
     current_user: User = Depends(require_operator),
     db: AsyncSession = Depends(get_db),
 ) -> Any:
     """Execute sequential multi-pass assessment on the target to track stability, finding drift, and emit lifecycle alerts."""
     effective_loc = payload.target_locator if payload and payload.target_locator else target_locator
     if not effective_loc:
@@ -595,7 +617,10 @@ async def run_loop_test(
+    loops_count = payload.loops if payload else 3
+    chosen_profile = payload.profile.value if payload else ScanProfile.QUICK.value
+    engine_list = payload.engines if payload and payload.engines else ["nuclei", "zap", "empire_engine", "crawler"]
+    engine_str = ",".join(engine_list) if engine_list else "all"
+
-    for pass_idx in range(1, payload.loops + 1):
+    for pass_idx in range(1, loops_count + 1):
         pass_t0 = time.perf_counter()
-        engine_str = ",".join(payload.engines) if payload.engines else "all"
         scan = Scan(
             id=uuid.uuid4(),
             asset_id=asset.id,
             engine=engine_str,
-            profile=payload.profile.value,
+            profile=chosen_profile,
             status=ScanStatus.QUEUED.value,
             progress_percentage=0,
             target_locator=asset.target_locator,
-            allow_private_targets=True,
+            allow_private_targets=bool(not settings.is_production and settings.SSRF_ALLOW_PRIVATE_TARGETS),
             timeout_seconds=30,
         )
```

---

### Proposal 4: `backend/app/core/ssrf.py` & `backend/app/core/target_verifier.py`
**File**: `backend/app/core/ssrf.py`  
**Lines**: 204–217  
**Change Description**: Ensure cloud metadata and link-local ranges are blocked regardless of `allow_private` in any environment; bind sockets in `target_verifier.py` directly to the validated IP.

```diff
--- a/backend/app/core/ssrf.py
+++ b/backend/app/core/ssrf.py
@@ -203,8 +203,11 @@ class SSRFProtector:
-            # Cloud metadata IPs are strictly forbidden under all circumstances
-            if str(ip_obj) in cls.CLOUD_METADATA_IPS:
+            # Cloud metadata IPs and Link-Local subnets (169.254.0.0/16, fe80::/10) are STRICTLY FORBIDDEN under all circumstances
+            if str(ip_obj) in cls.CLOUD_METADATA_IPS or ip_obj.is_link_local:
                 raise SSRFValidationError(
-                    f"Target '{hostname}' resolves to cloud metadata address '{ip_obj}'."
+                    f"Target '{hostname}' resolves to protected cloud metadata / link-local address '{ip_obj}'."
                 )
 
             # Check general blocked networks
             if cls._is_ip_blocked(ip_obj):
-                if allow_private and not settings.is_production and (ip_obj.is_private or ip_obj.is_loopback):
+                if allow_private and not settings.is_production and (ip_obj.is_private or ip_obj.is_loopback) and not ip_obj.is_link_local:
                     # Authorized private lab target bypass
                     continue
```

**File**: `backend/app/core/target_verifier.py`  
**Lines**: 327–333  
**Change Description**: Bind socket connection directly to the pre-validated IP address to prevent DNS rebinding.

```diff
--- a/backend/app/core/target_verifier.py
+++ b/backend/app/core/target_verifier.py
@@ -327,5 +327,7 @@ class TargetVerificationOrchestrator:
         def _tls_probe() -> Dict[str, Any]:
             context = ssl.create_default_context()
-            with socket.create_connection((hostname, port), timeout=self.timeout) as raw_sock:
+            # Bind socket connection directly to resolved IP to prevent DNS rebinding
+            connect_target = resolved_ips[0] if (resolved_ips and len(resolved_ips) > 0) else hostname
+            with socket.create_connection((connect_target, port), timeout=self.timeout) as raw_sock:
                 with context.wrap_socket(raw_sock, server_hostname=hostname) as ssl_sock:
```

---

### Proposal 5: `frontend/src/lib/api.ts` & `frontend/src/app/active-assessments/page.tsx`
**File**: `frontend/src/lib/api.ts`  
**Lines**: 991–994  
**Change Description**: Allow retrieving logs beyond event 100 with pagination or expanded size.

```diff
--- a/frontend/src/lib/api.ts
+++ b/frontend/src/lib/api.ts
@@ -991,4 +991,5 @@ export class ApiClient {
-  public async getScanLogs(scanId: string): Promise<Array<{ timestamp: string; level: string; message: string; source: string }>> {
-    const data = await this.fetchJson<any>(`/scans/${scanId}/logs?size=100`);
-    return Array.isArray(data) ? data : (data.items || []);
+  public async getScanLogs(scanId: string, size: number = 500): Promise<Array<{ timestamp: string; level: string; message: string; source: string }>> {
+    const data = await this.fetchJson<any>(`/scans/${scanId}/logs?size=${size}`);
+    return Array.isArray(data) ? data : (data.items || []);
   }
```

**File**: `frontend/src/app/active-assessments/page.tsx`  
**Lines**: 223–237  
**Change Description**: Pass `size: 500` to `getScanLogs` in `fetchScanLogsFallback` to prevent truncating logs at 100 entries.

```diff
--- a/frontend/src/app/active-assessments/page.tsx
+++ b/frontend/src/app/active-assessments/page.tsx
@@ -223,4 +223,4 @@ function ActiveAssessmentsContent() {
   const fetchScanLogsFallback = useCallback(async (id: string) => {
     try {
-      const logsData = await api.getScanLogs(id).catch(() => []);
+      const logsData = await api.getScanLogs(id, 500).catch(() => []);
       if (logsData && logsData.length > 0) {
```

---

## 7. Report Summary Table

| Requirement Area | File Path | Existing Defect | Actionable Fix Proposal |
|---|---|---|---|
| **1. Startup Lifespan Safety** | `backend/main.py:41-52` | Blanket cancellation on boot cancels cluster-wide active scans | Remove unconditional SQL update; keep live leased jobs intact |
| **2. Dynamic Adapter Permissions** | `backend/app/core/dispatcher.py:697-706` | Hardcoded `allow_private_targets=True`, `custom_config={"is_verified": True}` | Derive dynamically from `Asset.verification_status` and `AssetAssessmentScope` |
| **3. Dispatcher SSRF Bypass** | `backend/app/core/dispatcher.py:633` | Hardcoded `or True` in `allow_private` | Derive from `scan.allow_private_targets and not settings.is_production` |
| **4. Worker Claim Tracing** | `backend/app/core/dispatcher.py:465-495` | Worker claim is untracked in logs/DB | Register worker identity `worker-{pid}-th{id}` in logs & telemetry |
| **5. Batch Target Validation** | `backend/app/api/scans.py:168-186` | Silent fallback on missing list targets and unexpected string targets | Reject unknown target IDs with HTTP 404; eliminate silent `else: select(Asset)` |
| **6. Loop-Test Rejection & Safety** | `backend/app/api/scans.py:561-608` | Crashes with 500 if `payload` is None; hardcodes `allow_private_targets=True` | Provide default fallbacks for query param calls; use dynamic private target flag |
| **7. Egress & SSRF Hardening** | `backend/app/core/ssrf.py:204-217` | Link-local (`169.254.0.0/16`) bypass in dev mode | Unconditionally block link-local and cloud metadata under all environments |
| **8. DNS Rebinding Socket Pinning** | `backend/app/core/target_verifier.py:328-330` | Socket connects to hostname via OS resolver | Bind socket connection directly to pre-validated IP address |
| **9. Events 101+ Buffering & Streaming** | `api.ts:992`, `scans.py:444`, `page.tsx:224` | `size=100` hardcoded; max query capped at 200; page 2 logs concealed | Increase query limit to 1000; query size=500 in fallback; prevent log truncation |
