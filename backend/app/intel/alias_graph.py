"""Vulnerability Alias Graph Engine.

Maintains bidirectional correlation mapping between ecosystem-specific vulnerability identifiers
(e.g. GHSA-..., PYSEC-..., RUSTSEC-...) and canonical CVE IDs (e.g. CVE-2021-44228).
Conforms to Noosforge Sentinel R3 specifications.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.intelligence import VulnerabilityAlias

logger = logging.getLogger("sentinel.intel.alias_graph")


class VulnerabilityAliasGraph:
    """Bidirectional alias correlation graph with in-memory caching and database persistence."""

    def __init__(self) -> None:
        # alias_id -> cve_id
        self._alias_to_cve: Dict[str, str] = {}
        # cve_id -> set of alias_ids
        self._cve_to_aliases: Dict[str, Set[str]] = {}

    def register_alias(self, alias_id: str, cve_id: str, alias_type: Optional[str] = None) -> None:
        """Register a bidirectional alias mapping in the in-memory graph."""
        if not alias_id or not cve_id:
            return

        clean_alias = alias_id.strip()
        clean_cve = cve_id.strip()

        self._alias_to_cve[clean_alias] = clean_cve

        if clean_cve not in self._cve_to_aliases:
            self._cve_to_aliases[clean_cve] = set()
        self._cve_to_aliases[clean_cve].add(clean_alias)

    def resolve_to_cve(self, identifier: str) -> Optional[str]:
        """Resolve any vulnerability identifier (GHSA, PYSEC, or canonical CVE) to canonical CVE ID.

        If the identifier is already a CVE ID, returns it directly.
        If it maps to an alias in the graph, returns the mapped CVE ID.
        Otherwise returns None.
        """
        if not identifier:
            return None

        clean_id = identifier.strip()
        if clean_id.upper().startswith("CVE-"):
            return clean_id.upper()

        return self._alias_to_cve.get(clean_id)

    def get_aliases_for_cve(self, cve_id: str) -> List[str]:
        """Return all known alias IDs mapped to the specified canonical CVE ID."""
        clean_cve = cve_id.strip().upper()
        return sorted(list(self._cve_to_aliases.get(clean_cve, set())))

    async def sync_with_db(self, session: AsyncSession) -> int:
        """Load all alias records from PostgreSQL / SQLite database into the in-memory graph."""
        stmt = select(VulnerabilityAlias)
        result = await session.execute(stmt)
        records = result.scalars().all()

        loaded_count = 0
        for r in records:
            self.register_alias(r.alias_id, r.cve_id, r.alias_type)
            loaded_count += 1

        logger.info("Loaded %d vulnerability alias pairs into memory graph from database.", loaded_count)
        return loaded_count

    async def persist_alias(
        self,
        session: AsyncSession,
        alias_id: str,
        cve_id: str,
        alias_type: str = "GHSA",
    ) -> bool:
        """Persist an alias pair to both database and in-memory graph idempotently."""
        clean_alias = alias_id.strip()
        clean_cve = cve_id.strip().upper()

        self.register_alias(clean_alias, clean_cve, alias_type)

        # Check existing record
        stmt = select(VulnerabilityAlias).where(VulnerabilityAlias.alias_id == clean_alias)
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing:
            if existing.cve_id != clean_cve:
                existing.cve_id = clean_cve
                existing.alias_type = alias_type
                await session.flush()
                return True
            return False

        new_alias = VulnerabilityAlias(
            alias_id=clean_alias,
            cve_id=clean_cve,
            alias_type=alias_type,
        )
        session.add(new_alias)
        await session.flush()
        return True

    def populate_from_records(self, records: List[Dict]) -> int:
        """Populate alias graph from a list of records containing 'aliases' and 'cve_id' or 'id'."""
        added = 0
        for r in records:
            cve_id = r.get("cve_id")
            rec_id = r.get("id") or r.get("ghsa_id")
            aliases = r.get("aliases", [])

            if cve_id and rec_id and rec_id != cve_id:
                alias_type = "GHSA" if rec_id.startswith("GHSA-") else ("PYSEC" if rec_id.startswith("PYSEC-") else "VENDOR")
                self.register_alias(rec_id, cve_id, alias_type)
                added += 1

            # If rec_id is an alias and aliases contains CVE
            for a in aliases:
                if a.startswith("CVE-") and rec_id and rec_id != a:
                    alias_type = "GHSA" if rec_id.startswith("GHSA-") else ("PYSEC" if rec_id.startswith("PYSEC-") else "VENDOR")
                    self.register_alias(rec_id, a, alias_type)
                    added += 1
                elif cve_id and not a.startswith("CVE-"):
                    alias_type = "GHSA" if a.startswith("GHSA-") else ("PYSEC" if a.startswith("PYSEC-") else "VENDOR")
                    self.register_alias(a, cve_id, alias_type)
                    added += 1

        return added
