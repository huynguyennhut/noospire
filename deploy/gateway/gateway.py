"""Noospire private gateway: serves the static console export and forwards API calls
to ONE fixed FastAPI origin taken from operator configuration.

Contract
- /api/*, /healthz/*  -> NOOSPIRE_API_ORIGIN (fixed; clients cannot choose upstream).
  Upstream status codes and bodies pass through unchanged (401/403/404/422 keep meaning).
  Upstream unreachable -> 502 JSON, upstream timeout -> 503 JSON, both with request_id.
  An upstream that answers an API path with HTML -> 502 code=MISROUTED (never forwarded).
  SSE (text/event-stream) is streamed without buffering and without the read timeout.
- /health/ and every other path -> static files from NOOSPIRE_STATIC_DIR (frontend/out).
  Unknown non-API paths -> 404.html with status 404. API paths never fall back to HTML.
- Cache: hashed static assets are immutable; HTML no-cache; API responses no-store.
- No mock data, no fake login, no success-on-error interception.

Run:  NOOSPIRE_API_ORIGIN=http://127.0.0.1:8000 NOOSPIRE_STATIC_DIR=frontend/out \
      uvicorn deploy.gateway.gateway:app --host 127.0.0.1 --port 8080
"""

from __future__ import annotations

import contextlib
import logging
import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route

log = logging.getLogger("noospire.gateway")

API_ORIGIN = os.getenv("NOOSPIRE_API_ORIGIN", "").rstrip("/")
STATIC_DIR = Path(os.getenv("NOOSPIRE_STATIC_DIR", "frontend/out")).resolve()
CONNECT_TIMEOUT = float(os.getenv("NOOSPIRE_GW_CONNECT_TIMEOUT", "3"))
READ_TIMEOUT = float(os.getenv("NOOSPIRE_GW_READ_TIMEOUT", "30"))
MAX_BODY = int(os.getenv("NOOSPIRE_GW_MAX_BODY_BYTES", str(25 * 1024 * 1024)))
MAX_CONN = int(os.getenv("NOOSPIRE_GW_MAX_CONNECTIONS", "100"))
BUILD_ID = os.getenv("NOOSPIRE_BUILD_ID", "dev")

PROXY_PREFIXES = ("/api/", "/healthz/")
HOP_BY_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers",
              "transfer-encoding", "upgrade", "host", "content-length"}
# Files that exist in the export for other hosting modes but must never be served here.
BLOCKED_STATIC = {"_worker.js", "_routes.json", "_redirects"}
_RID = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=CONNECT_TIMEOUT, read=READ_TIMEOUT, write=READ_TIMEOUT, pool=CONNECT_TIMEOUT),
            limits=httpx.Limits(max_connections=MAX_CONN, max_keepalive_connections=MAX_CONN // 2),
            follow_redirects=False,
        )
    return _client


def _error(status: int, code: str, detail: str, rid: str) -> JSONResponse:
    return JSONResponse(
        {"detail": detail, "code": code, "request_id": rid, "source": "gateway"},
        status_code=status,
        headers={"X-Request-ID": rid, "Cache-Control": "no-store"},
    )


async def proxy(request: Request) -> Response:
    incoming = request.headers.get("x-request-id", "")
    rid = incoming if _RID.match(incoming) else uuid.uuid4().hex
    if not API_ORIGIN:
        return _error(503, "GATEWAY_NOT_CONFIGURED", "API origin is not configured on the gateway.", rid)

    body = await request.body()
    if len(body) > MAX_BODY:
        return _error(413, "PAYLOAD_TOO_LARGE", "Request body exceeds gateway limit.", rid)

    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
    headers["x-request-id"] = rid
    headers["x-forwarded-proto"] = request.url.scheme
    if request.client:
        headers["x-forwarded-for"] = request.client.host
    url = API_ORIGIN + request.url.path + (("?" + request.url.query) if request.url.query else "")
    wants_stream = "text/event-stream" in request.headers.get("accept", "") or request.url.path.endswith("/stream")

    client = _get_client()
    req = client.build_request(request.method, url, headers=headers, content=body)
    try:
        if wants_stream:
            # No read timeout for SSE; heartbeats keep it alive, disconnect ends it.
            req.extensions["timeout"] = httpx.Timeout(connect=CONNECT_TIMEOUT, read=None, write=READ_TIMEOUT,
                                                      pool=CONNECT_TIMEOUT).as_dict()
        upstream = await client.send(req, stream=True)
    except httpx.TimeoutException:
        log.warning("upstream timeout rid=%s path=%s", rid, request.url.path)
        return _error(503, "UPSTREAM_TIMEOUT", "The API did not respond in time.", rid)
    except httpx.TransportError as exc:
        log.warning("upstream unreachable rid=%s path=%s err=%s", rid, request.url.path, type(exc).__name__)
        return _error(502, "UPSTREAM_UNREACHABLE", "The API origin is unreachable.", rid)

    ctype = upstream.headers.get("content-type", "")
    if ctype.startswith("text/html"):
        await upstream.aclose()
        return _error(502, "MISROUTED", "API path answered with HTML; routing is misconfigured.", rid)

    # Keep repeated headers (e.g. two Set-Cookie) intact: work on the raw multi-item list.
    raw_headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in upstream.headers.multi_items()
                   if k.lower() not in HOP_BY_HOP and k.lower() not in ("content-encoding", "x-request-id")]
    names = {k.lower() for k, _ in raw_headers}
    if b"cache-control" not in names:
        raw_headers.append((b"cache-control", b"no-store"))
    raw_headers.append((b"x-request-id", upstream.headers.get("x-request-id", rid).encode("latin-1")))
    if ctype.startswith("text/event-stream"):
        raw_headers.append((b"x-accel-buffering", b"no"))

    async def body_iter():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        except httpx.HTTPError:
            # Upstream dropped mid-stream; the client sees a truncated stream and reconnects.
            return

    resp = StreamingResponse(body_iter(), status_code=upstream.status_code,
                             background=BackgroundTask(upstream.aclose))
    resp.raw_headers = [h for h in resp.raw_headers if h[0] not in (b"content-type",)] + raw_headers
    return resp


def _static_headers(rel: str) -> dict:
    if rel.startswith("_next/static/"):
        return {"Cache-Control": "public, max-age=31536000, immutable"}
    if rel.endswith(".html") or rel.endswith(".txt"):
        return {"Cache-Control": "no-cache"}
    return {"Cache-Control": "public, max-age=3600"}


def _resolve_static(path: str) -> Optional[Path]:
    rel = path.lstrip("/")
    candidates = [rel] if rel else []
    if not rel or rel.endswith("/"):
        candidates = [rel + "index.html"]
    else:
        candidates += [rel + "/index.html", rel + ".html"]
    for c in candidates:
        p = (STATIC_DIR / c).resolve()
        if not p.is_relative_to(STATIC_DIR) or p.name in BLOCKED_STATIC:
            continue
        if p.is_file():
            return p
    return None


async def static(request: Request) -> Response:
    if request.method not in ("GET", "HEAD"):
        return Response(status_code=405)
    p = _resolve_static(request.url.path)
    if p is None:
        nf = STATIC_DIR / "404.html"
        if nf.is_file():
            return FileResponse(nf, status_code=404, media_type="text/html", headers={"Cache-Control": "no-cache"})
        return Response("Not Found", status_code=404, media_type="text/plain")
    rel = p.relative_to(STATIC_DIR).as_posix()
    media = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return FileResponse(p, media_type=media, headers=_static_headers(rel))


async def gateway_health(request: Request) -> Response:
    # Gateway's own liveness (does not touch the API). API health is /healthz/*.
    return JSONResponse({"status": "live", "component": "gateway", "build": BUILD_ID,
                         "api_origin_configured": bool(API_ORIGIN),
                         "static_present": (STATIC_DIR / "index.html").is_file()},
                        headers={"Cache-Control": "no-store"})


async def dispatch(request: Request) -> Response:
    path = request.url.path
    if path == "/gateway/live":
        return await gateway_health(request)
    if path.startswith(PROXY_PREFIXES) or path in ("/api", "/healthz"):
        return await proxy(request)
    return await static(request)


@contextlib.asynccontextmanager
async def _lifespan(_app):
    yield
    if _client is not None:
        await _client.aclose()


app = Starlette(
    routes=[Route("/{path:path}", dispatch, methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])],
    lifespan=_lifespan,
)
