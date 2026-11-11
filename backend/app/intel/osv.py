"""OSV (Open Source Vulnerabilities) API Client.

Conforms to OSV Schema v1.6.0, supporting single vulnerability retrieval,
package querying, batch package lookup (querybatch), and offline seed fixtures.
Conforms to Noosforge Sentinel R3 specifications.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("sentinel.intel.osv")


class OSVClient:
    """OSV REST API v1 Client."""

    BASE_URL = "https://api.osv.dev/v1"

    def __init__(self, fixture_path: Optional[str] = None, timeout: float = 30.0):
        self.timeout = timeout
        if fixture_path:
            self.fixture_path = Path(fixture_path)
        else:
            base_dir = Path(__file__).resolve().parents[3]
            self.fixture_path = base_dir / "fixtures" / "threat_intel" / "osv.json"

    def load_offline_fixture(self) -> List[Dict[str, Any]]:
        """Load OSV sample fixture from disk."""
        if not self.fixture_path.exists():
            logger.warning("OSV offline fixture not found at %s", self.fixture_path)
            return []

        try:
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [self.parse_osv_record(r) for r in data]
            return []
        except Exception as e:
            logger.error("Failed to parse OSV offline fixture: %s", e)
            return []

    def parse_osv_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw OSV v1.6.0 record into normalized format with alias mapping."""
        osv_id = record.get("id", "")
        aliases = record.get("aliases", [])
        canonical_cve = next((a for a in aliases if a.startswith("CVE-")), None)

        cvss_v3_vector = None
        for sev in record.get("severity", []):
            if sev.get("type") in ("CVSS_V3", "CVSS_V31"):
                cvss_v3_vector = sev.get("score")
                break

        ecosystems: List[str] = []
        packages: List[str] = []
        for aff in record.get("affected", []):
            pkg = aff.get("package", {})
            eco = pkg.get("ecosystem")
            name = pkg.get("name")
            if eco and eco not in ecosystems:
                ecosystems.append(eco)
            if name and name not in packages:
                packages.append(name)

        return {
            "id": osv_id,
            "cve_id": canonical_cve,
            "aliases": aliases,
            "summary": record.get("summary"),
            "details": record.get("details"),
            "cvss_v3_vector": cvss_v3_vector,
            "ecosystems": ecosystems,
            "packages": packages,
            "published_at": record.get("published"),
            "modified_at": record.get("modified"),
            "source_provenance": {
                "source": "OSV v1.6.0",
                "schema_version": record.get("schema_version"),
            },
        }

    async def get_vuln_by_id(self, vuln_id: str) -> Optional[Dict[str, Any]]:
        """Fetch vulnerability record by ID (e.g. GHSA-jfh8-c2jp-5v3q or CVE-2021-44228)."""
        url = f"{self.BASE_URL}/vulns/{vuln_id}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "NoosforgeSentinel/1.0 (+https://github.com/noosforge/sentinel)",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    return self.parse_osv_record(data)
                elif resp.status_code == 404:
                    logger.debug("OSV ID %s not found on api.osv.dev", vuln_id)
                else:
                    logger.warning("OSV returned status %d for %s", resp.status_code, vuln_id)
        except Exception as e:
            logger.warning("OSV network error for %s: %s. Using fixture fallback.", vuln_id, e)

        # Fallback to offline fixtures
        fixtures = self.load_offline_fixture()
        for item in fixtures:
            if item.get("id") == vuln_id or vuln_id in item.get("aliases", []):
                return item
        return None

    async def query_batch(self, queries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Perform batch lookup for multiple packages across ecosystems.

        queries: [{"package": {"name": "org.apache.logging.log4j:log4j-core", "ecosystem": "Maven"}, "version": "2.14.1"}]
        """
        url = f"{self.BASE_URL}/querybatch"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "NoosforgeSentinel/1.0 (+https://github.com/noosforge/sentinel)",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=headers, json={"queries": queries})
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    for res in data.get("results", []):
                        for vuln in res.get("vulns", []):
                            results.append(self.parse_osv_record(vuln))
                    return results
        except Exception as e:
            logger.warning("OSV querybatch network failure: %s. Using fixture fallback.", e)

        return self.load_offline_fixture()
