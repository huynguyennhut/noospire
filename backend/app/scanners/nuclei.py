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
from backend.app.scanners.lab_runners import NucleiLabRunner
from backend.app.schemas.common import AssetType, FindingSeverity, ScanProfile
from backend.app.schemas.finding import NormalizedFindingCreate


class NucleiAdapter(BaseScannerAdapter):
    """Adapter for ProjectDiscovery Nuclei vulnerability scanner.
    Executes native CLI binary when present on PATH, with high-fidelity embedded lab runner fallback.
    """

    @property
    def engine_name(self) -> str:
        return "nuclei"

    @property
    def supported_asset_types(self) -> List[AssetType]:
        return [AssetType.DOMAIN, AssetType.WEB_APP, AssetType.API_ENDPOINT]

    def is_available(self) -> Tuple[bool, str]:
        binary = shutil.which("nuclei") or shutil.which("nuclei.exe")
        if binary:
            return True, f"Native CLI binary located at {binary}"
        return False, "Native binary absent; high-fidelity NucleiLabRunner available"

    def _map_severity(self, raw_sev: str) -> FindingSeverity:
        sev = (raw_sev or "").lower()
        if sev == "critical":
            return FindingSeverity.CRITICAL
        elif sev == "high":
            return FindingSeverity.HIGH
        elif sev == "medium":
            return FindingSeverity.MEDIUM
        elif sev == "low":
            return FindingSeverity.LOW
        return FindingSeverity.INFO

    def parse_findings(
        self, raw_output: str, request: ScanExecutionRequest
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []
        for line in raw_output.splitlines():
            line_str = line.strip()
            if not line_str or not line_str.startswith("{"):
                continue
            try:
                data = json.loads(line_str)
                info = data.get("info", {})
                tmpl_id = data.get("template-id", "unknown-nuclei-rule")
                title = info.get("name", tmpl_id)
                desc = info.get("description", "Vulnerability detected by Nuclei template.")
                raw_sev = info.get("severity", "info")
                severity = self._map_severity(raw_sev)

                classification = info.get("classification", {})
                cve_id = None
                if classification.get("cve-id"):
                    cve_list = classification.get("cve-id")
                    cve_id = cve_list[0] if isinstance(cve_list, list) else str(cve_list)

                cwe_id = None
                if classification.get("cwe-id"):
                    cwe_list = classification.get("cwe-id")
                    cwe_id = cwe_list[0] if isinstance(cwe_list, list) else str(cwe_list)

                target_loc = data.get("matched-at", request.target_locator)
                matched_content = str(data.get("extracted-results", "")) or None

                evidence = {
                    "request": data.get("request"),
                    "response": data.get("response"),
                    "matched_content": matched_content,
                    "curl_command": data.get("curl-command"),
                }

                findings.append(
                    NormalizedFindingCreate(
                        asset_id=request.asset_id,
                        scan_id=request.scan_id,
                        scanner_engine=self.engine_name,
                        scanner_rule_id=tmpl_id,
                        title=title,
                        description=desc,
                        severity=severity,
                        original_severity=raw_sev,
                        cve_id=cve_id,
                        cwe_id=cwe_id,
                        target_location=target_loc,
                        target_component=tmpl_id,
                        evidence=evidence,
                        remediation=info.get("remediation"),
                        references=info.get("reference", []),
                    )
                )
            except Exception:
                continue

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
            await log_callback(self.engine_name, f"Executing Nuclei CLI: {desc}")
            timeout_limit = min(float(request.timeout_seconds), 15.0) if request.profile in ("QUICK", ScanProfile.QUICK.value) else float(request.timeout_seconds)
            cmd = [
                shutil.which("nuclei") or "nuclei",
                "-target", request.target_locator,
                "-jsonl",
                "-silent",
                "-nc",
                "-timeout", "5",
                "-tags", "cve,exposure",
                "-c", "10",
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
                    proc.communicate(), timeout=timeout_limit
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
                await log_callback(self.engine_name, f"CLI execution encountered error: {e}, falling back to lab runner")

        # High-Fidelity Embedded Lab Runner Fallback
        await log_callback(
            self.engine_name,
            "Native binary absent or failed; invoking embedded NucleiLabRunner"
        )
        runner = NucleiLabRunner()
        findings = await runner.run(
            target_url=request.target_locator,
            asset_id=request.asset_id,
            scan_id=request.scan_id,
            log_callback=log_callback,
        )
        duration = time.time() - start_time
        return ScannerExecutionResult(
            engine_name=self.engine_name,
            execution_mode="lab_engine",
            success=True,
            exit_code=0,
            raw_output=f"NucleiLabRunner evaluated {len(runner.TEMPLATES)} approved templates; found {len(findings)} issues.",
            error_message=None,
            duration_seconds=round(duration, 2),
            findings=findings,
        )
