# Register Windows Task Scheduler jobs for watchlist maintenance.
# NSE bhav is not scheduled; this script removes the old 17:00 and 17:15 tasks.
# All times are local clock - set the PC timezone to India Standard Time (IST).
# Run once from PowerShell (elevated if access denied).
param(
    [string]$AlertsTime = "07:00",
    [string]$QuotesTime = "07:15",
    [string]$ScreenerTime = "18:30",
    [string]$WeeklyDay = "Sunday",
    [string]$WeeklyTime = "03:00"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$AlertsScript = Join-Path $Root "scripts\windows\refresh-watchlists.ps1"
$QuotesScript = Join-Path $Root "scripts\windows\refresh-watchlist-quotes.ps1"
$ScreenerScript = Join-Path $Root "scripts\windows\sync-screener-export.ps1"
$WeeklyScript = Join-Path $Root "scripts\windows\refresh-watchlist-fundamentals.ps1"

foreach ($path in @($AlertsScript, $QuotesScript, $ScreenerScript, $WeeklyScript)) {
    if (-not (Test-Path $path)) { throw "Missing $path" }
}

# Bhav is manual only (Pivot upload or sync-nse-bhav.ps1). Remove the 17:00 and 17:15 pulls.
foreach ($name in @("PMS NSE Bhav Final", "PMS NSE Bhav Final 17:00", "PMS NSE Bhav Final 17:15")) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}

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

Register-ScheduledTask -TaskName "PMS Watchlist Fundamentals" `
    -Description "Weekly full BSE quarterly + annual + snapshot recompute (overnight)." `
    -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WeeklyScript`"") `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $WeeklyDay -At $WeeklyTime) `
    -Settings $Settings -Force | Out-Null

Write-Host "Registered scheduled tasks (PC clock must be IST):" -ForegroundColor Green
Write-Host "  PMS Watchlist Alerts         - daily $AlertsTime IST"
Write-Host "  PMS Watchlist Quotes         - daily $QuotesTime IST"
Write-Host "  PMS Screener Export Sync     - daily $ScreenerTime IST (drop Screener export first)"
Write-Host "  PMS Watchlist Fundamentals   - weekly $WeeklyDay $WeeklyTime IST"
Write-Host ""
Write-Host "Docker Desktop must be running before each task." -ForegroundColor Yellow
Write-Host "Screener: Export watchlist/screen, save into external fundamentals/screener/ before $ScreenerTime." -ForegroundColor Yellow
Write-Host "NSE bhav is manual: upload on Pivot Point Strategy, or run scripts\windows\sync-nse-bhav.ps1." -ForegroundColor Yellow
