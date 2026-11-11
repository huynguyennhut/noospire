r"""FIRST EPSS (Exploit Prediction Scoring System) Probability Client.

Provides single and batch query capabilities for 30-day exploitation probability ($EPSS \in [0.0, 1.0]$)
and percentile ranks, with bulk CSV ingestion and offline sample fixture support.
Conforms to Noosforge Sentinel R3 specifications.
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger("sentinel.intel.epss")


class EPSSClient:
    """FIRST EPSS API & CSV Data Ingestion Client."""

    BASE_URL = "https://api.first.org/data/v1/epss"

    def __init__(self, fixture_path: Optional[str] = None, timeout: float = 30.0):
        self.timeout = timeout
        if fixture_path:
            self.fixture_path = Path(fixture_path)
        else:
            base_dir = Path(__file__).resolve().parents[3]
            self.fixture_path = base_dir / "fixtures" / "threat_intel" / "epss.csv"

    def load_offline_fixture(self) -> Dict[str, Dict[str, Any]]:
        """Load EPSS scores from local offline CSV fixture."""
        if not self.fixture_path.exists():
            logger.warning("EPSS offline fixture not found at %s", self.fixture_path)
            return {}

        try:
            with open(self.fixture_path, "r", encoding="utf-8") as f:
                content = f.read()
            return self.parse_csv_content(content)
        except Exception as e:
            logger.error("Failed to parse EPSS offline fixture: %s", e)
            return {}

    def parse_csv_content(self, csv_text: str) -> Dict[str, Dict[str, Any]]:
        """Parse raw EPSS CSV text into a dictionary keyed by CVE ID."""
        scores: Dict[str, Dict[str, Any]] = {}
        reader = csv.reader(io.StringIO(csv_text))

        for row in reader:
            if not row or not row[0] or row[0].startswith("#"):
                continue
            if row[0].strip().lower() == "cve":
                continue  # Header line

            cve = row[0].strip()
            try:
                epss_val = float(row[1].strip()) if len(row) > 1 else 0.0001
                percentile_val = float(row[2].strip()) if len(row) > 2 else 0.0
                scores[cve] = {
                    "cve_id": cve,
                    "epss_score": epss_val,
                    "epss_percentile": percentile_val,
                    "epss_last_updated": datetime.now(timezone.utc),
                    "source_provenance": {"source": "FIRST EPSS CSV"},
                }
            except (ValueError, IndexError):
                continue

        return scores

    async def get_scores_batch(self, cve_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch EPSS scores for a list of CVE IDs using batch API calls (up to 100 per chunk).

        Falls back to local offline CSV fixture for missing items or network failures.
        """
        results: Dict[str, Dict[str, Any]] = {}
        if not cve_ids:
            return results

        # Deduplicate IDs
        unique_ids = list(dict.fromkeys(cve_ids))
        chunk_size = 100
        unresolved: List[str] = []

        headers = {
            "Accept": "application/json",
            "User-Agent": "NoosforgeSentinel/1.0 (+https://github.com/noosforge/sentinel)",
        }

        for i in range(0, len(unique_ids), chunk_size):
            chunk = unique_ids[i : i + chunk_size]
            cve_param = ",".join(chunk)
            params = {"cve": cve_param}

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(self.BASE_URL, headers=headers, params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in data.get("data", []):
                            cve = item.get("cve")
                            if cve:
                                epss_val = float(item.get("epss", 0.0001))
                                percentile_val = float(item.get("percentile", 0.0))
                                results[cve] = {
                                    "cve_id": cve,
                                    "epss_score": epss_val,
                                    "epss_percentile": percentile_val,
                                    "epss_last_updated": datetime.now(timezone.utc),
                                    "source_provenance": {
                                        "source": "FIRST EPSS API",
                                        "date": item.get("date"),
                                    },
                                }
                    else:
                        logger.warning("EPSS batch query returned status %d. Chunk marked unresolved.", resp.status_code)
                        unresolved.extend(chunk)
            except Exception as e:
                logger.warning("EPSS batch query network exception: %s. Using fixture fallback.", e)
                unresolved.extend(chunk)

        # Check for any requested IDs not returned by API or failed network calls
        for cve in unique_ids:
            if cve not in results:
                unresolved.append(cve)

        if unresolved:
            offline_scores = self.load_offline_fixture()
            for cve in unresolved:
                if cve in offline_scores:
                    results[cve] = offline_scores[cve]
                elif cve not in results:
                    # Conservative floor for unindexed CVEs
                    results[cve] = {
                        "cve_id": cve,
                        "epss_score": 0.0001,
                        "epss_percentile": 0.0,
                        "epss_last_updated": datetime.now(timezone.utc),
                        "source_provenance": {"source": "Sentinel Floor Default"},
                    }

        return results

    async def get_score(self, cve_id: str) -> Dict[str, Any]:
        """Fetch EPSS score for a single CVE ID."""
        scores = await self.get_scores_batch([cve_id])
        return scores.get(cve_id, {
            "cve_id": cve_id,
            "epss_score": 0.0001,
            "epss_percentile": 0.0,
            "epss_last_updated": datetime.now(timezone.utc),
            "source_provenance": {"source": "Sentinel Floor Default"},
        })
