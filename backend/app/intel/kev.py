"""CISA Known Exploited Vulnerabilities (KEV) Catalog Synchronization Client.

Parses bulk JSON feed, extracts ransomware campaign use indicators and federal remediation due dates,
and provides offline fallback seed fixtures for air-gapped environments.
Conforms to Noosforge Sentinel R3 specifications.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("sentinel.intel.kev")


class KEVClient:
    """CISA KEV Catalog Feed Client."""

    FEED_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"

    def __init__(self, fixture_path: Optional[str] = None, timeout: float = 30.0):
        self.timeout = timeout
        if fixture_path:
            self.fixture_path = Path(fixture_path)
        else:
            base_dir = Path(__file__).resolve().parents[3]
            self.fixture_path = base_dir / "fixtures" / "threat_intel" / "kev.json"

    def load_offline_fixture(self) -> List[Dict[str, Any]]:
        """Load CISA KEV seed fixture from disk."""
        if not self.fixture_path.exists():
            logger.warning("CISA KEV offline fixture not found at %s", self.fixture_path)
            return []

        try:
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self.parse_catalog_payload(data)
        except Exception as e:
            logger.error("Failed to parse CISA KEV offline fixture: %s", e)
            return []

    def parse_catalog_payload(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse raw CISA catalog JSON payload into normalized threat intelligence items."""
        vulns = data.get("vulnerabilities", [])
        catalog_version = data.get("catalogVersion")
        date_released = data.get("dateReleased")

        parsed_items: List[Dict[str, Any]] = []

        for item in vulns:
            cve_id = item.get("cveID")
            if not cve_id:
                continue

            date_added_str = item.get("dateAdded")
            due_date_str = item.get("dueDate")

            date_added = None
            if date_added_str:
                try:
                    date_added = date.fromisoformat(date_added_str)
                except ValueError:
                    pass

            due_date = None
            if due_date_str:
                try:
                    due_date = date.fromisoformat(due_date_str)
                except ValueError:
                    pass

            ransomware = item.get("knownRansomwareCampaignUse", "Unknown")
            cwes = item.get("cwes", [])
            if isinstance(cwes, str):
                cwes = [c.strip() for c in cwes.split(",") if c.strip()]

            parsed_items.append({
                "cve_id": cve_id,
                "title": item.get("vulnerabilityName") or f"{item.get('vendorProject', '')} {item.get('product', '')} Vulnerability",
                "summary": item.get("shortDescription"),
                "description": item.get("shortDescription"),
                "is_cisa_kev": True,
                "cisa_kev_date_added": date_added,
                "cisa_kev_due_date": due_date,
                "cisa_kev_ransomware": ransomware,
                "cisa_action_required": item.get("requiredAction"),
                "cwe_ids": cwes,
                "source_provenance": {
                    "source": "CISA KEV Catalog",
                    "vendorProject": item.get("vendorProject"),
                    "product": item.get("product"),
                    "notes": item.get("notes"),
                    "catalogVersion": catalog_version,
                    "dateReleased": date_released,
                },
            })

        return parsed_items

    async def fetch_catalog(self, etag: Optional[str] = None) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """Fetch the latest CISA KEV catalog via HTTPS, supporting ETag conditional requests.

        Falls back to offline fixture upon network failure or DNS resolution error.
        Returns (catalog_items, new_etag).
        """
        headers = {
            "Accept": "application/json",
            "User-Agent": "NoosforgeSentinel/1.0 (+https://github.com/noosforge/sentinel)",
        }
        if etag:
            headers["If-None-Match"] = etag

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.FEED_URL, headers=headers)
                if resp.status_code == 304:
                    logger.info("CISA KEV Catalog not modified (304 Not Modified).")
                    return [], etag
                elif resp.status_code == 200:
                    new_etag = resp.headers.get("ETag")
                    data = resp.json()
                    items = self.parse_catalog_payload(data)
                    logger.info("Successfully fetched %d items from CISA KEV live catalog.", len(items))
                    return items, new_etag
                else:
                    logger.warning("CISA KEV returned unexpected status code %d. Falling back to offline fixture.", resp.status_code)
        except Exception as e:
            logger.warning("Failed to fetch CISA KEV catalog online (%s). Falling back to offline fixture.", e)

        # Fallback to offline fixtures
        items = self.load_offline_fixture()
        logger.info("Loaded %d items from offline CISA KEV fixture.", len(items))
        return items, None
