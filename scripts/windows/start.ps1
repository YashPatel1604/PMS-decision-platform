# Start PMS Decision Platform (Docker Desktop must be running)
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if (-not (Test-Path ".env")) {
    Write-Host "Missing .env — copy .env.example to .env and set RESEARCH_DIR." -ForegroundColor Red
    exit 1
}

$envContent = Get-Content ".env" -Raw
if ($envContent -notmatch "(?m)^RESEARCH_DIR=.+") {
    Write-Host "Set RESEARCH_DIR in .env to your Research folder (contains Portfolio)." -ForegroundColor Red
    exit 1
}

Write-Host "Building and starting postgres + api + ui ..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
docker compose ps
Write-Host ""
Write-Host "Open http://localhost:3000  then click Refresh data on first run." -ForegroundColor Green
