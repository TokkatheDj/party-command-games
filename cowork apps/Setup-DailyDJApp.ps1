# Setup-DailyDJApp.ps1
# Registers a daily Windows Task Scheduler job that builds a new DJ app locally
# (via the Claude CLI) and saves it into dj_music_apps. Mirrors Setup-DailyCheck.ps1.

$AppsDir  = $PSScriptRoot
$Worker   = "$AppsDir\Run-DailyDJApp.ps1"
$TaskName = "CoworkApps-DailyDJApp"
$RunAt    = "6:00AM"

$PwshExe = (Get-Command powershell -ErrorAction SilentlyContinue)?.Source
if (-not $PwshExe) {
    Write-Host "ERROR: powershell not found on PATH" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Worker)) {
    Write-Host "ERROR: worker script not found at $Worker" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  Registering daily DJ-app build task..." -ForegroundColor Cyan
Write-Host "  Worker : $Worker"
Write-Host "  Runs at: $RunAt daily"
Write-Host ""

$Action   = New-ScheduledTaskAction -Execute $PwshExe `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Worker`"" `
    -WorkingDirectory $AppsDir
$Trigger  = New-ScheduledTaskTrigger -Daily -At $RunAt
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -StartWhenAvailable

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action   $Action `
    -Trigger  $Trigger `
    -Settings $Settings `
    -RunLevel Limited `
    -Force | Out-Null

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($task) {
    Write-Host "  Task registered: '$TaskName'" -ForegroundColor Green
    Write-Host ""
    Write-Host "  To run now      : powershell -File `"$Worker`"" -ForegroundColor Gray
    Write-Host "  To check log    : Get-Content `"$AppsDir\dj_daily.log`" -Tail 40" -ForegroundColor Gray
    Write-Host "  To remove task  : Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Gray
    Write-Host "  To change time  : Edit `$RunAt in this script and re-run" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host "  ERROR: Task not found after registration. Try running as Administrator." -ForegroundColor Red
}
