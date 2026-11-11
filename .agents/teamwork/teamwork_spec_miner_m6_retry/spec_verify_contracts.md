# Specification Report: Asset Verification & Target Detail Drawer API Contracts

**Document Path**: `C:\Users\nguye\desktop\noospire\.agents\teamwork\teamwork_spec_miner_m6_retry\spec_verify_contracts.md`  
**Milestone**: Milestone 6 Retry — Asset Verification & Drawer API Contracts  
**Investigated Files**:
- `backend/app/schemas/asset.py`
- `backend/app/schemas/common.py`
- `backend/app/core/target_verifier.py`
- `backend/app/api/assets.py`
- `backend/app/models/asset.py`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/types.ts`
- `frontend/src/components/verification/TargetVerificationModal.tsx`
- `frontend/src/app/assets/page.tsx`
- `tests/test_m6_targets_scans_adversarial.py`
- `scripts/verify_m6_targets_scans.py`

---

## 1. Executive Summary & Authoritative Specification Source

This specification report details the complete, authoritative backend API contracts and forensic data structures governing **Asset Verification** and the **Target Detail Profile Drawer (5 Tabs)** within NOOSFORGE Security Intelligence.

### Authoritative Specification Sources
1. **Backend Schemas & Models**: `backend/app/schemas/asset.py`, `backend/app/schemas/common.py`, `backend/app/models/asset.py`
2. **Target Verifier Diagnostic Engine**: `backend/app/core/target_verifier.py`
3. **Mounted REST API Endpoints**: `backend/app/api/assets.py`
4. **Empirical Test Suites**: `tests/test_m6_targets_scans_adversarial.py` (9/9 passed) and `scripts/verify_m6_targets_scans.py`

---

## 2. Features Discovered & Authoritative Contracts

## Features Discovered
| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Asset Schema | `AssetResponse` / `AssetRead` | Complete schema representing an asset in inventory | None (serialization model) | JSON object with 19 fields | ValidationError on type mismatch | `backend/app/schemas/asset.py:56` |
| 2 | Asset Verification | `POST /api/v1/assets/{id}/verify` | Executes 8-step live network probe and updates verification status | `asset_id: UUID`, `AssetVerifyRequest` | `AssetVerifyResponse` (steps, fingerprint, verdict) | 404 if asset not found; 422 if invalid UUID | `backend/app/api/assets.py:654` |
| 3 | Verification Steps | 8-Step Probe Pipeline | 8 sequential live diagnostic network checks | `target_locator: str`, `allow_private: bool` | `List[VerificationStepResult]` | Returns `status: "FAIL"` for failed steps | `backend/app/core/target_verifier.py:38` |
| 4 | Forensic Fingerprinting | Infrastructure Fingerprint | Server, WAF/proxy, framework, tech list, and security headers | `httpx.Response`, discovery data | `TargetFingerprint` dict | Defaults to "Unknown" / "None detected" | `backend/app/core/target_verifier.py:608` |
| 5 | Target Drawer | `GET /api/v1/assets/{id}/summary` | Aggregated finding metrics, last scan status, and telemetry for Drawer Tab 1 | `asset_id: UUID` | `AssetSummary` dict | 404 if asset not found | `backend/app/api/assets.py:578` |
| 6 | Bulk Ingestion | `POST /api/v1/assets/bulk-preview` | Previews and partitions targets into new vs duplicate against DB and intra-batch | `AssetBulkPreviewRequest` (TXT, CSV, JSON, OpenAPI) | `AssetBulkPreviewResponse` (`total`, `new`, `duplicate`) | 422 on malformed request | `backend/app/api/assets.py:256` |
| 7 | Bulk Ingestion | `POST /api/v1/assets/bulk-import` | Commits batch of targets into database with deduplication | `AssetBulkImportRequest` | `AssetBulkImportResponse` (`imported_count`, `skipped_duplicates`, `errors`, `imported_assets`) | 422 on malformed input | `backend/app/api/assets.py:141` |
| 8 | Target CRUD | `GET /api/v1/assets` | Paginated listing of asset inventory with multi-field search and filters | Query: `page`, `size`, `asset_type`, `empire_module`, `environment`, `verification_status`, `search` | `PaginatedResponse[AssetResponse]` | 422 on out-of-range page/size | `backend/app/api/assets.py:52` |
| 9 | Target CRUD | `POST /api/v1/assets` | Creates a new target asset in inventory | `AssetCreate` body | `AssetResponse` (201 Created) | 400 if target locator already exists; 422 on invalid schema | `backend/app/api/assets.py:104` |
| 10 | Target CRUD | `GET /api/v1/assets/{id}` | Retrieves a single asset by UUID | `asset_id: UUID` path | `AssetResponse` | 404 if not found | `backend/app/api/assets.py:566` |
| 11 | Target CRUD | `PUT /api/v1/assets/{id}` | Partially updates asset properties | `asset_id: UUID`, `AssetUpdate` body | `AssetResponse` | 404 if not found | `backend/app/api/assets.py:617` |
| 12 | Target CRUD | `DELETE /api/v1/assets/{id}` | Deletes target asset and associated cascades | `asset_id: UUID` path | 204 No Content | 404 if not found | `backend/app/api/assets.py:640` |

---

## 3. Edge Cases & Observed Behavior

## Edge Cases
| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | Target Verification | `allow_private: false` against `127.0.0.1` or `10.0.0.0/8` | Step 1 fails with `SSRFValidationError`, pipeline halts immediately with Step 8 `status: "FAIL"`, total 2 steps returned. |
| 2 | Target Verification | `allow_private: true` against loopback / lab target | Step 1 and Step 2 pass with `"Simulated DNS resolution under private lab bypass: {hostname} -> 127.0.0.1"`, `lab_simulated: true`. |
| 3 | TLS Verification | Plain HTTP target (`http://...`) | Step 3 returns `status: "INFO"` and `metadata: {"tls_active": false, "scheme": "http"}`. It does not fail the pipeline. |
| 4 | TLS Verification | Expired TLS Certificate (`days_until_expiry <= 0`) | Step 3 returns `status: "FAIL"`, `metadata.expired: true`. Pipeline verdict evaluates to `FAILED` unless `ADMIN_OVERRIDE` is set. |
| 5 | Redirect Inspection | Protocol Downgrade (HTTPS redirects to HTTP) | Step 5 returns `status: "FAIL"`, `detail: "Insecure protocol downgrade detected: HTTPS redirected to plain HTTP..."`, `protocol_downgrade: true`. |
| 6 | HTTP Connectivity | HTTP 401, 403, 404, 502, 503 response codes | Considered reachable (`status < 500 or status in (502, 503)`). Step 4 returns `status: "PASS"`. Proves live HTTP service. |
| 7 | HTTP Connectivity | Network timeout (> 10.0s) or connection refused | Step 4 returns `status: "FAIL"`, `metadata.error: "Timeout"` or `RequestError`. Step 8 fails. |
| 8 | Bulk Preview | Intra-batch duplicate (`https://lms-stress.empire.edu.vn` twice) | First occurrence added to `new[]`; second occurrence added to `duplicate[]` with `reason: "Duplicate target entry detected within current import batch"`. |
| 9 | Bulk Preview | Target locator already exists in database | Added to `duplicate[]` with `reason: "Target locator already registered in inventory (Asset ID: <uuid>)"` and `existing_asset_id: "<uuid>"`. |
| 10 | Target Creation | Duplicate `target_locator` on `POST /api/v1/assets` | Returns HTTP 400 with `{"detail": "Target locator already registered in inventory"}`. |

---

## 4. Deep-Dive: Schema Contracts (`backend/app/schemas/asset.py` & `common.py`)

### 4.1. `AssetResponse` (Conceptually `AssetRead`)
In `backend/app/schemas/asset.py`, the asset response schema is declared as `AssetResponse` (inheriting `AssetBase`). It is serialized and returned by `GET /api/v1/assets`, `POST /api/v1/assets`, `GET /api/v1/assets/{id}`, and `PUT /api/v1/assets/{id}`.

#### Field-by-Field Definition
| Field | Type | Default | Description / Constraints |
|-------|------|---------|---------------------------|
| `id` | `uuid.UUID` (str) | Auto-generated | Unique primary key UUID |
| `name` | `str` | Required | Human-readable asset name (`min_length=1, max_length=255`) |
| `asset_type` | `AssetType` (enum) | `WEB_APP` | `'DOMAIN'`, `'WEB_APP'`, `'API_ENDPOINT'`, `'PROJECT_ARCHIVE'`, `'CONTAINER_IMAGE'`, `'OBJECT_STORAGE'`, `'SERVER'` |
| `target_locator` | `str` | Required | URL, domain, hostname, IP, or path (`min_length=1, max_length=1024`) |
| `empire_module` | `EmpireModule` (enum) | `STUDENT_MANAGEMENT` | `'STUDENT_MANAGEMENT'`, `'LEARNING_MATERIALS'`, `'SUPPORTING_TOOLS'`, `'API_SERVICES'`, `'WEB_APPLICATION'`, `'SERVER_INFRASTRUCTURE'` |
| `environment` | `str` | `"PRODUCTION"` | Environment tier (`"PRODUCTION"`, `"STAGING"`, `"DEV"`, `"LAB"`) |
| `technology` | `str` | `"Web Service"` | Detected or declared framework/server stack profile |
| `criticality` | `Criticality` (enum) | `MEDIUM` | `'LOW'`, `'MEDIUM'`, `'HIGH'`, `'CRITICAL'` |
| `exposure` | `Exposure` (enum) | `INTERNET` | `'INTERNET'`, `'INTERNAL'`, `'ISOLATED'` |
| `description` | `Optional[str]` | `None` | Optional notes, context, or asset ownership |
| `tags` | `List[str]` | `[]` | Categorization tags (e.g. `["empire", "production", "sso"]`) |
| `approved_media_baseline` | `bool` | `False` | Special policy flag permitting anonymous public access on `/media` |
| `assessment_policy` | `Dict[str, Any]` | `{}` | Persistent assessment rules, crawling limits, safe scanning scope |
| `auth_profile` | `Dict[str, Any]` | `{}` | Configured authentication credentials/headers for authenticated scans |
| `excluded_endpoints` | `List[str]` | `[]` | Scope exclusion list (e.g. `["/logout", "/delete-account"]`) |
| `verification_status` | `VerificationStatus` (enum) | `VERIFIED` | `'PENDING'`, `'VERIFIED'`, `'FAILED'`, `'REVOKED'` |
| `verification_type` | `VerificationType` (enum) | `ADMIN_OVERRIDE` | `'DNS_TXT'`, `'HTTP_WELL_KNOWN'`, `'ADMIN_OVERRIDE'` |
| `verification_token` | `str` | `sentinel-{uuid[:16]}` | Cryptographic token for DNS/HTTP ownership challenge |
| `verified_at` | `Optional[str]` | `None` | ISO 8601 UTC timestamp when verification succeeded |
| `created_at` | `datetime` (ISO str) | Auto | Record creation timestamp |
| `updated_at` | `datetime` (ISO str) | Auto | Record last modification timestamp |

#### Reconciliation of Conceptual vs Implemented Schema Fields
Some early platform drafts referenced field names that map directly to the implemented schema:
- `metadata_json`: Mapped to `assessment_policy` and `auth_profile` (plus frontend `tags`).
- `verification_policy`: Mapped to `verification_type` and `assessment_policy.verification_policy`.
- `scope_declaration`: Mapped to `excluded_endpoints` and `target_locator` boundary rules.

### 4.2. `AssetVerifyRequest`
Payload sent to `POST /api/v1/assets/{id}/verify`:
```json
{
  "verification_type": "ADMIN_OVERRIDE", // "DNS_TXT" | "HTTP_WELL_KNOWN" | "ADMIN_OVERRIDE"
  "allow_private": true                 // Permits loopback/staging RFC1918 addresses
}
```

### 4.3. `AssetVerifyResponse`
Schema returned by `POST /api/v1/assets/{id}/verify`:
```json
{
  "asset_id": "e4304f02-40e7-4135-b19e-0bd3b2bf431a",
  "verification_status": "VERIFIED",
  "verified": true,
  "status": "VERIFIED",
  "message": "All verification steps passed successfully in 1434.98ms. Target id.empire.edu.vn is live, reachable, and authenticated.",
  "steps": [
    {
      "step": 1,
      "name": "Input Validation",
      "status": "PASS",
      "detail": "Target syntax and SSRF security policies verified for https://id.empire.edu.vn",
      "metadata": {
        "scheme": "https",
        "hostname": "id.empire.edu.vn",
        "port": 443,
        "normalized_url": "https://id.empire.edu.vn",
        "ssrf_validated": true,
        "initial_ip": "103.142.26.18"
      }
    }
  ],
  "fingerprint": {
    "server": "envoy",
    "reverse_proxy_waf": "Envoy Reverse Proxy",
    "framework": "Generic Web",
    "technologies": ["Envoy"],
    "security_headers": {
      "strict_transport_security": "max-age=31536000; includeSubDomains",
      "content_security_policy": null,
      "x_frame_options": "SAMEORIGIN",
      "x_content_type_options": "nosniff",
      "referrer_policy": "strict-origin-when-cross-origin"
    },
    "active_security_headers_count": 4
  }
}
```

### 4.4. `AssetSummary` (`GET /api/v1/assets/{id}/summary`)
Used by Tab 1 of the Target Detail Drawer:
```json
{
  "asset_id": "e4304f02-40e7-4135-b19e-0bd3b2bf431a",
  "name": "Empire Identity & Student Management",
  "target_locator": "https://id.empire.edu.vn",
  "empire_module": "STUDENT_MANAGEMENT",
  "environment": "PRODUCTION",
  "critical_findings": 0,
  "high_findings": 2,
  "open_findings": 7,
  "fixed_findings": 1,
  "total_findings": 8,
  "last_assessment_at": "2026-11-08T15:20:12.123456+00:00",
  "last_scan_status": "COMPLETED"
}
```

### 4.5. Bulk Ingestion Schemas (`bulk-preview` and `bulk-import`)
- `AssetBulkPreviewRequest`:
  - `import_type`: `str` (`"AUTO"`, `"CSV"`, `"JSON"`, `"TXT"`, `"OPENAPI"`, `"CIDR"`, `"IP"`, `"URL"`)
  - `raw_content`: `Optional[str]`
  - `items`: `Optional[List[AssetBulkImportItem]]`
- `AssetBulkPreviewResponse`:
  - `total`: `int`
  - `new`: `List[BulkPreviewItem]`
  - `duplicate`: `List[BulkPreviewItem]`
- `BulkPreviewItem`:
  - `target_locator`: `str`
  - `name`: `str`
  - `asset_type`: `AssetType`
  - `empire_module`: `EmpireModule`
  - `environment`: `str`
  - `criticality`: `Criticality`
  - `is_duplicate`: `bool`
  - `existing_asset_id`: `Optional[str]`
  - `reason`: `Optional[str]`

---

## 5. Authoritative Target Verifier Engine (`backend/app/core/target_verifier.py`)

The verification engine runs 8 ordered network probe stages. All 8 steps and their exact signatures, behaviors, and metadata outputs are:

### Step 1: Input Validation
- **Sequence Number**: `1`
- **Name**: `"Input Validation"`
- **Status Values**: `"PASS"` | `"FAIL"`
- **Diagnostics**:
  - Validates URL syntax, host parsing, scheme whitelist (`http` or `https` only).
  - Enforces `SSRFProtector.validate_target`: blocks private/loopback/cloud-metadata addresses (`169.254.169.254`, `127.0.0.1`, RFC1918) unless `allow_private=True`.
- **PASS Detail**: `f"Target syntax and SSRF security policies verified for {normalized_url}"`
- **FAIL Detail**: `f"Input validation rejected target: {exc}"`
- **PASS Metadata**:
  ```json
  {
    "scheme": "http" | "https",
    "hostname": "id.empire.edu.vn",
    "port": 443,
    "normalized_url": "https://id.empire.edu.vn",
    "ssrf_validated": true,
    "initial_ip": "103.142.26.18"
  }
  ```
- **FAIL Metadata**:
  ```json
  {
    "error": "SSRF violation...",
    "ssrf_validated": false
  }
  ```

### Step 2: DNS Resolution
- **Sequence Number**: `2`
- **Name**: `"DNS Resolution"`
- **Status Values**: `"PASS"` | `"FAIL"`
- **Diagnostics**:
  - Resolves authoritative IPv4 (`A`) and IPv6 (`AAAA`) addresses asynchronously via `loop.getaddrinfo`.
  - In private lab mode (`allow_private=True`), provides simulated fallback (`127.0.0.1`) if external DNS resolution fails.
- **PASS Detail**: `f"Resolved {len(all_ips)} IP addresses for {hostname} (IPv4: {len(ipv4_addrs)}, IPv6: {len(ipv6_addrs)})"`
- **FAIL Detail**: `f"DNS resolution failed for hostname '{hostname}': {exc}"`
- **PASS Metadata**:
  ```json
  {
    "hostname": "id.empire.edu.vn",
    "ipv4_addresses": ["103.142.26.18", "103.142.26.19"],
    "ipv6_addresses": ["2405:4803:c400::18"],
    "total_ips": 3,
    "lab_simulated": false
  }
  ```
- **FAIL Metadata**:
  ```json
  {
    "hostname": "id.empire.edu.vn",
    "error": "getaddrinfo failed..."
  }
  ```

### Step 3: TLS Verification
- **Sequence Number**: `3`
- **Name**: `"TLS Verification"`
- **Status Values**: `"PASS"` | `"FAIL"` | `"INFO"`
- **Diagnostics**:
  - For HTTP targets: skipped with `"INFO"` (`"Scheme is 'http'; TLS handshake verification not applicable."`).
  - For HTTPS targets: performs TLS handshake, inspects peer certificate, verifies certificate trust chain, extracts Subject CN, Issuer Org, SANs, TLS version (`TLSv1.3`), cipher suite (`TLS_AES_256_GCM_SHA384`), and calculates `days_until_expiry`.
  - Fails if certificate is expired (`days_until_expiry <= 0`) or handshake fails.
- **PASS Detail**: `f"TLS certificate valid (Issued by {issuer_org}, expires in {days_until_expiry} days)"`
- **FAIL Detail**: `f"TLS certificate expired {abs(days_until_expiry)} days ago ({not_after_str})."` or SSL error.
- **PASS Metadata**:
  ```json
  {
    "subject": "id.empire.edu.vn",
    "issuer": "Let's Encrypt / Cloudflare Inc",
    "san": ["id.empire.edu.vn", "*.empire.edu.vn"],
    "expires_at": "Feb 15 12:00:00 2027 GMT",
    "days_until_expiry": 78,
    "tls_version": "TLSv1.3",
    "cipher": "TLS_AES_256_GCM_SHA384"
  }
  ```
- **INFO Metadata**:
  ```json
  {
    "tls_active": false,
    "scheme": "http"
  }
  ```

### Step 4: HTTP Connectivity
- **Sequence Number**: `4`
- **Name**: `"HTTP Connectivity"`
- **Status Values**: `"PASS"` | `"FAIL"`
- **Diagnostics**:
  - Executes GET probe using `User-Agent: NOOSFORGE-Security-Verifier/1.0 (+https://empire.edu.vn/security)`.
  - Measures high-resolution round-trip latency (`latency_ms`).
  - Evaluates status code: `status < 500 or status in (502, 503)` is considered reachable (proves live HTTP daemon).
- **PASS Detail**: `f"HTTP probe responded with status {status_code} in {latency_ms}ms"`
- **FAIL Detail**: `f"HTTP connectivity timed out after {timeout}s: {exc}"` or connection error.
- **PASS Metadata**:
  ```json
  {
    "status_code": 200,
    "latency_ms": 38.45,
    "http_version": "HTTP/1.1",
    "content_type": "text/html; charset=utf-8",
    "server": "cloudflare",
    "headers_count": 22
  }
  ```

### Step 5: Redirect Inspection
- **Sequence Number**: `5`
- **Name**: `"Redirect Inspection"`
- **Status Values**: `"PASS"` | `"FAIL"`
- **Diagnostics**:
  - Follows redirect chain (up to 10 hops).
  - Inspects hop-by-hop URLs and locations.
  - Detects protocol downgrade (HTTPS initial redirected to plain HTTP), returning `"FAIL"`.
- **PASS Detail**: `f"Followed {len(redirect_chain)} redirect hop(s) to landing URL: {final_url}"` or `"Direct landing without redirects on {final_url}"`.
- **FAIL Detail**: `f"Insecure protocol downgrade detected: HTTPS redirected to plain HTTP ({final_url})"`.
- **PASS Metadata**:
  ```json
  {
    "initial_url": "https://id.empire.edu.vn",
    "final_url": "https://id.empire.edu.vn",
    "redirect_count": 0,
    "redirect_chain": [],
    "protocol_downgrade": false
  }
  ```

### Step 6: Web Discovery
- **Sequence Number**: `6`
- **Name**: `"Web Discovery"`
- **Status Values**: `"PASS"`
- **Diagnostics**:
  - Concurrently probes 3 standard paths: `/robots.txt`, `/sitemap.xml`, and `/.well-known/security.txt`.
  - Records status code, accessibility (`status_code == 200`), content type, and snippet sample.
- **PASS Detail**: `f"Web discovery probed {len(endpoints)} standard endpoints ({accessible_count} accessible)"`
- **PASS Metadata**:
  ```json
  {
    "base_origin": "https://id.empire.edu.vn",
    "endpoints": {
      "/robots.txt": {
        "status_code": 200,
        "accessible": true,
        "content_type": "text/plain",
        "sample": "User-agent: *\nDisallow: /admin\nDisallow: /api/private\n"
      },
      "/sitemap.xml": {
        "status_code": 404,
        "accessible": false,
        "content_type": "text/html",
        "sample": null
      },
      "/.well-known/security.txt": {
        "status_code": 200,
        "accessible": true,
        "content_type": "text/plain",
        "sample": "Contact: security@empire.edu.vn\nPolicy: https://empire.edu.vn/security\n"
      }
    },
    "accessible_count": 2
  }
  ```

### Step 7: Target Fingerprint
- **Sequence Number**: `7`
- **Name**: `"Target Fingerprint"`
- **Status Values**: `"PASS"`
- **Diagnostics**:
  - Server identification: Inspects `Server`, `Via`, `X-Powered-By` headers.
  - Reverse Proxy / WAF identification: Envoy, Cloudflare Edge WAF, Nginx Web Server, AWS CloudFront.
  - Framework signatures: Next.js (`/_next/`, `x-nextjs-cache`), Express.js, FastAPI / Uvicorn, Vite / SPA.
  - Security headers posture: Evaluates 5 baseline headers (`Strict-Transport-Security`, `Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`).
- **PASS Detail**: `f"Fingerprint identified framework '{framework}' behind '{waf_or_proxy}' ({active_sec_headers}/5 baseline security headers active)"`
- **PASS Metadata & Fingerprint**:
  ```json
  {
    "server": "envoy",
    "reverse_proxy_waf": "Envoy Reverse Proxy",
    "framework": "Generic Web",
    "technologies": ["Envoy"],
    "security_headers": {
      "strict_transport_security": "max-age=31536000; includeSubDomains",
      "content_security_policy": null,
      "x_frame_options": "SAMEORIGIN",
      "x_content_type_options": "nosniff",
      "referrer_policy": "strict-origin-when-cross-origin"
    },
    "active_security_headers_count": 4
  }
  ```

### Step 8: Verification Result
- **Sequence Number**: `8`
- **Name**: `"Verification Result"`
- **Status Values**: `"PASS"` | `"FAIL"`
- **Diagnostics**:
  - Evaluates critical step passes:
    ```python
    critical_passes = (
        step1_result["status"] == "PASS"
        and step2_result["status"] == "PASS"
        and (step3_result["status"] in ("PASS", "INFO"))
        and step4_result["status"] == "PASS"
        and (step5_result["status"] in ("PASS", "INFO"))
    )
    ```
  - Calculates total execution duration (`total_duration_ms`).
- **PASS Detail**: `f"All verification steps passed successfully in {total_duration_ms}ms. Target {hostname} is live, reachable, and authenticated."`
- **FAIL Detail**: `"Target verification failed critical connectivity, security, or validation checks."` or Step 1 abort reason.
- **PASS Metadata**:
  ```json
  {
    "verdict": "VERIFIED",
    "verified": true,
    "total_duration_ms": 1434.98,
    "verified_at": "2026-11-08T17:07:12.123456+00:00",
    "steps_summary": {
      "Input Validation": "PASS",
      "DNS Resolution": "PASS",
      "TLS Verification": "PASS",
      "HTTP Connectivity": "PASS",
      "Redirect Inspection": "PASS",
      "Web Discovery": "PASS",
      "Target Fingerprint": "PASS"
    }
  }
  ```

---

## 6. Target Detail Profile Drawer Contracts (5 Tabs)

When a target is selected in `frontend/src/app/assets/page.tsx`, the Slide-Over Profile Drawer opens with 5 active tabs:

1. **Tab 1: Overview (`drawerTab === 'overview'`)**:
   - Hydrated via `GET /api/v1/assets/{id}/summary` and selected `Asset` properties.
   - Displays Verification Status Badge, Verification Method, Approved `/media` baseline toggle status, Target Environment, Network Exposure, Detected Technology, Verification Token, Timestamp of Creation & Verification, Tags list, and Description.
   - Action buttons: "Re-Verify Target (8-Step Probe)" (opens `TargetVerificationModal`) and "View Findings" (links to `/findings?asset_id={id}`).
2. **Tab 2: DNS & TLS Records (`drawerTab === 'dns_tls'`)**:
   - Authoritative DNS Resolution panel: A Records (IPv4), AAAA Records (IPv6), Authoritative Nameservers, and TTL duration.
   - TLS / SSL Certificate Posture panel: TLS Protocol (`TLSv1.3`), Cipher Suite (`TLS_AES_256_GCM_SHA384`), Certificate Authority (`Let's Encrypt / Cloudflare Inc`), SAN Matching list, and Days to Expiration count.
3. **Tab 3: Discovered Endpoints (`drawerTab === 'endpoints'`)**:
   - Table of mapped HTTP endpoints with HTTP Method (`GET`, `POST`), Endpoint Path (`/`, `/robots.txt`, `/api/v1/auth/login`, `/media/uploads/*`, `/api/student/profile`), Status Code (`200 OK`, `401 Auth`, `403 Forbidden`), and Route Classification (`PUBLIC_ROOT`, `DISCOVERY`, `AUTH_GATE`, `PUBLIC_MEDIA`, `BOLA_TARGET`).
4. **Tab 4: Scan History (`drawerTab === 'scans'`)**:
   - Hydrated via `GET /api/v1/scans?asset_id={id}&size=20`.
   - Displays list of prior executions with engine badge, scan profile, execution status, elapsed duration, findings counter, and direct link to live terminal `/active-assessments?scan_id={id}`.
5. **Tab 5: Vulnerabilities (`drawerTab === 'vulnerabilities'`)**:
   - Hydrated via `api.listFindings({ assetId: id })` (`GET /api/v1/findings?asset_id={id}&size=20`).
   - Displays vulnerability title, rule ID (`scanner_rule_id`), severity badge (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`), and lifecycle status (`OPEN`, `CONFIRMED`, `FIXED`).

---

## 7. Exact TypeScript Type Definitions (Zero `any` Casts)

To guarantee 100% type safety and eradicate all `any` casts in `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`, `frontend/src/components/verification/TargetVerificationModal.tsx`, and `frontend/src/app/assets/page.tsx`, use the following comprehensive definitions:

### 7.1. New & Enhanced Types for `frontend/src/lib/types.ts`

```typescript
// ============================================================================
// ASSET MANAGEMENT & VERIFICATION CONTRACTS (ZERO ANY)
// ============================================================================

export type VerificationType = 'DNS_TXT' | 'HTTP_WELL_KNOWN' | 'ADMIN_OVERRIDE';
export type VerificationStepStatus = 'PENDING' | 'RUNNING' | 'PASS' | 'FAIL' | 'INFO';

/**
 * 8-Step pipeline step metadata schemas
 */
export interface Step1InputValidationMetadata {
  scheme: 'http' | 'https';
  hostname: string;
  port: number;
  normalized_url: string;
  ssrf_validated: boolean;
  initial_ip?: string;
  error?: string;
}

export interface Step2DnsResolutionMetadata {
  hostname: string;
  ipv4_addresses?: string[];
  ipv6_addresses?: string[];
  total_ips?: number;
  lab_simulated?: boolean;
  error?: string;
}

export interface Step3TlsVerificationMetadata {
  subject?: string;
  issuer?: string;
  san?: string[];
  expires_at?: string;
  days_until_expiry?: number;
  tls_version?: string;
  cipher?: string;
  expired?: boolean;
  tls_active?: boolean;
  scheme?: string;
  error?: string;
}

export interface Step4HttpConnectivityMetadata {
  status_code?: number;
  latency_ms?: number;
  http_version?: string;
  content_type?: string | null;
  server?: string | null;
  headers_count?: number;
  error?: string;
  timeout_seconds?: number;
}

export interface RedirectHop {
  status_code: number;
  url: string;
  location?: string | null;
}

export interface Step5RedirectInspectionMetadata {
  initial_url: string;
  final_url: string;
  redirect_count: number;
  redirect_chain?: RedirectHop[];
  protocol_downgrade?: boolean;
  error?: string;
}

export interface WebDiscoveryEndpointResult {
  status_code: number | null;
  accessible: boolean;
  content_type?: string | null;
  sample?: string | null;
  error?: string;
}

export interface Step6WebDiscoveryMetadata {
  base_origin: string;
  endpoints: Record<string, WebDiscoveryEndpointResult>;
  accessible_count: number;
}

export interface SecurityHeadersPosture {
  strict_transport_security?: string | null;
  content_security_policy?: string | null;
  x_frame_options?: string | null;
  x_content_type_options?: string | null;
  referrer_policy?: string | null;
  [key: string]: string | null | undefined;
}

export interface Step7TargetFingerprintMetadata {
  server: string;
  reverse_proxy_waf: string;
  framework: string;
  technologies: string[];
  security_headers: SecurityHeadersPosture;
  active_security_headers_count: number;
  title?: string;
  status_code?: number;
  headers?: Record<string, string>;
  tls_info?: Step3TlsVerificationMetadata;
}

export interface Step8VerificationResultMetadata {
  verdict: 'VERIFIED' | 'FAILED';
  verified: boolean;
  total_duration_ms: number;
  verified_at?: string;
  steps_summary?: Record<string, string>;
  failed_step?: number;
}

export type VerificationStepMetadata =
  | Step1InputValidationMetadata
  | Step2DnsResolutionMetadata
  | Step3TlsVerificationMetadata
  | Step4HttpConnectivityMetadata
  | Step5RedirectInspectionMetadata
  | Step6WebDiscoveryMetadata
  | Step7TargetFingerprintMetadata
  | Step8VerificationResultMetadata
  | Record<string, unknown>;

export interface VerificationStepResult {
  step: number;
  name: string;
  status: 'PASS' | 'FAIL' | 'INFO';
  detail: string;
  metadata: VerificationStepMetadata;
}

export interface TargetFingerprint {
  server: string;
  reverse_proxy_waf: string;
  framework: string;
  technologies: string[];
  security_headers: SecurityHeadersPosture;
  active_security_headers_count: number;
  title?: string;
  status_code?: number;
  headers?: Record<string, string>;
  tls_info?: Step3TlsVerificationMetadata;
  [key: string]: unknown;
}

export interface AssetVerifyRequest {
  verification_type?: VerificationType;
  allow_private?: boolean;
}

export interface AssetVerifyResponse {
  asset_id: string;
  verification_status: VerificationStatus;
  verified: bool;
  status: 'VERIFIED' | 'FAILED';
  message: string;
  steps: VerificationStepResult[];
  fingerprint: TargetFingerprint;
}

export interface AssetSummary {
  asset_id: string;
  name: string;
  target_locator: string;
  empire_module: EmpireModuleType | string;
  environment: string;
  critical_findings: number;
  high_findings: number;
  open_findings: number;
  fixed_findings: number;
  total_findings: number;
  last_assessment_at: string | null;
  last_scan_status: ScanStatus | string | null;
}

export interface BulkPreviewItem {
  target_locator: string;
  name: string;
  asset_type: AssetType;
  empire_module: EmpireModuleType;
  environment: string;
  criticality: CriticalityTier;
  is_duplicate: boolean;
  existing_asset_id: string | null;
  reason: string | null;
}

export interface AssetBulkPreviewRequest {
  import_type?: string;
  raw_content?: string;
  items?: Array<{
    name?: string;
    target_locator: string;
    asset_type?: AssetType;
    empire_module?: EmpireModuleType;
    environment?: string;
    criticality?: CriticalityTier;
  }>;
}

export interface AssetBulkPreviewResponse {
  total: number;
  new: BulkPreviewItem[];
  duplicate: BulkPreviewItem[];
}

export interface AssetBulkImportRequest {
  import_type?: string;
  raw_content?: string;
  items?: Array<{
    name?: string;
    target_locator: string;
    asset_type?: AssetType;
    empire_module?: EmpireModuleType;
    environment?: string;
    criticality?: CriticalityTier;
  }>;
}

export interface AssetBulkImportResponse {
  imported_count: number;
  skipped_duplicates: number;
  errors: string[];
  imported_assets: Asset[];
}

export interface AssetCreateInput {
  name: string;
  target_locator: string;
  asset_type?: AssetType;
  empire_module?: EmpireModuleType;
  environment?: string;
  technology?: string;
  criticality?: CriticalityTier;
  exposure?: ExposureLevel;
  description?: string | null;
  tags?: string[];
  approved_media_baseline?: boolean;
  assessment_policy?: Record<string, unknown>;
  auth_profile?: Record<string, unknown>;
  excluded_endpoints?: string[];
}

export interface AssetUpdateInput {
  name?: string;
  empire_module?: EmpireModuleType;
  environment?: string;
  technology?: string;
  criticality?: CriticalityTier;
  exposure?: ExposureLevel;
  description?: string | null;
  tags?: string[];
  approved_media_baseline?: boolean;
  assessment_policy?: Record<string, unknown>;
  auth_profile?: Record<string, unknown>;
  excluded_endpoints?: string[];
}
```

### 7.2. Strongly-Typed Methods for `frontend/src/lib/api.ts`

Replace existing loosely typed methods in `ApiClient`:

```typescript
  // Assets & Target Management
  public async listAssets(params?: {
    page?: number;
    size?: number;
    module?: string;
    assetType?: string;
    environment?: string;
    verificationStatus?: string;
    search?: string;
  }): Promise<{ items: Asset[]; total: number; page: number; size: number; pages: number }> {
    const q = new URLSearchParams();
    if (params?.page) q.append('page', params.page.toString());
    q.append('size', (params?.size || 100).toString());
    if (params?.module) q.append('empire_module', params.module);
    if (params?.assetType) q.append('asset_type', params.assetType);
    if (params?.environment) q.append('environment', params.environment);
    if (params?.verificationStatus) q.append('verification_status', params.verificationStatus);
    if (params?.search) q.append('search', params.search);
    return this.fetchJson(`/assets?${q.toString()}`);
  }

  public async getAsset(assetId: string): Promise<Asset> {
    return this.fetchJson<Asset>(`/assets/${assetId}`);
  }

  public async createAsset(data: AssetCreateInput): Promise<Asset> {
    return this.fetchJson<Asset>('/assets', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async updateAsset(assetId: string, data: AssetUpdateInput): Promise<Asset> {
    return this.fetchJson<Asset>(`/assets/${assetId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  public async deleteAsset(assetId: string): Promise<void> {
    await this.fetchJson(`/assets/${assetId}`, { method: 'DELETE' });
  }

  public async getAssetSummary(assetId: string): Promise<AssetSummary> {
    return this.fetchJson<AssetSummary>(`/assets/${assetId}/summary`);
  }

  public async verifyAsset(
    assetId: string,
    options?: AssetVerifyRequest | string
  ): Promise<AssetVerifyResponse> {
    const payload: AssetVerifyRequest =
      typeof options === 'string'
        ? { verification_type: options as VerificationType, allow_private: true }
        : { verification_type: 'ADMIN_OVERRIDE', allow_private: true, ...options };

    return this.fetchJson<AssetVerifyResponse>(`/assets/${assetId}/verify`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  public async previewBulkAssets(data: AssetBulkPreviewRequest): Promise<AssetBulkPreviewResponse> {
    return this.fetchJson<AssetBulkPreviewResponse>('/assets/bulk-preview', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  public async bulkImportAssets(data: AssetBulkImportRequest): Promise<AssetBulkImportResponse> {
    return this.fetchJson<AssetBulkImportResponse>('/assets/bulk-import', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  // Scans query support by asset_id
  public async listScans(assetId?: string): Promise<{ items: ScanJob[]; total: number }> {
    const url = assetId ? `/scans?asset_id=${assetId}&size=100` : '/scans?size=100';
    return this.fetchJson<{ items: ScanJob[]; total: number }>(url);
  }
```

### 7.3. Refactoring State in `frontend/src/app/assets/page.tsx` (Eliminating `any`)

```typescript
// Replace lines 58, 73, 74, 98:
const [summaries, setSummaries] = useState<Record<string, AssetSummary>>({});
const [drawerScans, setDrawerScans] = useState<ScanJob[]>([]);
const [drawerFindings, setDrawerFindings] = useState<Finding[]>([]);
const [bulkPreviewData, setBulkPreviewData] = useState<AssetBulkPreviewResponse | null>(null);

// In loadDrawerDetails (lines 134-140):
const [scansRes, findingsRes] = await Promise.all([
  api.listScans(selectedAssetForDrawer.id).catch(() => ({ items: [] as ScanJob[], total: 0 })),
  api.listFindings({ assetId: selectedAssetForDrawer.id }).catch(() => ({ items: [] as Finding[], total: 0 })),
]);
setDrawerScans(scansRes.items);
setDrawerFindings(findingsRes.items);

// In handlePreviewBulk (line 262):
const data = await api.previewBulkAssets({
  import_type: bulkImportType,
  raw_content: bulkContent,
});
setBulkPreviewData(data);
```

### 7.4. Refactoring `TargetVerificationModal.tsx` (Eliminating `any`)

```typescript
// Replace line 42 details?: Record<string, any>;
export interface VerificationStep {
  id: number;
  key: string;
  titleKey: string;
  descKey: string;
  defaultTitle: string;
  defaultDesc: string;
  icon: React.ComponentType<{ className?: string }>;
  status: VerificationStepStatus;
  latencyMs?: number;
  details?: VerificationStepMetadata;
}

// In runVerificationPipeline:
const verifyResponse = await api.verifyAsset(asset.id, {
  verification_type: 'ADMIN_OVERRIDE',
  allow_private: true,
});

// Update steps with genuine probe results from backend
if (verifyResponse.steps && verifyResponse.steps.length > 0) {
  setSteps((prev) =>
    prev.map((s, idx) => {
      const backendStep = verifyResponse.steps[idx];
      return backendStep
        ? {
            ...s,
            status: backendStep.status as VerificationStepStatus,
            details: backendStep.metadata,
          }
        : s;
    })
  );
}
setOverallStatus(verifyResponse.status === 'VERIFIED' ? 'VERIFIED' : 'FAILED');
```

---

## 8. Verification & Empirical Evidence

1. **Pytest Adversarial Test Suite**:
   Command: `pytest tests/test_m6_targets_scans_adversarial.py`
   Output: **9 passed in 11.22s (100%)**
   - `test_target_drawer_five_tabs_contract` PASSED
   - `test_drawer_body_scroll_and_transitions_contract` PASSED
   - `test_bulk_import_partitioning_contract` PASSED
   - `test_eight_step_verification_modal_contract` PASSED
   - `test_scan_profiles_and_engine_toggles_contract` PASSED
   - `test_live_scanning_hud_and_terminal_contract` PASSED
   - `test_bulk_preview_duplicate_partitioning_empirical` PASSED
   - `test_eight_step_verification_probe_empirical` PASSED
   - `test_scan_dispatch_with_profiles_empirical` PASSED

2. **Milestone 6 Empirical Target & Scanner Verifier**:
   Command: `python scripts/verify_m6_targets_scans.py`
   Output: **ALL MILESTONE 6 EMPIRICAL VERIFICATION TESTS PASSED!**
   - Verified 5-Tab Drawer contracts (Overview, DNS & TLS, Endpoints, Scans, Vulnerabilities).
   - Verified 8-Step Live Probe Pipeline against live target `https://id.empire.edu.vn`.
   - Verified Bulk Preview duplicate partitioning (5 items -> 3 new, 2 duplicates).
