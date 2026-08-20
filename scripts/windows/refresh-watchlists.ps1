# Watchlist maintenance scripts.
# Daily: alerts only. Manual full refresh: fundamentals then alerts.
# Requires Docker stack running.
param(
    [switch]$SkipFundamentals
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if ($SkipFundamentals) {
    Write-Host "Syncing insider disclosures (last 14 days) ..." -ForegroundColor Cyan
    docker compose exec -T api uv run pms-platform sync-insider-disclosures --days 14
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "Syncing watchlists (resolve + alerts only) ..." -ForegroundColor Cyan
    docker compose exec -T api uv run pms-platform sync-watchlists --external-dir /data/external_seed --skip-fundamentals
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
} else {
    Write-Host "Step 1/3: Full fundamentals (weekly BSE job) ..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "refresh-watchlist-fundamentals.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "Step 2/3: Daily quotes refresh ..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "refresh-watchlist-quotes.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "Step 3/3: Resolve symbols + poll alerts ..." -ForegroundColor Cyan
    docker compose exec -T api uv run pms-platform sync-watchlists --external-dir /data/external_seed --skip-fundamentals
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host ""
Write-Host "Done. Screener reads materialized cache instantly." -ForegroundColor Green
Write-Host "Schedule (run install-watchlist-schedule.ps1 once):" -ForegroundColor Yellow
Write-Host "  Daily 07:00  alerts only" -ForegroundColor Yellow
Write-Host "  Daily 07:15  quotes + screener cache" -ForegroundColor Yellow
Write-Host "  Weekly Sun   full fundamentals" -ForegroundColor Yellow
