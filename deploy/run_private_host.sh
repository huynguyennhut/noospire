#!/usr/bin/env bash
# =============================================================================
#   NOOSFORGE SECURITY INTELLIGENCE — PRIVATE HOST ORCHESTRATOR (LINUX)
#   Production-grade execution harness for self-hosted enterprise deployment
# =============================================================================

set -eo pipefail

echo "============================================================================"
echo "  NOOSFORGE SECURITY INTELLIGENCE — PRIVATE HOST LINUX LAUNCHER"
echo "  Continuous Security Assessment Platform (Self-Hosted Edition)"
echo "============================================================================"

# Ensure database directory exists
mkdir -p storage/reports storage/evidence

echo "[1/3] Khoi dong Backend API tai 127.0.0.1:8000..."
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --workers 2 &
BACKEND_PID=$!

echo "[2/3] Khoi dong Next.js Liquid Glass Console tai 127.0.0.1:3000..."
cd frontend
npm run start &
FRONTEND_PID=$!
cd ..

cleanup() {
    echo ""
    echo "[*] Dang tat cac tien trinh..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo "[+] Da dung toan bo he thong!"
}
trap cleanup EXIT INT TERM

echo ""
echo "[+] He thong Private Host da san sang!"
echo "    - Frontend SOC Console: http://localhost:3000/dashboard"
echo "    - Backend OpenAPI Spec: http://127.0.0.1:8000/docs"
echo ""

if [ -n "$TUNNEL_TOKEN" ]; then
    echo "[3/3] Khoi dong Cloudflare Tunnel voi token..."
    cloudflared tunnel run --token "$TUNNEL_TOKEN"
else
    echo "[*] Nhan Ctrl+C de ket thuc tien trinh."
    wait
fi
