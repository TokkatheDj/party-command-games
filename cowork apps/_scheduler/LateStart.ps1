# LateStart.ps1 - how late is this run, measured against when Windows ACTUALLY fires the task?
# (9 Nov 2026). Dot-sourced by Run-CoworkRoutine.ps1; tested by test_late_start.ps1.
#
# Why this exists: New-ScheduledTaskTrigger -At 12:00 stores the start as "12:00-04:00" in summer
# (EDT). Windows then fires it at that fixed UTC moment every day, so when the clocks went back on
# 1 Nov every routine started firing at 11:00. The late-start guard measured against the manifest's
# 12:00, read 11:00 as "-60 min, a previous day's run", and SKIPPED: 103 skips across the factory
# from 2 Nov to 9 Nov, while catch-up reruns at most 3 a day. In March the same triggers will fire
# an hour LATE, which the guard would skip as late. Measuring against the real firing time is right
# in both directions, and stays right if the tasks are ever re-registered with local-time triggers.

function Get-TriggerFireTimes {
    # When does this trigger fire around $Now? Returns three local DateTimes (yesterday, today,
    # tomorrow), or $null if the boundary can't be read.
    param([datetime]$Now, [string]$StartBoundary)
    if (-not $StartBoundary) { return $null }
    try {
        $hasOffset = $StartBoundary -match '(Z|[+-]\d{2}:\d{2})$'
        $dto = [datetimeoffset]::Parse($StartBoundary, [Globalization.CultureInfo]::InvariantCulture)
        $times = @()
        foreach ($d in -1, 0, 1) {
            if ($hasOffset) {
                # Fixed UTC moment each day ("synchronize across time zones"): convert with the
                # offset in force on THAT day, not on the day the task was registered.
                $utc = [datetime]::SpecifyKind($Now.ToUniversalTime().Date.AddDays($d).Add($dto.UtcDateTime.TimeOfDay), [DateTimeKind]::Utc)
                $times += $utc.ToLocalTime()
            } else {
                # Local-time trigger: same wall-clock time every day.
                $times += $Now.Date.AddDays($d).Add($dto.DateTime.TimeOfDay)
            }
        }
        return $times
    } catch { return $null }
}

function Get-MinutesLate {
    # Minutes between $Now and the nearest firing of the task (negative = early).
    # Order of trust: the task's real trigger -> the manifest's localAt -> $null (caller runs).
    # Returns @{ Late = <double>; From = "trigger" | "manifest" } or $null.
    param([datetime]$Now, [string]$StartBoundary, [string]$LocalAt)
    $times = Get-TriggerFireTimes -Now $Now -StartBoundary $StartBoundary
    $from = "trigger"
    if (-not $times -and $LocalAt) {
        try {
            $tod = ([datetime]::ParseExact($LocalAt, "HH:mm", $null)).TimeOfDay
            $times = foreach ($d in -1, 0, 1) { $Now.Date.AddDays($d).Add($tod) }
            $from = "manifest"
        } catch { $times = $null }
    }
    if (-not $times) { return $null }
    $best = $null
    foreach ($t in $times) {
        $m = ($Now - $t).TotalMinutes
        if ($null -eq $best -or [math]::Abs($m) -lt [math]::Abs($best)) { $best = $m }
    }
    return @{ Late = $best; From = $from }
}
