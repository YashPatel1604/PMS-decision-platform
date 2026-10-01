# Download NSE CM-UDiFF Common Bhavcopy Final and commit.
# Manual only. Pass -Date YYYY-MM-DD for a specific session; otherwise today IST.
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
    Write-Host "Upload the zip on Pivot Point Strategy, or rerun this script with -Date YYYY-MM-DD." -ForegroundColor Yellow
    exit $code
}

Write-Host ""
Write-Host "Done (fetched or already had today)." -ForegroundColor Green
