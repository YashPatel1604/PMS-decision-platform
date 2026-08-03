# Import prices/benchmarks into Postgres, then rebuild exit / ownership analysis.
# Requires Docker stack running. Refresh alone does NOT populate Open positions %.
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "Checking market-data files inside API container ..." -ForegroundColor Cyan
docker compose exec -T api ls -la /data/external/prices/daily_prices.csv
if ($LASTEXITCODE -ne 0) {
    Write-Host "Missing daily_prices.csv. Set EXTERNAL_DATA_DIR in .env or pull latest repo (docker/market_data_seed)." -ForegroundColor Red
    exit 1
}

Write-Host "Importing market data (prices, dividends, benchmarks) ..." -ForegroundColor Cyan
docker compose exec -T api uv run pms-platform import-market-data
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Analyzing episodes (ownership + post-exit signals) ..." -ForegroundColor Cyan
docker compose exec -T api uv run pms-platform analyze-episodes
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Hard-refresh the browser (Ctrl+F5). Open positions % and exit signals should populate." -ForegroundColor Green
