"""Automated Rule Test Fixture Runner.

Evaluates detection rules against positive and negative test cases to ensure detection accuracy
and regression prevention before promotion to approved/active states.
Conforms to Noosforge Sentinel R4 specifications.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from backend.app.rules.engine import DetectionEngine
from backend.app.schemas.rule import (
    RuleTestCaseSchema,
    RuleTestFixtureRunnerResponse,
    TestCaseResultItem,
)

logger = logging.getLogger("sentinel.rules.test_runner")


class RuleTestRunner:
    """Automated unit test execution harness for Sentinel detection rules."""

    @classmethod
    def load_fixture_file(cls, rule_id: str, fixtures_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """Look up corresponding test fixture file on disk: fixtures/rules/{rule_id}.test.yaml."""
        if fixtures_dir:
            dir_path = Path(fixtures_dir)
        else:
            base_dir = Path(__file__).resolve().parents[3]
            dir_path = base_dir / "fixtures" / "rules"

        fixture_file = dir_path / f"{rule_id}.test.yaml"
        if not fixture_file.exists():
            return []

        try:
            with open(fixture_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return data.get("test_cases", [])
            return []
        except Exception as e:
            logger.error("Failed to load fixture file %s: %s", fixture_file, e)
            return []

    @classmethod
    def run_tests(
        cls,
        rule_dict: Dict[str, Any],
        test_cases: Optional[List[Dict[str, Any]]] = None,
        fixtures_dir: Optional[str] = None,
    ) -> RuleTestFixtureRunnerResponse:
        """Run all provided or file-backed test cases against the specified rule."""
        rule_id = rule_dict.get("id", "unknown-rule")

        # If test_cases not explicitly provided, try loading from disk
        cases = test_cases or cls.load_fixture_file(rule_id, fixtures_dir=fixtures_dir)

        results: List[TestCaseResultItem] = []
        passed_count = 0
        failed_count = 0

        for idx, case in enumerate(cases):
            name = case.get("name", f"Test Case #{idx + 1}")
            expected_match = case.get("expected_match", True)
            input_data = case.get("input", {})

            # Execute rule against input
            try:
                exec_result = DetectionEngine.evaluate_rule(rule_dict, input_data)
                actual_match = exec_result.matched
                passed = actual_match == expected_match
                if passed:
                    passed_count += 1
                else:
                    failed_count += 1

                results.append(
                    TestCaseResultItem(
                        name=name,
                        expected_match=expected_match,
                        actual_match=actual_match,
                        passed=passed,
                        matched_by=exec_result.matched_by,
                        error_message=None if passed else (
                            f"Expected match={expected_match}, but got match={actual_match} (matched_by: {exec_result.matched_by})"
                        ),
                    )
                )
            except Exception as e:
                failed_count += 1
                results.append(
                    TestCaseResultItem(
                        name=name,
                        expected_match=expected_match,
                        actual_match=False,
                        passed=False,
                        matched_by=[],
                        error_message=f"Execution error: {str(e)}",
                    )
                )

        total = len(cases)
        all_passed = (total > 0) and (failed_count == 0)

        return RuleTestFixtureRunnerResponse(
            rule_id=rule_id,
            total_tests=total,
            passed_tests=passed_count,
            failed_tests=failed_count,
            all_passed=all_passed,
            results=results,
        )
