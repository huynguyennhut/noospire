"""Private operator CLI (run on the host, never exposed over HTTP).

    python -m backend.app.cli bootstrap-owner --username owner [--password-stdin]
    python -m backend.app.cli init-db
    python -m backend.app.cli backup --out backups/noospire-YYYYmmddTHHMMSSZ.db
    python -m backend.app.cli restore-check --backup backups/x.db

The owner email and immutable ID come from settings (SENTINEL_SOLE_OWNER_EMAIL,
SENTINEL_SOLE_OWNER_ACCOUNT_ID). The password is read from stdin or an interactive
prompt; it is never accepted as a command-line argument (shell history / process list).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.app.core.config import settings  # noqa: E402


def _sqlite_path() -> Path:
    url = settings.DATABASE_URL
    if not url.startswith("sqlite"):
        raise SystemExit("backup/restore-check helpers support SQLite only; use pg_dump/pg_restore for PostgreSQL.")
    return Path(url.split("///", 1)[1])


async def _bootstrap(username: str, password: str) -> int:
    from fastapi import HTTPException

    from backend.app.api.auth import bootstrap_owner
    from backend.app.core.database import AsyncSessionLocal, init_db

    await init_db()
    async with AsyncSessionLocal() as db:
        try:
            owner = await bootstrap_owner(db, username, settings.SOLE_OWNER_EMAIL, password)
        except HTTPException as exc:
            print(f"bootstrap refused: {exc.detail}", file=sys.stderr)
            return 2
    print(f"sole owner created id={owner.id} email={owner.email}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="noospire")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bootstrap-owner")
    b.add_argument("--username", required=True)
    b.add_argument("--password-stdin", action="store_true")
    sub.add_parser("init-db")
    bk = sub.add_parser("backup")
    bk.add_argument("--out", required=False)
    rc = sub.add_parser("restore-check")
    rc.add_argument("--backup", required=True)
    args = ap.parse_args(argv)

    if args.cmd == "bootstrap-owner":
        if args.password_stdin:
            password = sys.stdin.readline().rstrip("\r\n")
        else:
            password = getpass.getpass("Owner password (min 12 chars): ")
            if password != getpass.getpass("Repeat: "):
                print("passwords differ", file=sys.stderr)
                return 2
        return asyncio.run(_bootstrap(args.username, password))

    if args.cmd == "init-db":
        from backend.app.core.database import init_db
        asyncio.run(init_db())
        print("schema ready")
        return 0

    if args.cmd == "backup":
        src = _sqlite_path()
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = Path(args.out or f"backups/noospire-{stamp}.db")
        out.parent.mkdir(parents=True, exist_ok=True)
        # sqlite3 online backup API: consistent snapshot even with WAL and live writers.
        with sqlite3.connect(src) as s, sqlite3.connect(out) as d:
            s.backup(d)
        print(f"backup written {out}")
        return 0

    if args.cmd == "restore-check":
        # Restore into a fresh scratch DB and verify integrity + row counts.
        bk = Path(args.backup)
        scratch = bk.with_suffix(".restore-check.db")
        if scratch.exists():
            scratch.unlink()
        with sqlite3.connect(bk) as s, sqlite3.connect(scratch) as d:
            s.backup(d)
        with sqlite3.connect(scratch) as d:
            ok = d.execute("PRAGMA integrity_check").fetchone()[0]
            tables = [r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            for t in tables:
                n = d.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                print(f"{t}\t{n}")
        scratch.unlink()
        print(f"integrity_check={ok}")
        return 0 if ok == "ok" else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
