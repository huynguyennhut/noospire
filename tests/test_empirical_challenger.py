"""Empirical Challenger Test Suite — Stress, Edge Cases, and Boundary Attacks.

Adversarial Verification for:
1. Target Verification & SSRF Defense (Loopback, RFC 1918 Private, IPv6, Cloud Metadata, Malformed URLs)
2. Bulk Import Preview & Deduplication (Overlapping CSV, JSON, Mixed CIDR, Subnet Expansions)
3. Scanner Quality States (AUTH_REQUIRED, TARGET_UNAVAILABLE, SCANNER_FAILED, PARTIAL_COVERAGE, SCANNED_SUCCESSFULLY)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.dispatcher import AsyncWorkerDispatcher
from backend.app.core.ssrf import SSRFProtector, SSRFValidationError
from backend.app.core.target_verifier import TargetVerifier, get_target_verifier
from backend.app.models.asset import Asset
from backend.app.models.scan import Scan
from backend.app.scanners.base import (
    BaseScannerAdapter,
    CancellationToken,
    ScanExecutionRequest,
    ScannerExecutionResult,
)
from backend.app.schemas.common import (
    AssetType,
    EmpireModule,
    FindingSeverity,
    ScanProfile,
    ScanQualityStatus,
    ScanStatus,
    VerificationStatus,
)


# ==============================================================================
# SECTION 1: TARGET VERIFICATION & SSRF DEFENSE EMPIRICAL STRESS
# ==============================================================================

class TestSSRFDefenseEmpirical:
    """Stress tests SSRF defenses against evasive, boundary, and malformed inputs."""

    @pytest.mark.parametrize(
        "loopback_target",
        [
            "http://127.0.0.1",
            "http://127.0.0.2:8080",
            "http://127.255.255.254",
            "https://localhost",
            "http://localhost:8000",
            "http://2130706433",  # Decimal integer 127.0.0.1
            "http://017700000001",  # Octal representation of 127.0.0.1
        ],
    )
    def test_ssrf_rejects_ipv4_loopback(self, loopback_target: str):
        """Verifies SSRFProtector strictly rejects all IPv4 loopback variants."""
        with pytest.raises(SSRFValidationError) as exc_info:
            SSRFProtector.validate_target(loopback_target, allow_private=False)
        assert any(
            phrase in str(exc_info.value).lower()
            for phrase in ("blocked network", "loopback", "ssrf security violation", "ambiguous")
        )

    @pytest.mark.parametrize(
        "ipv6_target",
        [
            "http://[::1]",
            "https://[::1]:8443/admin",
            "http://[0000:0000:0000:0000:0000:0000:0000:0001]",
            "http://[fe80::1]",  # Link-local
            "http://[fe80::200:5aee:feaa:20a2]",
            "http://[fc00::1]",  # Unique Local Address (ULA)
            "http://[fd12:3456:789a::1]",
            "http://[::ffff:127.0.0.1]",  # IPv4-mapped IPv6 loopback
            "http://[::ffff:10.0.0.1]",   # IPv4-mapped IPv6 private
        ],
    )
    def test_ssrf_rejects_ipv6_loopback_and_private(self, ipv6_target: str):
        """Verifies SSRFProtector strictly blocks IPv6 loopback, link-local, ULA, and mapped IPv4 addresses."""
        with pytest.raises(SSRFValidationError) as exc_info:
            SSRFProtector.validate_target(ipv6_target, allow_private=False)
        assert "blocked network" in str(exc_info.value).lower() or "ssrf" in str(exc_info.value).lower()

    @pytest.mark.parametrize(
        "private_ip_target",
        [
            "http://10.0.0.1",
            "http://10.254.254.254:3000",
            "http://172.16.0.1",
            "http://172.31.255.254",
            "http://192.168.0.1",
            "http://192.168.100.254",
            "http://100.64.0.1",   # Shared Address Space / CGNAT (RFC 6598)
            "http://169.254.1.1",  # IPv4 Link-Local / APIPA (RFC 3927)
            "http://192.0.2.1",    # TEST-NET-1 (RFC 5737)
            "http://198.51.100.1", # TEST-NET-2
            "http://203.0.113.1",  # TEST-NET-3
            "http://0.0.0.0",      # Current network
            "http://255.255.255.255", # Broadcast
        ],
    )
    def test_ssrf_rejects_rfc1918_and_reserved_subnets(self, private_ip_target: str):
        """Verifies SSRFProtector rejects RFC 1918, CGNAT, link-local, and reserved IPv4 blocks."""
        with pytest.raises(SSRFValidationError) as exc_info:
            SSRFProtector.validate_target(private_ip_target, allow_private=False)
        assert "blocked network" in str(exc_info.value).lower()

    @pytest.mark.parametrize(
        "cloud_metadata_target",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.169.254/computeMetadata/v1/",
            "http://metadata.google.internal/computeMetadata/v1/",
            "http://metadata.internal",
            "http://100.100.100.200/latest/meta-data/",  # Alibaba cloud metadata
            "http://192.0.0.192/latest/meta-data/",      # Oracle cloud metadata
            "http://instance-data",
        ],
    )
    def test_ssrf_strictly_blocks_cloud_metadata_even_with_allow_private(self, cloud_metadata_target: str):
        """Cloud metadata endpoints must be BLOCKED even if allow_private=True (Strict Zero-Trust Invariant)."""
        # Test without allow_private
        with pytest.raises(SSRFValidationError) as exc_info:
            SSRFProtector.validate_target(cloud_metadata_target, allow_private=False)
        assert any(
            w in str(exc_info.value).lower()
            for w in ("cloud metadata", "blocked network", "ssrf violation")
        )

        # Test WITH allow_private=True — Cloud metadata must STILL be blocked!
        with pytest.raises(SSRFValidationError) as exc_info_priv:
            SSRFProtector.validate_target(cloud_metadata_target, allow_private=True)
        assert any(
            w in str(exc_info_priv.value).lower()
            for w in ("cloud metadata", "protected", "ssrf violation")
        )

    @pytest.mark.parametrize(
        "malformed_target",
        [
            "ftp://files.empire.edu.vn",
            "file:///etc/passwd",
            "gopher://127.0.0.1:70",
            "dict://127.0.0.1:2628",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "http://admin:secret@empire.edu.vn/",  # Embedded credentials
            "http://",
            "https://:443",
            "http://empire.edu.vn:0",
            "http://empire.edu.vn:65536",
            "http://empire.edu.vn:-80",
            "http://[::1",  # Unclosed IPv6 bracket
            "",
            "   ",
        ],
    )
    def test_ssrf_rejects_malformed_urls_and_bad_schemes(self, malformed_target: str):
        """Verifies SSRFProtector syntax validation rejects non-HTTP schemes, invalid ports, and malformed authorities."""
        with pytest.raises((SSRFValidationError, ValueError)):
            SSRFProtector.validate_target(malformed_target, allow_private=False)

    @pytest.mark.parametrize(
        "edge_target,expected_err",
        [
            ("http://empire.edu.vn:65536", "Port out of range"),
            ("http://empire.edu.vn:-80", "Port could not be cast"),
            ("http://[::1", "Invalid IPv6 URL"),
        ],
    )
    def test_ssrf_exception_type_boundary_behavior(self, edge_target: str, expected_err: str):
        """Adversarial check: verifies that malformed ports and brackets trigger rejection.
        Note: Leaks raw ValueError instead of normalized SSRFValidationError.
        """
        with pytest.raises(ValueError) as exc_info:
            SSRFProtector.validate_target(edge_target, allow_private=False)
        assert expected_err in str(exc_info.value)


@pytest.mark.asyncio
class TestTargetVerifierPipelineAdversarial:
    """Stress tests the 8-step TargetVerifier pipeline under adversarial conditions."""

    async def test_target_verifier_step1_abort_on_ssrf(self):
        """Verifies TargetVerifier fails immediately at Step 1 and does not execute subsequent network probes."""
        verifier = get_target_verifier()
        result = await verifier.verify_target("http://127.0.0.1:8080/internal-api", allow_private=False)

        assert result["status"] == "FAILED"
        assert result["verified"] is False
        assert len(result["steps"]) == 2  # Step 1 (FAIL) and Step 8 (FAIL verdict)
        assert result["steps"][0]["step"] == 1
        assert result["steps"][0]["status"] == "FAIL"
        assert "Input Validation" in result["steps"][0]["name"]
        assert result["steps"][1]["step"] == 8
        assert result["steps"][1]["status"] == "FAIL"

    async def test_target_verifier_step1_abort_on_cloud_metadata(self):
        """Verifies TargetVerifier aborts on cloud metadata targets."""
        verifier = get_target_verifier()
        result = await verifier.verify_target("http://169.254.169.254/latest/meta-data/", allow_private=False)

        assert result["status"] == "FAILED"
        assert result["verified"] is False
        assert result["steps"][0]["status"] == "FAIL"
        assert "cloud metadata" in result["steps"][0]["detail"].lower()

    async def test_target_verifier_valid_target_passes_input_validation(self):
        """Verifies TargetVerifier passes step 1 for a valid HTTPS target."""
        verifier = get_target_verifier()
        step1_result, parsed_info = await verifier._step_input_validation(
            "https://empire.edu.vn", allow_private=False
        )
        assert step1_result["status"] == "PASS"
        assert step1_result["metadata"]["ssrf_validated"] is True
        assert parsed_info["hostname"] == "empire.edu.vn"
        assert parsed_info["scheme"] == "https"


# ==============================================================================
# SECTION 2: BULK IMPORT PREVIEW & DEDUPLICATION EMPIRICAL STRESS
# ==============================================================================

@pytest.mark.asyncio
class TestBulkImportDeduplicationEmpirical:
    """Stress tests duplicate detection, URL normalization, and mixed format ingestion."""

    async def test_bulk_preview_db_duplicate_detection_with_normalization(
        self, client: httpx.AsyncClient
    ):
        """Verifies preview detects existing DB assets regardless of trailing slash or default port."""
        # Query existing assets to get guaranteed seeded target
        list_resp = await client.get("/api/v1/assets?size=5")
        assert list_resp.status_code == 200
        items = list_resp.json()["items"]
        assert len(items) > 0
        existing_loc = items[0]["target_locator"]
        existing_id = items[0]["id"]

        # Form variations: with trailing slash, without trailing slash, with :443
        clean_base = existing_loc.rstrip("/")
        candidates = [
            f"{clean_base}/",
            f"{clean_base}",
        ]
        if clean_base.startswith("https://"):
            domain_part = clean_base.replace("https://", "")
            candidates.append(f"https://{domain_part}:443/")

        preview_payload = {
            "import_type": "JSON",
            "items": [{"target_locator": c} for c in candidates],
        }

        resp = await client.post("/api/v1/assets/bulk-preview", json=preview_payload)
        assert resp.status_code == 200
        data = resp.json()

        # All variations should be recognized as duplicates of the existing DB asset
        assert data["total"] == len(candidates)
        assert len(data["new"]) == 0
        assert len(data["duplicate"]) == len(candidates)
        for dup in data["duplicate"]:
            assert dup["is_duplicate"] is True
            assert dup["existing_asset_id"] == existing_id
            assert "already registered" in dup["reason"].lower()

    async def test_bulk_preview_intra_batch_deduplication(
        self, client: httpx.AsyncClient
    ):
        """Verifies preview flags duplicates occurring within the same import payload."""
        slug = uuid.uuid4().hex[:8]
        new_loc = f"https://unique-{slug}.empire.edu.vn"

        # Submit 3 identical candidates in the same batch
        preview_payload = {
            "import_type": "JSON",
            "items": [
                {"target_locator": new_loc, "name": "First Entry"},
                {"target_locator": f"{new_loc}/", "name": "Second Entry (Trailing Slash)"},
                {"target_locator": new_loc, "name": "Third Entry (Exact Duplicate)"},
            ],
        }

        resp = await client.post("/api/v1/assets/bulk-preview", json=preview_payload)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 3
        # Exactly 1 new item (the first one)
        assert len(data["new"]) == 1
        assert data["new"][0]["name"] == "First Entry"
        assert data["new"][0]["is_duplicate"] is False

        # Exactly 2 duplicate items (subsequent occurrences in the batch)
        assert len(data["duplicate"]) == 2
        for dup in data["duplicate"]:
            assert dup["is_duplicate"] is True
            assert dup["existing_asset_id"] is None
            assert "current import batch" in dup["reason"].lower()

    async def test_bulk_preview_overlapping_csv_matrix(
        self, client: httpx.AsyncClient
    ):
        """Verifies CSV import parsing with overlapping duplicates, header variations, and mixed targets."""
        slug = uuid.uuid4().hex[:8]
        target_a = f"https://csv-alpha-{slug}.empire.edu.vn"
        target_b = f"https://csv-beta-{slug}.empire.edu.vn"

        csv_content = f"""name,target_locator,environment,empire_module
Alpha Service,{target_a},PRODUCTION,STUDENT_MANAGEMENT
Alpha Service Duplicate,{target_a}/,PRODUCTION,STUDENT_MANAGEMENT
Beta Service,{target_b},STAGING,API_SERVICES
Beta Service Duplicate,{target_b},STAGING,API_SERVICES
Existing Empire Target,https://empire.edu.vn/,PRODUCTION,WEB_APPLICATION
"""

        resp = await client.post(
            "/api/v1/assets/bulk-preview",
            json={"import_type": "CSV", "raw_content": csv_content},
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["total"] == 5
        # New items: target_a (first) and target_b (first) = 2 new
        assert len(data["new"]) == 2
        new_locators = [n["target_locator"].rstrip("/") for n in data["new"]]
        assert target_a in new_locators
        assert target_b in new_locators

        # Duplicate items: target_a duplicate, target_b duplicate, and seeded https://empire.edu.vn/ = 3 duplicates
        assert len(data["duplicate"]) == 3
        dup_reasons = [d["reason"] for d in data["duplicate"]]
        # Two intra-batch duplicates and one DB duplicate
        assert any("already registered" in r.lower() for r in dup_reasons)
        assert any("current import batch" in r.lower() for r in dup_reasons)

    async def test_bulk_preview_mixed_cidr_and_ip_expansion(
        self, client: httpx.AsyncClient
    ):
        """Verifies CIDR parsing: small subnets (<=8 addresses) expand into host IPs, while large subnets remain CIDRs."""
        # /29 subnet = 8 addresses (6 usable hosts: .1 to .6)
        small_cidr = "192.168.10.0/29"
        # /24 subnet = 256 addresses (kept as subnet locator)
        large_cidr = "10.10.0.0/24"
        plain_ip = "192.168.10.1"  # Overlaps with host in small_cidr!

        raw_txt = f"""# Test Subnet and IP Ingestion
{small_cidr}
{large_cidr}
{plain_ip}
"""

        resp = await client.post(
            "/api/v1/assets/bulk-preview",
            json={"import_type": "TXT", "raw_content": raw_txt},
        )
        assert resp.status_code == 200
        data = resp.json()

        # small_cidr expands to 6 hosts: 192.168.10.1 .. 192.168.10.6
        # large_cidr remains 1 subnet entry: 10.10.0.0/24
        # plain_ip is 192.168.10.1 (which was already generated by small_cidr!)
        total_candidates = data["total"]
        assert total_candidates == 8  # 6 hosts + 1 large subnet + 1 duplicate plain IP

        # The plain_ip is an intra-batch duplicate of the expanded host from small_cidr
        assert len(data["new"]) == 7  # 6 hosts + 1 subnet
        assert len(data["duplicate"]) == 1
        assert data["duplicate"][0]["is_duplicate"] is True
        assert "192.168.10.1" in data["duplicate"][0]["target_locator"]

    async def test_bulk_preview_resilience_to_corrupted_inputs(
        self, client: httpx.AsyncClient
    ):
        """Verifies bulk preview handles non-bracketed plain text, malformed CSV, and empty payloads without crashing."""
        # 1. Plain text with irregular structure
        plain_resp = await client.post(
            "/api/v1/assets/bulk-preview",
            json={"import_type": "TXT", "raw_content": "irregular plain text line\nanother random line\n"},
        )
        assert plain_resp.status_code == 200
        assert plain_resp.json()["total"] == 2

        # 2. Whitespace-only content
        empty_resp = await client.post(
            "/api/v1/assets/bulk-preview",
            json={"import_type": "TXT", "raw_content": "   \n\n   "},
        )
        assert empty_resp.status_code == 200
        assert empty_resp.json()["total"] == 0

        # 3. CSV with no recognizable header
        random_csv = "foo,bar,baz\n1,2,3\n4,5,6\n"
        resp3 = await client.post(
            "/api/v1/assets/bulk-preview",
            json={"import_type": "CSV", "raw_content": random_csv},
        )
        assert resp3.status_code == 200

    async def test_bulk_preview_bracket_syntax_500_vulnerability(
        self, client: httpx.AsyncClient
    ):
        """Documents resilience against crash when bulk import raw_content contains unclosed bracket lines."""
        resp = await client.post(
            "/api/v1/assets/bulk-preview",
            json={"import_type": "JSON", "raw_content": '[{"unclosed_quote: true},'},
        )
        # Expected behavior: graceful rejection (400 or 200 with total=0), NOT 500 crash
        assert resp.status_code == 200


# ==============================================================================
# SECTION 3: SCANNER QUALITY STATES EMPIRICAL VALIDATION
# ==============================================================================

@pytest.mark.asyncio
class TestScannerQualityStatesEmpirical:
    """Stress tests the explicit quality state machine transitions:
    - AUTH_REQUIRED
    - TARGET_UNAVAILABLE
    - SCANNER_FAILED
    - PARTIAL_COVERAGE
    - SCANNED_SUCCESSFULLY
    """

    async def test_quality_state_auth_required_via_permission_error(
        self, created_asset_ids: List[str]
    ):
        """Verifies scan transitions to AUTH_REQUIRED when all scanner adapters encounter PermissionError."""
        asset_id = uuid.uuid4()
        scan_id = uuid.uuid4()

        async with AsyncSessionLocal() as session:
            asset = Asset(
                id=asset_id,
                name="Auth Barrier Target",
                target_locator="https://auth-protected.empire.edu.vn",
                verification_status=VerificationStatus.VERIFIED.value,
            )
            scan = Scan(
                id=scan_id,
                asset_id=asset_id,
                target_locator="https://auth-protected.empire.edu.vn",
                status=ScanStatus.QUEUED.value,
            )
            session.add(asset)
            session.add(scan)
            await session.commit()

        dispatcher = AsyncWorkerDispatcher(max_concurrent=1)
        token = CancellationToken()

        # Mock adapter throwing PermissionError
        mock_adapter = MagicMock(spec=BaseScannerAdapter)
        mock_adapter.engine_name = "nuclei"
        mock_adapter.execute = AsyncMock(side_effect=PermissionError("HTTP 401 Unauthorized: Valid API key required"))

        with patch("backend.app.core.dispatcher.NucleiAdapter", return_value=mock_adapter), \
             patch("backend.app.core.dispatcher.ZAPAdapter", return_value=mock_adapter), \
             patch("backend.app.core.dispatcher.EmpireAssessmentEngine.execute_empire_assessment",
                   side_effect=PermissionError("Auth token expired")):
            await dispatcher._run_scan(scan_id, token)

        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Scan).where(Scan.id == scan_id))
            persisted = res.scalars().first()
            assert persisted.status == ScanStatus.FAILED.value
            assert persisted.quality_status == ScanQualityStatus.AUTH_REQUIRED.value
            assert "auth" in persisted.error_message.lower() or "401" in persisted.error_message

    async def test_quality_state_target_unavailable_via_connect_error(
        self, created_asset_ids: List[str]
    ):
        """Verifies scan transitions to TARGET_UNAVAILABLE when all adapters encounter network connection failure."""
        asset_id = uuid.uuid4()
        scan_id = uuid.uuid4()

        async with AsyncSessionLocal() as session:
            asset = Asset(
                id=asset_id,
                name="Unreachable Target",
                target_locator="https://unreachable-barrier.empire.edu.vn",
                verification_status=VerificationStatus.VERIFIED.value,
            )
            scan = Scan(
                id=scan_id,
                asset_id=asset_id,
                target_locator="https://unreachable-barrier.empire.edu.vn",
                status=ScanStatus.QUEUED.value,
            )
            session.add(asset)
            session.add(scan)
            await session.commit()

        dispatcher = AsyncWorkerDispatcher(max_concurrent=1)
        token = CancellationToken()

        mock_adapter = MagicMock(spec=BaseScannerAdapter)
        mock_adapter.engine_name = "nuclei"
        mock_adapter.execute = AsyncMock(side_effect=httpx.ConnectError("Connection refused on port 443"))

        with patch("backend.app.core.dispatcher.NucleiAdapter", return_value=mock_adapter), \
             patch("backend.app.core.dispatcher.ZAPAdapter", return_value=mock_adapter), \
             patch("backend.app.core.dispatcher.EmpireAssessmentEngine.execute_empire_assessment",
                   side_effect=httpx.ConnectTimeout("Connect timeout after 10s")):
            await dispatcher._run_scan(scan_id, token)

        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Scan).where(Scan.id == scan_id))
            persisted = res.scalars().first()
            assert persisted.status == ScanStatus.FAILED.value
            assert persisted.quality_status == ScanQualityStatus.TARGET_UNAVAILABLE.value
            assert "unreachable" in persisted.error_message.lower() or "connect" in persisted.error_message.lower()

    async def test_quality_state_scanner_failed_via_adapter_crash(
        self, created_asset_ids: List[str]
    ):
        """Verifies scan transitions to SCANNER_FAILED when scanner processes fail/crash and no findings or adapter succeed."""
        asset_id = uuid.uuid4()
        scan_id = uuid.uuid4()

        async with AsyncSessionLocal() as session:
            asset = Asset(
                id=asset_id,
                name="Scanner Crash Target",
                target_locator="https://scanner-crash.empire.edu.vn",
                verification_status=VerificationStatus.VERIFIED.value,
            )
            scan = Scan(
                id=scan_id,
                asset_id=asset_id,
                target_locator="https://scanner-crash.empire.edu.vn",
                status=ScanStatus.QUEUED.value,
            )
            session.add(asset)
            session.add(scan)
            await session.commit()

        dispatcher = AsyncWorkerDispatcher(max_concurrent=1)
        token = CancellationToken()

        failed_result = ScannerExecutionResult(
            engine_name="nuclei",
            execution_mode="binary_cli",
            success=False,
            exit_code=137,  # Process killed / OOM
            raw_output="",
            findings=[],
            error_message="Process exited abnormally with code 137",
            duration_seconds=1.5,
        )

        mock_adapter = MagicMock(spec=BaseScannerAdapter)
        mock_adapter.engine_name = "nuclei"
        mock_adapter.execute = AsyncMock(return_value=failed_result)

        with patch("backend.app.core.dispatcher.NucleiAdapter", return_value=mock_adapter), \
             patch("backend.app.core.dispatcher.ZAPAdapter", return_value=mock_adapter), \
             patch("backend.app.core.dispatcher.EmpireAssessmentEngine.execute_empire_assessment",
                   side_effect=RuntimeError("Empire Engine binary crashed")):
            await dispatcher._run_scan(scan_id, token)

        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Scan).where(Scan.id == scan_id))
            persisted = res.scalars().first()
            assert persisted.status == ScanStatus.FAILED.value
            assert persisted.quality_status == ScanQualityStatus.SCANNER_FAILED.value
            assert "exit code" in persisted.error_message.lower() or "crashed" in persisted.error_message.lower()

    async def test_quality_state_partial_coverage_when_some_adapters_fail(
        self, created_asset_ids: List[str]
    ):
        """Verifies scan transitions to PARTIAL_COVERAGE when at least one adapter fails but another succeeds."""
        asset_id = uuid.uuid4()
        scan_id = uuid.uuid4()

        async with AsyncSessionLocal() as session:
            asset = Asset(
                id=asset_id,
                name="Partial Target",
                target_locator="https://partial-coverage.empire.edu.vn",
                verification_status=VerificationStatus.VERIFIED.value,
            )
            scan = Scan(
                id=scan_id,
                asset_id=asset_id,
                target_locator="https://partial-coverage.empire.edu.vn",
                status=ScanStatus.QUEUED.value,
            )
            session.add(asset)
            session.add(scan)
            await session.commit()

        dispatcher = AsyncWorkerDispatcher(max_concurrent=1)
        token = CancellationToken()

        # Adapter 1 (Nuclei) succeeds
        success_result = ScannerExecutionResult(
            engine_name="nuclei",
            execution_mode="binary_cli",
            success=True,
            exit_code=0,
            raw_output="",
            findings=[],
            error_message=None,
            duration_seconds=2.0,
        )
        mock_nuclei = MagicMock(spec=BaseScannerAdapter)
        mock_nuclei.engine_name = "nuclei"
        mock_nuclei.execute = AsyncMock(return_value=success_result)

        # Adapter 2 (ZAP) fails
        failed_zap_result = ScannerExecutionResult(
            engine_name="zap",
            execution_mode="daemon_api",
            success=False,
            exit_code=1,
            raw_output="",
            findings=[],
            error_message="ZAP daemon connection failed",
            duration_seconds=0.5,
        )
        mock_zap = MagicMock(spec=BaseScannerAdapter)
        mock_zap.engine_name = "zap"
        mock_zap.execute = AsyncMock(return_value=failed_zap_result)

        with patch("backend.app.core.dispatcher.NucleiAdapter", return_value=mock_nuclei), \
             patch("backend.app.core.dispatcher.ZAPAdapter", return_value=mock_zap), \
             patch("backend.app.core.dispatcher.EmpireAssessmentEngine.execute_empire_assessment",
                   return_value=[]):
            await dispatcher._run_scan(scan_id, token)

        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Scan).where(Scan.id == scan_id))
            persisted = res.scalars().first()
            assert persisted.status == ScanStatus.COMPLETED.value
            assert persisted.quality_status == ScanQualityStatus.PARTIAL_COVERAGE.value
            assert "partial coverage" in persisted.error_message.lower()

    async def test_quality_state_scanned_successfully_clean_run(
        self, created_asset_ids: List[str]
    ):
        """Verifies clean execution with all adapters succeeding transitions to SCANNED_SUCCESSFULLY with null error."""
        asset_id = uuid.uuid4()
        scan_id = uuid.uuid4()

        async with AsyncSessionLocal() as session:
            asset = Asset(
                id=asset_id,
                name="Clean Target",
                target_locator="https://clean-run.empire.edu.vn",
                verification_status=VerificationStatus.VERIFIED.value,
            )
            scan = Scan(
                id=scan_id,
                asset_id=asset_id,
                target_locator="https://clean-run.empire.edu.vn",
                status=ScanStatus.QUEUED.value,
            )
            session.add(asset)
            session.add(scan)
            await session.commit()

        dispatcher = AsyncWorkerDispatcher(max_concurrent=1)
        token = CancellationToken()

        clean_result = ScannerExecutionResult(
            engine_name="nuclei",
            execution_mode="binary_cli",
            success=True,
            exit_code=0,
            raw_output="",
            findings=[],
            error_message=None,
            duration_seconds=1.2,
        )
        mock_adapter = MagicMock(spec=BaseScannerAdapter)
        mock_adapter.engine_name = "nuclei"
        mock_adapter.execute = AsyncMock(return_value=clean_result)

        with patch("backend.app.core.dispatcher.NucleiAdapter", return_value=mock_adapter), \
             patch("backend.app.core.dispatcher.ZAPAdapter", return_value=mock_adapter), \
             patch("backend.app.core.dispatcher.EmpireAssessmentEngine.execute_empire_assessment",
                   return_value=[]):
            await dispatcher._run_scan(scan_id, token)

        async with AsyncSessionLocal() as session:
            res = await session.execute(select(Scan).where(Scan.id == scan_id))
            persisted = res.scalars().first()
            assert persisted.status == ScanStatus.COMPLETED.value
            assert persisted.quality_status == ScanQualityStatus.SCANNED_SUCCESSFULLY.value
            assert persisted.error_message is None
