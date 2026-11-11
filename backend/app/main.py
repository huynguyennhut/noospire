"""Canonical ASGI Application Entrypoint for Noosforge Sentinel.

Exposes the FastAPI application instance `app` for Uvicorn and ASGI servers
targeting `backend.app.main:app`, while maintaining full interoperability
with `backend.main:app`.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from backend.main import app, create_app, lifespan

__all__ = ["app", "create_app", "lifespan"]

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
