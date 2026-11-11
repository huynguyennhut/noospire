"""Milestone 6 · client ↔ server contract audit.

Builds the OpenAPI document from the real FastAPI app (same import path as production) and
compares it with every API call the console makes:
  - `this.fetchJson(...)` and `api.request(...)` calls (method from `method: '...'`, default GET)
  - direct `fetch(...)`, `new EventSource(...)` and URL builders/anchors returning `/api/v1/...`

Usage:
  python scripts/contract_audit.py            # prints a summary, exit 1 on mismatches
  python scripts/contract_audit.py --write    # also writes docs/pilot/API_CONTRACT.md
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend" / "src"
API_PREFIX = "/api/v1"

CALL_RE = re.compile(r"(this\.fetchJson|api\.request|\bfetch|new EventSource)\s*(?:<[^()]*?>)?\s*\(\s*")
URL_RE = re.compile(r"`\$\{API_BASE\}(/[^`]*)`")
CONSTS = {"STREAM_URL": "/api/v1/events/stream", "POLL_URL": "/api/v1/events", "API_BASE": API_PREFIX}


@dataclass
class ClientCall:
    file: str
    line: int
    kind: str
    method: str
    raw: str
    path: Optional[str]          # normalized server path (without /api/v1), None = dynamic
    matched: Optional[str] = None  # "METHOD /openapi/path"
    status: str = "unchecked"     # ok | missing | method_mismatch | dynamic | non_api


def _read_literal(src: str, i: int) -> Optional[str]:
    """Return the string/template literal starting at src[i] (quotes stripped), else None."""
    if i >= len(src) or src[i] not in "'\"`":
        return None
    q = src[i]
    j, depth = i + 1, 0
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if q == "`" and src.startswith("${", j):
            depth += 1
            j += 2
            continue
        if q == "`" and c == "}" and depth:
            depth -= 1
        elif c == q and depth == 0:
            return src[i + 1:j]
        j += 1
    return None


def _resolve_identifier(src: str, at: int, call_pos: int) -> Optional[str]:
    """`fetch(name ...)`: follow `cond ? 'a' : 'b'` or the nearest `const name = ...` above the call."""
    ident = re.match(r"([A-Za-z_][\w.]*)\s*(\?\s*)?", src[at:])
    if not ident:
        return None
    name = ident.group(1)
    if name == "endpoint":
        return None
    if name in CONSTS:
        return "${" + name + "}"
    if ident.group(2):  # ternary: take the first branch literal
        return _read_literal(src, at + ident.end())
    decl = list(re.finditer(r"const\s+" + re.escape(name) + r"\s*=\s*", src[:call_pos]))
    if decl:
        j = decl[-1].end()
        lit = _read_literal(src, j)
        if lit is None:
            t = re.match(r"[^?;\n]*\?\s*", src[j:])
            if t:
                lit = _read_literal(src, j + t.end())
        return lit
    return "${" + name + "}"


def _normalize(raw: str) -> Optional[str]:
    s = raw
    for k, v in CONSTS.items():
        s = s.replace("${" + k + "}", v)
    if s.startswith("${"):
        return None  # fully dynamic endpoint (helper passthrough)
    s = re.split(r"\?|\$\{(?:q|params|qs|query)\b[^}]*\}", s, maxsplit=1)[0]
    s = re.sub(r"\$\{[^}]*\}", "{x}", s)
    if s.startswith(API_PREFIX):
        s = s[len(API_PREFIX):] or "/"
    elif s.startswith("/healthz"):
        pass
    elif not s.startswith("/"):
        return None
    return s.rstrip("/") or "/"


def scan_frontend() -> List[ClientCall]:
    calls: List[ClientCall] = []
    for p in sorted(FRONTEND.rglob("*.ts*")):
        src = p.read_text(encoding="utf-8")
        rel = p.relative_to(ROOT).as_posix()
        for m in CALL_RE.finditer(src):
            if rel.endswith("lib/api.ts") and m.group(1) == "fetch" and "${API_BASE}${endpoint}" in src[m.end():m.end() + 40]:
                continue  # the shared transport itself
            lit = _read_literal(src, m.end())
            line = src.count("\n", 0, m.start()) + 1
            if lit is None:
                lit = _resolve_identifier(src, m.end(), m.start())
                if lit is None:
                    continue  # the generic `request(endpoint)` passthrough
            tail = src[m.end():m.end() + 600]
            stop = re.search(r"\n\s*(public |private |async function|export |const \w+ = async)", tail)
            window = tail[: stop.start()] if stop else tail
            mm = re.search(r"method:\s*'([A-Z]+)'", window)
            method = mm.group(1) if mm else "GET"
            kind = {"this.fetchJson": "client", "api.request": "page", "fetch": "fetch",
                    "new EventSource": "eventsource"}[m.group(1)]
            norm = _normalize(lit)
            calls.append(ClientCall(rel, line, kind, method, lit, norm))
        for m in URL_RE.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            calls.append(ClientCall(rel, line, "url", "GET", m.group(0), _normalize("${API_BASE}" + m.group(1))))
    return calls


def _seg_match(client: str, server: str) -> bool:
    a, b = client.strip("/").split("/"), server.strip("/").split("/")
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y or x == "{x}" or (y.startswith("{") and y.endswith("}")):
            continue
        return False
    return True


def openapi_ops() -> Dict[str, List[str]]:
    os.environ.setdefault("SENTINEL_ENV", "test")
    sys.path.insert(0, str(ROOT))
    from backend.main import app  # noqa: E402

    spec = app.openapi()
    ops: Dict[str, List[str]] = {}
    for path, item in spec["paths"].items():
        p = path[len(API_PREFIX):] if path.startswith(API_PREFIX) else path
        ops[p.rstrip("/") or "/"] = [m.upper() for m in item if m in ("get", "post", "put", "patch", "delete")]
    # Routes excluded from the schema but served by the app (health probes).
    for extra in ("/healthz/live", "/healthz/ready"):
        ops.setdefault(extra, ["GET"])
    return ops


def audit() -> dict:
    ops = openapi_ops()
    calls = scan_frontend()
    used = set()
    for c in calls:
        if c.path is None:
            c.status = "dynamic"
            continue
        cands = [p for p in ops if _seg_match(c.path, p)]
        # Prefer the literal (non-templated) path when several match.
        cands.sort(key=lambda p: p.count("{"))
        hit = next((p for p in cands if c.method in ops[p]), None)
        if hit:
            c.status, c.matched = "ok", f"{c.method} {hit}"
            used.add((c.method, hit))
        elif cands:
            c.status, c.matched = "method_mismatch", f"{'/'.join(ops[cands[0]])} {cands[0]}"
        else:
            c.status = "missing"
    unused = sorted(f"{m} {p}" for p, ms in ops.items() for m in ms if (m, p) not in used)
    return {"operations": sum(len(v) for v in ops.values()), "calls": [asdict(c) for c in calls],
            "unused_operations": unused,
            "summary": {s: sum(1 for c in calls if c.status == s) for s in ("ok", "missing", "method_mismatch", "dynamic")}}


def to_markdown(r: dict) -> str:
    out = ["# Hợp đồng API · console ↔ FastAPI (sinh tự động)", "",
           "Sinh bởi `python scripts/contract_audit.py --write` từ OpenAPI của app thật và mã nguồn `frontend/src`.", "",
           f"- Operation trong OpenAPI: **{r['operations']}**",
           f"- Lời gọi từ client: **{len(r['calls'])}** · khớp {r['summary']['ok']} · thiếu route {r['summary']['missing']} · "
           f"sai method {r['summary']['method_mismatch']} · động {r['summary']['dynamic']}", "",
           "## Lời gọi từ client", "", "| Trạng thái | Method | Path client | Route server | Nơi gọi |", "|---|---|---|---|---|"]
    for c in sorted(r["calls"], key=lambda c: (c["status"] != "ok", c["path"] or "", c["file"])):
        out.append(f"| {c['status']} | {c['method']} | `{c['path'] or c['raw']}` | {c['matched'] or '—'} | "
                   f"`{c['file']}:{c['line']}` ({c['kind']}) |")
    out += ["", "## Operation server chưa có caller trong console", "",
            "Không phải lỗi: phần lớn là API cho CLI/automation, endpoint cũ giữ tương thích hoặc API admin chưa có màn hình.", ""]
    out += [f"- `{u}`" for u in r["unused_operations"]]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    res = audit()
    print(json.dumps(res["summary"]), "operations:", res["operations"], "unused:", len(res["unused_operations"]))
    for c in res["calls"]:
        if c["status"] in ("missing", "method_mismatch"):
            print(f"  {c['status']:16} {c['method']:6} {c['path']}  ({c['file']}:{c['line']})  server: {c['matched']}")
    if "--write" in sys.argv:
        (ROOT / "docs" / "pilot" / "API_CONTRACT.md").write_text(to_markdown(res), encoding="utf-8")
    sys.exit(1 if res["summary"]["missing"] or res["summary"]["method_mismatch"] else 0)
