# Register Windows Task Scheduler jobs for watchlist maintenance.
# Run once from PowerShell (elevated if access denied).
param(
    [string]$AlertsTime = "07:00",
    [string]$QuotesTime = "07:15",
    [string]$WeeklyDay = "Sunday",
    [string]$WeeklyTime = "03:00"
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$AlertsScript = Join-Path $Root "scripts\windows\refresh-watchlists.ps1"
$QuotesScript = Join-Path $Root "scripts\windows\refresh-watchlist-quotes.ps1"
$WeeklyScript = Join-Path $Root "scripts\windows\refresh-watchlist-fundamentals.ps1"

foreach ($path in @($AlertsScript, $QuotesScript, $WeeklyScript)) {
    if (-not (Test-Path $path)) { throw "Missing $path" }
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

Register-ScheduledTask -TaskName "PMS Watchlist Fundamentals" `
    -Description "Weekly full BSE quarterly + annual + snapshot recompute (overnight)." `
    -Action (New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$WeeklyScript`"") `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $WeeklyDay -At $WeeklyTime) `
    -Settings $Settings -Force | Out-Null

Write-Host "Registered scheduled tasks:" -ForegroundColor Green
Write-Host "  PMS Watchlist Alerts       — daily $AlertsTime"
Write-Host "  PMS Watchlist Quotes       — daily $QuotesTime"
Write-Host "  PMS Watchlist Fundamentals — weekly $WeeklyDay $WeeklyTime"
Write-Host ""
Write-Host "Docker Desktop must be running before each task." -ForegroundColor Yellow
