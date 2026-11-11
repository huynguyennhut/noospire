import sys
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import logging
import os
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.api.alerts import router as alerts_router
from backend.app.api.assets import router as assets_router
from backend.app.api.auth import router as auth_router
from backend.app.api.baselines import router as baselines_router
from backend.app.api.empire_modules import router as empire_modules_router
from backend.app.api.engines import router as engines_router
from backend.app.api.executions import router as executions_router
from backend.app.api.findings import router as findings_router
from backend.app.api.intel import router as intel_router
from backend.app.api.logs import router as logs_router
from backend.app.api.metrics import router as metrics_router
from backend.app.api.reports import router as reports_router
from backend.app.api.rules import router as rules_router
from backend.app.api.scans import router as scans_router
from backend.app.api.operations import legacy_schedules_router as schedules_router
from backend.app.api.operations import router as operations_router
from backend.app.api.console import router as console_router
from backend.app.api.settings import router as settings_router
from backend.app.api.system import router as system_router
from backend.app.core.config import settings
from backend.app.core.database import AsyncSessionLocal, init_db
from backend.app.core.dispatcher import AsyncWorkerDispatcher, get_dispatcher
from backend.app.core.monitor_scheduler import get_monitor_scheduler

logger = logging.getLogger("sentinel.api")

BUILD_ID = os.getenv("NOOSPIRE_BUILD_ID", "dev")
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


def _runs(component: str) -> bool:
    """SENTINEL_PROCESS_ROLE: all | api | worker | scheduler (comma-separated allowed)."""
    roles = {r.strip().lower() for r in settings.PROCESS_ROLE.split(",")}
    return "all" in roles or component in roles


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Schema only. Boot never seeds users, assets, findings or schedules.
    await init_db()

    dispatcher = get_dispatcher()
    started_worker = False
    if _runs("worker") and isinstance(dispatcher, AsyncWorkerDispatcher):
        dispatcher.start()
        started_worker = True

    # Milestone 4: the monitor scheduler (slot claims + reaper) replaces the legacy DailySchedule engine.
    scheduler_engine = get_monitor_scheduler()
    started_scheduler = False
    if _runs("scheduler"):
        scheduler_engine.start()
        started_scheduler = True

    app.state.components = {"worker": started_worker, "scheduler": started_scheduler}
    yield

    if started_scheduler:
        await scheduler_engine.stop()
    if started_worker:
        await dispatcher.stop()


def _error_body(request: Request, status_code: int, detail, code: str) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code, "request_id": rid},
        headers={"X-Request-ID": rid or "", "Cache-Control": "no-store"},
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="Noospire defensive security monitoring API for the Empire pilot.",
        lifespan=lifespan,
    )

    # Same-origin console: CORS only needed for local dev servers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS if settings.is_development else [],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", settings.CSRF_HEADER_NAME, "X-Request-ID",
                       "Idempotency-Key", "Last-Event-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        incoming = request.headers.get("x-request-id") or ""
        rid = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if request.url.path.startswith("/api/") or request.url.path.startswith("/healthz"):
            # API data, evidence and reports must never be stored by shared caches.
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException):
        code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT",
                405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        resp = _error_body(request, exc.status_code, exc.detail, code)
        for k, v in (getattr(exc, "headers", None) or {}).items():
            resp.headers[k] = v
        return resp

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError):
        from fastapi.encoders import jsonable_encoder
        return _error_body(request, 422, jsonable_encoder(exc.errors()), "VALIDATION_ERROR")

    @app.exception_handler(Exception)
    async def unhandled_exc(request: Request, exc: Exception):
        logger.exception("unhandled error request_id=%s path=%s", getattr(request.state, "request_id", None),
                         request.url.path)
        return _error_body(request, 500, "Internal server error", "INTERNAL_ERROR")

    for r in (auth_router, assets_router, scans_router, findings_router, settings_router, reports_router,
              metrics_router, intel_router, rules_router, empire_modules_router, baselines_router,
              schedules_router, alerts_router, logs_router, system_router, executions_router, engines_router,
              operations_router, console_router):
        app.include_router(r, prefix=settings.API_V1_STR)

    @app.get("/healthz/live", tags=["Health"])
    async def live():
        """Process is up. No dependency checks."""
        return {"status": "live", "build": BUILD_ID, "time_utc": datetime.now(timezone.utc).isoformat()}

    @app.get("/healthz/ready", tags=["Health"])
    async def ready(request: Request):
        """Ready to serve: DB reachable and schema present. Worker/scheduler readiness is
        reported separately and does not make the API unready."""
        checks: dict = {}
        ok = True
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
                await db.execute(text("SELECT COUNT(*) FROM users"))
            checks["database"] = "ok"
        except Exception as exc:  # pragma: no cover - exercised in failure tests
            ok = False
            checks["database"] = f"error:{type(exc).__name__}"
        comps = getattr(request.app.state, "components", {})
        body = {
            "status": "ready" if ok else "not_ready",
            "build": BUILD_ID,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
            "in_process": comps,
            "time_utc": datetime.now(timezone.utc).isoformat(),
        }
        return JSONResponse(status_code=200 if ok else 503, content=body)

    # Legacy liveness alias kept for existing probes.
    @app.get("/health", include_in_schema=False)
    async def health_check():
        return {"status": "healthy"}

    @app.get("/api/v1/version", tags=["Health"])
    async def version():
        return {"version": settings.VERSION, "build": BUILD_ID}

    return app


app = create_app()

__all__ = ["app", "create_app", "lifespan"]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000)
