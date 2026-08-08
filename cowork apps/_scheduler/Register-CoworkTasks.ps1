# Register-CoworkTasks.ps1
# Registers one Windows Scheduled Task per cowork routine, driven by manifest.json.
# Each task runs Run-CoworkRoutine.ps1 -Name <safeName> at the routine's LOCAL time
# (already converted from the old UTC cloud cron). Idempotent: -Force replaces.

$ErrorActionPreference = "Stop"
$Sched    = "C:\Users\tokka\Claude Local\cowork apps\_scheduler"
$Root     = "C:\Users\tokka\Claude Local\cowork apps"
$Wrapper  = Join-Path $Sched "Run-CoworkRoutine.ps1"
$Manifest = Join-Path $Sched "manifest.json"
$PS       = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"

$items = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json

# NO -StartWhenAvailable, deliberately. It used to be here so a run missed while
# the PC was off would fire "as soon as it can" -- but Windows fires EVERY missed
# task at once, with no stagger. Combined with a 01:00-06:30 schedule and a machine
# that gets shut down overnight, that meant every boot opened one console window per
# missed routine: seven of them on 2026-08-08, all stamped 09:45:09 in their logs,
# and the same pile-up on 07-30 and 08-06. A missed run is now simply skipped.
#
# The routines moved to 09:30-17:30 in the same change, so they run when the machine
# is actually on and there is little left to miss. WakeToRun is kept, but note it
# now means a SLEEPING machine wakes during the day to generate an app.
$Settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 45) `
    -MultipleInstances IgnoreNew

$ok = 0
$skipped = @()
foreach ($m in $items) {
    # Never replace a task that is mid-run. -Force swaps the definition out from
    # under the live instance and kills the routine partway through, losing
    # whatever it was generating. Skipping is safe because registration is
    # idempotent: re-run this script once the routine finishes.
    $live = Get-ScheduledTask -TaskName $m.taskName -ErrorAction SilentlyContinue
    if ($live -and $live.State -eq 'Running') {
        Write-Host ("  SKIPPED    {0,-34} running right now" -f $m.taskName)
        $skipped += $m.taskName
        continue
    }

    $arg = "-NoProfile -ExecutionPolicy Bypass -File `"$Wrapper`" -Name `"$($m.safeName)`""
    $Action = New-ScheduledTaskAction -Execute $PS -Argument $arg -WorkingDirectory $Root

    if ($m.triggerType -eq "Weekly") {
        $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $m.localDow -At $m.localAt
    } else {
        $Trigger = New-ScheduledTaskTrigger -Daily -At $m.localAt
    }

    Register-ScheduledTask `
        -TaskName    $m.taskName `
        -Action      $Action `
        -Trigger     $Trigger `
        -Settings    $Settings `
        -Description "Local cowork routine (migrated from cloud $($m.id)). Was $($m.cronUTC) UTC." `
        -RunLevel    Limited `
        -Force | Out-Null

    $when = if ($m.triggerType -eq "Weekly") { "$($m.localDow) $($m.localAt)" } else { "daily $($m.localAt)" }
    Write-Host ("  registered {0,-34} {1}" -f $m.taskName, $when)
    $ok++
}
Write-Host ""
Write-Host "Registered $ok / $($items.Count) tasks."
if ($skipped.Count -gt 0) {
    Write-Host ""
    Write-Host "$($skipped.Count) task(s) were mid-run and still carry the OLD schedule:"
    $skipped | ForEach-Object { Write-Host "  $_" }
    Write-Host "Re-run this script once they finish to pick up the new times."
}
