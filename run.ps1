# Noospire local launcher (Windows). Single supported local topology:
#   FastAPI  127.0.0.1:8000  (api + worker + scheduler in one process unless -Role is given)
#   Gateway  127.0.0.1:8080  static frontend/out + fixed-origin proxy to the API
# Open http://127.0.0.1:8080/  . No tunnel is opened by this script (see deploy/README_DEPLOY.md).
param(
    [string]$Role = "all",
    [switch]$BuildConsole
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

if (-not $env:SENTINEL_ENV) { $env:SENTINEL_ENV = "development" }
if ($env:SENTINEL_ENV -match "^prod" -and -not $env:SENTINEL_SECRET_KEY) {
    throw "SENTINEL_SECRET_KEY must come from the secret store in production."
}

if ($BuildConsole) {
    Push-Location frontend
    npm ci; if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
    npm run build; if ($LASTEXITCODE -ne 0) { throw "next build failed" }
    Pop-Location
}
if (-not (Test-Path "frontend\out\index.html")) {
    Write-Warning "frontend\out is missing: run .\run.ps1 -BuildConsole (needs Node 20). API is still usable."
}

$env:SENTINEL_PROCESS_ROLE = $Role
$api = Start-Process -FilePath $py -ArgumentList "-m","uvicorn","backend.main:app","--host","127.0.0.1","--port","8000" -PassThru -NoNewWindow

$env:NOOSPIRE_API_ORIGIN = "http://127.0.0.1:8000"
$env:NOOSPIRE_STATIC_DIR = (Resolve-Path "frontend").Path + "\out"
$gw = Start-Process -FilePath $py -ArgumentList "-m","uvicorn","deploy.gateway.gateway:app","--host","127.0.0.1","--port","8080" -PassThru -NoNewWindow

Write-Host "Console: http://127.0.0.1:8080/   API readiness: http://127.0.0.1:8080/healthz/ready"
Write-Host "Press Ctrl+C to stop."
try { Wait-Process -Id $api.Id } finally {
    foreach ($p in @($gw, $api)) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } }
}
