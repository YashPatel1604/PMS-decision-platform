# Daily quotes job: valuation + promoter + price returns -> materialized screener cache.
# Fast (~5-15 min for 200 codes). No quarterly XBRL.
param(
    [int]$WatchlistId = 0
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "Refreshing watchlist quotes (daily) ..." -ForegroundColor Cyan

$cmd = @(
    "docker", "compose", "exec", "-T", "api",
    "uv", "run", "pms-platform", "refresh-watchlist-quotes"
)
if ($WatchlistId -gt 0) {
    $cmd += @("--watchlist-id", "$WatchlistId")
}

& $cmd[0] $cmd[1..($cmd.Length - 1)]
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Screener will load instantly from materialized cache." -ForegroundColor Green
