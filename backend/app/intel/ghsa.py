"""GitHub Advisory Database REST API Client.

Supports advisory querying, rate-limit header tracking (X-RateLimit-Remaining, X-RateLimit-Reset),
and offline sample fixture fallbacks.
Conforms to Noosforge Sentinel R3 specifications.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("sentinel.intel.ghsa")


class GHSAClient:
    """GitHub Advisory Database Ingestion Client."""

    BASE_URL = "https://api.github.com/advisories"

    def __init__(
        self,
        token: Optional[str] = None,
        fixture_path: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.timeout = timeout
        self.rate_limit_remaining: Optional[int] = None
        self.rate_limit_reset: Optional[int] = None

        if fixture_path:
            self.fixture_path = Path(fixture_path)
        else:
            base_dir = Path(__file__).resolve().parents[3]
            self.fixture_path = base_dir / "fixtures" / "threat_intel" / "ghsa.json"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "NoosforgeSentinel/1.0 (+https://github.com/noosforge/sentinel)",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def load_offline_fixture(self) -> List[Dict[str, Any]]:
        """Load GitHub Advisory sample fixture from disk."""
        if not self.fixture_path.exists():
            logger.warning("GHSA offline fixture not found at %s", self.fixture_path)
            return []

        try:
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [self.parse_advisory(item) for item in data]
            return []
        except Exception as e:
            logger.error("Failed to parse GHSA offline fixture: %s", e)
            return []

    def parse_advisory(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw GitHub advisory record into standardized dictionary."""
        ghsa_id = item.get("ghsa_id", "")
        cve_id = item.get("cve_id")

        cwes: List[str] = []
        for c in item.get("cwes", []):
            if isinstance(c, dict) and "cwe_id" in c:
                cwes.append(c["cwe_id"])
            elif isinstance(c, str):
                cwes.append(c)

        cvss = item.get("cvss", {})
        cvss_score = cvss.get("score") if isinstance(cvss, dict) else None
        cvss_vector = cvss.get("vector_string") if isinstance(cvss, dict) else None

        return {
            "ghsa_id": ghsa_id,
            "cve_id": cve_id,
            "title": item.get("summary") or f"GitHub Advisory {ghsa_id}",
            "summary": item.get("summary"),
            "description": item.get("description"),
            "severity": item.get("severity", "medium").upper(),
            "cvss_v3_score": cvss_score,
            "cvss_v3_vector": cvss_vector,
            "cwe_ids": cwes,
            "published_at": item.get("published_at"),
            "last_modified_at": item.get("updated_at"),
            "source_provenance": {
                "source": "GitHub Advisory Database",
                "ghsa_id": ghsa_id,
                "url": item.get("url"),
                "type": item.get("type", "reviewed"),
            },
        }

    async def get_advisories(
        self,
        cve_id: Optional[str] = None,
        ecosystem: Optional[str] = None,
        severity: Optional[str] = None,
        per_page: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query GitHub advisories with filtering parameters."""
        params: Dict[str, Any] = {"per_page": min(per_page, 100)}
        if cve_id:
            params["cve_id"] = cve_id
        if ecosystem:
            params["ecosystem"] = ecosystem
        if severity:
            params["severity"] = severity

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.BASE_URL, headers=self._get_headers(), params=params)
                # Track rate limits
                if "X-RateLimit-Remaining" in resp.headers:
                    self.rate_limit_remaining = int(resp.headers["X-RateLimit-Remaining"])
                if "X-RateLimit-Reset" in resp.headers:
                    self.rate_limit_reset = int(resp.headers["X-RateLimit-Reset"])

                if resp.status_code == 200:
                    data = resp.json()
                    return [self.parse_advisory(item) for item in data]
                elif resp.status_code in (403, 429):
                    logger.warning("GitHub Advisory API rate limit reached (%d). Falling back to fixtures.", resp.status_code)
                else:
                    logger.warning("GitHub Advisory API returned status %d. Falling back to fixtures.", resp.status_code)
        except Exception as e:
            logger.warning("GitHub Advisory network failure (%s). Falling back to fixtures.", e)

        # Fallback to offline fixtures
        fixtures = self.load_offline_fixture()
        if cve_id:
            return [f for f in fixtures if f.get("cve_id") == cve_id]
        return fixtures
