# Scheduled fundamentals job: BSE fetch -> DB write -> snapshot recompute.
# Screener reads persisted data only; run this on a weekly cadence.
# Requires Docker stack running and FUNDAMENTALS_PROVIDER=xbrl in .env
param(
    [int]$WatchlistId = 0
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "Refreshing watchlist fundamentals (BSE -> DB -> snapshots) ..." -ForegroundColor Cyan

$cmd = @(
    "docker", "compose", "exec", "-T", "api",
    "uv", "run", "pms-platform", "refresh-watchlist-fundamentals",
    "--external-dir", "/data/external_seed"
)
if ($WatchlistId -gt 0) {
    $cmd += @("--watchlist-id", "$WatchlistId")
}

& $cmd[0] $cmd[1..($cmd.Length - 1)]
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Open the Screener tab — data is served from the database (no live BSE calls)." -ForegroundColor Green
