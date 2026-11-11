import asyncio
import json
import shutil
import time
from typing import Awaitable, Callable, List, Tuple

from backend.app.scanners.base import (
    BaseScannerAdapter,
    CancellationToken,
    ScanExecutionRequest,
    ScannerExecutionResult,
)
from backend.app.scanners.lab_runners import TrivyLabRunner
from backend.app.schemas.common import AssetType, FindingSeverity
from backend.app.schemas.finding import NormalizedFindingCreate


class TrivyAdapter(BaseScannerAdapter):
    """Adapter for Aqua Security Trivy vulnerability and secret scanner.
    Supports filesystem SCA, container inspection, and source secret scanning.
    """

    @property
    def engine_name(self) -> str:
        return "trivy"

    @property
    def supported_asset_types(self) -> List[AssetType]:
        return [AssetType.PROJECT_ARCHIVE, AssetType.CONTAINER_IMAGE]

    def is_available(self) -> Tuple[bool, str]:
        trivy_cli = shutil.which("trivy") or shutil.which("trivy.exe")
        if trivy_cli:
            return True, f"Native Trivy binary located at {trivy_cli}"
        return False, "Native Trivy CLI absent; high-fidelity TrivyLabRunner available"

    def _map_severity(self, raw_sev: str) -> FindingSeverity:
        s = (raw_sev or "").upper()
        if s == "CRITICAL":
            return FindingSeverity.CRITICAL
        elif s == "HIGH":
            return FindingSeverity.HIGH
        elif s == "MEDIUM":
            return FindingSeverity.MEDIUM
        return FindingSeverity.LOW

    def parse_findings(
        self, raw_output: str, request: ScanExecutionRequest
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []
        try:
            data = json.loads(raw_output)
            results = data.get("Results", [])

            for res in results:
                target_file = res.get("Target", request.target_locator)

                # 1. Vulnerabilities (Dependencies/SCA)
                for vuln in res.get("Vulnerabilities", []):
                    cve_id = vuln.get("VulnerabilityID", "UNKNOWN-CVE")
                    pkg = vuln.get("PkgName", "unknown-package")
                    installed_ver = vuln.get("InstalledVersion", "")
                    fixed_ver = vuln.get("FixedVersion")
                    raw_sev = vuln.get("Severity", "LOW")
                    title = vuln.get("Title") or f"Vulnerability in {pkg} ({cve_id})"
                    desc = vuln.get("Description") or f"Package {pkg} is affected by {cve_id}."

                    cvss_score = None
                    cvss_vector = None
                    cvss_data = vuln.get("CVSS", {})
                    for src in ("nvd", "redhat", "ghsa"):
                        if src in cvss_data:
                            cvss_score = cvss_data[src].get("V3Score")
                            cvss_vector = cvss_data[src].get("V3Vector")
                            break

                    cwe_list = vuln.get("CweIDs", [])
                    cwe_id = cwe_list[0] if cwe_list else None

                    evidence = {
                        "file_path": target_file,
                        "matched_content": f"{pkg}@{installed_ver}",
                    }

                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=request.asset_id,
                            scan_id=request.scan_id,
                            scanner_engine=self.engine_name,
                            scanner_rule_id=cve_id,
                            title=title,
                            description=desc,
                            severity=self._map_severity(raw_sev),
                            original_severity=raw_sev,
                            cve_id=cve_id,
                            cwe_id=cwe_id,
                            cvss_score=cvss_score,
                            cvss_vector=cvss_vector,
                            target_location=target_file,
                            target_component=pkg,
                            affected_version=installed_ver,
                            fixed_version=fixed_ver,
                            evidence=evidence,
                            remediation=f"Upgrade {pkg} to version {fixed_ver} or newer." if fixed_ver else "Review advisory.",
                            references=vuln.get("References", []),
                        )
                    )

                # 2. Hardcoded Secrets
                for secret in res.get("Secrets", []):
                    rule_id = secret.get("RuleID", "hardcoded-secret")
                    sec_title = secret.get("Title", "Exposed Secret")
                    raw_sev = secret.get("Severity", "CRITICAL")
                    start_line = secret.get("StartLine")
                    match_snippet = secret.get("Match", "***")

                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=request.asset_id,
                            scan_id=request.scan_id,
                            scanner_engine=self.engine_name,
                            scanner_rule_id=rule_id,
                            title=f"Secret Detected: {sec_title}",
                            description=f"Secret rule '{rule_id}' matched sensitive data at line {start_line}.",
                            severity=self._map_severity(raw_sev),
                            original_severity=raw_sev,
                            cwe_id="CWE-798",
                            target_location=target_file,
                            target_component=target_file,
                            evidence={
                                "file_path": target_file,
                                "line_number": start_line,
                                "matched_content": match_snippet,
                            },
                            remediation="Immediately revoke and rotate the exposed credential.",
                            references=["https://cwe.mitre.org/data/definitions/798.html"],
                        )
                    )
        except Exception:
            pass

        return findings

    async def execute(
        self,
        request: ScanExecutionRequest,
        cancel_token: CancellationToken,
        log_callback: Callable[[str, str], Awaitable[None]],
    ) -> ScannerExecutionResult:
        start_time = time.time()
        is_avail, desc = self.is_available()

        if is_avail:
            await log_callback(self.engine_name, f"Executing Trivy CLI: {desc}")
            subcommand = "fs"
            asset_type_str = str(getattr(request, "asset_type", "")).upper()
            if "CONTAINER_IMAGE" in asset_type_str or getattr(request, "asset_type", None) == AssetType.CONTAINER_IMAGE:
                subcommand = "image"
            elif "SBOM" in asset_type_str:
                subcommand = "sbom"

            cmd = [
                shutil.which("trivy") or "trivy",
                subcommand,
                "--format", "json",
                "--security-checks", "vuln,secret",
                request.target_locator,
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                from backend.app.core.dispatcher import process_safety
                await process_safety.register_pid(request.scan_id, proc.pid)
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(), timeout=float(request.timeout_seconds)
                )
                raw_out = stdout_data.decode("utf-8", errors="ignore")
                findings = self.parse_findings(raw_out, request)
                duration = time.time() - start_time
                return ScannerExecutionResult(
                    engine_name=self.engine_name,
                    execution_mode="binary_cli",
                    success=(proc.returncode == 0),
                    exit_code=proc.returncode or 0,
                    raw_output=raw_out,
                    error_message=stderr_data.decode("utf-8", errors="ignore") if proc.returncode != 0 else None,
                    duration_seconds=round(duration, 2),
                    findings=findings,
                )
            except Exception as e:
                await log_callback(self.engine_name, f"Trivy CLI failed: {e}; falling back to lab runner")

        # High-Fidelity Embedded Lab Runner Fallback
        await log_callback(
            self.engine_name,
            f"Invoking embedded TrivyLabRunner against {request.target_locator}"
        )
        runner = TrivyLabRunner()
        findings = runner.run(
            target_path=request.target_locator,
            asset_id=request.asset_id,
            scan_id=request.scan_id,
        )

        duration = time.time() - start_time
        return ScannerExecutionResult(
            engine_name=self.engine_name,
            execution_mode="lab_engine",
            success=True,
            exit_code=0,
            raw_output=f"TrivyLabRunner scanned manifests and secrets; found {len(findings)} findings.",
            error_message=None,
            duration_seconds=round(duration, 2),
            findings=findings,
        )
