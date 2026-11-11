"""Threat Intelligence Synchronization Manager.

Orchestrates multi-source ingestion (NVD 2.0, CISA KEV, FIRST EPSS, OSV, GHSA),
alias graph resolution, non-destructive database upserts, and offline seed fallbacks.
Conforms to Noosforge Sentinel R3 specifications.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.intel.alias_graph import VulnerabilityAliasGraph
from backend.app.intel.epss import EPSSClient
from backend.app.intel.ghsa import GHSAClient
from backend.app.intel.kev import KEVClient
from backend.app.intel.nvd import NVDClient
from backend.app.intel.osv import OSVClient
from backend.app.models.intelligence import VulnerabilityAlias, VulnerabilityIntelligence
from backend.app.schemas.intelligence import (
    ThreatIntelSourceStatus,
    ThreatIntelSummaryResponse,
    ThreatIntelSyncResultItem,
)

logger = logging.getLogger("sentinel.intel.sync_manager")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)



def _require_fixture_mode() -> None:
    """Synthetic offline fixtures may only be loaded on explicit request outside production."""
    from backend.app.core.config import settings
    if settings.is_production:
        raise PermissionError("offline threat-intel fixtures are disabled in production")

class ThreatIntelSyncManager:
    """Coordinator managing threat intel feeds, non-destructive upserts, and correlation."""

    def __init__(
        self,
        nvd_client: Optional[NVDClient] = None,
        kev_client: Optional[KEVClient] = None,
        epss_client: Optional[EPSSClient] = None,
        osv_client: Optional[OSVClient] = None,
        ghsa_client: Optional[GHSAClient] = None,
        alias_graph: Optional[VulnerabilityAliasGraph] = None,
    ):
        self.nvd = nvd_client or NVDClient()
        self.kev = kev_client or KEVClient()
        self.epss = epss_client or EPSSClient()
        self.osv = osv_client or OSVClient()
        self.ghsa = ghsa_client or GHSAClient()
        self.alias_graph = alias_graph or VulnerabilityAliasGraph()

        self._source_telemetry: Dict[str, ThreatIntelSourceStatus] = {
            "kev": ThreatIntelSourceStatus(source_name="CISA KEV Catalog"),
            "epss": ThreatIntelSourceStatus(source_name="FIRST EPSS"),
            "nvd": ThreatIntelSourceStatus(source_name="NVD 2.0"),
            "osv": ThreatIntelSourceStatus(source_name="OSV v1.6.0"),
            "ghsa": ThreatIntelSourceStatus(source_name="GitHub Advisory Database"),
        }
        self._last_global_sync: Optional[datetime] = None

    async def upsert_vulnerability(
        self,
        session: AsyncSession,
        data: Dict[str, Any],
    ) -> tuple[VulnerabilityIntelligence, bool]:
        """Perform a non-destructive upsert of a vulnerability record.

        Existing fields are preserved unless the new data explicitly provides a non-None update.
        Ingestion failures never delete or overwrite populated data with None.
        Returns (record, is_created).
        """
        cve_id = data.get("cve_id")
        if not cve_id:
            raise ValueError("Vulnerability record missing cve_id")

        stmt = select(VulnerabilityIntelligence).where(VulnerabilityIntelligence.cve_id == cve_id)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        is_created = False
        if record is None:
            record = VulnerabilityIntelligence(cve_id=cve_id)
            session.add(record)
            is_created = True

        # Non-destructive field merges
        for field in (
            "title",
            "summary",
            "description",
            "cvss_v3_score",
            "cvss_v3_vector",
            "cvss_v3_severity",
            "cvss_v2_score",
            "cvss_v4_score",
            "epss_score",
            "epss_percentile",
            "epss_last_updated",
            "cisa_kev_date_added",
            "cisa_kev_due_date",
            "cisa_action_required",
            "ssvc_exploitation",
            "ssvc_automatable",
            "ssvc_technical_impact",
            "published_at",
            "last_modified_at",
        ):
            new_val = data.get(field)
            if new_val is not None:
                setattr(record, field, new_val)

        # Boolean and string flags with defaults
        if data.get("is_cisa_kev") is True:
            record.is_cisa_kev = True
        if data.get("cisa_kev_ransomware") and data["cisa_kev_ransomware"] != "Unknown":
            record.cisa_kev_ransomware = data["cisa_kev_ransomware"]

        # Merge CWE lists idempotently
        new_cwes = data.get("cwe_ids")
        if new_cwes:
            existing_cwes = list(record.cwe_ids or [])
            for cwe in new_cwes:
                if cwe not in existing_cwes:
                    existing_cwes.append(cwe)
            record.cwe_ids = existing_cwes

        # Merge source provenance
        new_prov = data.get("source_provenance")
        if new_prov:
            existing_prov = dict(record.source_provenance or {})
            existing_prov.update(new_prov)
            record.source_provenance = existing_prov

        record.synced_at = utc_now()
        await session.flush()
        return record, is_created

    async def sync_cisa_kev(
        self,
        session: AsyncSession,
        force_offline: bool = False,
    ) -> ThreatIntelSyncResultItem:
        """Synchronize CISA KEV catalog."""
        start_time = time.perf_counter()
        source_key = "kev"
        self._source_telemetry[source_key].status = "syncing"

        try:
            if force_offline:
                _require_fixture_mode()
                items = self.kev.load_offline_fixture()
                used_offline = True
            else:
                items, _ = await self.kev.fetch_catalog()
                used_offline = False
                if not items:
                    raise RuntimeError("CISA KEV live feed returned no data; offline fixture NOT loaded")

            created_count = 0
            updated_count = 0
            for item in items:
                _, created = await self.upsert_vulnerability(session, item)
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "success"
            self._source_telemetry[source_key].last_sync_at = utc_now()
            self._source_telemetry[source_key].records_synced = len(items)

            return ThreatIntelSyncResultItem(
                source="CISA KEV Catalog",
                success=True,
                records_ingested=created_count,
                records_updated=updated_count,
                used_offline_fixture=used_offline,
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            logger.error("CISA KEV sync failed: %s", e)
            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "failed"
            self._source_telemetry[source_key].error_message = str(e)
            return ThreatIntelSyncResultItem(
                source="CISA KEV Catalog",
                success=False,
                records_ingested=0,
                records_updated=0,
                used_offline_fixture=force_offline,
                duration_ms=round(duration, 2),
                error=str(e),
            )

    async def sync_epss(
        self,
        session: AsyncSession,
        cve_subset: Optional[List[str]] = None,
        force_offline: bool = False,
    ) -> ThreatIntelSyncResultItem:
        """Synchronize FIRST EPSS scores for known or specified CVE IDs."""
        start_time = time.perf_counter()
        source_key = "epss"
        self._source_telemetry[source_key].status = "syncing"

        try:
            if cve_subset:
                cve_list = cve_subset
            else:
                # Query all CVE IDs currently in database
                stmt = select(VulnerabilityIntelligence.cve_id)
                res = await session.execute(stmt)
                cve_list = list(res.scalars().all())

            if force_offline:
                _require_fixture_mode()
                scores = self.epss.load_offline_fixture()
                used_offline = True
            elif not cve_list:
                scores, used_offline = {}, False  # no CVE in the database yet: nothing to score
            else:
                scores = await self.epss.get_scores_batch(cve_list)
                used_offline = False

            created_count = 0
            updated_count = 0
            for cve, score_data in scores.items():
                _, created = await self.upsert_vulnerability(session, score_data)
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "success"
            self._source_telemetry[source_key].last_sync_at = utc_now()
            self._source_telemetry[source_key].records_synced = len(scores)

            return ThreatIntelSyncResultItem(
                source="FIRST EPSS",
                success=True,
                records_ingested=created_count,
                records_updated=updated_count,
                used_offline_fixture=used_offline,
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            logger.error("EPSS sync failed: %s", e)
            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "failed"
            self._source_telemetry[source_key].error_message = str(e)
            return ThreatIntelSyncResultItem(
                source="FIRST EPSS",
                success=False,
                records_ingested=0,
                records_updated=0,
                used_offline_fixture=force_offline,
                duration_ms=round(duration, 2),
                error=str(e),
            )

    async def sync_nvd(
        self,
        session: AsyncSession,
        force_offline: bool = False,
    ) -> ThreatIntelSyncResultItem:
        """Synchronize NVD 2.0 records."""
        start_time = time.perf_counter()
        source_key = "nvd"
        self._source_telemetry[source_key].status = "syncing"

        try:
            if force_offline:
                _require_fixture_mode()
                items = self.nvd.load_offline_fixture()
                used_offline = True
            else:
                # Sync last 30 days or fallback
                start_date = utc_now() - timedelta(days=30)
                items = await self.nvd.sync_incremental(start_date=start_date)
                used_offline = False
                if not items:
                    raise RuntimeError("NVD live feed returned no data; offline fixture NOT loaded")

            created_count = 0
            updated_count = 0
            for item in items:
                _, created = await self.upsert_vulnerability(session, item)
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "success"
            self._source_telemetry[source_key].last_sync_at = utc_now()
            self._source_telemetry[source_key].records_synced = len(items)

            return ThreatIntelSyncResultItem(
                source="NVD 2.0",
                success=True,
                records_ingested=created_count,
                records_updated=updated_count,
                used_offline_fixture=used_offline,
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            logger.error("NVD sync failed: %s", e)
            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "failed"
            self._source_telemetry[source_key].error_message = str(e)
            return ThreatIntelSyncResultItem(
                source="NVD 2.0",
                success=False,
                records_ingested=0,
                records_updated=0,
                used_offline_fixture=force_offline,
                duration_ms=round(duration, 2),
                error=str(e),
            )

    async def sync_osv(
        self,
        session: AsyncSession,
        force_offline: bool = False,
    ) -> ThreatIntelSyncResultItem:
        """Synchronize OSV vulnerability records and register aliases."""
        start_time = time.perf_counter()
        source_key = "osv"
        self._source_telemetry[source_key].status = "syncing"

        try:
            if not force_offline:
                raise NotImplementedError("live OSV sync is not configured in the pilot; the SBOM engine uses "
                                          "owner-imported advisory snapshots instead")
            _require_fixture_mode()
            records = self.osv.load_offline_fixture()
            created_count = 0
            updated_count = 0

            for rec in records:
                cve_id = rec.get("cve_id")
                if cve_id:
                    vuln_data = {
                        "cve_id": cve_id,
                        "title": rec.get("summary") or f"OSV {rec.get('id')}",
                        "summary": rec.get("summary"),
                        "description": rec.get("details"),
                        "cvss_v3_vector": rec.get("cvss_v3_vector"),
                        "source_provenance": rec.get("source_provenance", {}),
                    }
                    _, created = await self.upsert_vulnerability(session, vuln_data)
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                    # Register aliases
                    if rec.get("id"):
                        await self.alias_graph.persist_alias(
                            session,
                            alias_id=rec["id"],
                            cve_id=cve_id,
                            alias_type="OSV",
                        )
                    for a in rec.get("aliases", []):
                        if not a.startswith("CVE-"):
                            await self.alias_graph.persist_alias(
                                session,
                                alias_id=a,
                                cve_id=cve_id,
                                alias_type="ALIAS",
                            )

            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "success"
            self._source_telemetry[source_key].last_sync_at = utc_now()
            self._source_telemetry[source_key].records_synced = len(records)

            return ThreatIntelSyncResultItem(
                source="OSV v1.6.0",
                success=True,
                records_ingested=created_count,
                records_updated=updated_count,
                used_offline_fixture=True,
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            logger.error("OSV sync failed: %s", e)
            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "failed"
            self._source_telemetry[source_key].error_message = str(e)
            return ThreatIntelSyncResultItem(
                source="OSV v1.6.0",
                success=False,
                records_ingested=0,
                records_updated=0,
                used_offline_fixture=force_offline,
                duration_ms=round(duration, 2),
                error=str(e),
            )

    async def sync_ghsa(
        self,
        session: AsyncSession,
        force_offline: bool = False,
    ) -> ThreatIntelSyncResultItem:
        """Synchronize GitHub Advisory Database records and register GHSA aliases."""
        start_time = time.perf_counter()
        source_key = "ghsa"
        self._source_telemetry[source_key].status = "syncing"

        try:
            if not force_offline:
                raise NotImplementedError("live GHSA sync is not configured in the pilot")
            _require_fixture_mode()
            records = self.ghsa.load_offline_fixture()
            created_count = 0
            updated_count = 0

            for rec in records:
                cve_id = rec.get("cve_id")
                if cve_id:
                    vuln_data = {
                        "cve_id": cve_id,
                        "title": rec.get("title"),
                        "summary": rec.get("summary"),
                        "description": rec.get("description"),
                        "cvss_v3_score": rec.get("cvss_v3_score"),
                        "cvss_v3_vector": rec.get("cvss_v3_vector"),
                        "cvss_v3_severity": rec.get("severity"),
                        "cwe_ids": rec.get("cwe_ids", []),
                        "source_provenance": rec.get("source_provenance", {}),
                    }
                    _, created = await self.upsert_vulnerability(session, vuln_data)
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

                    # Register GHSA alias
                    ghsa_id = rec.get("ghsa_id")
                    if ghsa_id:
                        await self.alias_graph.persist_alias(
                            session,
                            alias_id=ghsa_id,
                            cve_id=cve_id,
                            alias_type="GHSA",
                        )

            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "success"
            self._source_telemetry[source_key].last_sync_at = utc_now()
            self._source_telemetry[source_key].records_synced = len(records)

            return ThreatIntelSyncResultItem(
                source="GitHub Advisory Database",
                success=True,
                records_ingested=created_count,
                records_updated=updated_count,
                used_offline_fixture=True,
                duration_ms=round(duration, 2),
            )
        except Exception as e:
            logger.error("GHSA sync failed: %s", e)
            duration = (time.perf_counter() - start_time) * 1000
            self._source_telemetry[source_key].status = "failed"
            self._source_telemetry[source_key].error_message = str(e)
            return ThreatIntelSyncResultItem(
                source="GitHub Advisory Database",
                success=False,
                records_ingested=0,
                records_updated=0,
                used_offline_fixture=force_offline,
                duration_ms=round(duration, 2),
                error=str(e),
            )

    async def seed_from_offline_fixtures(self, session: AsyncSession) -> List[ThreatIntelSyncResultItem]:
        """Seed threat intelligence store with bundled offline sample fixtures."""
        logger.info("Executing offline fixture seeding across all intelligence sources...")
        results: List[ThreatIntelSyncResultItem] = []

        res_kev = await self.sync_cisa_kev(session, force_offline=True)
        results.append(res_kev)

        res_nvd = await self.sync_nvd(session, force_offline=True)
        results.append(res_nvd)

        res_epss = await self.sync_epss(session, force_offline=True)
        results.append(res_epss)

        res_osv = await self.sync_osv(session, force_offline=True)
        results.append(res_osv)

        res_ghsa = await self.sync_ghsa(session, force_offline=True)
        results.append(res_ghsa)

        await session.commit()
        await self.alias_graph.sync_with_db(session)
        self._last_global_sync = utc_now()
        return results

    async def sync_all(
        self,
        session: AsyncSession,
        sources: Optional[List[str]] = None,
        force_offline: bool = False,
    ) -> List[ThreatIntelSyncResultItem]:
        """Synchronize threat intelligence across specified sources or all 5 sources."""
        active_sources = sources or ["kev", "nvd", "epss", "osv", "ghsa"]
        results: List[ThreatIntelSyncResultItem] = []

        if "kev" in active_sources:
            results.append(await self.sync_cisa_kev(session, force_offline=force_offline))
        if "nvd" in active_sources:
            results.append(await self.sync_nvd(session, force_offline=force_offline))
        if "epss" in active_sources:
            results.append(await self.sync_epss(session, force_offline=force_offline))
        if "osv" in active_sources:
            results.append(await self.sync_osv(session, force_offline=force_offline))
        if "ghsa" in active_sources:
            results.append(await self.sync_ghsa(session, force_offline=force_offline))

        await session.commit()
        await self.alias_graph.sync_with_db(session)
        self._last_global_sync = utc_now()
        return results

    async def get_summary(self, session: AsyncSession) -> ThreatIntelSummaryResponse:
        """Calculate aggregate metrics for the threat intelligence summary view."""
        # Total CVEs
        stmt_total = select(func.count(VulnerabilityIntelligence.cve_id))
        total_cves = (await session.execute(stmt_total)).scalar() or 0

        # Total KEV exploited
        stmt_kev = select(func.count(VulnerabilityIntelligence.cve_id)).where(
            VulnerabilityIntelligence.is_cisa_kev.is_(True)
        )
        total_kev = (await session.execute(stmt_kev)).scalar() or 0

        # Total Ransomware exploited
        stmt_rw = select(func.count(VulnerabilityIntelligence.cve_id)).where(
            VulnerabilityIntelligence.cisa_kev_ransomware == "Known"
        )
        total_rw = (await session.execute(stmt_rw)).scalar() or 0

        # Total High EPSS (> 0.36, top 1% risk)
        stmt_epss = select(func.count(VulnerabilityIntelligence.cve_id)).where(
            VulnerabilityIntelligence.epss_score > 0.36
        )
        total_high_epss = (await session.execute(stmt_epss)).scalar() or 0

        # Total Critical CVSS (>= 9.0)
        stmt_cvss = select(func.count(VulnerabilityIntelligence.cve_id)).where(
            VulnerabilityIntelligence.cvss_v3_score >= 9.0
        )
        total_crit_cvss = (await session.execute(stmt_cvss)).scalar() or 0

        return ThreatIntelSummaryResponse(
            total_cves=total_cves,
            total_kev_exploited=total_kev,
            total_ransomware_exploited=total_rw,
            total_high_epss=total_high_epss,
            total_critical_cvss=total_crit_cvss,
            sources=self._source_telemetry,
            last_global_sync=self._last_global_sync,
        )
