"""Pydantic V2 schemas for Threat Intelligence, Vulnerability Ingestion & Correlation.

Conforms to Noosforge Sentinel R3 specifications.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class VulnerabilityAliasSchema(BaseModel):
    """Schema for vulnerability alias (GHSA, PYSEC, etc.)."""

    model_config = ConfigDict(from_attributes=True)

    alias_id: str
    cve_id: str
    alias_type: str
    created_at: Optional[datetime] = None


class VulnerabilityIntelligenceBase(BaseModel):
    """Base schema for vulnerability intelligence."""

    cve_id: str = Field(..., pattern=r"^CVE-\d{4}-\d{4,}$", description="Canonical CVE identifier")
    title: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None

    cvss_v3_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    cvss_v3_vector: Optional[str] = None
    cvss_v3_severity: Optional[str] = None
    cvss_v2_score: Optional[float] = Field(None, ge=0.0, le=10.0)
    cvss_v4_score: Optional[float] = Field(None, ge=0.0, le=10.0)

    epss_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    epss_percentile: Optional[float] = Field(None, ge=0.0, le=1.0)
    epss_last_updated: Optional[datetime] = None

    is_cisa_kev: bool = False
    cisa_kev_date_added: Optional[date] = None
    cisa_kev_due_date: Optional[date] = None
    cisa_kev_ransomware: Optional[str] = "Unknown"
    cisa_action_required: Optional[str] = None

    ssvc_exploitation: Optional[str] = None
    ssvc_automatable: Optional[str] = None
    ssvc_technical_impact: Optional[str] = None

    cwe_ids: List[str] = Field(default_factory=list)
    source_provenance: Dict[str, Any] = Field(default_factory=dict)
    published_at: Optional[datetime] = None
    last_modified_at: Optional[datetime] = None


class VulnerabilityIntelligenceCreate(VulnerabilityIntelligenceBase):
    """Schema for inserting a new vulnerability intelligence record."""

    aliases: List[str] = Field(default_factory=list)


class VulnerabilityIntelligenceUpdate(BaseModel):
    """Schema for updating an existing vulnerability intelligence record."""

    title: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    cvss_v3_score: Optional[float] = None
    cvss_v3_vector: Optional[str] = None
    cvss_v3_severity: Optional[str] = None
    epss_score: Optional[float] = None
    epss_percentile: Optional[float] = None
    is_cisa_kev: Optional[bool] = None
    cisa_kev_due_date: Optional[date] = None
    cisa_kev_ransomware: Optional[str] = None
    cisa_action_required: Optional[str] = None
    ssvc_exploitation: Optional[str] = None
    ssvc_automatable: Optional[str] = None
    ssvc_technical_impact: Optional[str] = None
    cwe_ids: Optional[List[str]] = None
    source_provenance: Optional[Dict[str, Any]] = None
    last_modified_at: Optional[datetime] = None


class VulnerabilityIntelligenceResponse(VulnerabilityIntelligenceBase):
    """Full response schema for vulnerability intelligence."""

    model_config = ConfigDict(from_attributes=True)

    synced_at: Optional[datetime] = None
    aliases: List[str] = Field(default_factory=list)


class ThreatIntelSourceStatus(BaseModel):
    """Status telemetry for an individual intelligence source."""

    source_name: str  # nvd, kev, epss, osv, ghsa
    enabled: bool = True
    last_sync_at: Optional[datetime] = None
    records_synced: int = 0
    status: str = "idle"  # idle, syncing, success, failed, offline_fallback
    error_message: Optional[str] = None


class ThreatIntelSummaryResponse(BaseModel):
    """Executive dashboard summary metrics for threat intelligence."""

    total_cves: int = 0
    total_kev_exploited: int = 0
    total_ransomware_exploited: int = 0
    total_high_epss: int = 0  # EPSS > 0.36 (top 1% risk)
    total_critical_cvss: int = 0  # CVSS >= 9.0
    sources: Dict[str, ThreatIntelSourceStatus] = Field(default_factory=dict)
    last_global_sync: Optional[datetime] = None


class ThreatIntelSyncRequest(BaseModel):
    """Request payload to trigger threat intel synchronization."""

    sources: Optional[List[str]] = Field(
        default=None,
        description="List of sources to sync: ['kev', 'epss', 'nvd', 'osv', 'ghsa'] or None for all",
    )
    force_offline_fixtures: bool = False
    cve_subset: Optional[List[str]] = None


class ThreatIntelSyncResultItem(BaseModel):
    """Result per source of a sync job."""

    source: str
    success: bool
    records_ingested: int
    records_updated: int
    used_offline_fixture: bool = False
    duration_ms: float
    error: Optional[str] = None


class ThreatIntelSyncResponse(BaseModel):
    """Response returned upon completion or dispatch of sync job."""

    job_id: str
    status: str  # completed, partial, failed
    timestamp: datetime
    results: List[ThreatIntelSyncResultItem] = Field(default_factory=list)


class EPSSBatchQueryRequest(BaseModel):
    """Request to look up EPSS scores for multiple CVE IDs."""

    cve_ids: List[str] = Field(..., min_length=1, max_length=500)


class EPSSScoreItem(BaseModel):
    """Individual EPSS score response item."""

    cve: str
    epss: float
    percentile: float
    date: Optional[str] = None


class EPSSBatchQueryResponse(BaseModel):
    """Batch response for EPSS lookups."""

    count: int
    scores: Dict[str, EPSSScoreItem]
