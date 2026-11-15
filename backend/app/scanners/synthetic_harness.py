import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.asset import Asset
from backend.app.models.checklist import ChecklistResultState
from backend.app.models.synthetic_identity import SyntheticIdentity

logger = logging.getLogger("sentinel.synthetic_harness")


class SyntheticTestHarness:
    """Dedicated test harness for API authorization testing (BOLA/IDOR and BFLA).
    Uses customer-approved synthetic accounts and test records.
    
    INVARIANT:
    If test account credentials are missing or inactive, marks checks BLOCKED
    (NEVER PASS, NEVER NOT_APPLICABLE).
    """

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    async def get_active_identities(
        self, session: AsyncSession, role: Optional[str] = None
    ) -> List[SyntheticIdentity]:
        """Queries active synthetic identities from the database."""
        stmt = select(SyntheticIdentity).where(SyntheticIdentity.is_active == True)  # noqa: E712
        if role:
            stmt = stmt.where(SyntheticIdentity.role == role)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def evaluate_bola(
        self, asset: Asset, session: AsyncSession
    ) -> Dict[str, Any]:
        """Evaluates API-001 (Broken Object Level Authorization / BOLA / IDOR).
        
        Requires at least two distinct active student identities to verify horizontal
        access control boundaries between peers.
        """
        start_time = time.perf_counter()
        students = await self.get_active_identities(session, role="STUDENT")

        # Invariant: If test account credentials are missing/inactive, mark BLOCKED
        if len(students) < 2:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning(
                "BOLA assessment blocked: required 2 synthetic student identities, found %d",
                len(students),
            )
            return {
                "check_id": "API-001",
                "state": ChecklistResultState.BLOCKED.value,
                "evidence_payload": {
                    "reason": "Missing required synthetic student identities for cross-account testing.",
                    "required_identities": 2,
                    "active_identities_found": len(students),
                    "identities": [s.identifier for s in students],
                    "guidance": "Seed or activate at least two synthetic student accounts in synthetic_identities table.",
                },
                "execution_duration_ms": duration_ms,
            }

        student_a = students[0]
        student_b = students[1]

        # Update last_used_at timestamps
        now_utc = datetime.now(timezone.utc)
        student_a.last_used_at = now_utc
        student_b.last_used_at = now_utc
        await session.commit()

        base_url = asset.target_locator.rstrip("/")
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        # Test cross-account access: Student A attempts to access Student B's learning records
        target_endpoint = urljoin(base_url, f"/api/users/{student_b.identifier}/learning-records")
        auth_headers = {
            "Authorization": f"Bearer synthetic_token_{student_a.identifier}",
            "X-Synthetic-Identity": student_a.identifier,
            "User-Agent": "Noospire-Synthetic-Harness/1.0",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                resp = await client.get(target_endpoint, headers=auth_headers)
                status_code = resp.status_code
                resp_text = resp.text[:500]

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # If student A can view student B's records with 200 OK -> BOLA VULNERABILITY
            if status_code == 200:
                return {
                    "check_id": "API-001",
                    "state": ChecklistResultState.FAIL.value,
                    "evidence_payload": {
                        "endpoint": target_endpoint,
                        "requesting_identity": student_a.identifier,
                        "target_resource_owner": student_b.identifier,
                        "response_status": status_code,
                        "response_snippet": resp_text,
                        "finding": "Cross-account authorization bypass confirmed: Student A successfully retrieved Student B records.",
                    },
                    "execution_duration_ms": duration_ms,
                }
            elif status_code in (401, 403, 404):
                return {
                    "check_id": "API-001",
                    "state": ChecklistResultState.PASS.value,
                    "evidence_payload": {
                        "endpoint": target_endpoint,
                        "requesting_identity": student_a.identifier,
                        "target_resource_owner": student_b.identifier,
                        "response_status": status_code,
                        "details": "Cross-account access correctly denied by authorization gate.",
                    },
                    "execution_duration_ms": duration_ms,
                }
            else:
                return {
                    "check_id": "API-001",
                    "state": ChecklistResultState.NEEDS_REVIEW.value,
                    "evidence_payload": {
                        "endpoint": target_endpoint,
                        "response_status": status_code,
                        "response_snippet": resp_text,
                        "details": f"Unexpected HTTP status {status_code} received during BOLA validation.",
                    },
                    "execution_duration_ms": duration_ms,
                }

        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning("BOLA synthetic check exception against %s: %s", target_endpoint, exc)
            return {
                "check_id": "API-001",
                "state": ChecklistResultState.ERROR.value,
                "evidence_payload": {
                    "endpoint": target_endpoint,
                    "error": str(exc),
                    "details": "Probe failed due to connection error or unreachable target.",
                },
                "execution_duration_ms": duration_ms,
            }

    async def evaluate_bfla(
        self, asset: Asset, session: AsyncSession
    ) -> Dict[str, Any]:
        """Evaluates API-005 (Broken Function Level Authorization / BFLA).
        
        Uses a low-privileged synthetic student identity to attempt executing
        restricted administrative function endpoints.
        """
        start_time = time.perf_counter()
        students = await self.get_active_identities(session, role="STUDENT")

        # Invariant: If low-privileged student identity is missing, mark BLOCKED
        if not students:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.warning("BFLA assessment blocked: no active synthetic student identity found")
            return {
                "check_id": "API-005",
                "state": ChecklistResultState.BLOCKED.value,
                "evidence_payload": {
                    "reason": "Missing synthetic student identity for function-level privilege escalation testing.",
                    "required_role": "STUDENT",
                    "guidance": "Seed an active STUDENT role identity in synthetic_identities table.",
                },
                "execution_duration_ms": duration_ms,
            }

        student = students[0]
        student.last_used_at = datetime.now(timezone.utc)
        await session.commit()

        base_url = asset.target_locator.rstrip("/")
        if not base_url.startswith("http"):
            base_url = f"https://{base_url}"

        # Probing restricted administrative functions with low-privilege student credentials
        admin_endpoints = [
            "/api/v1/system/config",
            "/api/admin/users",
            "/api/v1/operations/kill-switch",
        ]

        bfla_failures = []
        tested_endpoints = []

        headers = {
            "Authorization": f"Bearer synthetic_token_{student.identifier}",
            "X-Synthetic-Identity": student.identifier,
            "User-Agent": "Noospire-Synthetic-Harness/1.0",
        }

        async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
            for path in admin_endpoints:
                target_url = urljoin(base_url, path)
                try:
                    resp = await client.get(target_url, headers=headers)
                    tested_endpoints.append({"url": target_url, "status": resp.status_code})
                    if resp.status_code in (200, 201, 204):
                        bfla_failures.append({
                            "endpoint": target_url,
                            "status": resp.status_code,
                            "snippet": resp.text[:200],
                        })
                except Exception as exc:
                    tested_endpoints.append({"url": target_url, "error": str(exc)})

        duration_ms = int((time.perf_counter() - start_time) * 1000)

        if bfla_failures:
            return {
                "check_id": "API-005",
                "state": ChecklistResultState.FAIL.value,
                "evidence_payload": {
                    "requesting_identity": student.identifier,
                    "role": student.role,
                    "vulnerable_endpoints": bfla_failures,
                    "tested_endpoints": tested_endpoints,
                    "finding": "Vertical privilege escalation detected: Low-privileged student accessed administrative functions.",
                },
                "execution_duration_ms": duration_ms,
            }

        # If any endpoint returned 401 or 403, and none succeeded -> PASS
        denied_count = sum(1 for ep in tested_endpoints if ep.get("status") in (401, 403, 404))
        if denied_count > 0:
            return {
                "check_id": "API-005",
                "state": ChecklistResultState.PASS.value,
                "evidence_payload": {
                    "requesting_identity": student.identifier,
                    "role": student.role,
                    "tested_endpoints": tested_endpoints,
                    "details": "Function-level access controls successfully restricted administrative endpoints.",
                },
                "execution_duration_ms": duration_ms,
            }

        return {
            "check_id": "API-005",
            "state": ChecklistResultState.NEEDS_REVIEW.value,
            "evidence_payload": {
                "requesting_identity": student.identifier,
                "tested_endpoints": tested_endpoints,
                "details": "Administrative endpoints were unreachable or returned ambiguous responses.",
            },
            "execution_duration_ms": duration_ms,
        }

    async def run_all(
        self, asset: Asset, session: AsyncSession
    ) -> List[Dict[str, Any]]:
        """Executes both BOLA (API-001) and BFLA (API-005) assessment checks."""
        bola_res = await self.evaluate_bola(asset, session)
        bfla_res = await self.evaluate_bfla(asset, session)
        return [bola_res, bfla_res]


__all__ = ["SyntheticTestHarness"]
