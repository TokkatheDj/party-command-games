# Setup-DailyCheck.ps1
# Registers a daily Windows Task Scheduler job that runs the AI notes check.

$AppsDir  = $PSScriptRoot
$Script   = "$AppsDir\daily_check.py"
$TaskName = "CoworkApps-DailyCheck"
$RunAt    = "09:00AM"

$PythonExe = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $PythonExe) {
    Write-Host "ERROR: python not found on PATH" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  Registering daily AI check task..." -ForegroundColor Cyan
Write-Host "  Script : $Script"
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
    Write-Host "  To run now      : python `"$Script`"" -ForegroundColor Gray
    Write-Host "  To check log    : Get-Content `"$AppsDir\daily_check.log`" -Tail 30" -ForegroundColor Gray
    Write-Host "  To remove task  : Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false" -ForegroundColor Gray
    Write-Host "  To change time  : Edit this script and re-run" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host "  ERROR: Task not found after registration. Try running as Administrator." -ForegroundColor Red
}