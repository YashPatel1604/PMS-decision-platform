# Refresh watchlists: resolve symbols, fundamentals CSV, SAST/insider alerts.
# Requires Docker stack running.
param(
    [switch]$SkipFundamentals
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

$extra = ""
if ($SkipFundamentals) {
    $extra = "--skip-fundamentals"
}

Write-Host "Syncing watchlists (resolve + fundamentals + alerts) ..." -ForegroundColor Cyan
if ($extra) {
    docker compose exec -T api uv run pms-platform sync-watchlists --external-dir /data/external_seed $extra
} else {
    docker compose exec -T api uv run pms-platform sync-watchlists --external-dir /data/external_seed
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Open Watchlists in the browser and check the Screener + Alerts strip." -ForegroundColor Green
Write-Host "Suggested Task Scheduler cadence:" -ForegroundColor Yellow
Write-Host "  - Daily (morning):  .\scripts\windows\refresh-watchlists.ps1 -SkipFundamentals" -ForegroundColor Yellow
Write-Host "  - Weekly (Sunday):  .\scripts\windows\refresh-watchlists.ps1" -ForegroundColor Yellow
