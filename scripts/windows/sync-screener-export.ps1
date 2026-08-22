# Daily Screener export sync: import CSV/XLSX → BSE gap-fill → metrics cache.
# Drop the newest Screener.in Export into data/external/fundamentals/screener/
# (or the OneDrive external mount) before this runs.
param(
    [int]$WatchlistId = 0,
    [string]$Export = ""
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "Syncing Screener export + BSE gaps ..." -ForegroundColor Cyan

$cmd = @(
    "docker", "compose", "exec", "-T", "api",
    "uv", "run", "pms-platform", "sync-screener-export"
)
if ($WatchlistId -gt 0) {
    $cmd += @("--watchlist-id", "$WatchlistId")
}
if ($Export -ne "") {
    $cmd += @("--export", $Export)
}

& $cmd[0] $cmd[1..($cmd.Length - 1)]
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Done. Watchlist screener cache rebuilt." -ForegroundColor Green
