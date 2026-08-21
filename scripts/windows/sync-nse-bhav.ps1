# Download NSE CM-UDiFF Common Bhavcopy Final for today (IST) and commit.
# Scheduled at 17:00 IST and again at 17:15 IST. No older-day fallback —
# if both miss, upload manually on Pivot Point Strategy.
param(
    [string]$Date = ""
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

Write-Host "Fetching NSE CM-UDiFF Final bhav for today IST (skip if already committed) ..." -ForegroundColor Cyan

$cmd = @(
    "docker", "compose", "exec", "-T", "api",
    "uv", "run", "pms-platform", "fetch-bhav-day"
)
if ($Date) {
    $cmd += @("--date", $Date)
}

& $cmd[0] $cmd[1..($cmd.Length - 1)]
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host ""
    Write-Host "Final bhav not available yet (or download failed)." -ForegroundColor Yellow
    Write-Host "Next auto try: 17:15 IST (skipped if today is already uploaded). After that, upload manually on Pivot Point Strategy." -ForegroundColor Yellow
    exit $code
}

Write-Host ""
Write-Host "Done (fetched or already had today)." -ForegroundColor Green
