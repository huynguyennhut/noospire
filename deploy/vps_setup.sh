#!/usr/bin/env bash
# =============================================================================
#   NOOSFORGE SECURITY INTELLIGENCE — VPS AUTOMATED DEPLOYMENT SCRIPT
#   Turnkey 1-Command Setup for Ubuntu / Debian / RHEL Cloud VPS
# =============================================================================

set -eo pipefail

echo "============================================================================"
echo "  NOOSFORGE SECURITY INTELLIGENCE — VPS 1-CLICK CLOUD DEPLOYER"
echo "  Deploying Enterprise Continuous Security Platform to Private VPS Host"
echo "============================================================================"

# Check root privileges
if [ "$EUID" -ne 0 ]; then
  echo "[-] Vui long chay voi quyen root (sudo bash deploy/vps_setup.sh)"
  exit 1
fi

echo "[1/5] Cap nhat he thong va cai dat cac goi tien ich..."
apt-get update -qq
apt-get install -y -qq curl wget git build-essential ufw apt-transport-https ca-certificates gnupg

echo "[2/5] Cai dat Docker & Docker Compose..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable --now docker
fi

echo "[3/5] Cai dat cloudflared (Cloudflare Tunnel Client)..."
if ! command -v cloudflared &> /dev/null; then
    curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
    echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' | tee /etc/apt/sources.list.d/cloudflared.list
    apt-get update -qq && apt-get install -y -qq cloudflared
fi

echo "[4/5] Khoi tao thu muc du lieu va phan quyen..."
mkdir -p storage/reports storage/evidence
chmod -R 775 storage

echo "[5/5] Khoi chay he thong container Noosforge qua Docker Compose..."
if [ -f "deploy/docker-compose.yml" ]; then
    docker compose -f deploy/docker-compose.yml up -d --build
    echo ""
    echo "============================================================================"
    echo "  [+] XANH MUOT! NOOSFORGE DA KHOI CHAY HOAN TAT TREN VPS!"
    echo "  - SOC Console (Next.js): http://$(curl -s ifconfig.me):3000/dashboard"
    echo "  - Backend API (FastAPI): http://$(curl -s ifconfig.me):8000/docs"
    echo "============================================================================"
else
    echo "[-] Khong tim thay deploy/docker-compose.yml!"
    exit 1
fi
