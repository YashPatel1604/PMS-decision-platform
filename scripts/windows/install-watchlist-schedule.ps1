# Register Windows Task Scheduler jobs for watchlist maintenance + NSE bhav.
# All times are local clock — set the PC timezone to India Standard Time (IST).
# Run once from PowerShell (elevated if access denied).
param(
    [string]$AlertsTime = "07:00",
    [string]$QuotesTime = "07:15",
    [string]$ScreenerTime = "18:30",
    [string]$BhavTime = "17:00",
    [string]$BhavRetryTime = "17:15",
    [string]$WeeklyDay = "Sunday",
    [string]$WeeklyTime = "03:00"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$AlertsScript = Join-Path $Root "scripts\windows\refresh-watchlists.ps1"
$QuotesScript = Join-Path $Root "scripts\windows\refresh-watchlist-quotes.ps1"
$ScreenerScript = Join-Path $Root "scripts\windows\sync-screener-export.ps1"
$WeeklyScript = Join-Path $Root "scripts\windows\refresh-watchlist-fundamentals.ps1"
$BhavScript = Join-Path $Root "scripts\windows\sync-nse-bhav.ps1"

foreach ($path in @($AlertsScript, $QuotesScript, $ScreenerScript, $WeeklyScript, $BhavScript)) {
    if (-not (Test-Path $path)) { throw "Missing $path" }
}

# Drop older single-shot bhav task if present (replaced by 17:00 + 17:15).
Unregister-ScheduledTask -TaskName "PMS NSE Bhav Final" -Confirm:$false -ErrorAction SilentlyContinue

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable

Register-ScheduledTask -TaskName "PMS Watchlist Alerts" `
    -Description "Daily SAST/insider alert poll (no BSE fundamentals)." `
    -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$AlertsScript`" -SkipFundamentals") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $AlertsTime) `
    -Settings $Settings -Force | Out-Null

Register-ScheduledTask -TaskName "PMS Watchlist Quotes" `
    -Description "Daily valuation + promoter + materialized screener cache (~200 stocks)." `
    -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$QuotesScript`"") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $QuotesTime) `
    -Settings $Settings -Force | Out-Null

Register-ScheduledTask -TaskName "PMS Screener Export Sync" `
    -Description "Daily Screener.in CSV/XLSX import + BSE gap-fill + screener cache (drop file in fundamentals/screener/ first)." `
    -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScreenerScript`"") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $ScreenerTime) `
    -Settings $Settings -Force | Out-Null

Register-ScheduledTask -TaskName "PMS NSE Bhav Final 17:00" `
    -Description "IST 17:00 — NSE CM-UDiFF Common Bhavcopy Final (today only)." `
    -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$BhavScript`"") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $BhavTime) `
    -Settings $Settings -Force | Out-Null

Register-ScheduledTask -TaskName "PMS NSE Bhav Final 17:15" `
    -Description "IST 17:15 retry — same day only; after this Dad uploads manually if still missing." `
    -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$BhavScript`"") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At $BhavRetryTime) `
    -Settings $Settings -Force | Out-Null

Register-ScheduledTask -TaskName "PMS Watchlist Fundamentals" `
    -Description "Weekly full BSE quarterly + annual + snapshot recompute (overnight)." `
    -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WeeklyScript`"") `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $WeeklyDay -At $WeeklyTime) `
    -Settings $Settings -Force | Out-Null

Write-Host "Registered scheduled tasks (PC clock must be IST):" -ForegroundColor Green
Write-Host "  PMS Watchlist Alerts         — daily $AlertsTime IST"
Write-Host "  PMS Watchlist Quotes         — daily $QuotesTime IST"
Write-Host "  PMS Screener Export Sync     — daily $ScreenerTime IST (drop Screener export first)"
Write-Host "  PMS NSE Bhav Final 17:00     — daily $BhavTime IST (today only)"
Write-Host "  PMS NSE Bhav Final 17:15     — daily $BhavRetryTime IST retry"
Write-Host "  PMS Watchlist Fundamentals   — weekly $WeeklyDay $WeeklyTime IST"
Write-Host ""
Write-Host "Docker Desktop must be running before each task." -ForegroundColor Yellow
Write-Host "Screener: Export watchlist/screen → save into external fundamentals/screener/ before $ScreenerTime." -ForegroundColor Yellow
Write-Host "If Final bhav is still missing after 17:15 IST, upload manually on Pivot Point Strategy." -ForegroundColor Yellow
