# =============================================================================
#   NOOSFORGE SECURITY INTELLIGENCE — CLOUDFLARE TUNNEL AUTOMATION
#   Expose Private Host to Cloudflare Zero Trust without Open Inbound Ports
# =============================================================================

param (
    [string]$TunnelToken = "eyJhIjoiNTdlNzRjNmRiN2E1YmQ0NzQ4NzdmMjZjODQ5MDEwMDkiLCJ0IjoiODIzNDY0YTctM2JmMi00MTgyLWE0MGItY2IwZjFmY2ExOWY4IiwicyI6Ik9HVXdPV1UxTWprdE1UVmxOUzAwTVdJeUxUZ3pNak10TnpaaU16azBPV1UwT0RFNCJ9",
    [switch]$QuickTunnel,
    [switch]$InstallService,
    [switch]$Status,
    [switch]$Stop
)

$CLOUDFLARED_BIN = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $CLOUDFLARED_BIN)) {
    $found = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($found) {
        $CLOUDFLARED_BIN = $found.Source
    } else {
        Write-Host "[-] Khong tim thay cloudflared tren he thong!" -ForegroundColor Red
        Write-Host "[*] Dang cai dat cloudflared qua winget..." -ForegroundColor Yellow
        winget install --id Cloudflare.cloudflared -e --accept-source-agreements --accept-package-agreements
        $CLOUDFLARED_BIN = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    }
}

function Show-Header {
    Write-Host "============================================================================" -ForegroundColor Cyan
    Write-Host "  NOOSFORGE - CLOUDFLARE ZERO TRUST ARGO TUNNEL GATEWAY" -ForegroundColor Cyan
    Write-Host "  Dang nhap Cloudflare: dangnhutnguyen0910@gmail.com" -ForegroundColor DarkGray
    Write-Host "============================================================================" -ForegroundColor Cyan
}

if ($Status) {
    Show-Header
    Write-Host "[*] Kiem tra trang thai cloudflared service..." -ForegroundColor Yellow
    Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
    exit 0
}

if ($Stop) {
    Show-Header
    Write-Host "[*] Dang dung tien trinh tunnel..." -ForegroundColor Yellow
    Stop-Process -Name "cloudflared" -Force -ErrorAction SilentlyContinue
    Stop-Service -Name "cloudflared" -ErrorAction SilentlyContinue
    Write-Host "[+] Da dung toan bo tien trinh Cloudflare Tunnel!" -ForegroundColor Green
    exit 0
}

# 1. Quick Tunnel Mode (TryCloudflare)
if ($QuickTunnel) {
    Show-Header
    Write-Host "`n[*] Khoi chay Quick Tunnel (trycloudflare.com) toi http://localhost:3000..." -ForegroundColor Green
    Write-Host "[*] Giao thuc HTTP/2 duoc thiet lap..." -ForegroundColor Yellow
    & $CLOUDFLARED_BIN tunnel --protocol http2 --url http://localhost:3000
    exit 0
}

# 2. Token-Based Named Tunnel Mode (Production Zero Trust)
if ($TunnelToken -ne "") {
    Show-Header
    if ($InstallService) {
        Write-Host "`n[*] Cai dat cloudflared nhu Windows Service tu dong chay khi khoi dong..." -ForegroundColor Yellow
        & $CLOUDFLARED_BIN service install $TunnelToken
        Start-Service cloudflared
        Write-Host "`n[+] Cloudflare Tunnel Service da duoc cai dat va khoi chay thanh cong!" -ForegroundColor Green
    } else {
        Write-Host "`n[*] Khoi chay Cloudflare Tunnel bang Token toi Zero Trust Edge..." -ForegroundColor Green
        & $CLOUDFLARED_BIN tunnel --protocol http2 run --token $TunnelToken
    }
    exit 0
}

# 3. Interactive Menu
Show-Header
Write-Host ""
Write-Host "  [1] Khoi chay Quick Tunnel (trycloudflare.com - Khong can token, chay ngay)" -ForegroundColor White
Write-Host "  [2] Khoi chay Named Tunnel bang Zero Trust Token (dash.cloudflare.com)" -ForegroundColor White
Write-Host "  [3] Cai dat cloudflared thanh Windows Service chay ngam vinh vien" -ForegroundColor White
Write-Host "  [4] Kiem tra trang thai dich vu" -ForegroundColor White
Write-Host "  [5] Dung tunnel" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Nhap lua chon [1-5]"
switch ($choice) {
    "1" {
        & $CLOUDFLARED_BIN tunnel --protocol http2 --url http://localhost:3000
    }
    "2" {
        $token = Read-Host "Dan ma Cloudflare Tunnel Token cua Dai Ca vao day"
        if ($token) {
            & $CLOUDFLARED_BIN tunnel --protocol http2 run --token $token
        }
    }
    "3" {
        $token = Read-Host "Dan ma Cloudflare Tunnel Token cua Dai Ca de cai service"
        if ($token) {
            & $CLOUDFLARED_BIN service install $token
            Start-Service cloudflared
            Write-Host "[+] Service cai thanh cong!" -ForegroundColor Green
        }
    }
    "4" {
        Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
    }
    "5" {
        Stop-Process -Name "cloudflared" -Force -ErrorAction SilentlyContinue
        Write-Host "[+] Da dung!" -ForegroundColor Green
    }
    default { exit 0 }
}
