# Pull latest code from GitHub and rebuild containers
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "Pulling from origin ..." -ForegroundColor Cyan
git pull
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Rebuilding and restarting containers ..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
docker compose ps
Write-Host ""
Write-Host "Done. Hard-refresh the browser (Ctrl+F5)." -ForegroundColor Green
