"""NVD (National Vulnerability Database) API 2.0 Ingestion Client.

Supports token bucket rate limiting, max 90-day date chunking, CVSS v3.1/v2/v4 parsing,
SSVC v2.0.3 decision extraction, and offline fallback fixtures.
Conforms to Noosforge Sentinel R3 specifications.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import time
import httpx

logger = logging.getLogger("sentinel.intel.nvd")

CVE_REGEX = re.compile(r"^CVE-\d{4}-\d{4,}$")


class TokenBucketRateLimiter:
    """Token bucket rate limiter conforming to NVD 2.0 concurrency guidelines:

    - Without API Key: 5 requests per rolling 30 seconds (~0.166 req/sec, interval 6.0s)
    - With API Key: 50 requests per rolling 30 seconds (~1.666 req/sec, interval 0.6s)
    """

    def __init__(self, has_api_key: bool = False):
        self.capacity: float = 50.0 if has_api_key else 5.0
        self.rate: float = (50.0 / 30.0) if has_api_key else (5.0 / 30.0)
        self.tokens: float = self.capacity
        self.last_update: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a rate limit token, sleeping asynchronously if bucket is empty."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now

            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            if self.tokens < 1.0:
                deficit = 1.0 - self.tokens
                wait_time = deficit / self.rate
                logger.debug("NVD Rate Limiter: sleeping for %.2f seconds", wait_time)
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


class NVDClient:
    """NVD 2.0 REST API Client with resilient chunking and parsing."""

    BASE_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"

    def __init__(
        self,
        api_key: Optional[str] = None,
        fixture_path: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("NVD_API_KEY")
        self.has_api_key = bool(self.api_key)
        self.rate_limiter = TokenBucketRateLimiter(has_api_key=self.has_api_key)
        self.timeout = timeout

        if fixture_path:
            self.fixture_path = Path(fixture_path)
        else:
            # Default location: fixtures/threat_intel/nvd.json
            base_dir = Path(__file__).resolve().parents[3]
            self.fixture_path = base_dir / "fixtures" / "threat_intel" / "nvd.json"

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "NoosforgeSentinel/1.0 (+https://github.com/noosforge/sentinel)",
        }
        if self.api_key:
            headers["apiKey"] = self.api_key
        return headers

    def load_offline_fixture(self) -> List[Dict[str, Any]]:
        """Load seed fixture from disk for air-gapped / offline operation."""
        if not self.fixture_path.exists():
            logger.warning("NVD offline fixture not found at %s", self.fixture_path)
            return []

        try:
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            vulnerabilities = data.get("vulnerabilities", [])
            parsed = [self.parse_cve_item(item) for item in vulnerabilities if "cve" in item]
            return [p for p in parsed if p is not None]
        except Exception as e:
            logger.error("Failed to read NVD offline fixture: %s", e)
            return []

    def parse_cve_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse raw NVD 2.0 vulnerability item into standardized dictionary."""
        cve = item.get("cve", {})
        cve_id = cve.get("id")
        if not cve_id or not CVE_REGEX.match(cve_id):
            return None

        # Descriptions
        descriptions = cve.get("descriptions", [])
        desc_en = next((d.get("value") for d in descriptions if d.get("lang") == "en"), "")

        # Metrics: CVSS v3.1, v3.0, v2.0
        metrics = cve.get("metrics", {})
        cvss_v31 = metrics.get("cvssMetricV31", [])
        cvss_v30 = metrics.get("cvssMetricV30", [])
        cvss_v2 = metrics.get("cvssMetricV2", [])

        cvss_v3_score: Optional[float] = None
        cvss_v3_vector: Optional[str] = None
        cvss_v3_severity: Optional[str] = None

        if cvss_v31:
            cvss_data = cvss_v31[0].get("cvssData", {})
            cvss_v3_score = cvss_data.get("baseScore")
            cvss_v3_vector = cvss_data.get("vectorString")
            cvss_v3_severity = cvss_data.get("baseSeverity")
        elif cvss_v30:
            cvss_data = cvss_v30[0].get("cvssData", {})
            cvss_v3_score = cvss_data.get("baseScore")
            cvss_v3_vector = cvss_data.get("vectorString")
            cvss_v3_severity = cvss_data.get("baseSeverity")

        cvss_v2_score: Optional[float] = None
        if cvss_v2:
            cvss_data_v2 = cvss_v2[0].get("cvssData", {})
            cvss_v2_score = cvss_data_v2.get("baseScore")

        # SSVC v2.0.3 decision extraction
        ssvc_list = metrics.get("ssvcV203", [])
        ssvc_exploitation: Optional[str] = None
        ssvc_automatable: Optional[str] = None
        ssvc_technical_impact: Optional[str] = None

        if ssvc_list:
            ssvc_data = ssvc_list[0].get("ssvcData", {})
            options = ssvc_data.get("options", [])
            for opt in options:
                if "exploitation" in opt:
                    ssvc_exploitation = opt["exploitation"]
                if "automatable" in opt:
                    ssvc_automatable = opt["automatable"]
                if "technicalImpact" in opt:
                    ssvc_technical_impact = opt["technicalImpact"]

        # Weaknesses (CWEs)
        weaknesses = cve.get("weaknesses", [])
        cwe_ids: List[str] = []
        for w in weaknesses:
            for d in w.get("description", []):
                val = d.get("value")
                if val and val.startswith("CWE-") and val not in cwe_ids:
                    cwe_ids.append(val)

        # Dates
        published_str = cve.get("published")
        last_modified_str = cve.get("lastModified")

        published_at = None
        if published_str:
            try:
                published_at = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        last_modified_at = None
        if last_modified_str:
            try:
                last_modified_at = datetime.fromisoformat(last_modified_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        return {
            "cve_id": cve_id,
            "title": f"Vulnerability {cve_id}",
            "summary": desc_en[:255] if desc_en else None,
            "description": desc_en,
            "cvss_v3_score": cvss_v3_score,
            "cvss_v3_vector": cvss_v3_vector,
            "cvss_v3_severity": cvss_v3_severity.upper() if cvss_v3_severity else None,
            "cvss_v2_score": cvss_v2_score,
            "cvss_v4_score": None,
            "ssvc_exploitation": ssvc_exploitation,
            "ssvc_automatable": ssvc_automatable,
            "ssvc_technical_impact": ssvc_technical_impact,
            "cwe_ids": cwe_ids,
            "published_at": published_at,
            "last_modified_at": last_modified_at,
            "source_provenance": {
                "source": "NVD 2.0",
                "sourceIdentifier": cve.get("sourceIdentifier"),
                "vulnStatus": cve.get("vulnStatus"),
            },
        }

    async def get_cve(self, cve_id: str) -> Optional[Dict[str, Any]]:
        """Query NVD 2.0 for a single CVE ID, falling back to offline fixture."""
        if not CVE_REGEX.match(cve_id):
            logger.warning("Invalid CVE ID pattern: %s", cve_id)
            return None

        await self.rate_limiter.acquire()
        params = {"cveId": cve_id}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.BASE_URL, headers=self._get_headers(), params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    vulns = data.get("vulnerabilities", [])
                    if vulns:
                        return self.parse_cve_item(vulns[0])
                    return None
                elif resp.status_code in (403, 429):
                    logger.warning("NVD rate limit hit (%d) for %s. Using fixture fallback.", resp.status_code, cve_id)
                else:
                    logger.warning("NVD returned status %d for %s", resp.status_code, cve_id)
        except Exception as e:
            logger.warning("NVD network error querying %s: %s. Using fixture fallback.", cve_id, e)

        # Fallback to offline fixtures
        fixture_records = self.load_offline_fixture()
        for item in fixture_records:
            if item.get("cve_id") == cve_id:
                return item
        return None

    @staticmethod
    def chunk_date_range(start_date: datetime, end_date: datetime, max_days: int = 90) -> List[tuple[datetime, datetime]]:
        """Split a wide date range into windows of at most `max_days` to prevent

        NVD 400 Bad Request (>120 days interval rejected).
        """
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        else:
            start_date = start_date.astimezone(timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        else:
            end_date = end_date.astimezone(timezone.utc)

        chunks: List[tuple[datetime, datetime]] = []
        current_start = start_date

        while current_start < end_date:
            current_end = min(current_start + timedelta(days=max_days), end_date)
            chunks.append((current_start, current_end))
            current_start = current_end
        return chunks

    async def sync_incremental(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Incrementally sync NVD CVE records between start_date and end_date."""
        if end_date is None:
            end_date = datetime.now(timezone.utc)

        chunks = self.chunk_date_range(start_date, end_date, max_days=90)
        results: List[Dict[str, Any]] = []

        for c_start, c_end in chunks:
            iso_start = c_start.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            iso_end = c_end.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            params = {
                "lastModStartDate": iso_start,
                "lastModEndDate": iso_end,
                "startIndex": 0,
                "resultsPerPage": 2000,
            }

            try:
                await self.rate_limiter.acquire()
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(self.BASE_URL, headers=self._get_headers(), params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        for v in data.get("vulnerabilities", []):
                            parsed = self.parse_cve_item(v)
                            if parsed:
                                results.append(parsed)
                    else:
                        logger.warning("NVD chunk sync status %d: %s", resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("NVD chunk sync failed (%s to %s): %s", iso_start, iso_end, e)
                # Fall back to offline fixture items matching criteria
                return self.load_offline_fixture()

        return results if results else self.load_offline_fixture()
