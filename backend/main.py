import sys
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.alerts import router as alerts_router
from backend.app.api.assets import router as assets_router
from backend.app.api.auth import router as auth_router
from backend.app.api.baselines import router as baselines_router
from backend.app.api.empire_modules import router as empire_modules_router
from backend.app.api.engines import router as engines_router
from backend.app.api.findings import router as findings_router
from backend.app.api.intel import router as intel_router
from backend.app.api.logs import router as logs_router
from backend.app.api.metrics import router as metrics_router
from backend.app.api.reports import router as reports_router
from backend.app.api.rules import router as rules_router
from backend.app.api.scans import router as scans_router
from backend.app.api.schedules import router as schedules_router
from backend.app.api.settings import router as settings_router
from backend.app.api.system import router as system_router
from backend.app.core.config import settings
from backend.app.core.database import init_db
from backend.app.core.dispatcher import AsyncWorkerDispatcher, get_dispatcher
from backend.app.core.scheduler import get_scheduler_engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # 1. Startup: Initialize database tables and seed Empire ecosystem
    await init_db()

    # 1.1 Startup: Multi-replica safe initialization
    # Do NOT execute cluster-wide scan cancellation on startup.
    # Live scans leased or executing on other workers/replicas must remain untouched.

    # 2. Startup: Launch background worker if running in async worker mode
    dispatcher = get_dispatcher()
    if isinstance(dispatcher, AsyncWorkerDispatcher):
        dispatcher.start()

    # 2.1 Startup: Launch active background scheduler ticker
    scheduler_engine = get_scheduler_engine()
    scheduler_engine.start()

    yield

    # 3. Shutdown: Cleanly stop background tasks
    await scheduler_engine.stop()

    if isinstance(dispatcher, AsyncWorkerDispatcher):
        await dispatcher.stop()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="NOOSFORGE Security Intelligence — Continuous Attack Surface Monitoring & Vulnerability Management for Empire Platform.",
        lifespan=lifespan,
    )

    # CORS configuration
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Routers
    app.include_router(auth_router, prefix=settings.API_V1_STR)
    app.include_router(assets_router, prefix=settings.API_V1_STR)
    app.include_router(scans_router, prefix=settings.API_V1_STR)
    app.include_router(findings_router, prefix=settings.API_V1_STR)
    app.include_router(settings_router, prefix=settings.API_V1_STR)
    app.include_router(reports_router, prefix=settings.API_V1_STR)
    app.include_router(metrics_router, prefix=settings.API_V1_STR)
    app.include_router(intel_router, prefix=settings.API_V1_STR)
    app.include_router(rules_router, prefix=settings.API_V1_STR)
    app.include_router(empire_modules_router, prefix=settings.API_V1_STR)
    app.include_router(baselines_router, prefix=settings.API_V1_STR)
    app.include_router(schedules_router, prefix=settings.API_V1_STR)
    app.include_router(alerts_router, prefix=settings.API_V1_STR)
    app.include_router(logs_router, prefix=settings.API_V1_STR)
    app.include_router(system_router, prefix=settings.API_V1_STR)
    app.include_router(engines_router, prefix=settings.API_V1_STR)

    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}

    @app.get("/")
    async def root():
        return {
            "message": f"Welcome to {settings.PROJECT_NAME} ({settings.PLATFORM_TARGET}) API",
            "docs": "/docs",
            "version": settings.VERSION,
        }

    return app


app = create_app()

__all__ = ["app", "create_app", "lifespan"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
