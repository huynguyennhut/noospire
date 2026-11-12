"""Post-deploy smoke test through the gateway (Milestone 6). Read-only: it never launches a job.

  python deploy/smoke.py http://127.0.0.1:8080
  python deploy/smoke.py https://<admin-hostname>          # through the Named Tunnel

Optional environment (read from the environment only; values are never printed):
  NOOSPIRE_SMOKE_USER / NOOSPIRE_SMOKE_PASSWORD   sign in and check session-bound routes + SSE
  NOOSPIRE_SMOKE_ACCESS_JWT                       Cloudflare Access token (service token / browser cookie)
Exit code 0 = every check passed.
"""

from __future__ import annotations

import os
import sys
import time

import httpx

RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    return ok


def main(base: str) -> int:
    base = base.rstrip("/")
    headers = {}
    if os.getenv("NOOSPIRE_SMOKE_ACCESS_JWT"):
        headers["Cf-Access-Jwt-Assertion"] = os.environ["NOOSPIRE_SMOKE_ACCESS_JWT"]
    c = httpx.Client(base_url=base, headers=headers, timeout=15, follow_redirects=False)

    r = c.get("/gateway/live")
    check("gateway live", r.status_code == 200 and r.json().get("component") == "gateway",
          f"{r.status_code} access={r.json().get('access') if r.status_code == 200 else '-'}")
    for p in ("/healthz/live", "/healthz/ready"):
        r = c.get(p)
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json")
        check(f"{p}", ok and r.headers.get("cache-control") == "no-store", f"{r.status_code} {r.text[:80]}")
    r = c.get("/api/v1/version")
    check("version", r.status_code == 200 and "build" in r.json(), r.text[:120])

    r = c.get("/")
    check("console index", r.status_code == 200 and "text/html" in r.headers.get("content-type", "")
          and r.headers.get("cache-control") == "no-cache", f"{r.status_code} {r.headers.get('cache-control')}")
    r = c.get("/health/")
    check("/health/ page is static HTML", r.status_code == 200 and "text/html" in r.headers.get("content-type", ""),
          str(r.status_code))
    r = c.get("/api/v1/definitely-not-a-route")
    check("API 404 is JSON", r.status_code == 404 and r.headers.get("content-type", "").startswith("application/json")
          and r.json().get("code") == "NOT_FOUND", f"{r.status_code} {r.headers.get('content-type')}")
    r = c.get("/definitely-not-a-page/")
    check("page 404 is HTML", r.status_code == 404 and "text/html" in r.headers.get("content-type", ""),
          str(r.status_code))
    r = c.get("/_worker.js")
    check("Pages worker not served", r.status_code == 404, str(r.status_code))
    r = c.get("/api/v1/findings")
    check("unauthenticated API is 401 JSON", r.status_code == 401 and r.json().get("code") == "UNAUTHENTICATED",
          str(r.status_code))

    user, pw = os.getenv("NOOSPIRE_SMOKE_USER"), os.getenv("NOOSPIRE_SMOKE_PASSWORD")
    if user and pw:
        r = c.post("/api/v1/auth/login", json={"username": user, "password": pw})
        cookies = r.headers.get_list("set-cookie")
        check("login sets session + CSRF cookies", r.status_code == 200 and len(cookies) >= 2
              and any("HttpOnly" in x for x in cookies), f"{r.status_code} cookies={len(cookies)}")
        if r.status_code == 200:
            c.headers["X-CSRF-Token"] = c.cookies.get("noospire_csrf") or ""
            r = c.get("/api/v1/auth/me")
            check("session /auth/me", r.status_code == 200, str(r.status_code))
            r = c.get("/api/v1/operations/overview")
            check("operations overview", r.status_code == 200 and "server_time" in r.json(), str(r.status_code))
            r = c.get("/api/v1/events", params={"after": 0, "limit": 5})
            check("event polling (cursor)", r.status_code == 200 and "cursor" in r.json(), str(r.status_code))
            t0 = time.monotonic()
            frames = []
            try:
                with c.stream("GET", "/api/v1/events/stream", params={"max_seconds": 3},
                              headers={"Accept": "text/event-stream"}, timeout=httpx.Timeout(10, read=10)) as s:
                    ok_ct = s.headers.get("content-type", "").startswith("text/event-stream")
                    for line in s.iter_lines():
                        if line.startswith("event: "):
                            frames.append(line[7:])
                check("SSE through gateway", ok_ct and "hello" in frames,
                      f"events={frames[:4]} in {time.monotonic() - t0:.1f}s")
            except httpx.HTTPError as exc:
                check("SSE through gateway", False, type(exc).__name__)
            r = c.post("/api/v1/auth/logout")
            check("logout", r.status_code == 200, str(r.status_code))
            r = c.get("/api/v1/auth/me")
            check("session revoked after logout", r.status_code == 401, str(r.status_code))
    else:
        check("signed-in checks", True, "skipped (NOOSPIRE_SMOKE_USER/PASSWORD not set)")

    width = max(len(n) for n, _, _ in RESULTS)
    for name, ok, detail in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'}  {name.ljust(width)}  {detail}")
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"))
