"""Global pytest fixtures and test harness configuration for NOOSFORGE Security Intelligence.
Provides ASGI HTTP async client, database session management, and isolation helpers.
"""

from __future__ import annotations

import os
import sys
import uuid
from typing import AsyncGenerator, List
from pathlib import Path

import pytest
import pytest_asyncio
import httpx

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from backend.main import app
from backend.app.core.database import AsyncSessionLocal, init_db
from backend.app.core.config import settings
from backend.app.core.security import create_access_token, get_password_hash
from backend.app.models.asset import Asset
from backend.app.models.user import User, UserRole
from backend.app.schemas.common import VerificationStatus

OWNER_USER_ID = uuid.UUID(settings.SOLE_OWNER_ACCOUNT_ID)


def pytest_sessionstart(session):
    """Sanitize storage/reports at session start so stale artifacts from prior runs do not pollute tests."""
    storage_dir = PROJECT_ROOT / "storage" / "reports"
    if storage_dir.exists():
        for p in storage_dir.iterdir():
            if p.suffix in (".html", ".json", ".pdf"):
                try:
                    p.unlink()
                except OSError:
                    pass


@pytest_asyncio.fixture(autouse=True)
async def initialize_test_database():
    """Ensure database schemas and Empire baseline seeds are initialized."""
    settings.SEED_DEMO_DATA = True
    settings.SSRF_ALLOW_PRIVATE_TARGETS = True
    await init_db()
    async with AsyncSessionLocal() as session:
        user = await session.get(User, OWNER_USER_ID)
        if not user:
            user = User(
                id=OWNER_USER_ID,
                username="owner_admin",
                email=settings.SOLE_OWNER_EMAIL,
                hashed_password=get_password_hash("ValidOwnerPassword123!"),
                role=UserRole.OWNER.value,
                is_active=True,
                is_superuser=True,
            )
            session.add(user)
            await session.commit()
        else:
            user.role = UserRole.OWNER.value
            user.is_active = True
            user.is_superuser = True
            await session.commit()

        # Ensure primary root target has verified baseline status
        stmt = select(Asset).where(Asset.target_locator.in_(("https://empire.edu.vn/", "https://empire.edu.vn")))
        res = await session.execute(stmt)
        primary_asset = res.scalars().first()
        if primary_asset and primary_asset.verification_status != VerificationStatus.VERIFIED.value:
            primary_asset.verification_status = VerificationStatus.VERIFIED.value
            await session.commit()

    yield
    from backend.app.core.database import engine
    await engine.dispose()


@pytest_asyncio.fixture
def auth_headers() -> dict[str, str]:
    """Generates valid signed JWT bearer token for the sole owner."""
    token = create_access_token(
        subject=str(OWNER_USER_ID),
        role=UserRole.OWNER.value,
        is_superuser=True,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(auth_headers: dict[str, str]) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provides an asynchronous HTTP client wired directly to the FastAPI ASGI application with owner credentials."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        yield ac


@pytest_asyncio.fixture
async def unauth_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provides an unauthenticated HTTP client for anonymous security testing."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session():
    """Provides an isolated database session for state assertions."""
    async with AsyncSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def created_asset_ids(client: httpx.AsyncClient) -> AsyncGenerator[List[str], None]:
    """Tracks asset IDs created during a test and automatically deletes them during teardown."""
    ids: List[str] = []
    yield ids
    # Cleanup after test completes
    for asset_id in ids:
        try:
            await client.delete(f"/api/v1/assets/{asset_id}")
        except Exception:
            pass
