# ============================================================================
#   NOOSFORGE SECURITY INTELLIGENCE -- EMPIRE COMBAT PLATFORM LAUNCHER
#   Continuous Security Assessment, Attack Surface Monitoring & Remediation
# ============================================================================

param (
    [string]$Preset = "",
    [switch]$Check,
    [switch]$Backend,
    [switch]$Frontend,
    [switch]$HostServer,
    [switch]$Tunnel,
    [switch]$Y
)

function Show-Header {
    Write-Host "============================================================================" -ForegroundColor Cyan
    Write-Host "  NOOSFORGE SECURITY INTELLIGENCE (EMPIRE PLATFORM v16.0.0 APEX)" -ForegroundColor Cyan
    Write-Host "  Chien Truong Tac Chien An Ninh Mang Toan Dien Cho Empire" -ForegroundColor Cyan
    Write-Host "============================================================================" -ForegroundColor Cyan
}

function Run-Check {
    Write-Host "`n[*] Dang kich hoat Doctor va E2E Capability Verification Suite..." -ForegroundColor Yellow
    python scripts\verify_empire_e2e.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "`n[+] HE THONG XANH MUOT 100% - SAN SANG TAC CHIEN!`n" -ForegroundColor Green
    } else {
        Write-Host "`n[-] BAO DONG DO: He thong gap su co kiem dinh!`n" -ForegroundColor Red
        exit 1
    }
}

function Run-Backend {
    Write-Host "`n[*] Khoi chay Backend FastAPI tai http://127.0.0.1:8000..." -ForegroundColor Cyan
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
}

function Run-Frontend {
    Write-Host "`n[*] Khoi chay Frontend Next.js tai http://localhost:3000..." -ForegroundColor Cyan
    Set-Location frontend
    npm run dev
}

function Run-All {
    Show-Header
    Write-Host "`n[*] Dang xuat quan toan bo he thong..." -ForegroundColor Green
    Write-Host "[*] Khoi dong Backend API tai cua khau port 8000..." -ForegroundColor Cyan
    Start-Process cmd.exe -ArgumentList '/c', 'uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload'

    Write-Host "[*] Khoi dong Frontend Cyber-Slate UI tai cua khau port 3000..." -ForegroundColor Cyan
    Start-Process cmd.exe -ArgumentList '/c', 'cd frontend && npm run dev'

    Write-Host "[*] Dang mo trinh duyet web vao thang Dashboard..." -ForegroundColor Cyan
    Start-Sleep -Seconds 3
    Start-Process "http://localhost:3000/dashboard"

    Write-Host "`n[+] He thong da khoi dong thanh cong hai cua khau tac chien!" -ForegroundColor Green
    Write-Host "    - Backend API & Docs:   http://127.0.0.1:8000/docs" -ForegroundColor Yellow
    Write-Host "    - SOC Console Dashboard: http://localhost:3000/dashboard" -ForegroundColor Yellow
    Write-Host "    - Empire Modules:        http://localhost:3000/empire-modules" -ForegroundColor Yellow
    Write-Host "`nNhan phim bat ky de tiep tuc..." -ForegroundColor Gray
}

# Check direct arguments
if ($Check -or ($args -contains "--check") -or ($args -contains "doctor") -or ($args -contains "verify") -or ($args -contains "check")) {
    Run-Check
    exit 0
}

if ($Preset -eq "all" -or ($args -contains "--preset" -and $args -contains "all")) {
    Run-All
    exit 0
}

if ($Backend -or ($args -contains "--backend")) {
    Run-Backend
    exit 0
}

if ($Frontend -or ($args -contains "--frontend")) {
    Run-Frontend
    exit 0
}

if ($HostServer -or $Tunnel -or ($args -contains "--host") -or ($args -contains "--tunnel")) {
    & .\deploy\run_private_host.ps1 -WithTunnel
    exit 0
}

# Interactive Menu
Clear-Host
Show-Header
Write-Host ""
Write-Host "  [1] Khoi chay toan bo he thong (Backend + Frontend Next.js)" -ForegroundColor White
Write-Host "  [2] Kiem dinh & Chan doan he thong (Doctor / 10 E2E Capability Tests)" -ForegroundColor White
Write-Host "  [3] Chi chay Backend API FastAPI (Port 8000)" -ForegroundColor White
Write-Host "  [4] Chi chay Frontend Next.js Dark Mode (Port 3000)" -ForegroundColor White
Write-Host "  [5] Tu dong hoa Private Host & Cloudflare Tunnel (Mo ra Internet)" -ForegroundColor White
Write-Host "  [6] Thoat" -ForegroundColor White
Write-Host ""
$choice = Read-Host "Lua chon lenh tac chien [1-6]"

switch ($choice) {
    "1" { Run-All }
    "2" { Run-Check }
    "3" { Run-Backend }
    "4" { Run-Frontend }
    "5" { & .\deploy\run_private_host.ps1 -WithTunnel }
    default { exit 0 }
}
