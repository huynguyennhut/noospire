# EMPIRE PENTEST CHECKLIST — TOOL COVERAGE & EXECUTION MATRIX

**Document Version**: 1.0.0  
**Target Architecture**: Multi-Engine Process-Isolated Vulnerability Scanner Framework  
**Process Execution Security Invariant**: `shell=False` across all subprocess invocations  
**Supported Engines**: OWASP ZAP, ProjectDiscovery Nuclei, Aqua Security Trivy, Empire Core Engine, Synthetic Test Harness, File Policy Engine  

---

## 1. Scanner Adapter Framework & Execution Security

The Noospire platform orchestrates a defense-in-depth scanner adapter framework (`backend/app/scanners/`). Every third-party tool is executed with strict operating system boundaries to prevent command injection, process leakage, and system instability.

### 1.1 Process Isolation Invariants
1. **Zero Shell Execution (`shell=False`)**:
   - All tool invocations use structured argument lists via `asyncio.create_subprocess_exec()` (`shell=False`).
   - String concatenation, shell interpolations (`bash -c`, `sh -c`), and piping are strictly prohibited across the entire adapter layer.
2. **Non-Root Execution**:
   - Subprocesses run under an unprivileged user identity (`uid=1000`, `gid=1000`).
   - No scanner process has access to Docker socket (`/var/run/docker.sock`) or host filesystem roots.
3. **Strict Resource Quotas & Timeouts**:
   - Memory limits enforced via cgroups/process rlimits (max 1024 MB RAM per tool).
   - Execution deadlines enforced: maximum 300 seconds for Nuclei/ZAP scans; 180 seconds for Trivy.
4. **Complete Process Tree Cancellation**:
   - Every subprocess is launched in an isolated process group (`preexec_fn=os.setsid`).
   - On cancellation, `os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` is dispatched, followed by `SIGKILL` after 3.0 seconds if needed.

---

## 2. 39-Check Tool Coverage Mapping Matrix

Below is the definitive mapping of all 39 Empire Pentest check definitions to their primary detection engines, execution parameters, and coverage classification:

| Check ID | Check Category | Bilingual Title | Primary Tool Engine | Subprocess / Driver Command | Execution Security Flags | Coverage Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`WEB-001`** | `WEB` | TLS/SSL & Cipher Hardening | `EMPIRE_ENGINE` | Native Python `ssl.create_default_context` | In-process, TLS $\ge$ 1.2 | `FULL_AUTOMATED` |
| **`WEB-002`** | `WEB` | HTTP Security Headers | `ZAP` | `zap-baseline.py -t <target> -r report.json` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`WEB-003`** | `WEB` | Cross-Site Scripting (XSS) | `ZAP` | `zap-baseline.py -t <target> -m 5` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`WEB-004`** | `WEB` | CSRF Protection | `ZAP` | `zap-baseline.py -t <target> --hook=csrf.py` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`WEB-005`** | `WEB` | SQL Injection & Prepared Stmts | `NUCLEI` | `nuclei -u <target> -t dast/vulnerabilities/sqli/` | `shell=False`, rate-limit=5 | `FULL_AUTOMATED` |
| **`WEB-006`** | `WEB` | SSRF Egress Defense | `EMPIRE_ENGINE` | Native `SSRFProtector.validate_target()` | In-process, DNS resolve | `FULL_AUTOMATED` |
| **`WEB-007`** | `WEB` | Open Redirection | `ZAP` | `zap-baseline.py -t <target> -r zap.json` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`WEB-008`** | `WEB` | Error & Stack Trace Leakage | `ZAP` | `zap-baseline.py -t <target> -s` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`WEB-009`** | `WEB` | CORS Policy Validation | `ZAP` | `zap-baseline.py -t <target>` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`WEB-010`** | `WEB` | Directory Indexing & Sensitive Paths | `NUCLEI` | `nuclei -u <target> -t exposures/files/` | `shell=False`, rate-limit=5 | `FULL_AUTOMATED` |
| **`API-001`** | `API` | BOLA / IDOR Authorization | `SYNTHETIC_HARNESS` | `SyntheticTestHarness.evaluate_bola()` | In-process, 2 identities | `FULL_AUTOMATED` |
| **`API-002`** | `API` | Broken Authentication & JWT | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_jwt()` | In-process, pyjwt checks | `FULL_AUTOMATED` |
| **`API-003`** | `API` | Excessive Data & Mass Assignment | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_mass_assign()`| In-process schema audit | `FULL_AUTOMATED` |
| **`API-004`** | `API` | Rate Limiting & Anti-Brute Force | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_rate_limits()` | In-process velocity test | `FULL_AUTOMATED` |
| **`API-005`** | `API` | BFLA Function Privilege Escalation | `SYNTHETIC_HARNESS` | `SyntheticTestHarness.evaluate_bfla()` | In-process, student identity | `FULL_AUTOMATED` |
| **`API-006`** | `API` | SSRF in API Webhooks | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_api_ssrf()` | In-process, SSRFProtector | `FULL_AUTOMATED` |
| **`API-007`** | `API` | Security Misconfig & Gateway | `ZAP` | `zap-api-scan.py -t <target> -f openapi` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`API-008`** | `API` | Anti-Automation & Scraping | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_scraping()` | In-process velocity test | `HYBRID_HEURISTIC` |
| **`API-009`** | `API` | Shadow API & GraphQL Exposure | `NUCLEI` | `nuclei -u <target> -t exposures/apis/` | `shell=False`, rate-limit=5 | `FULL_AUTOMATED` |
| **`API-010`** | `API` | 3rd-Party API Credential Leaks | `TRIVY` | `trivy fs --scanners secret <code_dir>` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`FILE-001`** | `FILE` | Approved Media (PUBLIC_BY_DESIGN) | `FILE_POLICY` | `FilePolicyEngine.evaluate_approved_media()`| In-process baseline check | `FULL_AUTOMATED` |
| **`FILE-002`** | `FILE` | Sensitive File Leak Prevention | `FILE_POLICY` | `FilePolicyEngine.evaluate_sensitive_leaks()`| In-process forbidden check | `FULL_AUTOMATED` |
| **`FILE-003`** | `FILE` | Cloud Storage & MinIO/S3 Exposure | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_s3_buckets()` | In-process, anonymous List | `FULL_AUTOMATED` |
| **`FILE-004`** | `FILE` | File Upload & Antivirus Probing | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_file_upload()` | In-process, magic bytes | `HYBRID_HEURISTIC` |
| **`FILE-005`** | `FILE` | Path Traversal & LFI | `ZAP` | `zap-baseline.py -t <target> -m 3` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`AUTH-001`** | `AUTH` | Brute-Force & Credential Stuffing | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_lockout()` | In-process, 5-attempt | `FULL_AUTOMATED` |
| **`AUTH-002`** | `AUTH` | Session Token Entropy & Revoke | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_session_entropy()`| In-process, Shannon entropy | `FULL_AUTOMATED` |
| **`AUTH-003`** | `AUTH` | Password Complexity Policy | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_password_policy()`| In-process dictionary | `MANUAL_REVIEW` |
| **`AUTH-004`** | `AUTH` | User Enumeration & Timing Attack | `ZAP` | `zap-baseline.py -t <target>` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`AUTH-005`** | `AUTH` | Multi-Factor Authentication (MFA) | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_mfa_stepup()` | In-process step-up check | `HYBRID_HEURISTIC` |
| **`INFRA-001`**| `INFRA`| Perimeter Port Exposure | `NUCLEI` | `nuclei -target <ip> -t network/` | `shell=False`, scoped ports | `FULL_AUTOMATED` |
| **`INFRA-002`**| `INFRA`| DNS Zone Transfer & Subdomain | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_dns_zone()` | In-process AXFR query | `FULL_AUTOMATED` |
| **`INFRA-003`**| `INFRA`| Server & OS Banner Minimization | `NUCLEI` | `nuclei -u <target> -t exposures/tokens/` | `shell=False`, rate-limit=5 | `FULL_AUTOMATED` |
| **`INFRA-004`**| `INFRA`| WAF & Egress Filtering Validation | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_waf_rules()` | In-process benign probe | `HYBRID_HEURISTIC` |
| **`DEP-001`** | `DEP` | Vulnerable 3rd-Party OSS Libs | `TRIVY` | `trivy fs --scanners vuln <repo_dir>` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`DEP-002`** | `DEP` | Container Base Image CVEs | `TRIVY` | `trivy image --severity HIGH,CRITICAL <img_ref>` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`DEP-003`** | `DEP` | Software Bill of Materials (SBOM) | `TRIVY` | `trivy fs --format cyclonedx <repo_dir>` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`DEP-004`** | `DEP` | Hardcoded Secrets in Source Code | `TRIVY` | `trivy fs --scanners secret <repo_dir>` | `shell=False`, non-root | `FULL_AUTOMATED` |
| **`DEP-005`** | `DEP` | End-of-Life Component Auditing | `EMPIRE_ENGINE` | `EmpireAssessmentEngine._audit_eol_runtimes()` | In-process EOL database | `FULL_AUTOMATED` |

---

## 3. Tool Responsibilities & Integration Details

### 3.1 OWASP ZAP (Zed Attack Proxy)
- **Role**: DAST baseline scanning, passive traffic analysis, HTTP header validation, injection fuzzing, and cookie flags.
- **Adapter File**: `backend/app/scanners/zap.py`
- **Output Normalization**: Parses ZAP JSON reports into `NormalizedFinding` instances, mapping alert tags to CWE and CVSS scores.

### 3.2 ProjectDiscovery Nuclei
- **Role**: Fast, curated, community-validated vulnerability signature verification across web, DNS, and network exposure layers.
- **Adapter File**: `backend/app/scanners/nuclei.py`
- **Output Normalization**: Ingests JSONLines (`-jsonl`) stream, extracting CVE numbers, CVSS base scores, and HTTP request/response proofs.

### 3.3 Aqua Security Trivy
- **Role**: Software Composition Analysis (SCA), container base image scanning, SBOM generation (CycloneDX/SPDX), and secret detection.
- **Adapter File**: `backend/app/scanners/trivy.py`
- **Output Normalization**: Unpacks Trivy JSON artifacts into vulnerability lists, extracting CVEs, fixed versions, and file paths.

### 3.4 Custom Synthetic Test Harness
- **Role**: Behavioral API authorization testing requiring authentic student personas (BOLA/IDOR on `API-001`, BFLA on `API-005`).
- **Adapter File**: `backend/app/scanners/synthetic_harness.py`
- **Safety Invariant**: Returns `BLOCKED` if test credentials are unavailable (never falsely returns `PASS`).

### 3.5 File Policy Engine
- **Role**: Enforces the Approved Public Exposure Policy for `/media` (`PUBLIC_BY_DESIGN` on `FILE-001`) and flags sensitive file leaks on `FILE-002`.
- **Adapter File**: `backend/app/scanners/file_policy.py`

### 3.6 Empire Assessment Engine
- **Role**: Native, non-destructive Python engine evaluating educational logic rules, TLS handshake security, JWT verification, rate limiting, and MinIO S3 bucket access.
- **Adapter File**: `backend/app/scanners/empire_engine.py`

---

## 4. Coverage Summary by Tool

```
+-----------------------------------+----------------+--------------------+
| Engine                            | Assigned Checks| Percent of Catalog |
+-----------------------------------+----------------+--------------------+
| Empire Core Engine (Native Python)| 15 checks      | 38.5%              |
| OWASP ZAP (DAST / Baseline)       | 10 checks      | 25.6%              |
| ProjectDiscovery Nuclei           |  6 checks      | 15.4%              |
| Aqua Security Trivy               |  4 checks      | 10.3%              |
| Synthetic Test Harness            |  2 checks      |  5.1%              |
| File Policy Engine                |  2 checks      |  5.1%              |
+-----------------------------------+----------------+--------------------+
| TOTAL                             | 39 checks      | 100.0%             |
+-----------------------------------+----------------+--------------------+
```

*Every tool adapter implements `BaseScannerAdapter` with uniform cancellation, secret redaction, and error handling.*
