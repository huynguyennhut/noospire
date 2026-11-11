"""Empirical Stress-Test Suite by m1_it2_challenger_1.

Adversarially tests:
1. SSRF & Egress Protection boundaries (0.0.0.0, [::], multicast, metadata, lab whitelist).
2. Datetime comparisons and token revocation across endpoints (naive, aware, non-UTC, float/int iat).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select

from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.core.ssrf import SSRFProtector, SSRFValidationError, validate_egress_target
from backend.app.models.user import User, UserRole


def generate_token_with_iat(
    username: str,
    role: str,
    email: str = "",
    user_id: str = "",
    iat_val: int | float | None = None,
) -> str:
    claims = {"email": email, "id": user_id, "role": role}
    # Note: create_access_token automatically sets iat to datetime.now(timezone.utc)
    # If custom iat is needed, we encode directly
    import jwt
    to_encode = {
        "sub": username,
        "role": role,
        "is_superuser": False,
        **claims,
    }
    now = datetime.now(timezone.utc)
    to_encode["exp"] = now + timedelta(minutes=60)
    if iat_val is not None:
        to_encode["iat"] = iat_val
    else:
        to_encode["iat"] = now

    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# =============================================================================
# SUITE 1: SSRF & Egress Protection Comprehensive Boundary Matrix
# =============================================================================

class TestEmpiricalSSRFBoundaries:
    """Empirically stress-tests SSRF edge cases across dev and prod environments."""

    UNCONDITIONAL_BLOCKED_TARGETS = [
        # Unspecified & 0.0.0.0/8
        "http://0.0.0.0",
        "http://0.0.0.0:8000",
        "http://0.0.0.1",
        "http://0.255.255.255",
        "http://[::]",
        "http://[::]:8080",
        # IPv4 Multicast
        "http://224.0.0.1",
        "http://239.255.255.250",
        # IPv6 Multicast
        "http://[ff02::1]",
        "http://[ff05::2]",
        "http://[ff01::1]",
        # Cloud Metadata IPs & Hostnames
        "http://169.254.169.254",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200",
        "http://192.0.0.192",
        "http://metadata.google.internal",
        "http://metadata.internal",
        "http://instance-data",
        # Link-Local Unicast
        "http://169.254.1.1",
        "http://169.254.254.254",
        "http://[fe80::1]",
        "http://[fe80::a00:27ff:fe4e:66a1]",
    ]

    NON_LAB_SPECIAL_TARGETS = [
        # CGNAT (100.64.0.0/10) - blocked, not in ALLOWED_LAB_NETWORKS
        "http://100.64.0.1",
        "http://100.127.255.254",
        # Benchmarking (198.18.0.0/15) - blocked, not in ALLOWED_LAB_NETWORKS
        "http://198.18.0.1",
        # TEST-NET-1 (192.0.2.0/24) - blocked, not in ALLOWED_LAB_NETWORKS
        "http://192.0.2.1",
        # TEST-NET-2 (198.51.100.0/24) - blocked, not in ALLOWED_LAB_NETWORKS
        "http://198.51.100.1",
        # TEST-NET-3 (203.0.113.0/24) - blocked, not in ALLOWED_LAB_NETWORKS
        "http://203.0.113.1",
        # IPv6 Documentation (2001:db8::/32)
        "http://[2001:db8::1]",
        # IPv6 6to4 relay anycast (2002::/16)
        "http://[2002::1]",
    ]

    ALLOWED_LAB_TARGETS = [
        ("http://127.0.0.1", "127.0.0.1"),
        ("http://127.0.0.5:8080", "127.0.0.5"),
        ("http://10.0.0.1", "10.0.0.1"),
        ("http://10.254.0.1:9000", "10.254.0.1"),
        ("http://172.16.0.1", "172.16.0.1"),
        ("http://172.31.255.254", "172.31.255.254"),
        ("http://192.168.1.1", "192.168.1.1"),
        ("http://192.168.100.50:3000", "192.168.100.50"),
        ("http://[::1]", "::1"),
        ("http://[fd12:3456:789a::1]", "fd12:3456:789a::1"),
    ]

    @pytest.mark.parametrize("target", UNCONDITIONAL_BLOCKED_TARGETS)
    def test_unconditional_targets_rejected_in_all_configurations(self, target: str):
        """Zero bypass: 0.0.0.0, [::], multicast, metadata, link-local must fail under all modes."""
        # 1. Dev mode, allow_private=False
        with pytest.raises(SSRFValidationError):
            validate_egress_target(target, allow_private=False)

        # 2. Dev mode, allow_private=True (MUST STILL FAIL)
        with pytest.raises(SSRFValidationError):
            validate_egress_target(target, allow_private=True)

        # 3. Production mode, allow_private=True (MUST STILL FAIL)
        with patch.object(settings, "ENVIRONMENT", "production"):
            with pytest.raises(SSRFValidationError):
                validate_egress_target(target, allow_private=True)

        # 4. Production mode, allow_private=False
        with patch.object(settings, "ENVIRONMENT", "production"):
            with pytest.raises(SSRFValidationError):
                validate_egress_target(target, allow_private=False)

    @pytest.mark.parametrize("target", NON_LAB_SPECIAL_TARGETS)
    def test_non_lab_special_ranges_rejected_even_with_allow_private(self, target: str):
        """Ranges not in ALLOWED_LAB_NETWORKS (e.g. CGNAT, TEST-NET) must NOT bypass in dev."""
        with pytest.raises(SSRFValidationError):
            validate_egress_target(target, allow_private=True)

    @pytest.mark.parametrize("target, expected_ip", ALLOWED_LAB_TARGETS)
    def test_allowed_lab_networks_in_dev_vs_production(self, target: str, expected_ip: str):
        """ALLOWED_LAB_NETWORKS can bypass in dev when allow_private=True,

        but MUST BE STRICTLY BLOCKED in production.
        """
        # In Dev with allow_private=False -> Blocked
        with pytest.raises(SSRFValidationError):
            validate_egress_target(target, allow_private=False)

        # In Dev with allow_private=True -> Allowed
        norm_url, resolved_ip = validate_egress_target(target, allow_private=True)
        assert resolved_ip == expected_ip

        # In Production with allow_private=True -> STRICTLY BLOCKED (zero bypass)
        with patch.object(settings, "ENVIRONMENT", "production"):
            with pytest.raises(SSRFValidationError):
                validate_egress_target(target, allow_private=True)


# =============================================================================
# SUITE 2: Datetime Comparison & Token Revocation Across Routes
# =============================================================================

class TestEmpiricalDatetimeAndRevocation:
    """Empirically stress-tests datetime comparisons and token invalidation across routes."""

    @pytest.mark.asyncio
    async def test_naive_vs_aware_datetime_in_tokens_valid_after(self, client: httpx.AsyncClient):
        """Stress-test: User.tokens_valid_after set to offset-naive datetime.

        Verifies that tokens issued before tokens_valid_after return 401 with 'Session expired/revoked'
        without raising TypeError across multiple endpoints (/auth/me, /assets, /scans).
        """
        user_id = uuid.uuid4()
        username = f"user_{user_id.hex[:8]}"
        email = f"{username}@example.com"

        async with AsyncSessionLocal() as session:
            test_user = User(
                id=user_id,
                username=username,
                email=email,
                hashed_password=get_password_hash("SecretPass123!"),
                role=UserRole.OPERATOR.value,
                is_active=True,
                is_superuser=False,
            )
            session.add(test_user)
            await session.commit()

        # Generate token issued 10 minutes ago
        past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        past_iat = int(past_time.timestamp())
        token = generate_token_with_iat(username, UserRole.OPERATOR.value, email=email, user_id=str(user_id), iat_val=past_iat)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Update user.tokens_valid_after to offset-naive UTC timestamp (5 minutes ago)
        # Token (10m ago) < tokens_valid_after (5m ago) => MUST BE REVOKED
        naive_dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
        async with AsyncSessionLocal() as session:
            u = (await session.execute(select(User).where(User.id == user_id))).scalars().first()
            u.tokens_valid_after = naive_dt
            await session.commit()

        # Test route 1: /api/v1/auth/me
        res1 = await client.get("/api/v1/auth/me", headers=headers)
        assert res1.status_code == 401
        assert "Session expired/revoked" in res1.json()["detail"]

        # Test route 2: /api/v1/assets
        res2 = await client.get("/api/v1/assets", headers=headers)
        assert res2.status_code == 401
        assert "Session expired/revoked" in res2.json()["detail"]

        # Test route 3: /api/v1/scans
        res3 = await client.get("/api/v1/scans", headers=headers)
        assert res3.status_code == 401
        assert "Session expired/revoked" in res3.json()["detail"]

    @pytest.mark.asyncio
    async def test_non_utc_timezone_aware_datetime_in_tokens_valid_after(self, client: httpx.AsyncClient):
        """Stress-test: User.tokens_valid_after set to non-UTC timezone (e.g. Asia/Ho_Chi_Minh UTC+7).

        Verifies that timezone conversion works seamlessly and comparisons behave identically.
        """
        user_id = uuid.uuid4()
        username = f"user_{user_id.hex[:8]}"
        email = f"{username}@example.com"

        async with AsyncSessionLocal() as session:
            test_user = User(
                id=user_id,
                username=username,
                email=email,
                hashed_password=get_password_hash("SecretPass123!"),
                role=UserRole.OPERATOR.value,
                is_active=True,
                is_superuser=False,
            )
            session.add(test_user)
            await session.commit()

        # Generate token issued 10 minutes ago
        past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        past_iat = int(past_time.timestamp())
        token = generate_token_with_iat(username, UserRole.OPERATOR.value, email=email, user_id=str(user_id), iat_val=past_iat)
        headers = {"Authorization": f"Bearer {token}"}

        # Set tokens_valid_after in Asia/Ho_Chi_Minh (UTC+7) 5 minutes ago
        tz_hcm = timezone(timedelta(hours=7))
        hcm_dt = (datetime.now(timezone.utc) - timedelta(minutes=5)).astimezone(tz_hcm)
        async with AsyncSessionLocal() as session:
            u = (await session.execute(select(User).where(User.id == user_id))).scalars().first()
            u.tokens_valid_after = hcm_dt
            await session.commit()

        # Call endpoint -> Must be revoked (401)
        res = await client.get("/api/v1/auth/me", headers=headers)
        assert res.status_code == 401
        assert "Session expired/revoked" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_float_and_int_iat_comparison(self, client: httpx.AsyncClient):
        """Stress-test: Token with float iat (microseconds precision) vs integer iat.

        Both must compare accurately against tokens_valid_after without crashing.
        """
        user_id = uuid.uuid4()
        username = f"user_{user_id.hex[:8]}"
        email = f"{username}@example.com"

        async with AsyncSessionLocal() as session:
            test_user = User(
                id=user_id,
                username=username,
                email=email,
                hashed_password=get_password_hash("SecretPass123!"),
                role=UserRole.OPERATOR.value,
                is_active=True,
                is_superuser=False,
            )
            session.add(test_user)
            await session.commit()

        # Test Float iat
        float_iat = (datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp()
        float_token = generate_token_with_iat(username, UserRole.OPERATOR.value, email=email, user_id=str(user_id), iat_val=float_iat)

        async with AsyncSessionLocal() as session:
            u = (await session.execute(select(User).where(User.id == user_id))).scalars().first()
            u.tokens_valid_after = datetime.now(timezone.utc) - timedelta(minutes=5)
            await session.commit()

        res_float = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {float_token}"})
        assert res_float.status_code == 401
        assert "Session expired/revoked" in res_float.json()["detail"]

    @pytest.mark.asyncio
    async def test_fresh_token_after_revocation_succeeds(self, client: httpx.AsyncClient):
        """Stress-test: After token revocation, a freshly issued token (issued_at >= tokens_valid_after)

        must successfully authenticate.
        """
        user_id = uuid.uuid4()
        username = f"user_{user_id.hex[:8]}"
        email = f"{username}@example.com"

        async with AsyncSessionLocal() as session:
            test_user = User(
                id=user_id,
                username=username,
                email=email,
                hashed_password=get_password_hash("SecretPass123!"),
                role=UserRole.OPERATOR.value,
                is_active=True,
                is_superuser=False,
            )
            session.add(test_user)
            await session.commit()

        # Set revocation threshold to 2 minutes ago
        revocation_instant = datetime.now(timezone.utc) - timedelta(minutes=2)
        async with AsyncSessionLocal() as session:
            u = (await session.execute(select(User).where(User.id == user_id))).scalars().first()
            u.tokens_valid_after = revocation_instant
            await session.commit()

        # 1. Old token (5 minutes ago) -> REJECTED
        old_token = generate_token_with_iat(
            username,
            UserRole.OPERATOR.value,
            email=email,
            user_id=str(user_id),
            iat_val=int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp()),
        )
        res_old = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"})
        assert res_old.status_code == 401
        assert "Session expired/revoked" in res_old.json()["detail"]

        # 2. Fresh token (issued right now) -> ACCEPTED
        fresh_token = generate_token_with_iat(
            username,
            UserRole.OPERATOR.value,
            email=email,
            user_id=str(user_id),
            iat_val=int(datetime.now(timezone.utc).timestamp()),
        )
        res_fresh = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {fresh_token}"})
        assert res_fresh.status_code == 200
        assert res_fresh.json()["username"] == username
