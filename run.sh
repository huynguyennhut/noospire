#!/usr/bin/env bash
# ============================================================================
#   NOOSFORGE SECURITY INTELLIGENCE — EMPIRE COMBAT PLATFORM LAUNCHER
#   Continuous Security Assessment, Attack Surface Monitoring & Remediation
# ============================================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

do_check() {
    echo -e "\033[1;36m[*] Kích hoạt Doctor & E2E Capability Verification Suite...\033[0m"
    python3 scripts/verify_empire_e2e.py
    if [ $? -eq 0 ]; then
        echo -e "\n\033[1;32m[+] HỆ THỐNG XANH MƯỢT 100% — SẴN SÀNG TÁC CHIẾN!\033[0m"
    else
        echo -e "\n\033[1;31m[-] BÁO ĐỘNG ĐỎ: Hệ thống gặp sự cố kiểm định!\033[0m"
        exit 1
    fi
}

do_backend() {
    echo -e "\033[1;36m[*] Khởi chạy Backend FastAPI tại http://127.0.0.1:8000...\033[0m"
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
}

do_frontend() {
    echo -e "\033[1;36m[*] Khởi chạy Frontend Next.js tại http://localhost:3000...\033[0m"
    cd frontend && npm run dev
}

do_all() {
    echo -e "\033[1;32m====================================================================\033[0m"
    echo -e "\033[1;32m   ĐANG XUẤT QUÂN TOÀN HỆ THỐNG NOOSFORGE SECURITY INTELLIGENCE\033[0m"
    echo -e "\033[1;32m====================================================================\033[0m"
    
    echo -e "\033[1;34m[*] Khởi chạy Backend API (Port 8000)...\033[0m"
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
    BACKEND_PID=$!
    
    echo -e "\033[1;34m[*] Khởi chạy Frontend Next.js (Port 3000)...\033[0m"
    (cd frontend && npm run dev) &
    FRONTEND_PID=$!
    
    trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM
    
    echo -e "\n\033[1;32m[+] Hệ thống đang vận hành!\033[0m"
    echo -e "    - Backend API Docs: http://127.0.0.1:8000/docs"
    echo -e "    - Dashboard UI:     http://localhost:3000/dashboard"
    echo -e "    (Nhấn Ctrl+C để hạ cờ giải tán)\n"
    
    wait
}

case "$1" in
    --check|doctor|verify|check|--test)
        do_check
        ;;
    --backend)
        do_backend
        ;;
    --frontend)
        do_frontend
        ;;
    --preset)
        if [ "$2" == "all" ]; then
            do_all
        else
            echo "Unknown preset: $2"
            exit 1
        fi
        ;;
    all|"")
        do_all
        ;;
    *)
        echo "Usage: ./run.sh [--check|--preset all|--backend|--frontend]"
        exit 1
        ;;
esac
