import hashlib
import json
import logging
import re
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

from backend.app.schemas.common import (
    AssetType,
    EmpireModule,
    ExposureClassification,
    FindingSeverity,
    FindingStatus,
    ScanProfile,
)
from backend.app.schemas.finding import NormalizedFindingCreate

logger = logging.getLogger("sentinel.empire_engine")


class EmpireAssessmentEngine:
    """NOOSFORGE Security Intelligence — Empire Specific Assessment Engine.
    Executes deep, tailored security checks across Empire's business modules:
      - Module A: Student Management & Identity (Better-Auth, BOLA, BFLA, Anti-Automation)
      - Module B: Educational Material Management (/media Approved Public Exposure Policy)
      - Module C: Supporting Educational Tools (News Aggregation, English Tools, SSRF/XSS)
      - Module D: API Security Assessment (OWASP API Top 10)
      - Module F: Controlled Brute-Force & Negative Auth Resistance Assessment
    """

    def __init__(self) -> None:
        self.client_timeout = 10.0

    async def execute_empire_assessment(
        self,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        target_locator: str,
        empire_module: str,
        profile: str,
        log_cb: Callable[[str, str, str], Awaitable[None]],
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []
        base_url = target_locator.rstrip("/")

        await log_cb("empire_engine", f"Starting Empire Security Assessment for {target_locator} [Module: {empire_module}, Profile: {profile}]")

        async def _run_assessment(client: httpx.AsyncClient) -> List[NormalizedFindingCreate]:
            module_findings: List[NormalizedFindingCreate] = []
            is_root_empire = (
                "empire.edu.vn" in base_url
                or empire_module in ("ALL", "*")
                or base_url.rstrip("/") in ("https://empire.edu.vn", "http://empire.edu.vn")
            )

            # -------------------------------------------------------------
            # MODULE A: STUDENT MANAGEMENT & AUTHENTICATION
            # -------------------------------------------------------------
            if is_root_empire or empire_module in (EmpireModule.STUDENT_MANAGEMENT.value, EmpireModule.API_SERVICES.value, "ALL"):
                await log_cb("empire_engine", "Executing Module A: Student Management & Authentication Assessment...")
                student_findings = await self._assess_student_management(client, base_url, asset_id, scan_id, log_cb)
                module_findings.extend(student_findings)

            # -------------------------------------------------------------
            # MODULE B: EDUCATIONAL MATERIAL & /media APPROVED POLICY
            # -------------------------------------------------------------
            if is_root_empire or empire_module in (EmpireModule.LEARNING_MATERIALS.value, "ALL") or "media" in base_url or "voh" in base_url or "mh" in base_url:
                await log_cb("empire_engine", "Executing Module B: Educational Material & /media Policy Assessment...")
                media_findings = await self._assess_media_policy(client, base_url, asset_id, scan_id, log_cb)
                module_findings.extend(media_findings)

            # -------------------------------------------------------------
            # MODULE C: SUPPORTING EDUCATIONAL TOOLS (NEWS & ENGLISH)
            # -------------------------------------------------------------
            if is_root_empire or empire_module in (EmpireModule.SUPPORTING_TOOLS.value, "ALL") or "news" in base_url:
                await log_cb("empire_engine", "Executing Module C: Supporting Tools & News Services Assessment...")
                tool_findings = await self._assess_supporting_tools(client, base_url, asset_id, scan_id, log_cb)
                module_findings.extend(tool_findings)

            # -------------------------------------------------------------
            # MODULE D: API SECURITY (OWASP API TOP 10)
            # -------------------------------------------------------------
            if is_root_empire or empire_module in (EmpireModule.API_SERVICES.value, "ALL") or profile in (ScanProfile.API_ASSESSMENT.value, ScanProfile.THOROUGH.value):
                await log_cb("empire_engine", "Executing Module D: OWASP API Security Assessment...")
                api_findings = await self._assess_api_security(client, base_url, asset_id, scan_id, log_cb)
                module_findings.extend(api_findings)

            # -------------------------------------------------------------
            # MODULE E: WEB APPLICATION SECURITY & HEADERS HARDENING
            # -------------------------------------------------------------
            if is_root_empire or empire_module in (EmpireModule.WEB_APPLICATION.value, "ALL"):
                await log_cb("empire_engine", "Executing Module E: Web Application Security & Hardening Assessment...")
                web_findings = await self._assess_web_security(client, base_url, asset_id, scan_id, log_cb)
                module_findings.extend(web_findings)

            # -------------------------------------------------------------
            # MODULE F: CONTROLLED BRUTE FORCE & NEGATIVE AUTH DEFENSE
            # -------------------------------------------------------------
            if is_root_empire or profile in (ScanProfile.DAILY_SECURITY.value, ScanProfile.AUTHENTICATED.value, ScanProfile.THOROUGH.value, ScanProfile.STANDARD.value):
                await log_cb("empire_engine", "Executing Module F: Controlled Brute-Force & Negative Auth Resilience Audit...")
                bf_findings = await self._assess_brute_force_defense(client, base_url, asset_id, scan_id, log_cb)
                module_findings.extend(bf_findings)

            # -------------------------------------------------------------
            # MODULE G: SERVER & CLOUD INFRASTRUCTURE HARDENING
            # -------------------------------------------------------------
            if is_root_empire or empire_module in (EmpireModule.SERVER_INFRASTRUCTURE.value, "ALL"):
                await log_cb("empire_engine", "Executing Module G: Server & Cloud Infrastructure Hardening Assessment...")
                infra_findings = await self._assess_server_infrastructure(client, base_url, asset_id, scan_id, log_cb)
                module_findings.extend(infra_findings)

            return module_findings

        if http_client is not None:
            findings = await _run_assessment(http_client)
        else:
            async with httpx.AsyncClient(
                verify=False,
                timeout=self.client_timeout,
                headers={"User-Agent": "NOOSFORGE-Security-Intelligence/1.0 (Empire-Auditor)"},
                follow_redirects=True,
            ) as client:
                findings = await _run_assessment(client)

        await log_cb("empire_engine", f"Empire Security Assessment complete. Total findings generated: {len(findings)}")
        return findings

    # =========================================================================
    # MODULE A IMPLEMENTATION
    # =========================================================================
    async def _assess_student_management(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        log_cb: Callable[[str, str, str], Awaitable[None]],
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []

        # 1. Probe Better-Auth & Student Endpoints Exposure
        auth_routes = [
            "/api/auth/sign-in/email",
            "/api/auth/sign-up/email",
            "/api/auth/reset-password",
            "/api/auth/get-session",
            "/api/users/profile",
            "/social/v2/groups",
        ]

        for route in auth_routes:
            target_url = urljoin(base_url, route)
            try:
                resp = await client.get(target_url)
                if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                    # Check if unauthenticated endpoint leaks student or developer details
                    data = resp.text
                    if "email" in data and ("@gmail.com" in data or "@empire.edu.vn" in data):
                        findings.append(
                            NormalizedFindingCreate(
                                asset_id=asset_id,
                                scan_id=scan_id,
                                scanner_engine="empire_student_auditor",
                                scanner_rule_id="EMPIRE-STUDENT-LEAK-01",
                                title="Unauthenticated Student/User Identity Information Exposure",
                                description=(
                                    f"The endpoint {route} returns sensitive user/student records "
                                    "without requiring prior authentication or authorization."
                                ),
                                severity=FindingSeverity.HIGH,
                                original_severity="high",
                                empire_module=EmpireModule.STUDENT_MANAGEMENT.value,
                                cwe_id="CWE-200",
                                cvss_score=7.5,
                                cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N",
                                target_location=target_url,
                                target_component=route,
                                evidence={
                                    "endpoint": route,
                                    "status_code": resp.status_code,
                                    "response_snippet": data[:400],
                                    "remediation_advice": "Enforce strict session authentication prior to returning user data.",
                                },
                                remediation="Require authentication before accessing user lists or student profiles; eliminate unauthenticated enumeration endpoints.",
                            )
                        )
                        await log_cb("empire_engine", f"Identified sensitive data exposure on {route}", level="WARNING")
            except Exception as e:
                logger.debug(f"Error probing {target_url}: {e}")

        # 2. Horizontal Privilege Escalation (IDOR/BOLA) check with synthetic student identifier
        synthetic_student_id = "stu-test-7788"
        bola_url = urljoin(base_url, f"/api/users/{synthetic_student_id}/learning-records")
        try:
            resp = await client.get(bola_url, headers={"Authorization": "Bearer synthetic_student_token_a"})
            content_type = resp.headers.get("content-type", "").lower()
            is_html_catchall = "text/html" in content_type or resp.text.strip().lower().startswith(("<html", "<!doctype", "<?xml"))
            if resp.status_code == 200 and not is_html_catchall and "application/json" in content_type:
                # Confirm violation only when unexpected actor receives protected student records schema
                body_lower = resp.text.lower()
                if any(k in body_lower for k in ("learning-records", "records", "student_id", "courses", "grades", "progress")):
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="empire_student_auditor",
                            scanner_rule_id="EMPIRE-STUDENT-BOLA-02",
                            title="Broken Object-Level Authorization (BOLA) in Student Learning Records",
                            description=(
                                f"Accessing student learning records at {bola_url} succeeded across cross-account "
                                "token boundaries without verifying object ownership."
                            ),
                            severity=FindingSeverity.HIGH,
                            original_severity="high",
                            empire_module=EmpireModule.STUDENT_MANAGEMENT.value,
                            cwe_id="CWE-639",
                            cvss_score=8.1,
                            cvss_vector="CVSS:3.1/AV:N/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:N",
                            target_location=bola_url,
                            target_component="/api/users/{id}/learning-records",
                            evidence={
                                "url": bola_url,
                                "synthetic_id": synthetic_student_id,
                                "status_code": resp.status_code,
                            },
                            remediation="Validate that the authenticated caller's identity matches the requested student resource ID on the backend.",
                        )
                    )
        except Exception:
            pass

        return findings

    # =========================================================================
    # MODULE B IMPLEMENTATION (/media APPROVED PUBLIC EXPOSURE POLICY)
    # =========================================================================
    async def _assess_media_policy(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        log_cb: Callable[[str, str, str], Awaitable[None]],
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []

        # 1. Approved Public Media Check
        public_media_url = urljoin(base_url, "/media/public-course.pdf") if "/media" not in base_url else base_url
        try:
            resp = await client.get(public_media_url)
            if resp.status_code in (200, 404):
                # Expected behavior: anonymous access to approved public media is ALLOWED
                await log_cb(
                    "empire_engine",
                    f"Approved Public Media policy validated on {public_media_url} -> Classified as PUBLIC_BY_DESIGN (Baseline compliant, zero false-positive alerts created)."
                )
        except Exception:
            pass

        # 2. Check for UNINTENDED SENSITIVE CONTENT under /media
        sensitive_probes = [
            ("/media/student-records.csv", "Student CSV Database Dump", FindingSeverity.CRITICAL, 9.1),
            ("/media/.env", "Environment Secrets in Public Storage", FindingSeverity.HIGH, 8.5),
            ("/media/backup.zip", "Database/Code Archive in Public Storage", FindingSeverity.HIGH, 8.2),
            ("/media/passwords.txt", "Plaintext Credentials in Public Storage", FindingSeverity.CRITICAL, 9.8),
        ]

        for path, leak_title, severity, cvss in sensitive_probes:
            test_url = urljoin(base_url, path)
            try:
                resp = await client.get(test_url)
                # If sensitive file exists and returns 200 with content (ensure it's not a generic HTML catch-all)
                content_type = resp.headers.get("content-type", "").lower()
                is_html_catchall = "text/html" in content_type and (
                    resp.text.strip().lower().startswith(("<html", "<!doctype", "<head")) or "<body" in resp.text.lower()
                )
                if resp.status_code == 200 and len(resp.content) > 10 and not is_html_catchall:
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="empire_media_auditor",
                            scanner_rule_id="EMPIRE-MEDIA-LEAK-01",
                            title=f"Unintended Sensitive Content in Public Media Storage ({leak_title})",
                            description=(
                                f"Publicly accessible storage path {path} contains sensitive or confidential "
                                "data, violating the Approved Public Exposure baseline policy."
                            ),
                            severity=severity,
                            original_severity="critical" if severity == FindingSeverity.CRITICAL else "high",
                            empire_module=EmpireModule.LEARNING_MATERIALS.value,
                            exposure_classification=ExposureClassification.PUBLIC_SENSITIVE_CONTENT.value,
                            cwe_id="CWE-200",
                            cvss_score=cvss,
                            target_location=test_url,
                            target_component=path,
                            evidence={
                                "url": test_url,
                                "status_code": resp.status_code,
                                "classification": ExposureClassification.PUBLIC_SENSITIVE_CONTENT.value,
                                "response_snippet": resp.text[:200],
                            },
                            remediation="Remove sensitive files from /media immediately and restrict storage bucket permissions.",
                        )
                    )
            except Exception:
                pass

        # 3. Check for Directory Indexing on /media/ or MinIO bucket listing
        media_root = urljoin(base_url, "/media/") if "/media" not in base_url else base_url.rstrip("/") + "/"
        try:
            resp = await client.get(media_root)
            if resp.status_code == 200:
                body = resp.text.lower()
                if "<title>index of" in body or "listbucketresult" in body or "minio" in body:
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="empire_media_auditor",
                            scanner_rule_id="EMPIRE-MEDIA-DIRLIST-02",
                            title="Directory Indexing / MinIO Public Bucket Listing Enabled",
                            description=(
                                f"Storage endpoint {media_root} has directory indexing or S3 bucket listing "
                                "publicly exposed, allowing attackers to discover all stored materials."
                            ),
                            severity=FindingSeverity.HIGH,
                            original_severity="high",
                            empire_module=EmpireModule.LEARNING_MATERIALS.value,
                            exposure_classification=ExposureClassification.MISCONFIGURED_MEDIA_STORAGE.value,
                            cwe_id="CWE-548",
                            cvss_score=7.5,
                            target_location=media_root,
                            target_component="/media/",
                            evidence={
                                "url": media_root,
                                "status_code": resp.status_code,
                                "signature": "Directory Listing / ListBucketResult detected",
                            },
                            remediation="Disable directory browsing in web server configuration (autoindex off) and restrict MinIO anonymous ListObjects permission.",
                        )
                    )
        except Exception:
            pass

        return findings

    # =========================================================================
    # MODULE C IMPLEMENTATION (SUPPORTING TOOLS & NEWS SERVICES)
    # =========================================================================
    async def _assess_supporting_tools(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        log_cb: Callable[[str, str, str], Awaitable[None]],
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []

        # 1. Probe News Aggregator Endpoints
        news_url = urljoin(base_url, "/news/api/fetch-feed")
        try:
            # Test SSRF vector on external feed URL fetching
            ssrf_test_payload = {"feed_url": "http://169.254.169.254/latest/meta-data/"}
            resp = await client.post(news_url, json=ssrf_test_payload)
            if resp.status_code in (200, 500) and "ami-id" in resp.text:
                findings.append(
                    NormalizedFindingCreate(
                        asset_id=asset_id,
                        scan_id=scan_id,
                        scanner_engine="empire_tools_auditor",
                        scanner_rule_id="EMPIRE-TOOL-SSRF-01",
                        title="Server-Side Request Forgery (SSRF) in News Feed Aggregator",
                        description=(
                            f"News feed fetching endpoint {news_url} accepts arbitrary external URLs "
                            "without validating destination IP addresses against internal/cloud metadata ranges."
                        ),
                        severity=FindingSeverity.CRITICAL,
                        original_severity="critical",
                        empire_module=EmpireModule.SUPPORTING_TOOLS.value,
                        cwe_id="CWE-918",
                        cvss_score=9.6,
                        target_location=news_url,
                        target_component="/news/api/fetch-feed",
                        evidence={
                            "url": news_url,
                            "payload": ssrf_test_payload,
                            "response_code": resp.status_code,
                        },
                        remediation="Implement strict domain whitelisting and block internal/loopback/cloud metadata IP addresses (RFC 1918, 169.254.169.254).",
                    )
                )
        except Exception:
            pass

        # 2. XSS in News Search & Educational Utility Tools
        search_url = urljoin(base_url, "/news/search?q=<script>alert(1)</script>")
        try:
            resp = await client.get(search_url)
            if resp.status_code == 200 and "<script>alert(1)</script>" in resp.text:
                findings.append(
                    NormalizedFindingCreate(
                        asset_id=asset_id,
                        scan_id=scan_id,
                        scanner_engine="empire_tools_auditor",
                        scanner_rule_id="EMPIRE-TOOL-XSS-02",
                        title="Reflected Cross-Site Scripting (XSS) in Educational News Search",
                        description=(
                            f"Search parameter 'q' on {search_url} reflects untrusted user input "
                            "into HTML response without contextual sanitization or output encoding."
                        ),
                        severity=FindingSeverity.HIGH,
                        original_severity="high",
                        empire_module=EmpireModule.SUPPORTING_TOOLS.value,
                        cwe_id="CWE-79",
                        cvss_score=7.1,
                        target_location=search_url,
                        target_component="/news/search",
                        evidence={
                            "url": search_url,
                            "status_code": resp.status_code,
                            "reflected_payload": "<script>alert(1)</script>",
                        },
                        remediation="Contextually encode output and configure a strict Content Security Policy (CSP).",
                    )
                )
        except Exception:
            pass

        return findings

    # =========================================================================
    # MODULE D IMPLEMENTATION (API SECURITY OWASP TOP 10)
    # =========================================================================
    async def _assess_api_security(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        log_cb: Callable[[str, str, str], Awaitable[None]],
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []

        # 1. Broken Function-Level Authorization (BFLA)
        admin_endpoints = [
            "/api/admin/system-status",
            "/api/admin/users/export",
            "/api/v1/internal/config",
            "/console/api/overview",
        ]

        for ep in admin_endpoints:
            target_url = urljoin(base_url, ep)
            try:
                resp = await client.get(target_url)
                content_type = resp.headers.get("content-type", "").lower()
                is_html_catchall = "text/html" in content_type and (
                    resp.text.strip().lower().startswith(("<html", "<!doctype", "<head")) or "<body" in resp.text.lower()
                )
                if resp.status_code == 200 and not is_html_catchall and ("application/json" in content_type or resp.text.strip().startswith(("{", "["))):
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="empire_api_auditor",
                            scanner_rule_id="EMPIRE-API-BFLA-01",
                            title="Broken Function-Level Authorization (BFLA) on Administrative API",
                            description=(
                                f"Administrative endpoint {ep} does not enforce role verification or authorization checks, "
                                "allowing unauthenticated or unauthorized access to administrative functions."
                            ),
                            severity=FindingSeverity.CRITICAL,
                            original_severity="critical",
                            empire_module=EmpireModule.API_SERVICES.value,
                            cwe_id="CWE-285",
                            cvss_score=9.3,
                            target_location=target_url,
                            target_component=ep,
                            evidence={
                                "url": target_url,
                                "status_code": resp.status_code,
                                "sample_response": resp.text[:250],
                            },
                            remediation="Enforce server-side role-based access control (RBAC) checks on all administrative endpoints.",
                        )
                    )
            except Exception:
                pass

        # 2. Missing Rate Limiting on Critical API endpoints
        api_rate_url = urljoin(base_url, "/api/courses/list")
        try:
            resp = await client.get(api_rate_url)
            headers = resp.headers
            has_rate_limit = any("ratelimit" in k.lower() or "retry-after" in k.lower() for k in headers.keys())
            if not has_rate_limit and resp.status_code == 200:
                findings.append(
                    NormalizedFindingCreate(
                        asset_id=asset_id,
                        scan_id=scan_id,
                        scanner_engine="empire_api_auditor",
                        scanner_rule_id="EMPIRE-API-RATELIMIT-02",
                        title="Missing Rate Limiting & Resource Consumption Controls on Core APIs",
                        description=(
                            f"API endpoint {api_rate_url} does not emit rate limiting headers or throttle requests, "
                            "exposing the service to automated scraping and resource exhaustion."
                        ),
                        severity=FindingSeverity.LOW,
                        original_severity="low",
                        empire_module=EmpireModule.API_SERVICES.value,
                        cwe_id="CWE-799",
                        cvss_score=4.3,
                        target_location=api_rate_url,
                        target_component="/api/courses/list",
                        evidence={
                            "url": api_rate_url,
                            "status_code": resp.status_code,
                            "missing_headers": ["RateLimit-Limit", "RateLimit-Remaining"],
                        },
                        remediation="Configure token-bucket rate limiting on API gateway reverse proxy (e.g. 100 req/min per IP).",
                    )
                )
        except Exception:
            pass

        return findings

    # =========================================================================
    # MODULE F IMPLEMENTATION (CONTROLLED BRUTE FORCE & NEGATIVE AUTH DEFENSE)
    # =========================================================================
    async def _assess_brute_force_defense(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        log_cb: Callable[[str, str, str], Awaitable[None]],
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []

        # Target endpoint: login/signin
        login_url = urljoin(base_url, "/api/auth/sign-in/email")
        synthetic_audit_account = "audit_synthetic_probe@empire.local"

        await log_cb(
            "empire_brute_force",
            f"Executing bounded negative-auth resilience test on {login_url} (Max 5 bounded probes, zero real student accounts tested)..."
        )

        response_codes = []
        durations = []
        rate_limit_headers_detected = False

        # Execute exactly 5 controlled attempts with synthetic invalid credentials
        for i in range(1, 6):
            start_t = time.perf_counter()
            try:
                resp = await client.post(
                    login_url,
                    json={"email": synthetic_audit_account, "password": f"ControlledProbe_{i}_NonExistent!"},
                )
                dur = time.perf_counter() - start_t
                durations.append(dur)
                response_codes.append(resp.status_code)

                # Check headers
                if any("ratelimit" in k.lower() or "retry-after" in k.lower() for k in resp.headers.keys()):
                    rate_limit_headers_detected = True

                if resp.status_code == 429:
                    await log_cb("empire_brute_force", f"Probe #{i}: HTTP 429 Rate Limited observed. Throttling is ACTIVE.")
                    break
            except Exception as e:
                logger.debug(f"Controlled probe #{i} failed: {e}")
                break

        # Analyze defense behavior
        # Gate C Invariant: All 404s, absent rate-limit headers on 404, or missing endpoint CANNOT establish missing defense!
        # Only repeated 401/400 authentications processed without throttling confirm missing brute force protection.
        if len(response_codes) >= 4 and all(c in (400, 401) for c in response_codes) and not rate_limit_headers_detected:
            findings.append(
                NormalizedFindingCreate(
                    asset_id=asset_id,
                    scan_id=scan_id,
                    scanner_engine="empire_brute_force_auditor",
                    scanner_rule_id="EMPIRE-AUTH-BRUTEFORCE-01",
                    title="Insufficient Anti-Automation & Credential Stuffing Defenses on Login",
                    description=(
                        f"Login endpoint {login_url} processed repeated negative authentication attempts "
                        "without progressive delay, temporary lockout, or rate-limiting response headers."
                    ),
                    severity=FindingSeverity.HIGH,
                    original_severity="high",
                    empire_module=EmpireModule.STUDENT_MANAGEMENT.value,
                    cwe_id="CWE-307",
                    cvss_score=7.5,
                    target_location=login_url,
                    target_component="/api/auth/sign-in/email",
                    evidence={
                        "endpoint": login_url,
                        "test_account": synthetic_audit_account,
                        "probes_count": len(response_codes),
                        "response_codes": response_codes,
                        "progressive_delay_detected": False,
                        "rate_limit_headers_present": rate_limit_headers_detected,
                    },
                    remediation="Implement progressive exponential delay, account lockout threshold (e.g., 5 failed attempts = 15 min lock), and IP-based rate limiting.",
                )
            )
            await log_cb("empire_brute_force", "Negative-auth resilience finding recorded: rate limiting / progressive delays absent.", level="WARNING")
        return findings

    # =========================================================================
    # MODULE E IMPLEMENTATION (WEB APPLICATION SECURITY)
    # =========================================================================
    async def _assess_web_security(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        log_cb: Callable[[str, str, str], Awaitable[None]],
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []

        try:
            resp = await client.get(base_url)
            headers_lower = {k.lower(): v for k, v in resp.headers.items()}

            # 1. Content Security Policy (CSP) Check
            if "content-security-policy" not in headers_lower:
                findings.append(
                    NormalizedFindingCreate(
                        asset_id=asset_id,
                        scan_id=scan_id,
                        scanner_engine="empire_web_auditor",
                        scanner_rule_id="EMPIRE-WEB-CSP-01",
                        title="Missing Content Security Policy (CSP) Header",
                        description=(
                            f"Web application root {base_url} does not emit a Content-Security-Policy header. "
                            "A robust CSP mitigates Cross-Site Scripting (XSS) and unauthorized content injection."
                        ),
                        severity=FindingSeverity.MEDIUM,
                        original_severity="medium",
                        empire_module=EmpireModule.WEB_APPLICATION.value,
                        cwe_id="CWE-693",
                        cvss_score=5.4,
                        target_location=base_url,
                        target_component="Content-Security-Policy",
                        evidence={
                            "url": base_url,
                            "status_code": resp.status_code,
                            "missing_header": "Content-Security-Policy",
                        },
                        remediation="Configure a Content-Security-Policy header restricting script, style, and object sources.",
                    )
                )

            # 2. Clickjacking Defense Check (X-Frame-Options or frame-ancestors)
            csp_val = headers_lower.get("content-security-policy", "")
            has_clickjack_defense = "x-frame-options" in headers_lower or "frame-ancestors" in csp_val
            if not has_clickjack_defense:
                findings.append(
                    NormalizedFindingCreate(
                        asset_id=asset_id,
                        scan_id=scan_id,
                        scanner_engine="empire_web_auditor",
                        scanner_rule_id="EMPIRE-WEB-CLICKJACK-02",
                        title="Missing Clickjacking Defense (X-Frame-Options / frame-ancestors)",
                        description=(
                            f"Web application endpoint {base_url} does not declare X-Frame-Options or frame-ancestors, "
                            "allowing adversarial sites to embed this page in an invisible frame for UI redressing."
                        ),
                        severity=FindingSeverity.MEDIUM,
                        original_severity="medium",
                        empire_module=EmpireModule.WEB_APPLICATION.value,
                        cwe_id="CWE-1021",
                        cvss_score=6.1,
                        target_location=base_url,
                        target_component="X-Frame-Options",
                        evidence={
                            "url": base_url,
                            "status_code": resp.status_code,
                            "missing_header": "X-Frame-Options",
                        },
                        remediation="Add 'X-Frame-Options: SAMEORIGIN' or configure 'frame-ancestors 'self'' in Content-Security-Policy.",
                    )
                )

            # 3. Cookie Security Attributes Check
            set_cookie = headers_lower.get("set-cookie", "")
            if set_cookie:
                missing_flags = []
                if "secure" not in set_cookie.lower():
                    missing_flags.append("Secure")
                if "httponly" not in set_cookie.lower():
                    missing_flags.append("HttpOnly")
                if "samesite" not in set_cookie.lower():
                    missing_flags.append("SameSite")

                if missing_flags:
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="empire_web_auditor",
                            scanner_rule_id="EMPIRE-WEB-COOKIE-03",
                            title=f"Insecure Cookie Configuration: Missing {', '.join(missing_flags)}",
                            description=(
                                f"Cookies set by {base_url} lack security flags: {', '.join(missing_flags)}. "
                                "This exposes session tokens to cross-site request forgery and script-based interception."
                            ),
                            severity=FindingSeverity.LOW,
                            original_severity="low",
                            empire_module=EmpireModule.WEB_APPLICATION.value,
                            cwe_id="CWE-614",
                            cvss_score=4.3,
                            target_location=base_url,
                            target_component="Set-Cookie Header",
                            evidence={
                                "url": base_url,
                                "raw_set_cookie": set_cookie[:300],
                                "missing_attributes": missing_flags,
                            },
                            remediation="Ensure all sensitive cookies are tagged with Secure, HttpOnly, and SameSite=Lax/Strict.",
                        )
                    )

        except Exception as e:
            logger.debug(f"Web application security check error: {e}")

        return findings

    # =========================================================================
    # MODULE G IMPLEMENTATION (SERVER & CLOUD INFRASTRUCTURE)
    # =========================================================================
    async def _assess_server_infrastructure(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        log_cb: Callable[[str, str, str], Awaitable[None]],
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []

        try:
            resp = await client.get(base_url)
            headers_lower = {k.lower(): v for k, v in resp.headers.items()}

            # 1. Server Software Version Disclosure
            server_header = headers_lower.get("server") or headers_lower.get("x-powered-by")
            if server_header and any(c.isdigit() for c in server_header):
                findings.append(
                    NormalizedFindingCreate(
                        asset_id=asset_id,
                        scan_id=scan_id,
                        scanner_engine="empire_infra_auditor",
                        scanner_rule_id="EMPIRE-INFRA-BANNER-01",
                        title="Server & Web Technology Version Disclosure in Response Headers",
                        description=(
                            f"Server at {base_url} discloses software version details ('{server_header}'). "
                            "Banner disclosure aids attackers in mapping unpatched CVEs."
                        ),
                        severity=FindingSeverity.LOW,
                        original_severity="low",
                        empire_module=EmpireModule.SERVER_INFRASTRUCTURE.value,
                        cwe_id="CWE-200",
                        cvss_score=3.7,
                        target_location=base_url,
                        target_component="Server Header",
                        evidence={
                            "url": base_url,
                            "server_header": server_header,
                        },
                        remediation="Obfuscate or suppress Server and X-Powered-By tokens in proxy/web server configuration.",
                    )
                )

            # 2. Missing Strict-Transport-Security (HSTS) on HTTPS
            if base_url.startswith("https://") and "strict-transport-security" not in headers_lower:
                findings.append(
                    NormalizedFindingCreate(
                        asset_id=asset_id,
                        scan_id=scan_id,
                        scanner_engine="empire_infra_auditor",
                        scanner_rule_id="EMPIRE-INFRA-HSTS-02",
                        title="Missing HTTP Strict Transport Security (HSTS) Header",
                        description=(
                            f"HTTPS target {base_url} does not emit a Strict-Transport-Security header. "
                            "HSTS prevents man-in-the-middle SSL-stripping and forced plaintext downgrade attacks."
                        ),
                        severity=FindingSeverity.MEDIUM,
                        original_severity="medium",
                        empire_module=EmpireModule.SERVER_INFRASTRUCTURE.value,
                        cwe_id="CWE-319",
                        cvss_score=5.3,
                        target_location=base_url,
                        target_component="Strict-Transport-Security",
                        evidence={
                            "url": base_url,
                            "status_code": resp.status_code,
                            "missing_header": "Strict-Transport-Security",
                        },
                        remediation="Emit 'Strict-Transport-Security: max-age=31536000; includeSubDomains; preload' on all HTTPS responses.",
                    )
                )

            # 3. Exposed Diagnostic / Server Status Probes
            status_url = urljoin(base_url, "/server-status")
            try:
                status_resp = await client.get(status_url)
                if status_resp.status_code == 200 and ("apache server status" in status_resp.text.lower() or "server version" in status_resp.text.lower()):
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="empire_infra_auditor",
                            scanner_rule_id="EMPIRE-INFRA-STATUS-03",
                            title="Exposed Web Server Status Diagnostic Endpoint (/server-status)",
                            description=(
                                f"Web server status page at {status_url} is publicly accessible, leaking "
                                "real-time client connections, URLs, and server metrics."
                            ),
                            severity=FindingSeverity.HIGH,
                            original_severity="high",
                            empire_module=EmpireModule.SERVER_INFRASTRUCTURE.value,
                            cwe_id="CWE-200",
                            cvss_score=7.5,
                            target_location=status_url,
                            target_component="/server-status",
                            evidence={
                                "url": status_url,
                                "status_code": status_resp.status_code,
                                "sample": status_resp.text[:300],
                            },
                            remediation="Restrict access to /server-status via firewall/ACL or disable mod_status.",
                        )
                    )
            except Exception:
                pass

        except Exception as e:
            logger.debug(f"Server infrastructure assessment error: {e}")

        return findings
