"""Review-Gated Rule Lifecycle State Machine.

Enforces formal state progression (draft -> in_review -> approved -> active -> deprecated/disabled),
separation of duties (author != reviewer), schema validation, test fixture verification, and audit logging.
Conforms to Noosforge Sentinel R4 specifications.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Set
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.rule import DetectionRule, RuleAuditLog, RuleStatus
from backend.app.rules.test_runner import RuleTestRunner
from backend.app.rules.validator import RuleValidator
from backend.app.schemas.rule import (
    RuleLifecycleTransitionRequest,
    RuleLifecycleTransitionResponse,
    RuleStatusEnum,
)

logger = logging.getLogger("sentinel.rules.lifecycle")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Permitted state transitions map
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    RuleStatus.DRAFT.value: {RuleStatus.IN_REVIEW.value, RuleStatus.DISABLED.value},
    RuleStatus.IN_REVIEW.value: {RuleStatus.DRAFT.value, RuleStatus.APPROVED.value, RuleStatus.DISABLED.value},
    RuleStatus.APPROVED.value: {RuleStatus.ACTIVE.value, RuleStatus.DISABLED.value, RuleStatus.DEPRECATED.value},
    RuleStatus.ACTIVE.value: {RuleStatus.DEPRECATED.value, RuleStatus.DISABLED.value, RuleStatus.IN_REVIEW.value},
    RuleStatus.DEPRECATED.value: {RuleStatus.DISABLED.value},
    RuleStatus.DISABLED.value: {RuleStatus.DRAFT.value, RuleStatus.APPROVED.value, RuleStatus.ACTIVE.value},
}


class RuleLifecycleManager:
    """Manages detection rule lifecycle transitions with separation-of-duties governance."""

    @classmethod
    def can_transition(cls, current_status: str, target_status: str) -> bool:
        """Check if transition is theoretically valid in the state graph."""
        allowed = VALID_TRANSITIONS.get(current_status, set())
        return target_status in allowed

    @classmethod
    async def transition_rule(
        cls,
        session: AsyncSession,
        rule_id: str,
        target_status: RuleStatusEnum,
        actor: str,
        notes: Optional[str] = None,
        require_tests: bool = True,
    ) -> RuleLifecycleTransitionResponse:
        """Execute a review-gated rule transition with all invariant checks."""
        stmt = select(DetectionRule).where(DetectionRule.id == rule_id)
        result = await session.execute(stmt)
        rule = result.scalar_one_or_none()

        if not rule:
            raise ValueError(f"Rule '{rule_id}' not found.")

        current_status = rule.status
        target_val = target_status.value

        # 1. State transition validity check
        if not cls.can_transition(current_status, target_val):
            raise ValueError(
                f"Invalid transition from '{current_status}' to '{target_val}'. "
                f"Permitted targets: {sorted(VALID_TRANSITIONS.get(current_status, set()))}"
            )

        # 2. Transition specific gate checks
        # A. Transitioning to IN_REVIEW requires valid schema
        if target_val == RuleStatus.IN_REVIEW.value:
            val_res = RuleValidator.validate_yaml_string(rule.raw_yaml)
            if not val_res.valid:
                raise ValueError(f"Rule schema validation failed: {'; '.join(val_res.errors)}")

        # B. Transitioning to APPROVED requires separation of duties AND passing test fixtures
        if target_val == RuleStatus.APPROVED.value:
            # Separation of duties: author/creator cannot approve their own rule!
            author = rule.author.strip().lower()
            creator = rule.created_by.strip().lower()
            reviewer = actor.strip().lower()

            if reviewer == author or reviewer == creator:
                raise PermissionError(
                    f"Separation of duties violation: Rule author '{rule.author}' / creator '{rule.created_by}' "
                    f"cannot approve their own rule. Reviewer must be an independent peer."
                )

            # Test fixture execution check
            if require_tests:
                rule_dict = {
                    "id": rule.id,
                    "name": rule.name,
                    "severity": rule.severity,
                    "detection": rule.detection_json,
                }
                test_results = RuleTestRunner.run_tests(rule_dict)
                if test_results.total_tests == 0:
                    raise ValueError(
                        f"Cannot approve rule '{rule_id}': No test fixtures found. "
                        f"Rules must pass at least one test case before approval."
                    )
                if not test_results.all_passed:
                    failed_msgs = [f"{t.name}: {t.error_message}" for t in test_results.results if not t.passed]
                    raise ValueError(
                        f"Cannot approve rule '{rule_id}': {test_results.failed_tests}/{test_results.total_tests} "
                        f"test cases failed: {'; '.join(failed_msgs)}"
                    )

            rule.approved_by = actor

        # Update rule status
        rule.status = target_val
        rule.updated_at = utc_now()

        # Create immutable audit log entry
        audit_entry = RuleAuditLog(
            rule_id=rule.id,
            actor=actor,
            action=f"transition_to_{target_val}",
            from_status=current_status,
            to_status=target_val,
            notes=notes,
            timestamp=utc_now(),
        )
        session.add(audit_entry)
        await session.commit()

        logger.info(
            "Rule '%s' successfully transitioned from '%s' to '%s' by actor '%s'.",
            rule_id,
            current_status,
            target_val,
            actor,
        )

        return RuleLifecycleTransitionResponse(
            rule_id=rule_id,
            previous_status=current_status,
            new_status=target_val,
            actor=actor,
            success=True,
            message=f"Rule transitioned from '{current_status}' to '{target_val}'.",
            transition_timestamp=audit_entry.timestamp,
        )
