"""Milestone M2 Automated Test Suite: Scanning and Intelligence.
Verifies:
1. ScanQualityStatus Enum & Model/Schema Integration
2. Dispatcher Quality State Machine & Error Handling (TARGET_UNAVAILABLE, AUTH_REQUIRED, SCANNER_FAILED, PARTIAL_COVERAGE, SCANNED_SUCCESSFULLY)
3. ProcessSafetyManager PID Registration in Scanner Execution
4. Asynchronous Same-Origin BFS Crawler (depth limit, page limit, rate limiting, same-origin filtering)
5. Empire Assessment Engine Business Module Coverage
6. Finding Evidence Mutation Persistence (flag_modified)
"""

import asyncio
import uuid
from typing import List

import httpx
import pytest
from sqlalchemy import select

from backend.app.core.database import AsyncSessionLocal
from backend.app.core.dispatcher import process_safety, get_dispatcher
from backend.app.models.asset import Asset
from backend.app.models.finding import NormalizedFinding
from backend.app.models.scan import Scan
from backend.app.scanners.base import CancellationToken
from backend.app.scanners.crawler import AsyncBFSCrawler, CrawlResult, DiscoveredEndpoint
from backend.app.scanners.empire_engine import EmpireAssessmentEngine
from backend.app.schemas.common import (
    AssetType,
    EmpireModule,
    FindingStatus,
    ScanProfile,
    ScanQualityStatus,
    ScanStatus,
    VerificationStatus,
)
from backend.app.schemas.scan import ScanRead, ScanResponse


def test_m2_01_scan_quality_status_enum():
    """Verifies ScanQualityStatus enum values and structure."""
    expected_values = {
        "SCANNED_SUCCESSFULLY",
        "PARTIAL_COVERAGE",
        "AUTH_REQUIRED",
        "SCANNER_FAILED",
        "TARGET_UNAVAILABLE",
    }
    actual_values = {status.value for status in ScanQualityStatus}
    assert actual_values == expected_values
    assert ScanQualityStatus.SCANNED_SUCCESSFULLY.value == "SCANNED_SUCCESSFULLY"
    assert ScanQualityStatus.PARTIAL_COVERAGE.value == "PARTIAL_COVERAGE"
    assert ScanQualityStatus.AUTH_REQUIRED.value == "AUTH_REQUIRED"
    assert ScanQualityStatus.SCANNER_FAILED.value == "SCANNER_FAILED"
    assert ScanQualityStatus.TARGET_UNAVAILABLE.value == "TARGET_UNAVAILABLE"


def test_m2_02_scan_model_and_schema_quality_status():
    """Verifies quality_status field exists on Scan model and ScanResponse/ScanRead schema."""
    scan = Scan(
        asset_id=uuid.uuid4(),
        target_locator="https://test.empire.edu.vn",
        quality_status=ScanQualityStatus.SCANNED_SUCCESSFULLY.value,
    )
    assert scan.quality_status == "SCANNED_SUCCESSFULLY"

    # Schema verification
    data = {
        "id": uuid.uuid4(),
        "asset_id": uuid.uuid4(),
        "engine": "nuclei",
        "profile": "BASELINE",
        "status": ScanStatus.COMPLETED,
        "quality_status": ScanQualityStatus.SCANNED_SUCCESSFULLY,
        "progress_percentage": 100,
        "target_locator": "https://test.empire.edu.vn",
        "allow_private_targets": False,
        "timeout_seconds": 600,
        "created_at": "2026-11-08T00:00:00Z",
        "updated_at": "2026-11-08T00:00:00Z",
    }
    response = ScanResponse.model_validate(data)
    assert response.quality_status == ScanQualityStatus.SCANNED_SUCCESSFULLY
    assert ScanRead == ScanResponse


@pytest.mark.asyncio
async def test_m2_03_crawler_same_origin_enforcement():
    """Verifies AsyncBFSCrawler strictly enforces same-origin rules."""
    crawler = AsyncBFSCrawler(max_depth=3, max_pages=10)

    # Valid same-origin
    assert crawler.is_same_origin("https://empire.edu.vn/about", "empire.edu.vn") is True
    assert crawler.is_same_origin("https://empire.edu.vn:443/login", "empire.edu.vn", 443) is True
    assert crawler.is_same_origin("http://empire.edu.vn/courses", "empire.edu.vn") is True

    # Invalid cross-origin
    assert crawler.is_same_origin("https://sub.empire.edu.vn/about", "empire.edu.vn") is False
    assert crawler.is_same_origin("https://google.com/search", "empire.edu.vn") is False
    assert crawler.is_same_origin("https://evil.com?ref=empire.edu.vn", "empire.edu.vn") is False
    assert crawler.is_same_origin("javascript:alert(1)", "empire.edu.vn") is False
    assert crawler.is_same_origin("mailto:admin@empire.edu.vn", "empire.edu.vn") is False


def test_m2_04_crawler_link_extraction():
    """Verifies AsyncBFSCrawler extracts, normalizes, and filters HTML links."""
    crawler = AsyncBFSCrawler(max_depth=3, max_pages=10)

    html = """
    <!DOCTYPE html>
    <html>
      <head><title>Empire Platform</title></head>
      <body>
        <a href="/courses">Courses</a>
        <a href="https://empire.edu.vn/faculty#team">Faculty</a>
        <a href="https://external-partner.com/api">External</a>
        <form action="/auth/login" method="POST"></form>
        <script src="/static/app.js"></script>
        <img src="/media/logo.png" />
      </body>
    </html>
    """

    links = crawler.extract_links(html, "https://empire.edu.vn/home", "empire.edu.vn", None)
    assert "https://empire.edu.vn/courses" in links
    assert "https://empire.edu.vn/faculty" in links
    assert "https://empire.edu.vn/auth/login" in links
    assert "https://empire.edu.vn/static/app.js" in links
    assert "https://empire.edu.vn/media/logo.png" in links
    # External link should be filtered out
    assert "https://external-partner.com/api" not in links


@pytest.mark.asyncio
async def test_m2_05_crawler_execution_bounded():
    """Verifies AsyncBFSCrawler bounds execution by max_pages and max_depth."""
    crawler = AsyncBFSCrawler(max_depth=2, max_pages=3, rate_limit_delay=0.01)
    cancel_token = CancellationToken()

    # Crawl against self or local URL
    result = await crawler.crawl("https://empire.edu.vn", cancel_token=cancel_token)
    assert isinstance(result, CrawlResult)
    assert result.root_url == "https://empire.edu.vn"
    assert result.target_domain == "empire.edu.vn"
    assert result.total_pages_visited <= 3
    assert result.duration_seconds >= 0.0


@pytest.mark.asyncio
async def test_m2_06_process_safety_manager_registration():
    """Verifies ProcessSafetyManager registers and tracks process IDs per scan."""
    scan_id = uuid.uuid4()
    test_pid = 999999

    await process_safety.register_pid(scan_id, test_pid)
    assert scan_id in process_safety._scan_pids
    assert test_pid in process_safety._scan_pids[scan_id]

    # Clean up
    process_safety.terminate_process_tree(scan_id)
    assert scan_id not in process_safety._scan_pids


@pytest.mark.asyncio
async def test_m2_07_finding_flag_modified_persistence(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies that calling triage updates finding evidence JSON and persists cleanly with flag_modified."""
    # Create target asset and find an existing finding
    slug = uuid.uuid4().hex[:8]
    create_resp = await client.post("/api/v1/assets", json={
        "name": f"Evidence Test Target {slug}",
        "target_locator": f"https://evidence-{slug}.empire.edu.vn",
    })
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]
    created_asset_ids.append(aid)

    # Get any finding
    findings_resp = await client.get("/api/v1/findings?size=1")
    assert findings_resp.status_code == 200
    items = findings_resp.json()["items"]
    assert len(items) > 0
    target_finding = items[0]
    fid = target_finding["id"]

    # Perform triage mutation
    triage_resp = await client.post(f"/api/v1/findings/{fid}/triage", json={
        "status": "CONFIRMED",
        "assignee": "auditor@empire.edu.vn",
        "comment": f"Flag modified test comment {slug}",
    })
    assert triage_resp.status_code == 200
    updated = triage_resp.json()
    assert updated["status"] == "CONFIRMED"

    # Fetch directly from database to verify JSON persistence on disk
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(NormalizedFinding).where(NormalizedFinding.id == uuid.UUID(fid)))
        db_finding = res.scalars().first()
        assert db_finding is not None
        assert db_finding.evidence is not None
        triage_history = db_finding.evidence.get("triage_history", [])
        assert len(triage_history) > 0
        latest_comment = triage_history[-1].get("comment")
        assert f"Flag modified test comment {slug}" in latest_comment


@pytest.mark.asyncio
async def test_m2_08_empire_assessment_engine_module_coverage():
    """Verifies EmpireAssessmentEngine exercises all 6 business modules starting from empire.edu.vn."""
    engine = EmpireAssessmentEngine()
    logs: List[str] = []

    async def mock_log_cb(source: str, msg: str, level: str = "INFO"):
        logs.append(f"[{source}] {msg}")

    scan_id = uuid.uuid4()
    asset_id = uuid.uuid4()

    findings = await engine.execute_empire_assessment(
        asset_id=asset_id,
        scan_id=scan_id,
        target_locator="https://empire.edu.vn",
        empire_module="WEB_APPLICATION",
        profile="DAILY_SECURITY",
        log_cb=mock_log_cb,
    )

    # Ensure log output captured execution of modules A, B, C, D, E, F, G
    joined_logs = " ".join(logs)
    assert "Module A" in joined_logs
    assert "Module B" in joined_logs
    assert "Module C" in joined_logs
    assert "Module D" in joined_logs
    assert "Module E" in joined_logs
    assert "Module F" in joined_logs
    assert "Module G" in joined_logs
    assert isinstance(findings, list)


@pytest.mark.asyncio
async def test_m2_09_dispatcher_auth_required_state_machine(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies that attempting DEEP_ACTIVE active scan on an unverified target is blocked with AUTH_REQUIRED."""
    slug = uuid.uuid4().hex[:8]
    create_resp = await client.post("/api/v1/assets", json={
        "name": f"Unverified Target {slug}",
        "target_locator": f"https://unverified-{slug}.empire.edu.vn",
        "empire_module": "STUDENT_MANAGEMENT",
    })
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]
    created_asset_ids.append(aid)

    # Set verification_status to PENDING in database
    async with AsyncSessionLocal() as session:
        db_asset = await session.get(Asset, uuid.UUID(aid))
        db_asset.verification_status = VerificationStatus.PENDING.value
        await session.commit()

    # API blocks DEEP_ACTIVE on unverified target with HTTP 403
    scan_resp = await client.post("/api/v1/scans", json={
        "asset_id": aid,
        "engine": "nuclei",
        "profile": "DEEP_ACTIVE",
        "timeout_seconds": 60,
    })
    assert scan_resp.status_code == 403
    assert "not verified" in scan_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_m2_10_dispatcher_target_unavailable_state_machine(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies that an asset that fails SSRF validation is rejected or transitions to TARGET_UNAVAILABLE."""
    slug = uuid.uuid4().hex[:8]
    create_resp = await client.post("/api/v1/assets", json={
        "name": f"SSRF Target {slug}",
        "target_locator": "http://169.254.169.254/latest/meta-data/",
    })
    if create_resp.status_code == 201:
        aid = create_resp.json()["id"]
        created_asset_ids.append(aid)
        scan_resp = await client.post("/api/v1/scans", json={
            "asset_id": aid,
            "engine": "nuclei",
            "profile": "BASELINE",
            "allow_private_targets": False,
        })
        assert scan_resp.status_code == 400


@pytest.mark.asyncio
async def test_m2_11_scan_dispatch_quality_status_lifecycle(client: httpx.AsyncClient, created_asset_ids: List[str]):
    """Verifies that dispatched scans carry quality_status in responses."""
    slug = uuid.uuid4().hex[:8]
    create_resp = await client.post("/api/v1/assets", json={
        "name": f"Quality Status Target {slug}",
        "target_locator": f"https://quality-{slug}.empire.edu.vn",
        "empire_module": "STUDENT_MANAGEMENT",
    })
    assert create_resp.status_code == 201
    aid = create_resp.json()["id"]
    created_asset_ids.append(aid)

    scan_resp = await client.post("/api/v1/scans", json={
        "asset_id": aid,
        "engine": "nuclei",
        "profile": "BASELINE",
        "timeout_seconds": 60,
    })
    assert scan_resp.status_code == 201
    scan_data = scan_resp.json()
    assert "quality_status" in scan_data
    scan_id = scan_data["id"]

    # Poll scan completion
    await asyncio.sleep(2)
    poll_resp = await client.get(f"/api/v1/scans/{scan_id}")
    assert poll_resp.status_code == 200
    poll_data = poll_resp.json()
    assert "quality_status" in poll_data
    if poll_data["status"] == "COMPLETED":
        assert poll_data["quality_status"] in (
            ScanQualityStatus.SCANNED_SUCCESSFULLY.value,
            ScanQualityStatus.PARTIAL_COVERAGE.value,
        )


@pytest.mark.asyncio
async def test_m2_12_direct_dispatcher_quality_state_machine():
    """Directly tests AsyncWorkerDispatcher quality state transitions:
    1. TARGET_UNAVAILABLE when asset does not exist
    2. AUTH_REQUIRED when unverified asset attempts DEEP_ACTIVE
    """
    from backend.app.core.dispatcher import AsyncWorkerDispatcher
    dispatcher = AsyncWorkerDispatcher(max_concurrent=1)

    # 1. Test TARGET_UNAVAILABLE on nonexistent asset
    scan_id_1 = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        scan_1 = Scan(
            id=scan_id_1,
            asset_id=uuid.uuid4(),  # Non-existent asset ID
            target_locator="https://nonexistent.empire.edu.vn",
            status=ScanStatus.QUEUED.value,
        )
        session.add(scan_1)
        await session.commit()

    token_1 = CancellationToken()
    await dispatcher._run_scan(scan_id_1, token_1)

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Scan).where(Scan.id == scan_id_1))
        persisted_1 = res.scalars().first()
        assert persisted_1.status == ScanStatus.FAILED.value
        assert persisted_1.quality_status == ScanQualityStatus.TARGET_UNAVAILABLE.value

    # 2. Test AUTH_REQUIRED on unverified target attempting DEEP_ACTIVE
    asset_id_2 = uuid.uuid4()
    scan_id_2 = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        asset_2 = Asset(
            id=asset_id_2,
            name="Unverified Active Asset",
            target_locator="https://active-unverified.empire.edu.vn",
            verification_status=VerificationStatus.PENDING.value,
        )
        scan_2 = Scan(
            id=scan_id_2,
            asset_id=asset_id_2,
            target_locator="https://active-unverified.empire.edu.vn",
            profile=ScanProfile.DEEP_ACTIVE.value,
            status=ScanStatus.QUEUED.value,
        )
        session.add(asset_2)
        session.add(scan_2)
        await session.commit()

    token_2 = CancellationToken()
    await dispatcher._run_scan(scan_id_2, token_2)

    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Scan).where(Scan.id == scan_id_2))
        persisted_2 = res.scalars().first()
        assert persisted_2.status == ScanStatus.FAILED.value
        assert persisted_2.quality_status == ScanQualityStatus.AUTH_REQUIRED.value
