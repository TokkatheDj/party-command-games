# Setup-PollutionCheck.ps1
# Registers a daily Windows Task Scheduler job that DRY-RUN checks for the
# dj_music_apps display-name pollution (via Cleanup-DjMusicPollution.ps1) and
# emails the owner if it recurs. Mirrors Setup-DailyCheck.ps1. Self-locating:
# put this + check_dj_pollution.py + Cleanup-DjMusicPollution.ps1 in the cowork
# apps root and run it (works on the Desktop or the Surface).

$AppsDir  = $PSScriptRoot
$Script   = "$AppsDir\check_dj_pollution.py"
$TaskName = "CoworkApps-PollutionCheck"
$RunAt    = "07:00AM"   # after the Surface's wee-hours generation window

$PythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $PythonExe) { Write-Host "ERROR: python not found on PATH" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $Script)) { Write-Host "ERROR: worker not found at $Script" -ForegroundColor Red; exit 1 }
if (-not (Test-Path "$AppsDir\Cleanup-DjMusicPollution.ps1")) {
    Write-Host "ERROR: Cleanup-DjMusicPollution.ps1 not found next to this script" -ForegroundColor Red; exit 1
}

Write-Host ""
Write-Host "  Registering daily dj_music_apps pollution check..." -ForegroundColor Cyan
Write-Host "  Worker : $Script"
Write-Host "  Python : $PythonExe"
Write-Host "  Runs at: $RunAt daily"
Write-Host ""

$Action   = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$Script`"" -WorkingDirectory $AppsDir
$Trigger  = New-ScheduledTaskTrigger -Daily -At $RunAt
$Settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -StartWhenAvailable

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
    Write-Host "  Run now      : python `"$Script`"" -ForegroundColor Gray
    Write-Host "  Check log    : Get-Content `"$AppsDir\dj_pollution_check.log`" -Tail 30" -ForegroundColor Gray
    Write-Host "  Remove task  : Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Gray
    Write-Host "  Change time  : edit `$RunAt in this script and re-run" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host "  ERROR: Task not found after registration. Try running as Administrator." -ForegroundColor Red
}
