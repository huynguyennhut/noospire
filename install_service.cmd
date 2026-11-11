@echo off
title NOOSFORGE - Cloudflare Tunnel Service Installer

:: ============================================================================
:: Tu dong xin quyen Administrator (UAC Self-Elevation)
:: ============================================================================
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if '%errorlevel%' NEQ '0' (
    echo [*] Dang yeu cau quyen Administrator de cai dat Windows Service...
    echo Set UAC = CreateObject^("Shell.Application"^) > "%temp%\getadmin.vbs"
    echo UAC.ShellExecute "%~s0", "", "", "runas", 1 >> "%temp%\getadmin.vbs"
    "%temp%\getadmin.vbs"
    exit /B
)
if exist "%temp%\getadmin.vbs" ( del "%temp%\getadmin.vbs" )
pushd "%CD%"
CD /D "%~dp0"

cls
echo ============================================================================
echo   NOOSFORGE SECURITY INTELLIGENCE — CAI DAT CLOUDFLARE SERVICE
echo   Tu dong dang ky Windows Service chay ngam 24/7 vinh vien
echo ============================================================================
echo.

set BIN="C:\Program Files (x86)\cloudflared\cloudflared.exe"
if not exist %BIN% (
    echo [-] Khong tim thay cloudflared.exe tai: %BIN%
    pause
    exit /b 1
)

set TOKEN=eyJhIjoiNTdlNzRjNmRiN2E1YmQ0NzQ4NzdmMjZjODQ5MDEwMDkiLCJ0IjoiODIzNDY0YTctM2JmMi00MTgyLWE0MGItY2IwZjFmY2ExOWY4IiwicyI6Ik9HVXdPV1UxTWprdE1UVmxOUzAwTVdJeUxUZ3pNak10TnpaaU16azBPV1UwT0RFNCJ9

echo [*] Buoc 1/2: Dang dang ky Windows Service vao he thong...
%BIN% service install %TOKEN%

echo.
echo [*] Buoc 2/2: Dang khoi dong Windows Service 'cloudflared'...
sc start cloudflared
sc config cloudflared start= auto

echo.
echo ============================================================================
echo   [+] XANH MUOT 100%%! DICH VU CLOUDFLARE TUNNEL DA HOAT DONG!
echo   - Trang thai: Windows Service 'cloudflared' chay ngam 24/7 tu dong khoi dong cung Windows
echo   - Edge Tunnel: Ket noi vao Cloudflare Zero Trust Network cua Dai Ca
echo ============================================================================
echo.
pause
