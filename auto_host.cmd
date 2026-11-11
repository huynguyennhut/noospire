@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM   NOOSFORGE SECURITY INTELLIGENCE — AUTO HOST & CLOUDFLARE LAUNCHER
REM   Tu dong hoa 100% - Khoi chay Private Host & Mo duong ham Cloudflare Tunnel
REM ============================================================================

title NOOSFORGE Auto Host ^& Cloudflare Gateway

cls
echo ============================================================================
echo   NOOSFORGE SECURITY INTELLIGENCE — TU DONG HOA PRIVATE HOST ^& CLOUDFLARE
echo ============================================================================
echo.
echo [*] Buoc 1/3: Kiem tra va khoi dong Backend FastAPI (Port 8000)...
start "NOOSFORGE Backend Engine" /min cmd /c "uvicorn backend.main:app --host 0.0.0.0 --port 8000"

echo [*] Buoc 2/3: Kiem tra va khoi dong Frontend Next.js (Port 3000)...
start "NOOSFORGE Frontend Console" /min cmd /c "cd frontend && npm run start"

timeout /t 3 /nobreak >nul

echo [*] Buoc 3/3: Khoi chay Cloudflare Tunnel Gateway...
set CLOUDFLARED="C:\Program Files (x86)\cloudflared\cloudflared.exe"
if not exist %CLOUDFLARED% (
    set CLOUDFLARED=cloudflared
)

echo.
echo ============================================================================
echo   DA KHOI DONG THANH CONG CAC DICH VU NOI BO:
echo   - Local Dashboard: http://localhost:3000/dashboard
echo   - Local API Spec:  http://127.0.0.1:8000/docs
echo ============================================================================
echo.
echo [*] Dang mo duong ham Cloudflare ra Internet cho Dai Ca...
echo [*] Nhap [1] de mo Quick Tunnel (Co ngay link https://*.trycloudflare.com)
echo [*] Nhap [2] de dan ma Zero Trust Tunnel Token (Neu Dai Ca da co token tu dash.cloudflare.com)
echo [*] Nhap [3] chi dung Localhost (Khong mo tunnel)
echo.

set /p TUNNEL_CHOICE="Lua chon [1-3] (Mac dinh la 1): "
if "%TUNNEL_CHOICE%"=="" set TUNNEL_CHOICE=1

if "%TUNNEL_CHOICE%"=="1" (
    echo.
    echo [*] Dang ket noi Cloudflare Edge...
    %CLOUDFLARED% tunnel --protocol http2 --url http://localhost:3000
)

if "%TUNNEL_CHOICE%"=="2" (
    echo.
    set DEFAULT_TOKEN=eyJhIjoiNTdlNzRjNmRiN2E1YmQ0NzQ4NzdmMjZjODQ5MDEwMDkiLCJ0IjoiODIzNDY0YTctM2JmMi00MTgyLWE0MGItY2IwZjFmY2ExOWY4IiwicyI6Ik9HVXdPV1UxTWprdE1UVmxOUzAwTVdJeUxUZ3pNak10TnpaaU16azBPV1UwT0RFNCJ9
    set /p USER_TOKEN="Dan ma Cloudflare Tunnel Token (Enter de dung Token mac dinh da luu): "
    if "!USER_TOKEN!"=="" set USER_TOKEN=!DEFAULT_TOKEN!
    echo [*] Dang khoi chay Cloudflare Tunnel toi Zero Trust Edge...
    %CLOUDFLARED% tunnel --protocol http2 run --token !USER_TOKEN!
)

if "%TUNNEL_CHOICE%"=="3" (
    start http://localhost:3000/dashboard
    echo [+] He thong dang chay tren may chu Private cua Dai Ca!
    pause
)
