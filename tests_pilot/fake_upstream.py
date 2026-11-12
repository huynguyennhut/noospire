"""Controlled misbehaving upstream for gateway tests (loopback only, synthetic)."""

import asyncio

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route


async def html(_):
    return HTMLResponse("<html>portal login</html>")


async def slow(_):
    await asyncio.sleep(30)
    return JSONResponse({"late": True})


async def status(request):
    code = int(request.path_params["code"])
    return JSONResponse({"detail": f"upstream {code}"}, status_code=code)


async def cookies(_):
    r = JSONResponse({"ok": True})
    r.set_cookie("a_session", "1", httponly=True)
    r.set_cookie("b_csrf", "2")
    return r


async def echo_cookies(request):
    return JSONResponse({"cookie": request.headers.get("cookie")})


async def ok(_):
    return Response('{"ok": true}', media_type="application/json")


app = Starlette(routes=[
    Route("/api/v1/html", html),
    Route("/api/v1/slow", slow),
    Route("/api/v1/status/{code:int}", status),
    Route("/api/v1/ok", ok),
    Route("/api/v1/echo-cookies", echo_cookies),
    Route("/api/v1/cookies", cookies),
])
