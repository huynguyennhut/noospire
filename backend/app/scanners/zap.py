import asyncio
import json
import os
import shutil
import tempfile
import time
from typing import Awaitable, Callable, List, Tuple

from backend.app.scanners.base import (
    BaseScannerAdapter,
    CancellationToken,
    ScanExecutionRequest,
    ScannerExecutionResult,
)
from backend.app.scanners.lab_runners import ZAPLabRunner
from backend.app.schemas.common import AssetType, FindingSeverity
from backend.app.schemas.finding import NormalizedFindingCreate


class ZAPAdapter(BaseScannerAdapter):
    """Adapter for OWASP ZAP (Zed Attack Proxy).
    Executes passive security audits and explicitly authorized active scans.
    """

    @property
    def engine_name(self) -> str:
        return "zap"

    @property
    def supported_asset_types(self) -> List[AssetType]:
        return [AssetType.WEB_APP, AssetType.API_ENDPOINT]

    def is_available(self) -> Tuple[bool, str]:
        zap_cli = shutil.which("zap.bat") or shutil.which("zap.sh") or shutil.which("zap")
        if zap_cli:
            return True, f"Native ZAP binary located at {zap_cli}"
        return False, "Native ZAP CLI absent; high-fidelity ZAPLabRunner available"

    def _map_risk(self, risk_str: str) -> FindingSeverity:
        r = (risk_str or "").lower().strip()
        if r in ("high", "3") or r.startswith("high"):
            return FindingSeverity.HIGH
        elif r in ("medium", "2") or r.startswith("medium") or r.startswith("med"):
            return FindingSeverity.MEDIUM
        elif r in ("low", "1") or r.startswith("low"):
            return FindingSeverity.LOW
        return FindingSeverity.INFO

    def parse_findings(
        self, raw_output: str, request: ScanExecutionRequest
    ) -> List[NormalizedFindingCreate]:
        findings: List[NormalizedFindingCreate] = []
        try:
            data = json.loads(raw_output)
            all_alerts: List[dict] = []
            if isinstance(data, dict):
                sites = data.get("site", [])
                if isinstance(sites, list):
                    for s in sites:
                        all_alerts.extend(s.get("alerts", []))
                elif isinstance(sites, dict):
                    all_alerts.extend(sites.get("alerts", []))
                if not all_alerts and "alerts" in data:
                    all_alerts = data.get("alerts", [])
            elif isinstance(data, list):
                all_alerts = data

            for alert in all_alerts:
                plugin_id = str(alert.get("pluginId", alert.get("pluginid", alert.get("plugin_id", "zap-rule"))))
                title = alert.get("alert", alert.get("name", "OWASP ZAP Finding"))
                desc = alert.get("description", alert.get("desc", "Vulnerability detected by OWASP ZAP."))
                raw_risk = str(alert.get("riskcode", alert.get("risk", alert.get("riskdesc", "Low"))))
                severity = self._map_risk(raw_risk)
                cwe_id = f"CWE-{alert['cweid']}" if alert.get("cweid") else None

                instances = alert.get("instances", [])
                if instances and isinstance(instances, list):
                    for inst in instances:
                        inst_uri = inst.get("uri", alert.get("url", request.target_locator))
                        evidence = {
                            "request": inst.get("attack", alert.get("attack", "")),
                            "response": inst.get("evidence", alert.get("evidence", "")),
                            "matched_content": inst.get("evidence", alert.get("evidence", "")),
                            "parameter": inst.get("param", alert.get("param", "")),
                            "method": inst.get("method", ""),
                        }
                        findings.append(
                            NormalizedFindingCreate(
                                asset_id=request.asset_id,
                                scan_id=request.scan_id,
                                scanner_engine=self.engine_name,
                                scanner_rule_id=plugin_id,
                                title=title,
                                description=desc,
                                severity=severity,
                                original_severity=raw_risk,
                                cwe_id=cwe_id,
                                target_location=inst_uri,
                                target_component=inst.get("param") or alert.get("param") or plugin_id,
                                evidence=evidence,
                                remediation=alert.get("solution"),
                                references=[alert.get("reference", "https://www.zaproxy.org/")],
                            )
                        )
                else:
                    evidence = {
                        "request": alert.get("attack", ""),
                        "response": alert.get("evidence", ""),
                        "matched_content": alert.get("evidence", ""),
                        "parameter": alert.get("param", ""),
                    }
                    findings.append(
                        NormalizedFindingCreate(
                            asset_id=request.asset_id,
                            scan_id=request.scan_id,
                            scanner_engine=self.engine_name,
                            scanner_rule_id=plugin_id,
                            title=title,
                            description=desc,
                            severity=severity,
                            original_severity=raw_risk,
                            cwe_id=cwe_id,
                            target_location=alert.get("url", request.target_locator),
                            target_component=alert.get("param") or plugin_id,
                            evidence=evidence,
                            remediation=alert.get("solution"),
                            references=[alert.get("reference", "https://www.zaproxy.org/")],
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

        # Authorization Gate for Active Probes
        if request.profile == "DEEP_ACTIVE":
            is_verified = request.custom_config.get("is_verified", False)
            if not is_verified:
                msg = "Unauthorized active scan: DEEP_ACTIVE requires verified asset ownership."
                await log_callback(self.engine_name, f"[ERROR] {msg}")
                raise PermissionError(msg)

        is_avail, desc = self.is_available()
        if is_avail:
            await log_callback(self.engine_name, f"Executing ZAP CLI: {desc}")
            zap_binary = shutil.which("zap.bat") or shutil.which("zap.sh") or shutil.which("zap")
            if zap_binary:
                report_file = os.path.join(tempfile.gettempdir(), f"zap_report_{request.scan_id}.json")
                try:
                    cmd = [zap_binary, "-cmd", "-quickurl", request.target_locator, "-quickout", report_file]
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
                    report_content = ""
                    if os.path.exists(report_file):
                        try:
                            with open(report_file, "r", encoding="utf-8") as rf:
                                report_content = rf.read()
                            os.remove(report_file)
                        except Exception:
                            pass
                    findings = self.parse_findings(report_content or raw_out, request)
                    duration = time.time() - start_time
                    return ScannerExecutionResult(
                        engine_name=self.engine_name,
                        execution_mode="binary_cli",
                        success=(proc.returncode == 0),
                        exit_code=proc.returncode or 0,
                        raw_output=report_content or raw_out,
                        error_message=stderr_data.decode("utf-8", errors="ignore") if proc.returncode != 0 else None,
                        duration_seconds=round(duration, 2),
                        findings=findings,
                    )
                except Exception as e:
                    await log_callback(self.engine_name, f"ZAP CLI execution encountered error: {e}, falling back to httpx engine")

        # High-Fidelity Embedded Lab Runner Fallback
        await log_callback(
            self.engine_name,
            f"Invoking embedded ZAPLabRunner (Profile: {request.profile})"
        )
        runner = ZAPLabRunner()
        findings = await runner.run(
            target_url=request.target_locator,
            asset_id=request.asset_id,
            scan_id=request.scan_id,
            profile=request.profile,
            log_callback=log_callback,
        )

        duration = time.time() - start_time
        return ScannerExecutionResult(
            engine_name=self.engine_name,
            execution_mode="lab_engine",
            success=True,
            exit_code=0,
            raw_output=f"ZAPLabRunner completed audit; {len(findings)} alerts identified.",
            error_message=None,
            duration_seconds=round(duration, 2),
            findings=findings,
        )
