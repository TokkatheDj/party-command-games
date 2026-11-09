# test_late_start.ps1 - the late-start guard measured against the REAL trigger (9 Nov 2026).
# Exits 1 on any failure. Times are this machine's local time (America/New_York: EDT until
# 1 Nov 2026, EST after), the same zone the scheduled tasks run in.
#   powershell -NoProfile -File test_late_start.ps1      (Windows PowerShell 5.1, like the tasks)
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "LateStart.ps1")

$script:fails = 0
function Check([string]$name, [bool]$ok, [string]$detail = "") {
    if ($ok) { Write-Host "PASS  $name" } else { Write-Host "FAIL  $name  -- $detail"; $script:fails++ }
}
function At([string]$s) { [datetime]::ParseExact($s, "yyyy-MM-dd HH:mm", $null) }
$LateMin = 30
function Skips($r) { $r.Late -gt $LateMin -or $r.Late -lt -5 }

if ([TimeZoneInfo]::Local.Id -ne "Eastern Standard Time") {
    Write-Host "SKIP  these cases assume US Eastern time; this machine is $([TimeZoneInfo]::Local.Id)"; exit 0
}

# The real trigger of CoworkApps-Daily-app-check, read on 9 Nov: registered in summer at 12:00.
$real = "2026-10-29T11:00:00-05:00"

$r = Get-MinutesLate -Now (At "2026-11-09 11:00") -StartBoundary $real -LocalAt "12:00"
Check "after the clocks went back, the 11:00 firing is ON TIME (was -60 and skipped)" ([math]::Abs($r.Late) -lt 1 -and -not (Skips $r) -and $r.From -eq "trigger") "late=$($r.Late) from=$($r.From)"

$r = Get-MinutesLate -Now (At "2026-10-30 12:00") -StartBoundary $real -LocalAt "12:00"
Check "before the change (EDT) the same trigger fired at 12:00 and is on time" ([math]::Abs($r.Late) -lt 1) "late=$($r.Late)"

$r = Get-MinutesLate -Now (At "2027-03-15 13:00") -StartBoundary $real -LocalAt "12:00"
Check "in March (EDT again) it fires at 12:00 local, so 13:00 is +60 late" ([math]::Abs($r.Late - 60) -lt 1 -and (Skips $r)) "late=$($r.Late)"

$r = Get-MinutesLate -Now (At "2026-11-09 14:54") -StartBoundary $real -LocalAt "12:00"
Check "woken from sleep hours later still SKIPS (the guard's real job)" ((Skips $r) -and $r.Late -gt 200) "late=$($r.Late)"

$r = Get-MinutesLate -Now (At "2026-11-10 07:54") -StartBoundary $real -LocalAt "12:00"
Check "yesterday's run firing next morning still SKIPS" ((Skips $r) -and $r.Late -lt -5) "late=$($r.Late)"

$r = Get-MinutesLate -Now (At "2026-11-09 12:10") -StartBoundary "2026-10-29T12:00:00" -LocalAt "12:00"
Check "a local-time trigger (no offset) is read as local: 12:10 is +10" ([math]::Abs($r.Late - 10) -lt 1 -and -not (Skips $r)) "late=$($r.Late)"

$r = Get-MinutesLate -Now (At "2026-11-10 00:10") -StartBoundary "2026-10-29T23:30:00" -LocalAt "23:30"
Check "just after midnight, a 23:30 run is +40 late, not -1400" ([math]::Abs($r.Late - 40) -lt 1) "late=$($r.Late)"

$r = Get-MinutesLate -Now (At "2026-11-09 12:31") -StartBoundary $null -LocalAt "12:00"
Check "no trigger readable -> falls back to the manifest slot (still guarded)" ($r.From -eq "manifest" -and (Skips $r)) "late=$($r.Late) from=$($r.From)"

$r = Get-MinutesLate -Now (At "2026-11-09 12:00") -StartBoundary "not a date" -LocalAt "12:00"
Check "an unreadable trigger also falls back to the manifest" ($r.From -eq "manifest" -and [math]::Abs($r.Late) -lt 1) "from=$($r.From)"

$r = Get-MinutesLate -Now (At "2026-11-09 12:00") -StartBoundary $null -LocalAt $null
Check "nothing to measure against -> null (caller runs, as before)" ($null -eq $r)

if ($script:fails) { Write-Host "`n$($script:fails) FAILED"; exit 1 }
Write-Host "`nall passed"
exit 0
