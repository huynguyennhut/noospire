"""Adversarial Empirical Stress Testing Suite for Milestone 1.

Challenger 1 Verification Harness:
1. SSRF & Egress Protection:
   - Challenge validate_egress_target against metadata (169.254.169.254), link-local IPv4 (169.254.1.1),
     IPv6 link-local (fe80::1), loopback (127.0.0.1), unspecified (0.0.0.0), and private ranges
     (10.0.0.1, 192.168.1.1, 172.16.0.1) under both production and development configurations.
   - Challenge alternative notations (decimal, octal, mapped IPv4-in-IPv6, metadata hostnames).
2. DNS Rebinding Defense:
   - Challenge _step_tls_verification direct IP socket binding in target_verifier.py.
3. Sole Owner Bootstrap Lock:
   - Verify sole owner bootstrap creates dangnhutnguyen0910@gmail.com with ID 00000000-0000-0000-0000-000000000001.
   - Verify second bootstrap attempt is rejected with HTTP 400.
   - Verify bootstrap with non-owner email is rejected with HTTP 400.
4. Immediate Session Invalidation:
   - Verify token issued before /logout is immediately rejected with HTTP 401.
   - Verify user deactivation immediately blocks authenticated calls with HTTP 403.
   - Verify offset-naive datetime bug in tokens_valid_after comparison (empirical bug discovery).
5. Scoped Developer Restrictions:
   - Verify developer cannot list ungranted assets.
   - Verify developer cannot view ungranted asset details (HTTP 403).
   - Verify developer cannot launch scan on ungranted asset (HTTP 403).
   - Verify non-owner cannot launch estate-wide batch scan (HTTP 403).
"""

from __future__ import annotations

import asyncio
import os
import socket
import ssl
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, or_, select

from backend.app.core.config import Settings, settings
from backend.app.core.database import AsyncSessionLocal
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.core.ssrf import SSRFPolicyViolation, SSRFProtector, SSRFValidationError, validate_egress_target
from backend.app.core.target_verifier import TargetVerifier
from backend.app.models.asset import Asset
from backend.app.models.scope import AssetAssessmentScope
from backend.app.models.user import User, UserAssetGrant, UserRole


# Helper to generate test tokens
def make_token(
    username: str,
    role: str,
    email: str = "",
    user_id: str = "",
    is_superuser: bool = False,
) -> str:
    claims = {"email": email, "id": user_id, "role": role}
    return create_access_token(
        subject=username,
        role=role,
        is_superuser=is_superuser,
        claims=claims,
    )


# =============================================================================
# PART 1: SSRF & Egress Protection Stress Testing
# =============================================================================

class TestSSRFAndEgressProtection:
    """Empirically stress-tests the SSRF and egress validation gatekeeper."""

    @pytest.mark.parametrize(
        "target_url",
        [
            "http://169.254.169.254",
            "http://169.254.169.254:80",
            "https://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal",
            "http://metadata.internal",
            "http://instance-data",
            "http://100.100.100.200",  # Alibaba metadata
            "http://192.0.0.192",      # Oracle Cloud metadata
        ],
    )
    def test_cloud_metadata_unconditionally_blocked_in_all_modes(self, target_url: str):
        """Cloud metadata addresses MUST be rejected under both prod and dev modes,

        even if allow_private=True is explicitly passed.
        """
        # 1. Test under default development settings
        with pytest.raises(SSRFValidationError) as exc_dev:
            validate_egress_target(target_url, allow_private=False)
        assert "metadata" in str(exc_dev.value).lower() or "blocked" in str(exc_dev.value).lower()

        # 2. Test under development with allow_private=True (MUST STILL BE BLOCKED)
        with pytest.raises(SSRFValidationError) as exc_dev_priv:
            validate_egress_target(target_url, allow_private=True)
        assert "metadata" in str(exc_dev_priv.value).lower() or "blocked" in str(exc_dev_priv.value).lower()

        # 3. Test under production simulation
        with patch.object(settings, "ENVIRONMENT", "production"):
            with pytest.raises(SSRFValidationError) as exc_prod:
                validate_egress_target(target_url, allow_private=True)
            assert "metadata" in str(exc_prod.value).lower() or "blocked" in str(exc_prod.value).lower()

    @pytest.mark.parametrize(
        "target_url",
        [
            "http://169.254.1.1",
            "http://169.254.254.254",
            "http://169.254.0.1:8080",
            "http://[fe80::1]",
            "http://[fe80::200:5aee:feaa:20a2]",
            "https://[fe80::1]:443/status",
        ],
    )
    def test_link_local_subnets_unconditionally_blocked_in_all_modes(self, target_url: str):
        """Link-local subnets (169.254.0.0/16 and fe80::/10) MUST be blocked in dev and prod,

        even when allow_private=True.
        """
        # Dev mode with allow_private=True
        with pytest.raises(SSRFValidationError) as exc_dev:
            validate_egress_target(target_url, allow_private=True)
        assert "link-local" in str(exc_dev.value).lower() or "blocked" in str(exc_dev.value).lower()

        # Production mode
        with patch.object(settings, "ENVIRONMENT", "production"):
            with pytest.raises(SSRFValidationError) as exc_prod:
                validate_egress_target(target_url, allow_private=True)
            assert "link-local" in str(exc_prod.value).lower() or "blocked" in str(exc_prod.value).lower()

    @pytest.mark.parametrize(
        "target_url",
        [
            "http://127.0.0.1",
            "http://127.0.0.1:8000",
            "http://127.0.1.1",
            "http://0.0.0.0",
            "http://0.0.0.0:80",
            "http://10.0.0.1",
            "http://10.255.255.254",
            "http://192.168.1.1",
            "http://192.168.0.254",
            "http://172.16.0.1",
            "http://172.31.255.255",
            "http://[::1]",
            "http://[::]",
        ],
    )
    def test_loopback_and_private_ranges_strictly_blocked_in_production(self, target_url: str):
        """In production, loopback, private RFC 1918, and unspecified 0.0.0.0 addresses

        MUST be rejected unconditionally even if allow_private=True is requested.
        """
        with patch.object(settings, "ENVIRONMENT", "production"):
            with pytest.raises(SSRFValidationError):
                validate_egress_target(target_url, allow_private=True)

    def test_loopback_and_private_ranges_blocked_in_dev_without_allow_private(self):
        """In development mode, loopback and private ranges MUST be blocked by default

        unless allow_private=True is explicitly specified.
        """
        for target in ["http://127.0.0.1", "http://0.0.0.0", "http://10.0.0.1", "http://192.168.1.1", "http://172.16.0.1"]:
            with pytest.raises(SSRFValidationError):
                validate_egress_target(target, allow_private=False)

    def test_private_lab_bypass_behavior_in_dev(self):
        """In development mode with allow_private=True, RFC 1918 and loopback are permitted for local labs."""
        url, ip = validate_egress_target("http://127.0.0.1:8080/test", allow_private=True)
        assert ip == "127.0.0.1"

        url, ip = validate_egress_target("http://10.0.0.1:80/api", allow_private=True)
        assert ip == "10.0.0.1"

    @pytest.mark.parametrize(
        "target_url",
        [
            "http://2130706433",          # 127.0.0.1 in decimal notation
            "http://017700000001",        # 127.0.0.1 in octal notation
            "http://2852039166",          # 169.254.169.254 in decimal notation
            "http://[::ffff:127.0.0.1]",  # IPv4-mapped IPv6 loopback
            "http://[::ffff:169.254.169.254]",  # IPv4-mapped IPv6 metadata
        ],
    )
    def test_alternative_and_obfuscated_ip_notations_blocked(self, target_url: str):
        """Decimal integer, octal, and mapped IPv6 notations MUST be normalized and blocked."""
        with patch.object(settings, "ENVIRONMENT", "production"):
            with pytest.raises(SSRFValidationError):
                validate_egress_target(target_url, allow_private=True)


# =============================================================================
# PART 2: DNS Rebinding Defense in Target Verifier
# =============================================================================

class TestDNSRebindingDefense:
    """Empirically tests that TargetVerifier binds network connections directly

    to the pre-validated IP address, eliminating TOCTOU DNS rebinding vulnerabilities.
    """

    @pytest.mark.asyncio
    async def test_tls_verification_binds_socket_to_prevalidated_ip(self):
        """Verify that _step_tls_verification connects directly to resolved_ips[0]

        rather than re-resolving hostname via DNS.
        """
        verifier = TargetVerifier(timeout=5.0)
        target_hostname = "rebinding-target.example.com"
        prevalidated_ip = "93.184.216.34"  # example.com public IP

        mock_raw_socket = MagicMock()
        mock_ssl_socket = MagicMock()
        mock_ssl_socket.getpeercert.return_value = {
            "subject": ((("commonName", target_hostname),),),
            "issuer": ((("organizationName", "DigiCert Inc"),),),
            "notAfter": "Jan 01 00:00:00 2030 GMT",
        }
        mock_ssl_socket.version.return_value = "TLSv1.3"
        mock_ssl_socket.cipher.return_value = ("TLS_AES_256_GCM_SHA384", "TLSv1.3", 256)

        with patch("socket.create_connection") as mock_create_conn, \
             patch("ssl.create_default_context") as mock_ssl_ctx:

            mock_create_conn.return_value.__enter__.return_value = mock_raw_socket
            mock_ssl_ctx.return_value.wrap_socket.return_value.__enter__.return_value = mock_ssl_socket

            result = await verifier._step_tls_verification(
                scheme="https",
                hostname=target_hostname,
                port=443,
                resolved_ips=[prevalidated_ip],
            )

            # Assert socket.create_connection was called with (prevalidated_ip, 443), NOT (target_hostname, 443)
            mock_create_conn.assert_called_once_with((prevalidated_ip, 443), timeout=5.0)

            # Assert SSL wrap_socket was called with server_hostname=target_hostname for SNI validation
            mock_ssl_ctx.return_value.wrap_socket.assert_called_once_with(
                mock_raw_socket,
                server_hostname=target_hostname,
            )

            assert result["status"] == "PASS"


# =============================================================================
# PART 3: Sole Owner Bootstrap Lock
# =============================================================================

class TestSoleOwnerBootstrapLock:
    """Empirically verifies the sole owner bootstrap mechanics and permanent locking."""

    @pytest.mark.asyncio
    async def test_first_bootstrap_creates_sole_owner_and_second_is_locked(self, client: httpx.AsyncClient):
        """Tests the full lifecycle of the one-time bootstrap mechanism:

        1. In a clean database without admins/owners/superusers, bootstrap creates sole owner.
        2. Account ID is set to 00000000-0000-0000-0000-000000000001.
        3. Email is set to dangnhutnguyen0910@gmail.com with OWNER role and is_superuser=True.
        4. Second bootstrap attempt is rejected with HTTP 400 (permanently locked).
        """
        async with AsyncSessionLocal() as session:
            # Clear any existing admin/owner/superuser users so bootstrap can be tested cleanly
            await session.execute(
                delete(User).where(
                    or_(
                        User.role.in_([UserRole.OWNER.value, UserRole.ADMIN.value, UserRole.SUPER_ADMIN.value, "OWNER", "ADMIN", "SUPER_ADMIN"]),
                        User.is_superuser == True,
                    )
                )
            )
            await session.commit()

        try:
            # 1. Attempt bootstrap with unauthorized email -> MUST FAIL (HTTP 400)
            res_unauthorized_email = await client.post(
                "/api/v1/auth/bootstrap",
                json={
                    "username": "attacker",
                    "email": "attacker@evil.corp",
                    "password": "AttackerPassword123!",
                },
            )
            assert res_unauthorized_email.status_code == 400
            assert "restricted solely" in res_unauthorized_email.json()["detail"].lower()

            # 2. First legitimate bootstrap with designated sole owner email
            res_first_bootstrap = await client.post(
                "/api/v1/auth/bootstrap",
                json={
                    "username": "dangnhutnguyen0910@gmail.com",
                    "email": "dangnhutnguyen0910@gmail.com",
                    "password": "SoleOwnerMasterPassword123!",
                },
            )
            assert res_first_bootstrap.status_code == 201
            data = res_first_bootstrap.json()
            assert data["email"] == "dangnhutnguyen0910@gmail.com"

            # Verify DB state of created owner
            async with AsyncSessionLocal() as session:
                owner = (
                    await session.execute(
                        select(User).where(User.email == "dangnhutnguyen0910@gmail.com")
                    )
                ).scalars().first()

                assert owner is not None
                assert str(owner.id) == "00000000-0000-0000-0000-000000000001"
                assert owner.role == UserRole.OWNER.value
                assert owner.is_superuser is True
                assert owner.is_active is True

            # 3. Second bootstrap attempt -> MUST FAIL WITH HTTP 400
            res_second_bootstrap = await client.post(
                "/api/v1/auth/bootstrap",
                json={
                    "username": "another_admin",
                    "email": "dangnhutnguyen0910@gmail.com",
                    "password": "AnotherPassword123!",
                },
            )
            assert res_second_bootstrap.status_code == 400
            assert "already" in res_second_bootstrap.json()["detail"].lower()
            assert "locked" in res_second_bootstrap.json()["detail"].lower()
        finally:
            # Cleanup bootstrapped owner to allow other test suites clean isolation
            async with AsyncSessionLocal() as session:
                await session.execute(
                    delete(User).where(User.id == uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID))
                )
                await session.commit()


# =============================================================================
# PART 4: Immediate Session Invalidation & Naive Datetime Bug Discovery
# =============================================================================

class TestImmediateSessionInvalidation:
    """Empirically tests that session invalidation (via /logout or deactivation)

    immediately rejects existing JWT bearer tokens, and documents timezone comparison flaw.
    """

    @pytest.mark.asyncio
    async def test_token_rejected_immediately_after_logout(self, client: httpx.AsyncClient):
        """Tokens issued prior to calling /logout must be rejected immediately on subsequent calls."""
        username = f"user_{uuid.uuid4().hex[:8]}"
        user_id = uuid.uuid4()
        async with AsyncSessionLocal() as session:
            test_user = User(
                id=user_id,
                username=username,
                email=f"{username}@example.com",
                hashed_password=get_password_hash("Pass123456!"),
                role=UserRole.OPERATOR.value,
                is_active=True,
                is_superuser=False,
            )
            session.add(test_user)
            await session.commit()

        token = make_token(username, UserRole.OPERATOR.value, email=f"{username}@example.com", user_id=str(user_id))
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Verify token works prior to logout
        res_before = await client.get("/api/v1/auth/me", headers=headers)
        assert res_before.status_code == 200

        # 2. Perform logout
        res_logout = await client.post("/api/v1/auth/logout", headers=headers)
        assert res_logout.status_code == 200

        # 3. Immediate reuse of token MUST fail with HTTP 401
        res_after = await client.get("/api/v1/auth/me", headers=headers)
        assert res_after.status_code == 401

    @pytest.mark.asyncio
    async def test_token_rejected_immediately_after_deactivation(self, client: httpx.AsyncClient):
        """When an account is deactivated, active tokens must be rejected immediately with HTTP 403."""
        username = f"user_{uuid.uuid4().hex[:8]}"
        user_id = uuid.uuid4()
        async with AsyncSessionLocal() as session:
            test_user = User(
                id=user_id,
                username=username,
                email=f"{username}@example.com",
                hashed_password=get_password_hash("Pass123456!"),
                role=UserRole.DEVELOPER.value,
                is_active=True,
                is_superuser=False,
            )
            session.add(test_user)
            await session.commit()

        token = make_token(username, UserRole.DEVELOPER.value, email=f"{username}@example.com", user_id=str(user_id))
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Active user succeeds
        res_before = await client.get("/api/v1/auth/me", headers=headers)
        assert res_before.status_code == 200

        # 2. Deactivate user in DB
        async with AsyncSessionLocal() as session:
            u = (await session.execute(select(User).where(User.id == user_id))).scalars().first()
            u.is_active = False
            await session.commit()

        # 3. Immediate call MUST be rejected with HTTP 403 (inactive user account)
        res_deactivated = await client.get("/api/v1/auth/me", headers=headers)
        assert res_deactivated.status_code == 403
        assert "inactive" in res_deactivated.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_bug_offset_naive_datetime_comparison_in_tokens_valid_after(self, client: httpx.AsyncClient):
        """EMPIRICAL BUG CONFIRMATION:

        When tokens_valid_after is loaded from SQLite, it returns a timezone-naive datetime (tzinfo=None).
        Comparing it to offset-aware token_issued_at (tzinfo=UTC) in backend/app/api/deps.py:131 causes:
        TypeError: can't compare offset-naive and offset-aware datetimes.
        """
        username = f"user_{uuid.uuid4().hex[:8]}"
        user_id = uuid.uuid4()
        async with AsyncSessionLocal() as session:
            test_user = User(
                id=user_id,
                username=username,
                email=f"{username}@example.com",
                hashed_password=get_password_hash("Pass123456!"),
                role=UserRole.OPERATOR.value,
                is_active=True,
                is_superuser=False,
            )
            session.add(test_user)
            await session.commit()

        token = make_token(username, UserRole.OPERATOR.value, email=f"{username}@example.com", user_id=str(user_id))
        headers = {"Authorization": f"Bearer {token}"}

        # Set tokens_valid_after in database and commit to SQLite
        async with AsyncSessionLocal() as session:
            u = (await session.execute(select(User).where(User.id == user_id))).scalars().first()
            u.tokens_valid_after = datetime.now(timezone.utc)
            await session.commit()

        # Calling get_current_active_user now gracefully handles offset-naive DB datetime
        # and rejects the expired token with HTTP 401 instead of crashing with TypeError
        res = await client.get("/api/v1/auth/me", headers=headers)
        assert res.status_code == 401
        assert "Session expired/revoked" in res.json()["detail"]


# =============================================================================
# PART 5: Scoped Developer Restrictions & Estate-Wide Scan Prevention
# =============================================================================

class TestScopedDeveloperRestrictions:
    """Empirically tests that scoped developers can only access granted assets,

    and non-owners cannot launch estate-wide scans.
    """

    @pytest.mark.asyncio
    async def test_developer_cannot_access_or_scan_ungranted_assets(self, client: httpx.AsyncClient):
        """Developer must be strictly confined to explicitly granted assets for viewing,

        and cannot launch scans on ungranted assets (HTTP 403).
        """
        dev_username = f"dev_{uuid.uuid4().hex[:8]}"
        dev_id = uuid.uuid4()
        asset_granted_id = uuid.uuid4()
        asset_forbidden_id = uuid.uuid4()

        async with AsyncSessionLocal() as session:
            # Create developer user in database
            dev_user = User(
                id=dev_id,
                username=dev_username,
                email=f"{dev_username}@example.com",
                hashed_password=get_password_hash("DevPass123!"),
                role=UserRole.DEVELOPER.value,
                is_active=True,
                is_superuser=False,
            )
            session.add(dev_user)

            # Create Asset 1 (Granted)
            asset_granted = Asset(
                id=asset_granted_id,
                name="Granted Asset",
                target_locator="https://granted.example.com",
                empire_module="API_SERVICES",
                environment="PRODUCTION",
                verification_status="VERIFIED",
                criticality="HIGH",
                exposure="INTERNET",
            )
            session.add(asset_granted)

            # Create Asset 2 (Forbidden)
            asset_forbidden = Asset(
                id=asset_forbidden_id,
                name="Forbidden Asset",
                target_locator="https://forbidden.example.com",
                empire_module="SERVER_INFRASTRUCTURE",
                environment="PRODUCTION",
                verification_status="VERIFIED",
                criticality="CRITICAL",
                exposure="INTERNAL",
            )
            session.add(asset_forbidden)

            # Grant developer access ONLY to Asset 1
            grant = UserAssetGrant(
                id=uuid.uuid4(),
                user_id=dev_id,
                asset_id=asset_granted_id,
                permissions="READ,SCAN",
                granted_by="owner",
            )
            session.add(grant)

            await session.commit()

        dev_token = make_token(dev_username, UserRole.DEVELOPER.value, user_id=str(dev_id))
        dev_headers = {"Authorization": f"Bearer {dev_token}"}

        # 1. Developer lists assets -> MUST only see asset_granted
        res_list = await client.get("/api/v1/assets", headers=dev_headers)
        assert res_list.status_code == 200
        items = res_list.json()["items"]
        returned_ids = [item["id"] for item in items]
        assert str(asset_granted_id) in returned_ids
        assert str(asset_forbidden_id) not in returned_ids

        # 2. Developer requests details of ungranted asset -> MUST return HTTP 403
        res_forbidden_get = await client.get(f"/api/v1/assets/{asset_forbidden_id}", headers=dev_headers)
        assert res_forbidden_get.status_code == 403
        assert "access denied" in res_forbidden_get.json()["detail"].lower()

        # 3. Developer requests details of granted asset -> MUST return HTTP 200
        res_granted_get = await client.get(f"/api/v1/assets/{asset_granted_id}", headers=dev_headers)
        assert res_granted_get.status_code == 200

        # 4. Developer attempts to scan ungranted asset -> MUST return HTTP 403 Forbidden
        res_scan_forbidden = await client.post(
            "/api/v1/scans",
            headers=dev_headers,
            json={"asset_id": str(asset_forbidden_id), "engine": "empire", "profile": "BASELINE"},
        )
        assert res_scan_forbidden.status_code == 403

    @pytest.mark.asyncio
    async def test_non_owner_cannot_launch_estate_wide_scan(self, client: httpx.AsyncClient):
        """Only the sole owner can launch an estate-wide scan with targets='ALL'.

        Admins, operators, and developers must be rejected with HTTP 403.
        """
        # Seed test users in DB
        async with AsyncSessionLocal() as session:
            for role_name in [UserRole.DEVELOPER.value, UserRole.OPERATOR.value, UserRole.ADMIN.value]:
                u_stmt = select(User).where(User.username == f"test_{role_name.lower()}")
                if not (await session.execute(u_stmt)).scalars().first():
                    session.add(
                        User(
                            id=uuid.uuid4(),
                            username=f"test_{role_name.lower()}",
                            email=f"test_{role_name.lower()}@example.com",
                            hashed_password=get_password_hash("Pass123!"),
                            role=role_name,
                            is_active=True,
                            is_superuser=False,
                        )
                    )
            await session.commit()

        # 1. Developer attempt -> HTTP 403
        dev_token = make_token("test_developer", UserRole.DEVELOPER.value)
        res_dev = await client.post(
            "/api/v1/scans/batch",
            headers={"Authorization": f"Bearer {dev_token}"},
            json={"targets": "ALL", "profile": "BASELINE"},
        )
        assert res_dev.status_code == 403

        # 2. Operator attempt -> HTTP 403 with owner-restricted detail
        op_token = make_token("test_operator", UserRole.OPERATOR.value)
        res_op = await client.post(
            "/api/v1/scans/batch",
            headers={"Authorization": f"Bearer {op_token}"},
            json={"targets": "ALL", "profile": "BASELINE"},
        )
        assert res_op.status_code == 403
        assert "restricted solely to the system owner" in res_op.json()["detail"].lower()

        # 3. Non-owner Admin attempt -> HTTP 403 with owner-restricted detail
        admin_token = make_token("test_admin", UserRole.ADMIN.value)
        res_admin = await client.post(
            "/api/v1/scans/batch",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"targets": "ALL", "profile": "BASELINE"},
        )
        assert res_admin.status_code == 403
        assert "restricted solely to the system owner" in res_admin.json()["detail"].lower()

        # 4. Sole Owner attempt -> Authorized
        created_owner = False
        async with AsyncSessionLocal() as session:
            owner_stmt = select(User).where(User.email == settings.SOLE_OWNER_EMAIL)
            owner = (await session.execute(owner_stmt)).scalars().first()
            if not owner:
                owner = User(
                    id=uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID),
                    username=settings.SOLE_OWNER_EMAIL,
                    email=settings.SOLE_OWNER_EMAIL,
                    hashed_password=get_password_hash("OwnerPass123!"),
                    role=UserRole.OWNER.value,
                    is_active=True,
                    is_superuser=True,
                )
                session.add(owner)
                await session.commit()
                created_owner = True

        try:
            owner_token = make_token(
                owner.username,
                UserRole.OWNER.value,
                email=settings.SOLE_OWNER_EMAIL,
                user_id=str(owner.id),
                is_superuser=True,
            )
            res_owner = await client.post(
                "/api/v1/scans/batch",
                headers={"Authorization": f"Bearer {owner_token}"},
                json={"targets": "ALL", "profile": "BASELINE"},
            )
            assert res_owner.status_code in (201, 200)
        finally:
            if created_owner:
                async with AsyncSessionLocal() as session:
                    u = await session.get(User, uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID))
                    if u:
                        await session.delete(u)
                        await session.commit()
