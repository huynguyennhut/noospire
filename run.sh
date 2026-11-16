#!/usr/bin/env bash
# Loopback local console; opt in to durable defensive jobs with --enable-jobs.
set -euo pipefail
cd "$(dirname "$0")"
PY=python3
[ ! -x .venv/bin/python ] || PY=.venv/bin/python
if [ "$#" -eq 0 ]; then set -- start; fi
if [[ "${1:-}" == --* ]]; then set -- start "$@"; fi
exec "$PY" scripts/local_stack.py "$@"
