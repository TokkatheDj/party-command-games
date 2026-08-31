# Register-CatchUpTask.ps1
# Registers CoworkApps-CatchUp: the ONE task allowed to carry -StartWhenAvailable.
#
# The 18 routine tasks deliberately do not have it -- Windows fires every missed
# task at once with no stagger, which produced a seven-task pile-up on 2026-08-08
# (see Register-CoworkTasks.ps1). Concentrating catch-up in a single task removes
# that failure mode by construction: one task cannot stampede, and Invoke-CatchUp.ps1
# reruns the missed routines serially with a cap.
#
# Runs at 20:00, after the last routine (19:00). If the machine is asleep or off at
# 20:00, StartWhenAvailable fires it on the next wake -- which is the actual point,
# since -WakeToRun cannot help here (this machine's wake-timer policy is "important
# timers only" on AC and disabled on battery).
#
# Idempotent. Run from a normal terminal; no elevation needed.

$ErrorActionPreference = "Stop"

$Sched = Split-Path -Parent $MyInvocation.MyCommand.Path
$WS    = "$env:SystemRoot\System32\wscript.exe"
$VBS   = Join-Path $Sched "catchup-hidden.vbs"
$Name  = "CoworkApps-CatchUp"

foreach ($p in @($VBS, (Join-Path $Sched "Invoke-CatchUp.ps1"))) {
    if (-not (Test-Path -LiteralPath $p)) { throw "missing: $p" }
}

$Action = New-ScheduledTaskAction -Execute $WS `
    -Argument "`"$VBS`" -Apply -MaxRuns 3" `
    -WorkingDirectory $Sched

$Trigger = New-ScheduledTaskTrigger -Daily -At "20:10"

# StartWhenAvailable is the whole reason this task exists.
# Four hours because it may rerun up to 3 routines back to back, each capped at
# 50 minutes by the wrapper.
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 4) `
    -MultipleInstances IgnoreNew

$live = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
if ($live -and $live.State -eq "Running") {
    Write-Host "  SKIP $Name -- currently running; re-run this script when it finishes"
    return
}

Register-ScheduledTask -TaskName $Name -Action $Action -Trigger $Trigger `
    -Settings $Settings -RunLevel Limited -Force | Out-Null

$t = Get-ScheduledTask -TaskName $Name
Write-Host "  registered $Name  daily 20:10  StartWhenAvailable=$($t.Settings.StartWhenAvailable)  limit=$($t.Settings.ExecutionTimeLimit)"
