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

# Wee-hours jobs need the machine to wake; all get StartWhenAvailable so a missed
# run (PC off/asleep) fires as soon as it can rather than silently skipping.
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 45) `
    -MultipleInstances IgnoreNew

$ok = 0
foreach ($m in $items) {
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
