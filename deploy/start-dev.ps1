# Meldi lokal starten (Windows, Entwicklung/Test).
#   .\deploy\start-dev.ps1 -HostName 192.168.8.10
# Voraussetzungen: uv, Node.js, caddy.exe im PATH oder unter deploy\bin\.
param(
    [string]$HostName = "localhost",
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $SkipBuild) {
    Push-Location "$root\frontend"
    if (-not (Test-Path node_modules)) { npm ci }
    npm run build
    Pop-Location
}

Push-Location "$root\backend"
uv sync
uv run meldi demo   # legt Übungseinsatz + Demo-Benutzer an, falls nicht vorhanden
Pop-Location

$caddyCmd = Get-Command caddy -ErrorAction SilentlyContinue
$caddy = if ($caddyCmd) { $caddyCmd.Source } else { "$root\deploy\bin\caddy.exe" }
$env:MELDI_HOST = $HostName
$caddyProc = Start-Process -FilePath $caddy -ArgumentList "run", "--config", "$root\deploy\Caddyfile" -PassThru -NoNewWindow

Write-Host ""
Write-Host "Melder:  https://$HostName/melder/" -ForegroundColor Green
Write-Host "ELW:     https://$HostName/elw/" -ForegroundColor Green
Write-Host ""

try {
    Push-Location "$root\backend"
    uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
    Stop-Process -Id $caddyProc.Id -ErrorAction SilentlyContinue
}
