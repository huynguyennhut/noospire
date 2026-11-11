"""Detection Rule Execution Engine conforming to Sentinel Rule Spec v1.

Evaluates HTTP request/response payloads or raw strings against declarative matchers (regex, words, status).
Conforms to Noosforge Sentinel R4 specifications.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class RuleExecutionResult:
    """Outcome of evaluating a detection rule against an input payload."""

    rule_id: str
    matched: bool
    matched_by: List[str] = field(default_factory=list)
    extracted_evidence: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None


class DetectionEngine:
    """Evaluates declarative rules against HTTP traffic or forensic inputs."""

    @classmethod
    def evaluate_rule(
        cls,
        rule_dict: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> RuleExecutionResult:
        """Evaluate a parsed rule dictionary against an input payload.

        payload format:
        {
            "request": {
                "method": "POST",
                "path": "/api/v1/auth",
                "headers": {"Content-Type": "application/json", "User-Agent": "..."},
                "body": "..."
            },
            "response": {
                "status_code": 200,
                "headers": {"Server": "Apache"},
                "body": "..."
            }
        }
        """
        rule_id = rule_dict.get("id", "unknown-rule")
        detection = rule_dict.get("detection", {})
        condition_strategy = detection.get("condition", "any_of_matchers")
        matchers = detection.get("matchers", [])

        if not matchers:
            return RuleExecutionResult(rule_id=rule_id, matched=False)

        matched_matcher_ids: List[str] = []
        evidence_dict: Dict[str, Any] = {}

        for m in matchers:
            m_id = m.get("id", "unnamed_matcher")
            m_res, m_ev = cls._evaluate_matcher(m, payload)
            if m_res:
                matched_matcher_ids.append(m_id)
                evidence_dict[m_id] = m_ev

        if condition_strategy == "all_of_matchers":
            is_match = len(matched_matcher_ids) == len(matchers)
        else:  # "any_of_matchers"
            is_match = len(matched_matcher_ids) > 0

        return RuleExecutionResult(
            rule_id=rule_id,
            matched=is_match,
            matched_by=matched_matcher_ids if is_match else [],
            extracted_evidence=evidence_dict if is_match else {},
        )

    @classmethod
    def _extract_part_text(cls, part: str, payload: Dict[str, Any]) -> str:
        """Extract relevant target text from payload according to the matcher 'part' spec."""
        req = payload.get("request", {}) or {}
        resp = payload.get("response", {}) or {}

        if part == "path":
            return str(req.get("path", "") or "")

        if part == "body":
            # Check response body first, then request body
            resp_body = resp.get("body", "") or ""
            req_body = req.get("body", "") or ""
            return f"{resp_body}\n{req_body}".strip()

        if part == "header":
            req_headers = " ".join(f"{k}: {v}" for k, v in (req.get("headers") or {}).items())
            resp_headers = " ".join(f"{k}: {v}" for k, v in (resp.get("headers") or {}).items())
            return f"{req_headers}\n{resp_headers}".strip()

        if part == "status_code":
            return str(resp.get("status_code", "") or "")

        # part == "all"
        req_headers = " ".join(f"{k}: {v}" for k, v in (req.get("headers") or {}).items())
        resp_headers = " ".join(f"{k}: {v}" for k, v in (resp.get("headers") or {}).items())
        req_path = req.get("path", "") or ""
        req_body = req.get("body", "") or ""
        resp_body = resp.get("body", "") or ""
        resp_code = str(resp.get("status_code", "") or "")

        return f"{req_path}\n{req_headers}\n{req_body}\n{resp_code}\n{resp_headers}\n{resp_body}"

    @classmethod
    def _evaluate_matcher(
        cls,
        matcher: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> tuple[bool, Dict[str, Any]]:
        """Evaluate a single matcher against payload."""
        m_type = matcher.get("type", "word")
        m_part = matcher.get("part", "all")
        is_negative = matcher.get("negative", False)
        condition = matcher.get("condition", "or").lower()
        case_insensitive = matcher.get("case_insensitive", True)

        evidence: Dict[str, Any] = {}
        target_text = cls._extract_part_text(m_part, payload)

        if m_type == "regex":
            patterns = matcher.get("regex", [])
            flags = re.IGNORECASE if case_insensitive else 0
            matches_found: List[str] = []

            for pat in patterns:
                try:
                    compiled = re.compile(pat, flags)
                    match = compiled.search(target_text)
                    if match:
                        matches_found.append(match.group(0))
                except re.error:
                    pass

            if condition == "and":
                matched = len(matches_found) == len(patterns) and len(patterns) > 0
            else:  # or
                matched = len(matches_found) > 0

            if matched:
                evidence["regex_matches"] = matches_found

        elif m_type == "word":
            words = matcher.get("words", [])
            check_text = target_text.lower() if case_insensitive else target_text
            words_found: List[str] = []

            for w in words:
                word_to_find = w.lower() if case_insensitive else w
                if word_to_find in check_text:
                    words_found.append(w)

            if condition == "and":
                matched = len(words_found) == len(words) and len(words) > 0
            else:  # or
                matched = len(words_found) > 0

            if matched:
                evidence["words_matched"] = words_found

        elif m_type == "status":
            expected_statuses = matcher.get("status", [])
            actual_status = (payload.get("response") or {}).get("status_code")
            matched = actual_status in expected_statuses
            if matched:
                evidence["status_code"] = actual_status

        else:
            matched = False

        if is_negative:
            matched = not matched

        return matched, evidence
