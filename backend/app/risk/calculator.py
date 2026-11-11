"""Transparent Multi-Factor Risk Calculation Engine.

Implements the Sentinel Risk Score (SRS) formula:
SRS = round(T_contextual * F_verif * 100.0, 1)
incorporating CVSS v3.1, FIRST EPSS probability, CISA KEV exploitation status (threat floor >= 0.75),
asset business criticality, network exposure, and verification confidence.
Conforms to Noosforge Sentinel R4 specifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class AssetCriticality(str, Enum):
    TIER_1_MISSION_CRITICAL = "tier_1_mission_critical"  # Factor: 1.00
    TIER_2_HIGH = "tier_2_high"                          # Factor: 0.80
    TIER_3_MEDIUM = "tier_3_medium"                      # Factor: 0.60
    TIER_4_LOW = "tier_4_low"                            # Factor: 0.40


class NetworkExposure(str, Enum):
    PUBLIC_INTERNET = "public_internet"  # Factor: 1.00
    DMZ_PARTNER = "dmz_partner"          # Factor: 0.75
    INTERNAL_PRIVATE = "internal_private" # Factor: 0.50
    ISOLATED_LOCAL = "isolated_local"    # Factor: 0.25


class VerificationConfidence(str, Enum):
    CONFIRMED_POC = "confirmed_poc"          # Factor: 1.00
    HIGH_CONFIDENCE = "high_confidence"      # Factor: 0.90
    MEDIUM_CONFIDENCE = "medium_confidence"  # Factor: 0.70
    UNCONFIRMED_FP = "unconfirmed_fp"        # Factor: 0.40


CRITICALITY_FACTORS: Dict[str, float] = {
    AssetCriticality.TIER_1_MISSION_CRITICAL.value: 1.00,
    AssetCriticality.TIER_2_HIGH.value: 0.80,
    AssetCriticality.TIER_3_MEDIUM.value: 0.60,
    AssetCriticality.TIER_4_LOW.value: 0.40,
    "critical": 1.00,
    "high": 0.80,
    "medium": 0.60,
    "low": 0.40,
}

EXPOSURE_FACTORS: Dict[str, float] = {
    NetworkExposure.PUBLIC_INTERNET.value: 1.00,
    NetworkExposure.DMZ_PARTNER.value: 0.75,
    NetworkExposure.INTERNAL_PRIVATE.value: 0.50,
    NetworkExposure.ISOLATED_LOCAL.value: 0.25,
    "public": 1.00,
    "dmz": 0.75,
    "internal": 0.50,
    "isolated": 0.25,
}

VERIFICATION_FACTORS: Dict[str, float] = {
    VerificationConfidence.CONFIRMED_POC.value: 1.00,
    VerificationConfidence.HIGH_CONFIDENCE.value: 0.90,
    VerificationConfidence.MEDIUM_CONFIDENCE.value: 0.70,
    VerificationConfidence.UNCONFIRMED_FP.value: 0.40,
    "confirmed": 1.00,
    "high": 0.90,
    "medium": 0.70,
    "unconfirmed": 0.40,
}

SEVERITY_FALLBACK_SCORES: Dict[str, float] = {
    "critical": 10.0,
    "high": 8.0,
    "medium": 5.0,
    "low": 2.0,
    "info": 0.0,
}


@dataclass
class RiskCalculationResult:
    """Detailed intermediate and final values of the risk scoring formula."""

    sentinel_risk_score: float
    risk_severity: str
    v_base: float
    b_threat: float
    t_threat: float
    m_context: float
    t_contextual: float
    f_verif: float
    c_asset: float
    e_net: float
    cvss: float
    epss: float
    is_cisa_kev: bool


class RiskCalculator:
    """Deterministic mathematical calculator for Sentinel Risk Score."""

    @classmethod
    def resolve_factors(
        cls,
        criticality: Any,
        exposure: Any,
        verification: Any,
    ) -> tuple[float, float, float]:
        """Convert enum or string representation to calibrated numerical factor."""
        # Criticality
        if isinstance(criticality, (int, float)):
            c_factor = max(0.1, min(1.0, float(criticality)))
        else:
            key = (criticality.value if hasattr(criticality, "value") else str(criticality)).lower().strip()
            c_factor = CRITICALITY_FACTORS.get(key, 0.60)  # Default medium

        # Exposure
        if isinstance(exposure, (int, float)):
            e_factor = max(0.1, min(1.0, float(exposure)))
        else:
            key = (exposure.value if hasattr(exposure, "value") else str(exposure)).lower().strip()
            e_factor = EXPOSURE_FACTORS.get(key, 0.50)  # Default internal

        # Verification
        if isinstance(verification, (int, float)):
            v_factor = max(0.1, min(1.0, float(verification)))
        else:
            key = (verification.value if hasattr(verification, "value") else str(verification)).lower().strip()
            v_factor = VERIFICATION_FACTORS.get(key, 0.90)  # Default high

        return c_factor, e_factor, v_factor

    @classmethod
    def calculate_risk(
        cls,
        cvss: Optional[float] = None,
        scanner_severity: Optional[str] = None,
        epss: Optional[float] = None,
        is_cisa_kev: bool = False,
        asset_criticality: Any = AssetCriticality.TIER_3_MEDIUM,
        network_exposure: Any = NetworkExposure.INTERNAL_PRIVATE,
        verification_confidence: Any = VerificationConfidence.HIGH_CONFIDENCE,
    ) -> RiskCalculationResult:
        """Compute Sentinel Risk Score ($SRS$) using the authoritative mathematical formula:

        1. V_base = CVSS / 10.0
        2. B_threat = 0.20 * EPSS + (0.30 if is_cisa_kev else 0.0)
        3. T_threat = min(1.0, V_base + B_threat)
           If is_cisa_kev: T_threat = max(0.75, T_threat)
        4. M_context = 0.50 * C_asset + 0.50 * E_net
        5. T_contextual = T_threat * (0.35 + 0.65 * M_context)
        6. SRS = round(min(100.0, max(0.0, T_contextual * F_verif * 100.0)), 1)
        """
        # Resolve CVSS (fallback to scanner severity if missing)
        if cvss is not None:
            eff_cvss = max(0.0, min(10.0, float(cvss)))
        else:
            sev_key = (scanner_severity or "medium").lower()
            eff_cvss = SEVERITY_FALLBACK_SCORES.get(sev_key, 5.0)

        # Inherent base severity
        v_base = eff_cvss / 10.0

        # Effective EPSS
        eff_epss = max(0.0, min(1.0, float(epss if epss is not None else 0.0001)))

        # Threat boost & urgency
        b_threat = 0.20 * eff_epss + (0.30 if is_cisa_kev else 0.0)
        t_threat = min(1.0, v_base + b_threat)

        # Mandatory CISA KEV Threat Floor
        if is_cisa_kev:
            t_threat = max(0.75, t_threat)

        # Context factors
        c_asset, e_net, f_verif = cls.resolve_factors(
            asset_criticality,
            network_exposure,
            verification_confidence,
        )

        m_context = 0.50 * c_asset + 0.50 * e_net
        t_contextual = t_threat * (0.35 + 0.65 * m_context)

        # Final Sentinel Risk Score
        raw_srs = t_contextual * f_verif * 100.0
        srs = round(min(100.0, max(0.0, raw_srs)), 1)

        # Severity mapping
        if srs >= 80.0:
            severity = "CRITICAL"
        elif srs >= 60.0:
            severity = "HIGH"
        elif srs >= 40.0:
            severity = "MEDIUM"
        elif srs >= 20.0:
            severity = "LOW"
        else:
            severity = "INFO"

        return RiskCalculationResult(
            sentinel_risk_score=srs,
            risk_severity=severity,
            v_base=round(v_base, 4),
            b_threat=round(b_threat, 4),
            t_threat=round(t_threat, 4),
            m_context=round(m_context, 5),
            t_contextual=round(t_contextual, 5),
            f_verif=f_verif,
            c_asset=c_asset,
            e_net=e_net,
            cvss=eff_cvss,
            epss=eff_epss,
            is_cisa_kev=is_cisa_kev,
        )
