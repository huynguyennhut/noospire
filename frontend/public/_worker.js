/**
 * Noospire — Cloudflare Pages advanced-mode worker (OPTIONAL hosting mode).
 *
 * The pilot's supported path is Named Tunnel -> private gateway (deploy/gateway).
 * If the console is ever hosted on Pages instead, this worker only:
 *   - serves static assets from the export,
 *   - forwards /api/* and /healthz/* to ONE origin fixed in Pages env (API_ORIGIN),
 *   - returns 502/503 JSON with request_id when that origin fails.
 * It holds no data, issues no identity, and never turns an upstream error into success.
 * Clients cannot choose the upstream (no header/query override).
 *
 * Status: code-reviewed only; not executed in this workspace (no workerd available).
 */

const PROXY_PREFIXES = ["/api/", "/healthz/"];
const TIMEOUT_MS = 30000;

function rid(request) {
  const incoming = request.headers.get("x-request-id") || "";
  return /^[A-Za-z0-9._:-]{8,128}$/.test(incoming) ? incoming : crypto.randomUUID().replace(/-/g, "");
}

function errorJson(status, code, detail, requestId) {
  return new Response(JSON.stringify({ detail, code, request_id: requestId, source: "gateway" }), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", "x-request-id": requestId },
  });
}

async function proxy(request, env, url) {
  const requestId = rid(request);
  const origin = (env && env.API_ORIGIN) || "";
  if (!origin) return errorJson(503, "GATEWAY_NOT_CONFIGURED", "API origin is not configured.", requestId);

  const target = new URL(url.pathname + url.search, origin);
  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("x-request-id", requestId);
  const isStream = url.pathname.endsWith("/stream") || (request.headers.get("accept") || "").includes("text/event-stream");

  const controller = new AbortController();
  const timer = isStream ? null : setTimeout(() => controller.abort("timeout"), TIMEOUT_MS);
  let upstream;
  try {
    upstream = await fetch(target.toString(), {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
      redirect: "manual",
      signal: controller.signal,
    });
  } catch (err) {
    const timedOut = controller.signal.aborted;
    return timedOut
      ? errorJson(503, "UPSTREAM_TIMEOUT", "The API did not respond in time.", requestId)
      : errorJson(502, "UPSTREAM_UNREACHABLE", "The API origin is unreachable.", requestId);
  } finally {
    if (timer) clearTimeout(timer);
  }

  if ((upstream.headers.get("content-type") || "").startsWith("text/html")) {
    return errorJson(502, "MISROUTED", "API path answered with HTML; routing is misconfigured.", requestId);
  }
  const out = new Response(upstream.body, upstream);
  if (!out.headers.has("cache-control")) out.headers.set("cache-control", "no-store");
  out.headers.set("x-request-id", upstream.headers.get("x-request-id") || requestId);
  return out;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (PROXY_PREFIXES.some((p) => url.pathname.startsWith(p))) {
      return proxy(request, env, url);
    }
    if (["/_worker.js", "/_routes.json", "/_redirects"].includes(url.pathname)) {
      return new Response("Not Found", { status: 404 });
    }
    const res = await env.ASSETS.fetch(request);
    if (res.status !== 404) return res;
    const nf = await env.ASSETS.fetch(new Request(new URL("/404.html", url), { method: "GET" }));
    return new Response(nf.body, { status: 404, headers: nf.headers });
  },
};
