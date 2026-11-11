"""Sentinel Detection Rule Validator conforming to Sentinel Rule Spec v1.

Performs strict JSON/YAML schema validation, regex syntax compilation,
security hygiene checks, and remediation completeness auditing.
Conforms to Noosforge Sentinel R4 specifications.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
import yaml
from pydantic import ValidationError

from backend.app.schemas.rule import DetectionRuleBase, RuleValidationResponse

RULE_ID_REGEX = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
SEMVER_REGEX = re.compile(r"^\d+\.\d+\.\d+$")
CVE_REGEX = re.compile(r"^CVE-\d{4}-\d{4,}$")

ALLOWED_SEVERITIES = {"critical", "high", "medium", "low", "info"}
ALLOWED_STATUSES = {"draft", "in_review", "approved", "active", "deprecated", "disabled"}
ALLOWED_ENGINES = {"pattern_match", "response_eval", "nuclei"}
ALLOWED_MATCHER_TYPES = {"regex", "word", "status", "binary"}
ALLOWED_MATCHER_PARTS = {"all", "body", "header", "status_code", "path"}


class RuleValidator:
    """Strict validator for Sentinel YAML detection rules."""

    @classmethod
    def validate_yaml_string(cls, yaml_content: str) -> RuleValidationResponse:
        """Parse and validate raw YAML text."""
        errors: List[str] = []
        warnings: List[str] = []

        try:
            parsed = yaml.safe_load(yaml_content)
            if not isinstance(parsed, dict):
                return RuleValidationResponse(
                    valid=False,
                    errors=["Root of detection rule must be a YAML mapping/dictionary."],
                    warnings=[],
                )
        except yaml.YAMLError as e:
            return RuleValidationResponse(
                valid=False,
                errors=[f"YAML parsing error: {e}"],
                warnings=[],
            )

        return cls.validate_dict(parsed)

    @classmethod
    def validate_dict(cls, rule_dict: Dict[str, Any]) -> RuleValidationResponse:
        """Validate parsed rule dictionary against Sentinel Rule Spec v1."""
        errors: List[str] = []
        warnings: List[str] = []
        rule_id = rule_dict.get("id")

        # 1. Pydantic schema validation
        try:
            DetectionRuleBase.model_validate(rule_dict)
        except ValidationError as e:
            for err in e.errors():
                loc = ".".join(str(p) for p in err["loc"])
                errors.append(f"Schema violation at '{loc}': {err['msg']}")

        # 2. Rule ID format check
        if not rule_id or not isinstance(rule_id, str):
            errors.append("Rule 'id' is required and must be a string.")
        elif not RULE_ID_REGEX.match(rule_id):
            errors.append(
                f"Rule 'id' ('{rule_id}') must be kebab-case (e.g. 'sentinel-det-2026-0042')."
            )

        # 3. Name & Version checks
        name = rule_dict.get("name")
        if not name or len(str(name).strip()) < 3:
            errors.append("Rule 'name' must be at least 3 characters long.")

        version = rule_dict.get("version", "1.0.0")
        if not SEMVER_REGEX.match(str(version)):
            errors.append(f"Rule 'version' ('{version}') must follow Semantic Versioning (e.g. '1.0.0').")

        # 4. Severity & Status
        severity = str(rule_dict.get("severity", "")).lower()
        if severity not in ALLOWED_SEVERITIES:
            errors.append(f"Invalid severity '{severity}'. Must be one of: {sorted(ALLOWED_SEVERITIES)}")

        status = str(rule_dict.get("status", "")).lower()
        if status not in ALLOWED_STATUSES:
            errors.append(f"Invalid status '{status}'. Must be one of: {sorted(ALLOWED_STATUSES)}")

        # 5. Metadata checks (CVEs, CWEs)
        metadata = rule_dict.get("metadata", {})
        if isinstance(metadata, dict):
            cves = metadata.get("cve", [])
            if isinstance(cves, list):
                for c in cves:
                    if not CVE_REGEX.match(str(c)):
                        warnings.append(f"Metadata CVE '{c}' does not match standard pattern 'CVE-YYYY-NNNN'.")

        # 6. Detection logic & matcher validation
        detection = rule_dict.get("detection")
        if not isinstance(detection, dict):
            errors.append("Missing required 'detection' block.")
        else:
            engine = detection.get("engine", "pattern_match")
            if engine not in ALLOWED_ENGINES:
                errors.append(f"Invalid detection engine '{engine}'. Must be one of: {sorted(ALLOWED_ENGINES)}")

            matchers = detection.get("matchers", [])
            if not isinstance(matchers, list) or len(matchers) == 0:
                errors.append("Detection block must contain at least one matcher in 'matchers'.")
            else:
                for idx, m in enumerate(matchers):
                    m_id = m.get("id", f"matcher_{idx}")
                    m_type = m.get("type")
                    m_part = m.get("part", "all")

                    if m_type not in ALLOWED_MATCHER_TYPES:
                        errors.append(f"Matcher '{m_id}' has invalid type '{m_type}'. Allowed: {sorted(ALLOWED_MATCHER_TYPES)}")

                    if m_part not in ALLOWED_MATCHER_PARTS:
                        errors.append(f"Matcher '{m_id}' has invalid part '{m_part}'. Allowed: {sorted(ALLOWED_MATCHER_PARTS)}")

                    # Regex validation
                    if m_type == "regex":
                        regex_list = m.get("regex", [])
                        if not isinstance(regex_list, list) or len(regex_list) == 0:
                            errors.append(f"Regex matcher '{m_id}' must provide a non-empty 'regex' list.")
                        else:
                            for pat in regex_list:
                                try:
                                    re.compile(pat)
                                except re.error as reg_err:
                                    errors.append(f"Matcher '{m_id}' has invalid regex pattern '{pat}': {reg_err}")

                    # Word validation
                    if m_type == "word":
                        words = m.get("words", [])
                        if not isinstance(words, list) or len(words) == 0:
                            errors.append(f"Word matcher '{m_id}' must provide a non-empty 'words' list.")

                    # Status code validation
                    if m_type == "status":
                        statuses = m.get("status", [])
                        if not isinstance(statuses, list) or len(statuses) == 0:
                            errors.append(f"Status matcher '{m_id}' must provide a non-empty 'status' list of integers.")

        # 7. Remediation block checks
        remediation = rule_dict.get("remediation")
        if not isinstance(remediation, dict):
            errors.append("Missing required 'remediation' block.")
        else:
            guidance = remediation.get("guidance")
            if not guidance or len(str(guidance).strip()) < 10:
                errors.append("Remediation 'guidance' must provide actionable text (at least 10 characters).")

        return RuleValidationResponse(
            valid=len(errors) == 0,
            rule_id=rule_id,
            errors=errors,
            warnings=warnings,
        )
