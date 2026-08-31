# Invoke-CatchUp.ps1
# Reruns routines that did not run today, ONE AT A TIME.
#
# WHY THIS EXISTS INSTEAD OF -StartWhenAvailable
# The obvious fix for a missed run is -StartWhenAvailable on each task. That was
# tried and removed: Windows fires every missed task at once with no stagger --
# seven of them at 09:45:09 on 2026-08-08, and the same pile-up on 07-30 and 08-06.
# See the comment block in Register-CoworkTasks.ps1.
#
# So catch-up lives in ONE task instead of eighteen. A single task cannot stampede,
# and this script serialises the reruns itself and caps how many it will do. The
# per-routine tasks keep their original "a missed run is simply skipped" behaviour.
#
# -WakeToRun is deliberately still absent everywhere: this machine's wake-timer
# policy is "important wake timers only" on AC and disabled on battery, so a task
# cannot wake it regardless. Catch-up therefore happens on the next wake, not at
# the original time.
#
# Dry-run by default, like Restore-CoworkContent.ps1 and Cleanup-DjMusicPollution.ps1.
# Add -Apply to actually run anything.
#
# Usage:  pwsh -File Invoke-CatchUp.ps1            # show what it would rerun
#         pwsh -File Invoke-CatchUp.ps1 -Apply     # actually rerun (max 3)

[CmdletBinding()]
param(
    [switch]$Apply,
    # A machine that was off all day would otherwise queue 16 reruns back to back.
    [int]$MaxRuns = 3,
    # How far back to look. 1 = today only; 2 = today and yesterday.
    [int]$Days = 1
)

$ErrorActionPreference = "Stop"
# $PSScriptRoot, not $MyInvocation.MyCommand.Path -- the latter is empty in some
# invocation contexts, which would silently send the log somewhere else.
$Sched     = $PSScriptRoot
$Manifest  = Join-Path $Sched "manifest.json"
$LogDir    = Join-Path $Sched "Logs"
$Wrapper   = Join-Path $Sched "Run-CoworkRoutine.ps1"
# Deliberately NOT named $Log: PowerShell variables are case-insensitive, so a
# loop variable called $log further down silently overwrote this and appended the
# whole sweep to a routine's own log file instead. Distinct name, no collision.
$CatchUpLog = Join-Path $LogDir "_CatchUp.log"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function W([string]$m) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $m
    Write-Host $line
    Add-Content -LiteralPath $CatchUpLog -Value $line -Encoding UTF8
}

# Never start a rerun while a scheduled routine is mid-flight -- the whole point
# is to avoid two generators writing at once. Only gate -Apply: a dry run starts
# nothing, so blocking it would just stop you inspecting during the working day.
if ($Apply) {
    $running = @(Get-ScheduledTask -TaskName "CoworkApps-*" -ErrorAction SilentlyContinue |
                 Where-Object { $_.State -eq "Running" -and $_.TaskName -ne "CoworkApps-Server-Boot" })
    if ($running.Count -gt 0) {
        W "SKIP: $($running[0].TaskName) is still running -- catch-up stands down"
        exit 0
    }
}

$items = Get-Content -Raw -LiteralPath $Manifest | ConvertFrom-Json
$now = Get-Date
$dates = 0..($Days - 1) | ForEach-Object { $now.Date.AddDays(-$_).ToString("yyyy-MM-dd") }

$missed = @()
foreach ($m in $items) {
    # Weekly routines only count on their own day; simplest correct thing is to
    # leave them to their own trigger.
    if ($m.triggerType -eq "Weekly") { continue }

    # Only consider slots whose time has already passed today.
    $slot = [datetime]::ParseExact($m.localAt, "HH:mm", $null)
    $slotToday = $now.Date.AddHours($slot.Hour).AddMinutes($slot.Minute)
    if ($slotToday -gt $now) { continue }

    # "Ran" means produced something, not merely started. A run killed by the daily
    # session limit exits in ~9 seconds having built nothing; counting that as done
    # would let exactly the runs most worth recovering fall through the net.
    # A max-turns run is NOT treated as missed -- those usually do write the app
    # before hitting the cap, and rerunning would duplicate it.
    $routineLog = Join-Path $LogDir "$($m.safeName).log"
    $ran = $false
    if (Test-Path -LiteralPath $routineLog) {
        $lines = @(Get-Content -LiteralPath $routineLog -ErrorAction SilentlyContinue)
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match "^(\d{4}-\d{2}-\d{2}) .*=== START" -and $dates -contains $Matches[1]) {
                # Read to the end of this run's block.
                $end = $lines.Count
                for ($j = $i + 1; $j -lt $lines.Count; $j++) {
                    if ($lines[$j] -match "^\d{4}-\d{2}-\d{2} .*=== START") { $end = $j; break }
                }
                $block = ($lines[$i..($end - 1)]) -join "`n"
                $barren = ($block -match "session limit") -or ($block -match "degraded=empty-output")
                if (-not $barren) { $ran = $true; break }
            }
        }
    }
    if (-not $ran) { $missed += $m }
}

$missed = @($missed | Sort-Object localAt)

if ($missed.Count -eq 0) {
    W "nothing to catch up -- every scheduled routine has run in the last $Days day(s)"
    exit 0
}

W "missed: $($missed.Count) -> $(($missed | ForEach-Object { $_.safeName }) -join ', ')"

$todo = @($missed | Select-Object -First $MaxRuns)
if ($missed.Count -gt $MaxRuns) {
    W "capping at $MaxRuns this sweep; the rest wait for the next one"
}

if (-not $Apply) {
    W "DRY RUN -- would rerun: $(($todo | ForEach-Object { $_.safeName }) -join ', ')"
    W "re-run with -Apply to actually generate"
    exit 0
}

$ok = 0
foreach ($m in $todo) {
    W "=== catch-up START '$($m.safeName)' (missed $($m.localAt)) ==="
    # Serial on purpose: & blocks until the routine finishes.
    & $Wrapper -Name $m.safeName
    $rc = $LASTEXITCODE
    W "=== catch-up DONE '$($m.safeName)' exit=$rc ==="
    if ($rc -eq 0) { $ok++ }
}
W "catch-up finished: $ok/$($todo.Count) clean"
