import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import httpx

from backend.app.schemas.common import AssetType, FindingSeverity
from backend.app.schemas.finding import NormalizedFindingCreate


class NucleiLabRunner:
    """Embedded high-fidelity Nuclei engine evaluating approved template checks
    against target HTTP endpoints using httpx. Preserves authentic request/response evidence.
    """

    TEMPLATES = [
        {
            "id": "git-config-exposure",
            "name": "Git Config File Disclosure",
            "severity": FindingSeverity.MEDIUM,
            "original_severity": "medium",
            "cwe_id": "CWE-200",
            "description": "The .git/config file was found exposed on the target server, leaking repository details and branch information.",
            "remediation": "Block access to .git and other hidden version control directories in your web server configuration.",
            "path": "/.git/config",
            "method": "GET",
            "matchers": [r"\[core\]", r"repositoryformatversion"],
        },
        {
            "id": "env-file-exposure",
            "name": "Environment Configuration File Disclosure",
            "severity": FindingSeverity.HIGH,
            "original_severity": "high",
            "cwe_id": "CWE-200",
            "description": "The .env configuration file was found exposed, leaking sensitive environment variables and credentials.",
            "remediation": "Ensure .env files reside outside the public web server root or deny HTTP access in reverse proxy rules.",
            "path": "/.env",
            "method": "GET",
            "matchers": [r"(DB_PASSWORD|SECRET_KEY|DATABASE_URL|API_KEY|AWS_SECRET)"],
        },
        {
            "id": "cors-misconfiguration",
            "name": "Insecure CORS Policy Misconfiguration",
            "severity": FindingSeverity.MEDIUM,
            "original_severity": "medium",
            "cwe_id": "CWE-942",
            "description": "Target server reflects arbitrary Origin headers in Access-Control-Allow-Origin, allowing cross-origin data theft.",
            "remediation": "Avoid wildcard or reflected origins when credentials are supported; restrict to a strict domain whitelist.",
            "path": "/",
            "method": "GET",
            "headers": {"Origin": "https://sentinel-security-audit.com"},
            "custom_eval": "cors_check",
        },
        {
            "id": "directory-listing-enabled",
            "name": "Directory Listing Enabled",
            "severity": FindingSeverity.LOW,
            "original_severity": "low",
            "cwe_id": "CWE-548",
            "description": "Directory index listing is enabled, exposing directory contents and filenames to unauthorized clients.",
            "remediation": "Disable directory indexing in the web server configuration (e.g. 'Options -Indexes' in Apache or 'autoindex off' in Nginx).",
            "path": "/static/",
            "method": "GET",
            "matchers": [r"Index of /", r"<title>Index of"],
        },
        {
            "id": "cve-2023-38606-spring-actuator",
            "name": "Spring Boot Actuator Information Disclosure",
            "severity": FindingSeverity.HIGH,
            "original_severity": "high",
            "cve_id": "CVE-2023-38606",
            "cwe_id": "CWE-200",
            "description": "Exposed Spring Boot Actuator endpoint leaking environment variables and internal infrastructure details.",
            "remediation": "Disable management endpoints or configure Spring Security to require authentication on /actuator/**.",
            "path": "/actuator/env",
            "method": "GET",
            "matchers": [r'"activeProfiles"', r'"propertySources"'],
        },
    ]

    async def run(
        self,
        target_url: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        log_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []
        base_url = target_url.rstrip("/")

        async with httpx.AsyncClient(timeout=8.0, verify=False, follow_redirects=True) as client:
            for tmpl in self.TEMPLATES:
                url = base_url + tmpl["path"]
                req_headers = tmpl.get("headers", {})

                if log_callback:
                    await log_callback("nuclei", f"Evaluating template [{tmpl['id']}] against {url}")

                try:
                    resp = await client.request(tmpl["method"], url, headers=req_headers)
                    body_text = resp.text

                    matched = False
                    matched_content = ""

                    if tmpl.get("custom_eval") == "cors_check":
                        acao = resp.headers.get("access-control-allow-origin", "")
                        if acao == "https://sentinel-security-audit.com" or (acao == "*" and "Origin" in req_headers):
                            matched = True
                            matched_content = f"Access-Control-Allow-Origin: {acao}"
                    elif "matchers" in tmpl:
                        for pattern in tmpl["matchers"]:
                            match = re.search(pattern, body_text, re.IGNORECASE)
                            if match:
                                matched = True
                                matched_content = match.group(0)
                                break

                    if matched:
                        req_str = f"{tmpl['method']} {tmpl['path']} HTTP/1.1\r\nHost: {urlparse(url).netloc}\r\n"
                        for k, v in req_headers.items():
                            req_str += f"{k}: {v}\r\n"

                        resp_headers_str = "\r\n".join(f"{k}: {v}" for k, v in resp.headers.items())
                        resp_str = f"HTTP/1.1 {resp.status_code} {resp.reason_phrase}\r\n{resp_headers_str}\r\n\r\n{body_text[:1024]}"

                        finding = NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="nuclei",
                            scanner_rule_id=tmpl["id"],
                            title=tmpl["name"],
                            description=tmpl["description"],
                            severity=tmpl["severity"],
                            original_severity=tmpl["original_severity"],
                            cve_id=tmpl.get("cve_id"),
                            cwe_id=tmpl.get("cwe_id"),
                            target_location=url,
                            target_component=tmpl["path"],
                            evidence={
                                "request": req_str,
                                "response": resp_str,
                                "matched_content": matched_content,
                                "curl_command": f"curl -X {tmpl['method']} '{url}'",
                            },
                            remediation=tmpl.get("remediation"),
                            references=[f"https://cwe.mitre.org/data/definitions/{tmpl.get('cwe_id', '200')}.html"],
                        )
                        findings.append(finding)
                        if log_callback:
                            await log_callback(
                                "nuclei",
                                f"[FOUND] {tmpl['name']} at {url} (Severity: {tmpl['severity'].value})"
                            )

                except Exception as e:
                    if log_callback:
                        await log_callback("nuclei", f"[DEBUG] Probe for {tmpl['id']} skipped/failed: {str(e)}")

        return findings


class ZAPLabRunner:
    """Embedded high-fidelity OWASP ZAP engine performing passive security audits
    and authorized active web probes.
    """

    async def run(
        self,
        target_url: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
        profile: str,
        log_callback: Optional[Callable[[str, str], Awaitable[None]]] = None,
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []
        base_url = target_url.rstrip("/")

        async with httpx.AsyncClient(timeout=10.0, verify=False, follow_redirects=True) as client:
            # 1. Passive Header & Configuration Audit
            if log_callback:
                await log_callback("zap", f"Executing passive baseline web audit on {target_url}")

            try:
                resp = await client.get(target_url)
                headers_lower = {k.lower(): v for k, v in resp.headers.items()}
                headers_text = "\r\n".join(f"{k}: {v}" for k, v in resp.headers.items())

                # Rule 10020: Missing Anti-clickjacking Header
                has_xfo = "x-frame-options" in headers_lower
                csp = headers_lower.get("content-security-policy", "")
                has_frame_ancestors = "frame-ancestors" in csp.lower()

                if not has_xfo and not has_frame_ancestors:
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="zap",
                            scanner_rule_id="10020",
                            title="Missing Anti-clickjacking Header",
                            description="The response does not include either Content-Security-Policy with 'frame-ancestors' directive or an X-Frame-Options header, leaving the page vulnerable to ClickJacking attacks.",
                            severity=FindingSeverity.MEDIUM,
                            original_severity="Medium",
                            cwe_id="CWE-1021",
                            target_location=target_url,
                            target_component="X-Frame-Options",
                            evidence={
                                "response": f"HTTP/1.1 {resp.status_code}\r\n{headers_text}",
                                "matched_content": "Neither X-Frame-Options nor CSP frame-ancestors detected in HTTP response headers.",
                                "parameter": "X-Frame-Options",
                            },
                            remediation="Modern web browsers support Content-Security-Policy frame-ancestors 'none' or 'self', and X-Frame-Options DENY / SAMEORIGIN.",
                            references=["https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options"],
                        )
                    )

                # Rule 10038: Content Security Policy (CSP) Header Not Set
                if "content-security-policy" not in headers_lower:
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="zap",
                            scanner_rule_id="10038",
                            title="Content Security Policy (CSP) Header Not Set",
                            description="Content Security Policy (CSP) is an added layer of security that helps to detect and mitigate certain types of attacks, including Cross Site Scripting (XSS) and data injection attacks.",
                            severity=FindingSeverity.MEDIUM,
                            original_severity="Medium",
                            cwe_id="CWE-1021",
                            target_location=target_url,
                            target_component="Content-Security-Policy",
                            evidence={
                                "response": f"HTTP/1.1 {resp.status_code}\r\n{headers_text}",
                                "matched_content": "Content-Security-Policy header absent.",
                                "parameter": "Content-Security-Policy",
                            },
                            remediation="Implement a robust Content-Security-Policy restricting allowed script, frame, and object sources.",
                            references=["https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP"],
                        )
                    )

                # Rule 10021: X-Content-Type-Options Header Missing
                if headers_lower.get("x-content-type-options", "").lower() != "nosniff":
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="zap",
                            scanner_rule_id="10021",
                            title="X-Content-Type-Options Header Missing",
                            description="The Anti-MIME-Sniffing header X-Content-Type-Options was not set to 'nosniff'. This allows older browsers to perform MIME-sniffing on the response body, potentially transforming non-executable MIME types into executable script.",
                            severity=FindingSeverity.LOW,
                            original_severity="Low",
                            cwe_id="CWE-693",
                            target_location=target_url,
                            target_component="X-Content-Type-Options",
                            evidence={
                                "response": f"HTTP/1.1 {resp.status_code}\r\n{headers_text}",
                                "matched_content": f"X-Content-Type-Options: {headers_lower.get('x-content-type-options', 'MISSING')}",
                                "parameter": "X-Content-Type-Options",
                            },
                            remediation="Set the X-Content-Type-Options header to 'nosniff' across all HTTP responses.",
                            references=["https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options"],
                        )
                    )

                # Rule 10096: Server Information Disclosure
                server_hdr = headers_lower.get("server") or headers_lower.get("x-powered-by")
                if server_hdr:
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=asset_id,
                            scan_id=scan_id,
                            scanner_engine="zap",
                            scanner_rule_id="10096",
                            title="Server Information Disclosure",
                            description=f"The web server reveals software and version details in HTTP headers ('{server_hdr}'), assisting attackers during fingerprinting.",
                            severity=FindingSeverity.LOW,
                            original_severity="Low",
                            cwe_id="CWE-200",
                            target_location=target_url,
                            target_component="Server / X-Powered-By",
                            evidence={
                                "response": f"Server: {headers_lower.get('server', 'N/A')}\r\nX-Powered-By: {headers_lower.get('x-powered-by', 'N/A')}",
                                "matched_content": server_hdr,
                                "parameter": "Server",
                            },
                            remediation="Suppress or obfuscate the Server and X-Powered-By HTTP response headers in production.",
                            references=["https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html"],
                        )
                    )

            except Exception as e:
                if log_callback:
                    await log_callback("zap", f"[WARN] Passive audit probe encountered error: {str(e)}")

            # 2. Active Probing (Strictly Gated to DEEP_ACTIVE Profile)
            if profile == "DEEP_ACTIVE":
                if log_callback:
                    await log_callback("zap", "Authorized DEEP_ACTIVE mode: launching active SQLi and XSS probes")

                test_endpoints = [
                    (f"{base_url}/api/products", "search"),
                    (f"{base_url}/search", "q"),
                    (f"{base_url}/rest/products/search", "q"),
                    (f"{base_url}/api/users", "id"),
                ]

                # SQL Injection Probe
                sqli_payload = "' OR '1'='1"
                sql_error_patterns = [
                    r"SQL syntax",
                    r"sqlite3::",
                    r"syntax error at or near",
                    r"ORA-[0-9]{5}",
                    r"Unclosed quotation mark",
                    r"check the manual that corresponds to your MySQL",
                    r"PostgreSQL query failed",
                ]

                for endpoint, param in test_endpoints:
                    probe_url = f"{endpoint}?{param}={sqli_payload}"
                    try:
                        resp = await client.get(probe_url)
                        for pattern in sql_error_patterns:
                            match = re.search(pattern, resp.text, re.IGNORECASE)
                            if match:
                                findings.append(
                                    NormalizedFindingCreate(
                                        asset_id=asset_id,
                                        scan_id=scan_id,
                                        scanner_engine="zap",
                                        scanner_rule_id="40018",
                                        title="SQL Injection - Error Based Probing",
                                        description=f"SQL injection error signature '{match.group(0)}' was returned when submitting payload to parameter '{param}'.",
                                        severity=FindingSeverity.HIGH,
                                        original_severity="High",
                                        cwe_id="CWE-89",
                                        target_location=probe_url,
                                        target_component=param,
                                        evidence={
                                            "request": f"GET {probe_url} HTTP/1.1",
                                            "response": resp.text[:1024],
                                            "matched_content": match.group(0),
                                            "parameter": param,
                                            "raw_payload": sqli_payload,
                                        },
                                        remediation="Use parameterized queries (prepared statements) or an ORM to prevent SQL injection.",
                                        references=["https://owasp.org/www-community/attacks/SQL_Injection"],
                                    )
                                )
                                break
                    except Exception:
                        pass

                # Reflected XSS Probe
                xss_canary = "<s3nt1n3l_xss_probe>"
                for endpoint, param in test_endpoints:
                    probe_url = f"{endpoint}?{param}={xss_canary}"
                    try:
                        resp = await client.get(probe_url)
                        if xss_canary in resp.text:
                            findings.append(
                                NormalizedFindingCreate(
                                    asset_id=asset_id,
                                    scan_id=scan_id,
                                    scanner_engine="zap",
                                    scanner_rule_id="40012",
                                    title="Reflected Cross-Site Scripting (XSS)",
                                    description=f"The parameter '{param}' reflects unescaped user input into the HTML body.",
                                    severity=FindingSeverity.HIGH,
                                    original_severity="High",
                                    cwe_id="CWE-79",
                                    target_location=probe_url,
                                    target_component=param,
                                    evidence={
                                        "request": f"GET {probe_url} HTTP/1.1",
                                        "response": resp.text[:1024],
                                        "matched_content": xss_canary,
                                        "parameter": param,
                                        "raw_payload": xss_canary,
                                    },
                                    remediation="Contextually encode all user-supplied input prior to rendering into HTML documents.",
                                    references=["https://owasp.org/www-community/attacks/xss/"],
                                )
                            )
                    except Exception:
                        pass

        return findings


class TrivyLabRunner:
    """Embedded high-fidelity Trivy engine scanning real project manifests
    (package.json, requirements.txt) and source code for secrets and vulnerable dependencies.
    """

    KNOWN_VULNS: Dict[str, List[Dict[str, Any]]] = {
        # Node packages
        "lodash": [
            {
                "cve": "CVE-2021-23337",
                "max_vulnerable": "4.17.20",
                "fixed": "4.17.21",
                "severity": FindingSeverity.HIGH,
                "cvss": 7.2,
                "title": "Command Injection in lodash template function",
                "cwe": "CWE-94",
            }
        ],
        "axios": [
            {
                "cve": "CVE-2020-28168",
                "max_vulnerable": "0.21.0",
                "fixed": "0.21.1",
                "severity": FindingSeverity.MEDIUM,
                "cvss": 5.9,
                "title": "SSRF / Insecure Proxy Header Handling in axios",
                "cwe": "CWE-918",
            }
        ],
        "express-jwt": [
            {
                "cve": "CVE-2020-15084",
                "max_vulnerable": "5.9.9",
                "fixed": "6.0.0",
                "severity": FindingSeverity.HIGH,
                "cvss": 7.5,
                "title": "Algorithms not specified in express-jwt",
                "cwe": "CWE-347",
            }
        ],
        # Python packages
        "requests": [
            {
                "cve": "CVE-2023-32681",
                "max_vulnerable": "2.30.0",
                "fixed": "2.31.0",
                "severity": FindingSeverity.MEDIUM,
                "cvss": 6.1,
                "title": "Unintended Proxy-Authorization Header Leak in requests",
                "cwe": "CWE-200",
            }
        ],
        "urllib3": [
            {
                "cve": "CVE-2023-45803",
                "max_vulnerable": "2.0.6",
                "fixed": "2.0.7",
                "severity": FindingSeverity.MEDIUM,
                "cvss": 6.5,
                "title": "HTTP Request Body Leak on Redirect in urllib3",
                "cwe": "CWE-200",
            }
        ],
        "cryptography": [
            {
                "cve": "CVE-2023-49083",
                "max_vulnerable": "41.0.5",
                "fixed": "41.0.6",
                "severity": FindingSeverity.HIGH,
                "cvss": 7.5,
                "title": "NULL Pointer Dereference in PKCS7 Parsing in cryptography",
                "cwe": "CWE-476",
            }
        ],
    }

    SECRET_PATTERNS = [
        {
            "id": "aws-access-key",
            "name": "AWS Access Key ID",
            "regex": re.compile(r"\b(AKIA[0-9A-Z]{16})\b"),
            "severity": FindingSeverity.CRITICAL,
        },
        {
            "id": "github-pat",
            "name": "GitHub Personal Access Token",
            "regex": re.compile(r"\b(ghp_[A-Za-z0-9]{36})\b"),
            "severity": FindingSeverity.CRITICAL,
        },
        {
            "id": "generic-private-key",
            "name": "Asymmetric Private Key",
            "regex": re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH)? PRIVATE KEY-----"),
            "severity": FindingSeverity.CRITICAL,
        },
        {
            "id": "slack-webhook",
            "name": "Slack Incoming Webhook URL",
            "regex": re.compile(r"https://hooks\.slack\.com/services/T[0-9A-Z]{8}/B[0-9A-Z]{8}/[0-9A-Za-z]{24}"),
            "severity": FindingSeverity.HIGH,
        },
    ]

    def _version_is_vulnerable(self, installed: str, max_vuln: str) -> bool:
        """Simple semantic version comparison."""
        try:
            inst_parts = [int(p) for p in re.split(r"[^\d]+", installed) if p]
            max_parts = [int(p) for p in re.split(r"[^\d]+", max_vuln) if p]
            return inst_parts <= max_parts
        except Exception:
            return installed == max_vuln

    def run(
        self,
        target_path: str,
        asset_id: uuid.UUID,
        scan_id: uuid.UUID,
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []
        path = Path(target_path)

        if not path.exists():
            return findings

        # Collect files to scan (if directory, inspect recursively; if single file, inspect directly)
        files_to_scan: List[Path] = []
        if path.is_file():
            files_to_scan.append(path)
        else:
            for root, _, files in os.walk(path):
                for f in files:
                    if not any(ignored in root for ignored in [".git", "node_modules", ".venv", "__pycache__"]):
                        files_to_scan.append(Path(root) / f)

        for file_path in files_to_scan:
            filename = file_path.name.lower()

            # 1. Manifest Analysis: package.json
            if filename == "package.json":
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        data = json.load(f)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                    for pkg, ver_spec in deps.items():
                        ver = re.sub(r"[^0-9.]", "", ver_spec)
                        if pkg in self.KNOWN_VULNS:
                            for vuln in self.KNOWN_VULNS[pkg]:
                                if self._version_is_vulnerable(ver, vuln["max_vulnerable"]):
                                    findings.append(
                                        NormalizedFindingCreate(
                                            asset_id=asset_id,
                                            scan_id=scan_id,
                                            scanner_engine="trivy",
                                            scanner_rule_id=vuln["cve"],
                                            title=f"{vuln['title']} ({pkg}@{ver})",
                                            description=f"Package {pkg} version {ver} is vulnerable to {vuln['cve']}. Upgrade to version {vuln['fixed']} or newer.",
                                            severity=vuln["severity"],
                                            original_severity=vuln["severity"].value,
                                            cve_id=vuln["cve"],
                                            cwe_id=vuln["cwe"],
                                            cvss_score=vuln["cvss"],
                                            target_location=str(file_path),
                                            target_component=pkg,
                                            affected_version=ver,
                                            fixed_version=vuln["fixed"],
                                            evidence={
                                                "file_path": str(file_path),
                                                "matched_content": f'"{pkg}": "{ver_spec}"',
                                            },
                                            remediation=f"Update {pkg} in package.json to >= {vuln['fixed']}.",
                                            references=[f"https://nvd.nist.gov/vuln/detail/{vuln['cve']}"],
                                        )
                                    )
                except Exception:
                    pass

            # 2. Manifest Analysis: requirements.txt
            elif filename == "requirements.txt":
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines, 1):
                        line_clean = line.strip()
                        if "==" in line_clean or ">=" in line_clean:
                            sep = "==" if "==" in line_clean else ">="
                            parts = line_clean.split(sep)
                            pkg = parts[0].strip().lower()
                            ver = parts[1].strip()
                            if pkg in self.KNOWN_VULNS:
                                for vuln in self.KNOWN_VULNS[pkg]:
                                    if self._version_is_vulnerable(ver, vuln["max_vulnerable"]):
                                        findings.append(
                                            NormalizedFindingCreate(
                                                asset_id=asset_id,
                                                scan_id=scan_id,
                                                scanner_engine="trivy",
                                                scanner_rule_id=vuln["cve"],
                                                title=f"{vuln['title']} ({pkg}=={ver})",
                                                description=f"Dependency {pkg}=={ver} is vulnerable to {vuln['cve']}. Recommended remediation: update to {vuln['fixed']}.",
                                                severity=vuln["severity"],
                                                original_severity=vuln["severity"].value,
                                                cve_id=vuln["cve"],
                                                cwe_id=vuln["cwe"],
                                                cvss_score=vuln["cvss"],
                                                target_location=str(file_path),
                                                target_component=pkg,
                                                affected_version=ver,
                                                fixed_version=vuln["fixed"],
                                                evidence={
                                                    "file_path": str(file_path),
                                                    "line_number": idx,
                                                    "matched_content": line_clean,
                                                },
                                                remediation=f"Update {pkg} in requirements.txt to >={vuln['fixed']}.",
                                                references=[f"https://nvd.nist.gov/vuln/detail/{vuln['cve']}"],
                                            )
                                        )
                except Exception:
                    pass

            # 3. Secret Pattern Scanning
            if file_path.suffix in [".py", ".js", ".ts", ".json", ".yml", ".yaml", ".env", ".txt", ".md", ".sh"]:
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content_lines = f.readlines()
                    for line_no, line_text in enumerate(content_lines, 1):
                        for sec in self.SECRET_PATTERNS:
                            m = sec["regex"].search(line_text)
                            if m:
                                matched_str = m.group(0)
                                # Mask sensitive portion for safe storage
                                masked = matched_str[:4] + "*" * (len(matched_str) - 8) + matched_str[-4:] if len(matched_str) > 8 else "***"
                                findings.append(
                                    NormalizedFindingCreate(
                                        asset_id=asset_id,
                                        scan_id=scan_id,
                                        scanner_engine="trivy",
                                        scanner_rule_id=sec["id"],
                                        title=f"Hardcoded Secret Detected: {sec['name']}",
                                        description=f"A hardcoded {sec['name']} secret pattern was found at line {line_no} in {file_path.name}.",
                                        severity=sec["severity"],
                                        original_severity=sec["severity"].value,
                                        cwe_id="CWE-798",
                                        target_location=str(file_path),
                                        target_component=file_path.name,
                                        evidence={
                                            "file_path": str(file_path),
                                            "line_number": line_no,
                                            "matched_content": masked,
                                        },
                                        remediation="Immediately revoke the exposed secret and store credentials in a secure secrets manager.",
                                        references=["https://cwe.mitre.org/data/definitions/798.html"],
                                    )
                                )
                except Exception:
                    pass

        return findings
