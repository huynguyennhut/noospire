"""Pilot acceptance suite (Round A): real FastAPI app over ASGI, disposable SQLite DB,
synthetic labelled data only (`*.pilot-test.invalid`). No network, no shared DB.

Environment is fixed BEFORE the app is imported so settings bind to the throwaway DB.
"""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="noospire-pilot-"))
os.environ["SENTINEL_DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP / 'pilot.db').as_posix()}"
os.environ["SENTINEL_ENV"] = "test"
os.environ["SENTINEL_SOLE_OWNER_EMAIL"] = "owner@pilot-test.invalid"
os.environ["SENTINEL_SOLE_OWNER_ACCOUNT_ID"] = "0f0f0f0f-0000-4000-8000-000000000001"
os.environ["SENTINEL_PROCESS_ROLE"] = "api"  # no background worker/scheduler in API tests
os.environ["SENTINEL_SEED_DEMO_DATA"] = "false"
os.environ["SENTINEL_STORAGE_DIR"] = str(_TMP / "storage")
os.environ.pop("SENTINEL_BOOTSTRAP_TOKEN", None)

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from backend.app.core.config import settings  # noqa: E402
from backend.app.core.database import AsyncSessionLocal, engine, init_db  # noqa: E402
from backend.app.core.security import get_password_hash  # noqa: E402
from backend.app.models.base import Base  # noqa: E402
from backend.main import app  # noqa: E402

OWNER_PASSWORD = "pilot-owner-" + uuid.uuid4().hex  # generated per run, never a real secret
USER_PASSWORD = "pilot-user-" + uuid.uuid4().hex


@pytest_asyncio.fixture(autouse=True)
async def fresh_db():
    """Every test starts from an empty schema."""
    await init_db()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(delete(table))
    yield


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


def new_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver")


@pytest_asyncio.fixture
async def owner(client):
    from backend.app.api.auth import bootstrap_owner

    async with AsyncSessionLocal() as db:
        u = await bootstrap_owner(db, "pilot-owner", settings.SOLE_OWNER_EMAIL, OWNER_PASSWORD)
    return u


async def make_user(role: str, username: str) -> uuid.UUID:
    from backend.app.models.user import User

    uid = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(User(id=uid, username=username, email=f"{username}@pilot-test.invalid",
                    hashed_password=get_password_hash(USER_PASSWORD), role=role, is_active=True,
                    is_superuser=False))
        await db.commit()
    return uid


async def make_asset(name: str, verified: bool = True) -> uuid.UUID:
    from backend.app.models.asset import Asset

    aid = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(Asset(id=aid, name=name, target_locator=f"https://{name}.pilot-test.invalid/",
                     verification_status="VERIFIED" if verified else "PENDING",
                     verification_token=uuid.uuid4().hex, tags=["pilot-test"]))
        await db.commit()
    return aid


async def make_finding(asset_id: uuid.UUID, title: str) -> uuid.UUID:
    from backend.app.models.finding import NormalizedFinding
    from backend.app.models.scan import Scan

    sid, fid = uuid.uuid4(), uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(Scan(id=sid, asset_id=asset_id, target_locator="fixture://pilot", status="COMPLETED"))
        db.add(NormalizedFinding(id=fid, scan_id=sid, asset_id=asset_id, fingerprint=uuid.uuid4().hex,
                                 scanner_engine="fixture", scanner_rule_id="PILOT-TEST-1", title=title,
                                 description="synthetic", severity="HIGH", original_severity="HIGH",
                                 target_location="fixture://pilot"))
        await db.commit()
    return fid


async def login(c: httpx.AsyncClient, ident: str, password: str) -> httpx.Response:
    return await c.post("/api/v1/auth/login", json={"username": ident, "password": password})


def csrf_headers(c: httpx.AsyncClient) -> dict:
    return {settings.CSRF_HEADER_NAME: c.cookies.get(settings.CSRF_COOKIE_NAME) or ""}
