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

from backend.main import app
from backend.app.core.database import AsyncSessionLocal, init_db
from backend.app.models.asset import Asset
from sqlalchemy import select


@pytest_asyncio.fixture(autouse=True)
async def initialize_test_database():
    """Ensure database schemas and Empire baseline seeds are initialized."""
    await init_db()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Provides an asynchronous HTTP client wired directly to the FastAPI ASGI application."""
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
