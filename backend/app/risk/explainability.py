"""Transparent Score Explanation Model for Risk Prioritization.

Builds structured component breakdowns and plain-language explainability summaries
demonstrating why a finding received its Sentinel Risk Score (SRS).
Conforms to Noosforge Sentinel R4 specifications.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from backend.app.risk.calculator import RiskCalculationResult


class UpstreamMetricsExplanation(BaseModel):
    cvss_v3_base_score: Optional[float] = None
    cvss_v3_vector: Optional[str] = None
    epss_score: Optional[float] = None
    epss_percentile: Optional[float] = None
    is_cisa_kev: bool = False
    cisa_kev_due_date: Optional[str] = None
    known_ransomware_use: Optional[str] = None


class ContextualFactorsExplanation(BaseModel):
    asset_criticality: str
    asset_criticality_factor: float
    network_exposure: str
    network_exposure_factor: float
    verification_status: str
    verification_factor: float


class RiskScoreBreakdown(BaseModel):
    v_base: float
    b_threat: float
    t_threat: float
    m_context: float
    t_contextual: float
    f_verif: float


class SentinelRiskAssessment(BaseModel):
    sentinel_risk_score: float
    severity: str
    score_breakdown: RiskScoreBreakdown
    upstream_metrics: UpstreamMetricsExplanation
    contextual_factors: ContextualFactorsExplanation
    score_explanation: str


class RiskExplainabilityBuilder:
    """Builds structured and narrative risk explanations from calculation results."""

    @classmethod
    def build_explanation(
        cls,
        calc_result: RiskCalculationResult,
        cvss_vector: Optional[str] = None,
        epss_percentile: Optional[float] = None,
        cisa_kev_due_date: Optional[str] = None,
        cisa_kev_ransomware: Optional[str] = None,
        asset_name: Optional[str] = None,
        asset_criticality_label: Optional[str] = None,
        network_exposure_label: Optional[str] = None,
        verification_status_label: Optional[str] = None,
    ) -> SentinelRiskAssessment:
        """Construct full SentinelRiskAssessment object with plain-language narrative."""
        crit_label = asset_criticality_label or (
            "Mission Critical (Tier 1)" if calc_result.c_asset >= 1.0 else (
                "High (Tier 2)" if calc_result.c_asset >= 0.8 else (
                    "Medium (Tier 3)" if calc_result.c_asset >= 0.6 else "Low (Tier 4)"
                )
            )
        )
        expo_label = network_exposure_label or (
            "Public Internet Facing" if calc_result.e_net >= 1.0 else (
                "DMZ / Partner Boundary" if calc_result.e_net >= 0.75 else (
                    "Internal Private Network" if calc_result.e_net >= 0.50 else "Isolated / Air-gapped"
                )
            )
        )
        verif_label = verification_status_label or (
            "Confirmed PoC" if calc_result.f_verif >= 1.0 else (
                "High Confidence Signature" if calc_result.f_verif >= 0.9 else (
                    "Medium Confidence Banner" if calc_result.f_verif >= 0.7 else "Unconfirmed Candidate"
                )
            )
        )

        # Build narrative explanation paragraph
        narrative_parts = []

        # 1. Severity & Base Threat
        if calc_result.is_cisa_kev:
            if cisa_kev_ransomware and cisa_kev_ransomware.lower() == "known":
                threat_clause = f"is listed in CISA KEV with active ransomware campaign exploitation (threat floor 0.75 applied, EPSS: {calc_result.epss:.1%})"
            else:
                threat_clause = f"is actively weaponized in the wild per CISA KEV catalog (threat floor 0.75 applied, EPSS: {calc_result.epss:.1%})"
        elif calc_result.epss > 0.36:
            threat_clause = f"has high empirical exploit prediction probability (EPSS: {calc_result.epss:.1%}, top 1% risk tier)"
        else:
            threat_clause = f"has moderate real-world exploit urgency (EPSS: {calc_result.epss:.2%})"

        narrative_parts.append(
            f"{calc_result.risk_severity} priority ({calc_result.sentinel_risk_score}/100.0): "
            f"Vulnerability has CVSS base severity of {calc_result.cvss:.1f}/10.0 and {threat_clause}."
        )

        # 2. Environmental Context
        narrative_parts.append(
            f"The affected asset is classified as {crit_label} (weight: {calc_result.c_asset:.2f}) "
            f"situated on {expo_label} (weight: {calc_result.e_net:.2f}), yielding environmental context multiplier M_context={calc_result.m_context:.3f}."
        )

        # 3. Verification & SLA
        if calc_result.f_verif >= 1.0:
            verif_clause = "The finding is actively confirmed via scanner PoC (100% confidence)"
        elif calc_result.f_verif >= 0.9:
            verif_clause = "The finding matches deterministic configuration signatures (90% confidence)"
        elif calc_result.f_verif < 0.5:
            verif_clause = "The finding is unconfirmed or flagged as candidate false positive, attenuating final risk score"
        else:
            verif_clause = f"The finding is based on heuristic observation ({calc_result.f_verif:.0%} confidence)"

        if calc_result.risk_severity == "CRITICAL":
            sla_clause = "Remediation recommended within 24 to 48 hours."
        elif calc_result.risk_severity == "HIGH":
            sla_clause = "Remediation recommended within 7 days."
        elif calc_result.risk_severity == "MEDIUM":
            sla_clause = "Remediation recommended within 30 days."
        else:
            sla_clause = "Remediation recommended during regular patching cycle."

        narrative_parts.append(f"{verif_clause}. {sla_clause}")
        full_narrative = " ".join(narrative_parts)

        return SentinelRiskAssessment(
            sentinel_risk_score=calc_result.sentinel_risk_score,
            severity=calc_result.risk_severity,
            score_breakdown=RiskScoreBreakdown(
                v_base=calc_result.v_base,
                b_threat=calc_result.b_threat,
                t_threat=calc_result.t_threat,
                m_context=calc_result.m_context,
                t_contextual=calc_result.t_contextual,
                f_verif=calc_result.f_verif,
            ),
            upstream_metrics=UpstreamMetricsExplanation(
                cvss_v3_base_score=calc_result.cvss,
                cvss_v3_vector=cvss_vector,
                epss_score=calc_result.epss,
                epss_percentile=epss_percentile,
                is_cisa_kev=calc_result.is_cisa_kev,
                cisa_kev_due_date=cisa_kev_due_date,
                known_ransomware_use=cisa_kev_ransomware,
            ),
            contextual_factors=ContextualFactorsExplanation(
                asset_criticality=crit_label,
                asset_criticality_factor=calc_result.c_asset,
                network_exposure=expo_label,
                network_exposure_factor=calc_result.e_net,
                verification_status=verif_label,
                verification_factor=calc_result.f_verif,
            ),
            score_explanation=full_narrative,
        )
