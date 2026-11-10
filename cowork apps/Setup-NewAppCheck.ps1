# Setup-NewAppCheck.ps1 - schedule the nightly new-app check on THIS machine (10 Nov 2026).
#
# new_app_check.py plays every new app on a phone and a tablet (smoke_new_apps.js, muted) and writes
# a "Played" section into that day's review. Its header always said "nightly", but on the Surface -
# where the factory builds the apps - nothing ran it: its only report was a one-off on 28 Oct, and
# from 30 Oct to 9 Nov 35 apps went live unplayed. This registers it.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File "Setup-NewAppCheck.ps1"            (20:30 daily)
#   powershell -NoProfile -ExecutionPolicy Bypass -File "Setup-NewAppCheck.ps1" -At 21:15
#
# - LOCAL-time trigger (StartBoundary with no offset), so it stays at 20:30 across the clock changes.
#   The factory's -At triggers store a summer offset and fired an hour early from 1 Nov.
# - No StartWhenAvailable: a night the Surface sleeps through is simply missed, and the next run
#   covers it, because new_app_check.py now looks back to its last run (3 to 21 days).
# - Windowless (pythonw), one at a time, stopped after 90 minutes.
param([string]$At = "20:30")
$ErrorActionPreference = "Stop"
$Here   = $PSScriptRoot
$Py     = "C:\Python314\pythonw.exe"
$Script = Join-Path $Here "new_app_check.py"
$Name   = "CoworkApps-NewAppCheck"
if (-not (Test-Path $Py))     { throw "pythonw not found at $Py" }
if (-not (Test-Path $Script)) { throw "new_app_check.py not found next to this script" }

$action   = New-ScheduledTaskAction -Execute $Py -Argument "`"$Script`"" -WorkingDirectory $Here
$trigger  = New-ScheduledTaskTrigger -Daily -At $At
$trigger.StartBoundary = (Get-Date $At).ToString("yyyy-MM-ddTHH:mm:ss")      # no offset = local time
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 90) `
            -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings `
    -Description "Plays new Cowork apps on phone + tablet (new_app_check.py). Setup-NewAppCheck.ps1." `
    -RunLevel Limited -Force | Out-Null

$t = Get-ScheduledTask -TaskName $Name
Write-Host ("registered {0}: daily at {1}, trigger {2}" -f $Name, $At, $t.Triggers[0].StartBoundary)
Write-Host "first run looks back to the last report (28 Oct), so it will take a while; later nights are quick."
