# =============================================================================
#   NOOSFORGE SECURITY INTELLIGENCE — PRIVATE HOST ORCHESTRATOR (WINDOWS)
#   Production-grade execution harness for self-hosted enterprise deployment
# =============================================================================

param (
    [switch]$WithTunnel,
    [string]$TunnelToken = "",
    [switch]$Check
)

$Host.UI.RawUI.WindowTitle = "NOOSFORGE Private Host Orchestrator"

function Show-Banner {
    Write-Host "============================================================================" -ForegroundColor Cyan
    Write-Host "  NOOSFORGE SECURITY INTELLIGENCE — PRIVATE HOST COMMAND CENTER" -ForegroundColor Cyan
    Write-Host "  Continuous Security Assessment Platform (Self-Hosted Edition)" -ForegroundColor DarkGray
    Write-Host "============================================================================" -ForegroundColor Cyan
}

Show-Banner

if ($Check) {
    Write-Host "`n[*] Chay kiem dinh toan dien he thong..." -ForegroundColor Yellow
    python scripts\verify_empire_e2e.py
    exit $LASTEXITCODE
}

Write-Host "`n[1/3] Khoi dong Backend API & Scan Engine tai 127.0.0.1:8000..." -ForegroundColor Green
$backendProc = Start-Process -FilePath "uvicorn" -ArgumentList "backend.main:app --host 127.0.0.1 --port 8000" -PassThru -NoNewWindow
Start-Sleep -Seconds 2

Write-Host "[2/3] Khoi dong Next.js Liquid Glass SOC Console tai 127.0.0.1:3000..." -ForegroundColor Green
Set-Location frontend
$frontendProc = Start-Process -FilePath "npm" -ArgumentList "run start" -PassThru -NoNewWindow
Set-Location ..
Start-Sleep -Seconds 3

Write-Host "`n[+] He thong Private Host da san sang!" -ForegroundColor Green
Write-Host "    - Frontend SOC Console: http://localhost:3000/dashboard" -ForegroundColor Yellow
Write-Host "    - Backend OpenAPI Spec: http://127.0.0.1:8000/docs" -ForegroundColor Yellow

if ($WithTunnel -or $TunnelToken -ne "") {
    Write-Host "`n[3/3] Khoi dong Cloudflare Zero Trust Tunnel Gateway..." -ForegroundColor Cyan
    $CLOUDFLARED = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    if ($TunnelToken -ne "") {
        & $CLOUDFLARED tunnel --protocol http2 run --token $TunnelToken
    } else {
        & $CLOUDFLARED tunnel --protocol http2 --url http://localhost:3000
    }
} else {
    Write-Host "`n[i] Meo: De mo public link bao mat qua Cloudflare, them tham so -WithTunnel hoac chay deploy\setup_cloudflare_tunnel.ps1" -ForegroundColor DarkGray
    Write-Host "[*] Nhan Ctrl+C de dung toan bo he thong." -ForegroundColor Gray
    
    # Keep alive
    try {
        while ($true) {
            Start-Sleep -Seconds 5
        }
    } finally {
        Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
        Stop-Process -Id $frontendProc.Id -Force -ErrorAction SilentlyContinue
    }
}
