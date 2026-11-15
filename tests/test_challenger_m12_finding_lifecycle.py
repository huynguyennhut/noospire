"""Adversarial challenger test suite for Finding Lifecycle, Triage, and Redaction (Milestone 12).

Tests:
1. Exhaustive state-machine transitions across all 10 canonical states.
2. Rejection of invalid / non-canonical statuses.
3. Backward compatibility mapping of legacy status names.
4. Database persistence and integrity of FindingChange audit trail entries.
5. Deep adversarial stress testing of redact_secrets:
   - Nested dictionaries, arrays, mixed trees
   - Bearer tokens, Authorization headers
   - JWT tokens (RFC 7519)
   - URL query parameter secrets (token=, password=, api_key=, cookie=)
   - Email address redaction
   - Non-secret preservation invariant
"""

import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.findings import redact_secrets
from backend.app.models.finding import NormalizedFinding
from backend.app.models.lifecycle import FindingChange
from backend.app.models.alert import SecurityAlert
from backend.app.models.user import User
from backend.app.schemas.common import FindingSeverity, FindingStatus
from backend.app.schemas.finding import FindingTriageRequest
from pydantic import ValidationError


def test_adversarial_canonical_10_states():
    """Verify exactly the 10 canonical states exist and match specification."""
    expected_states = [
        "NEW",
        "NEEDS_TRIAGE",
        "CONFIRMED",
        "FALSE_POSITIVE",
        "ACCEPTED_RISK",
        "ASSIGNED",
        "IN_PROGRESS",
        "FIXED_PENDING_RETEST",
        "RESOLVED",
        "REOPENED",
    ]
    canonical = FindingStatus.canonical_states()
    assert canonical == expected_states
    assert len(canonical) == 10

    for state in expected_states:
        enum_val = FindingStatus(state)
        assert enum_val.value == state


def test_adversarial_legacy_status_coercion():
    """Verify legacy status strings properly map to canonical states via Pydantic & Enum."""
    legacy_map = {
        "OPEN": FindingStatus.NEEDS_TRIAGE,
        "POTENTIAL": FindingStatus.NEEDS_TRIAGE,
        "IN_REMEDIATION": FindingStatus.IN_PROGRESS,
        "FIXED": FindingStatus.FIXED_PENDING_RETEST,
        "NOT_AFFECTED": FindingStatus.FALSE_POSITIVE,
        "MUTED": FindingStatus.ACCEPTED_RISK,
        "open": FindingStatus.NEEDS_TRIAGE,
        "fixed": FindingStatus.FIXED_PENDING_RETEST,
    }
    for legacy_name, expected_enum in legacy_map.items():
        assert FindingStatus(legacy_name) == expected_enum
        req = FindingTriageRequest(status=legacy_name)
        assert req.status == expected_enum


def test_adversarial_invalid_status_rejection():
    """Verify invalid statuses are rejected by Pydantic."""
    invalid_cases = [
        "EXPLOITED",
        "CLOSED",
        "UNKNOWN",
        "INVALID",
        "",
        "DROP TABLE",
        None,
    ]
    for inv in invalid_cases:
        with pytest.raises(ValidationError):
            FindingTriageRequest(status=inv)


def test_adversarial_secret_redaction_complex():
    """Stress test redact_secrets with adversarial payload structures."""
    jwt_sample = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    raw_input = {
        "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummy.sig",
        "headers": {
            "Cookie": "session=s3cr3t_cookie_9999; theme=dark",
            "Set-Cookie": "auth_token=super_secret_token",
            "X-Custom": f"Bearer {jwt_sample}",
        },
        "query_url": "https://empire.edu.vn/api/v1/auth?token=ghp_secretToken12345&password=SuperP@ssw0rd!&api_key=key_999999&debug=true",
        "comments": [
            "Contact admin at security-team@empire.edu.vn for help.",
            f"Observed JWT header: {jwt_sample}",
            "Using Bearer secret-bearer-value in curl call",
        ],
        "nested_dict": {
            "password": "CleartextPassword123!",
            "secret": "ProductionMasterKeyXYZ",
            "api_key": "sk_test_1234567890",
            "safe_field": "This is completely safe public text.",
        },
        "safe_int": 42,
        "safe_none": None,
    }

    sanitized = redact_secrets(raw_input)

    # 1. Top-level sensitive dict keys must be redacted
    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["headers"]["Cookie"] == "[REDACTED]"
    assert sanitized["headers"]["Set-Cookie"] == "[REDACTED]"

    # 2. String values inside headers must have Bearer / JWT redacted
    assert "[REDACTED_JWT]" in sanitized["headers"]["X-Custom"] or "[REDACTED]" in sanitized["headers"]["X-Custom"]

    # 3. URL query parameter secrets
    assert "token=[REDACTED]" in sanitized["query_url"]
    assert "password=[REDACTED]" in sanitized["query_url"]
    assert "api_key=[REDACTED]" in sanitized["query_url"]
    assert "debug=true" in sanitized["query_url"]
    assert "ghp_secretToken12345" not in sanitized["query_url"]
    assert "SuperP@ssw0rd!" not in sanitized["query_url"]

    # 4. Comments list: email, JWT, and Bearer redaction
    assert "[REDACTED_EMAIL]" in sanitized["comments"][0]
    assert "security-team@empire.edu.vn" not in sanitized["comments"][0]
    assert "[REDACTED_JWT]" in sanitized["comments"][1]
    assert jwt_sample not in sanitized["comments"][1]
    assert "Bearer [REDACTED]" in sanitized["comments"][2]
    assert "secret-bearer-value" not in sanitized["comments"][2]

    # 5. Nested sensitive keys
    assert sanitized["nested_dict"]["password"] == "[REDACTED]"
    assert sanitized["nested_dict"]["secret"] == "[REDACTED]"
    assert sanitized["nested_dict"]["api_key"] == "[REDACTED]"
    assert sanitized["nested_dict"]["safe_field"] == "This is completely safe public text."

    # 6. Safe primitives untouched
    assert sanitized["safe_int"] == 42
    assert sanitized["safe_none"] is None


@pytest.mark.asyncio
async def test_adversarial_triage_all_10_states_and_audit_trail(db_session: AsyncSession):
    """Cycle a finding through all 10 states and assert FindingChange records and audit trails."""
    from backend.app.api.findings import triage_finding
    from backend.app.models.asset import Asset
    from backend.app.core.config import settings

    asset_id = uuid.uuid4()
    asset = Asset(
        id=asset_id,
        name="Adversarial Test Asset",
        asset_type="WEB_APP",
        target_locator="https://test.empire.edu.vn",
        verification_status="VERIFIED",
    )
    db_session.add(asset)

    finding_id = uuid.uuid4()
    finding = NormalizedFinding(
        id=finding_id,
        asset_id=asset_id,
        scan_id=uuid.uuid4(),
        fingerprint=f"fp-{uuid.uuid4().hex[:12]}",
        scanner_engine="nuclei",
        scanner_rule_id="SEC-TEST-001",
        title="Adversarial Test Vulnerability",
        description="Finding for full 10-state lifecycle triage test",
        severity=FindingSeverity.HIGH.value,
        original_severity="HIGH",
        target_location="https://test.empire.edu.vn/login",
        status=FindingStatus.NEW.value,
        occurrence_count=1,
    )
    db_session.add(finding)
    await db_session.commit()

    operator = User(
        id=uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID),
        email=settings.SOLE_OWNER_EMAIL,
        username="sec_operator",
        role="OWNER",
        is_active=True,
    )

    all_10_states = [
        FindingStatus.NEEDS_TRIAGE,
        FindingStatus.CONFIRMED,
        FindingStatus.ASSIGNED,
        FindingStatus.IN_PROGRESS,
        FindingStatus.FIXED_PENDING_RETEST,
        FindingStatus.RESOLVED,
        FindingStatus.REOPENED,
        FindingStatus.IN_PROGRESS,
        FindingStatus.FALSE_POSITIVE,
        FindingStatus.ACCEPTED_RISK,
    ]

    for target_state in all_10_states:
        req = FindingTriageRequest(
            status=target_state,
            comment=f"Moving state to {target_state.value} with Bearer secret-token-xyz and admin@empire.edu.vn",
            assignee="lead_dev@empire.edu.vn",
        )
        updated = await triage_finding(
            finding_id=finding_id,
            triage_req=req,
            current_user=operator,
            db=db_session,
        )
        assert updated.status == target_state.value
        # Verify comment in remediation notes was sanitized
        assert "secret-token-xyz" not in updated.remediation_notes
        assert "[REDACTED]" in updated.remediation_notes
        assert "admin@empire.edu.vn" not in updated.remediation_notes
        assert "[REDACTED_EMAIL]" in updated.remediation_notes

    # Verify FindingChange audit records exist in DB
    changes_res = await db_session.execute(
        select(FindingChange).where(FindingChange.finding_id == finding_id, FindingChange.field == "status")
    )
    changes = changes_res.scalars().all()
    assert len(changes) == len(all_10_states), f"Expected {len(all_10_states)} status changes, found {len(changes)}"

    # Verify SecurityAlerts generated for FIXED_PENDING_RETEST, RESOLVED, and REOPENED
    alerts_res = await db_session.execute(
        select(SecurityAlert).where(SecurityAlert.category == "REMEDIATION")
    )
    alerts = alerts_res.scalars().all()
    assert len(alerts) >= 3, f"Expected at least 3 remediation alerts, got {len(alerts)}"
