@echo off
setlocal enabledelayedexpansion

REM ============================================================================
REM   NOOSFORGE SECURITY INTELLIGENCE — EMPIRE COMBAT PLATFORM LAUNCHER
REM   Continuous Security Assessment, Attack Surface Monitoring & Remediation
REM ============================================================================

title NOOSFORGE Security Intelligence — Empire Platform

if "%~1"=="--check" goto DO_CHECK
if "%~1"=="doctor" goto DO_CHECK
if "%~1"=="verify" goto DO_CHECK
if "%~1"=="check" goto DO_CHECK
if "%~1"=="--test" goto DO_CHECK

if "%~1"=="--preset" (
    if "%~2"=="all" goto DO_RUN_ALL
)

if "%~1"=="--backend" goto DO_RUN_BACKEND
if "%~1"=="--frontend" goto DO_RUN_FRONTEND
if "%~1"=="--host" goto DO_RUN_HOST
if "%~1"=="--tunnel" goto DO_RUN_HOST

:MENU
cls
echo ============================================================================
echo   NOOSFORGE SECURITY INTELLIGENCE (EMPIRE PLATFORM v16.0.0 APEX)
echo   Chien Truong Tac Chien An Ninh Mang Toan Dien Cho Empire
echo ============================================================================
echo.
echo   [1] Khoi chay toan bo he thong (Backend + Frontend Next.js)
echo   [2] Kiem dinh & Chan doan he thong (Doctor / 10 E2E Capability Tests)
echo   [3] Chi chay Backend API FastAPI (Port 8000)
echo   [4] Chi chay Frontend Next.js Dark Mode (Port 3000)
echo   [5] Tu dong hoa Private Host & Cloudflare Tunnel (Ra Internet)
echo   [6] Thoat
echo.
set /p CHOICE="Lua chon lenh tac chien [1-6]: "

if "%CHOICE%"=="1" goto DO_RUN_ALL
if "%CHOICE%"=="2" goto DO_CHECK
if "%CHOICE%"=="3" goto DO_RUN_BACKEND
if "%CHOICE%"=="4" goto DO_RUN_FRONTEND
if "%CHOICE%"=="5" goto DO_RUN_HOST
if "%CHOICE%"=="6" exit /b 0
goto MENU

:DO_CHECK
echo.
echo [*] Dang kich hoat Doctor va E2E Capability Verification Suite...
python scripts\verify_empire_e2e.py
if %ERRORLEVEL% equ 0 (
    echo.
    echo [+] HE THONG XANH MUOT 100%% - SAN SANG TAC CHIEN!
) else (
    echo.
    echo [-] BAO DONG DO: He thong gap su co kiem dinh!
)
exit /b %ERRORLEVEL%

:DO_RUN_BACKEND
echo.
echo [*] Khoi chay Backend FastAPI tai http://127.0.0.1:8000...
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
exit /b 0

:DO_RUN_FRONTEND
echo.
echo [*] Khoi chay Frontend Next.js tai http://localhost:3000...
cd frontend
npm run dev
exit /b 0

:DO_RUN_ALL
echo.
echo ============================================================================
echo   DANG XUAT QUAN TOAN HE THONG NOOSFORGE SECURITY INTELLIGENCE
echo ============================================================================
echo [*] Khoi dong Backend API tai cua khau port 8000...
start "NOOSFORGE Backend Engine" cmd /c "uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

echo [*] Khoi dong Frontend Cyber-Slate UI tai cua khau port 3000...
start "NOOSFORGE Cyber UI" cmd /c "cd frontend && npm run dev"

echo [*] Dang mo trinh duyet web vao thang Dashboard...
timeout /t 3 /nobreak >nul
start http://localhost:3000/dashboard

echo.
echo [+] He thong da khoi dong thanh cong hai cua khau tac chien!
echo     - Backend API & Docs: http://127.0.0.1:8000/docs
echo     - SOC Console Dashboard: http://localhost:3000/dashboard
echo     - Empire Modules: http://localhost:3000/empire-modules
echo.
pause
exit /b 0

:DO_RUN_HOST
call auto_host.cmd
exit /b 0
