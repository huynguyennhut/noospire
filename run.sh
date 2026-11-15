#!/usr/bin/env bash
# Noospire local launcher (Linux/macOS). Same topology as run.ps1:
#   FastAPI 127.0.0.1:8000, gateway 127.0.0.1:8080 (static frontend/out + fixed API origin).
set -euo pipefail
cd "$(dirname "$0")"
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
export SENTINEL_ENV="${SENTINEL_ENV:-development}"
export SENTINEL_PROCESS_ROLE="${SENTINEL_PROCESS_ROLE:-all}"

if [ "${1:-}" = "--build-console" ]; then (cd frontend && npm ci && npm run build); fi
[ -f frontend/out/index.html ] || echo "WARN: frontend/out missing; run ./run.sh --build-console (Node 20)." >&2

GW_HOST="${NOOSPIRE_GW_HOST:-0.0.0.0}"
GW_PORT="${NOOSPIRE_GW_PORT:-8080}"

"$PY" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 & API=$!
NOOSPIRE_API_ORIGIN=http://127.0.0.1:8000 NOOSPIRE_STATIC_DIR="$PWD/frontend/out" \
  "$PY" -m uvicorn deploy.gateway.gateway:app --host "$GW_HOST" --port "$GW_PORT" & GW=$!
trap 'kill $GW $API 2>/dev/null || true' EXIT INT TERM
echo "Console: http://localhost:${GW_PORT}/   readiness: http://localhost:${GW_PORT}/healthz/ready"
wait $API
