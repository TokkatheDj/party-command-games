# test_pull_alert.ps1 - the blocked-pull email (22 Nov 2026), against throwaway repos. Exits 1 on any failure.
# Builds REAL blocked pulls (a diverged clone, a differing untracked file), runs the real Update-Routines
# with the exact hook Run-CoworkRoutine.ps1 uses, and checks what Invoke-PullAlert / pull_alert.py decide.
# pull_alert.py runs with --dry-run (no email) and a throwaway --state file, except the one marked SENT test.
#   powershell -NoProfile -File test_pull_alert.ps1      (Windows PowerShell 5.1, like the tasks)
#   pwsh -NoProfile -File test_pull_alert.ps1
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "Update-Routines.ps1")
. (Join-Path $PSScriptRoot "PullAlert.ps1")

$script:fails = 0
function Check([string]$name, [bool]$ok, [string]$detail = "") {
    if ($ok) { Write-Host "PASS  $name" } else { Write-Host "FAIL  $name  -- $detail"; $script:fails++ }
}
function G { param([string]$dir) $ErrorActionPreference = "Continue"; $a = $args; & git -C $dir @a 2>&1 | Out-Null }

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("pull-alert-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $tmp | Out-Null
$desk = Join-Path $tmp "desk"; $surf = Join-Path $tmp "surface"; $state = Join-Path $tmp "state\sent.txt"
G $tmp init -q --bare -b master origin.git
G $tmp clone -q origin.git desk
G $desk config user.email t@t; G $desk config user.name t
Set-Content "$desk\a.txt" "v1"; G $desk add -A; G $desk commit -q -m v1; G $desk push -q origin master
G $tmp clone -q origin.git surface
G $surf config user.email s@s; G $surf config user.name s

$logged = New-Object System.Collections.Generic.List[string]
$W = { param($m) $logged.Add($m) }
# exactly the runner's hook, with W -> $W
function Invoke-Pull([string[]]$extra) {
    $script:PullWarn = ""
    $pullSay = { param($m) & $W $m; if ($m -like "WARN: routines NOT updated*") { $script:PullWarn = $m } }
    $pull = Update-Routines -Repo $surf -Say $pullSay
    $r = Invoke-PullAlert -Result $pull -Warn $script:PullWarn -Say $W -Extra $extra
    return @($pull, $r)
}
$dry = @("--dry-run", "--state", $state, "--repo", $surf)

try {
    # 1. a normal, current pull: no alert at all
    $p = Invoke-Pull $dry
    Check "pull ok -> no alert called" ($p[0] -eq "current" -and $p[1] -eq "none") "$p"

    # 2. REAL diverged clone (a Surface commit never pushed + a desk commit): alert names the unpushed commit
    Set-Content "$desk\a.txt" "desk v2"; G $desk add -A; G $desk commit -q -m v2; G $desk push -q origin master
    Set-Content "$surf\b.txt" "surface only"; G $surf add -A; G $surf commit -q -m local
    $p = Invoke-Pull $dry
    $warn = ($logged | Where-Object { $_ -like "WARN: routines NOT updated*" } | Select-Object -Last 1)
    $alert = $logged[-1]
    Check "diverged -> pull kept, WARN logged" ($p[0] -eq "kept" -and $warn) "$p / $warn"
    Check "diverged -> alert would send (dry run)" ($p[1] -eq "called" -and $alert -like "pull_alert: DRY RUN*") $alert
    $full = (& C:\Python314\python.exe -I (Join-Path $PSScriptRoot "pull_alert.py") @dry $warn 2>&1) -join "`n"
    Check "diverged -> cause: unpushed commit, with ahead/behind" ($full -match "never pushed" -and $full -match "1 commit\(s\) ahead and 1 behind") $full
    Check "dry run writes no state file" (-not (Test-Path $state))

    # 3. once a day: with today's date in the state file, a second blocked run is silent
    New-Item -ItemType Directory -Force -Path (Split-Path $state) | Out-Null
    Set-Content $state ("{0} 07:00:00 test" -f (Get-Date -Format "yyyy-MM-dd"))
    $p = Invoke-Pull $dry
    Check "already sent today -> not sent" ($logged[-1] -like "pull_alert: not sent (already sent today*") $logged[-1]
    Set-Content $state "2020-01-01 07:00:00 old"
    $p = Invoke-Pull $dry
    Check "sent on an earlier day -> sends again" ($logged[-1] -like "pull_alert: DRY RUN*") $logged[-1]

    # 4. REAL untracked file that differs from GitHub's: named as untracked files
    G $surf reset -q --hard origin/master~1          # back to v1, no local commit
    Set-Content "$desk\c.txt" "desk c"; G $desk add -A; G $desk commit -q -m c; G $desk push -q origin master
    Set-Content "$surf\c.txt" "surface's own c"      # untracked, differs
    Remove-Item $state
    $p = Invoke-Pull $dry
    $warn = ($logged | Where-Object { $_ -like "WARN: routines NOT updated*" } | Select-Object -Last 1)
    $full = (& C:\Python314\python.exe -I (Join-Path $PSScriptRoot "pull_alert.py") @dry $warn 2>&1) -join "`n"
    Check "untracked differs -> pull kept, cause: untracked files" ($p[0] -eq "kept" -and $full -match "untracked files on the Surface") "$p / $warn"

    # 5. the transient mutex case never emails
    $r = Invoke-PullAlert -Result "kept" -Warn "WARN: routines NOT updated - another run held the pull for 2 minutes -- using the prompts on disk" -Say $W -Extra $dry
    Check "another run held the pull -> not sent" ($logged[-1] -like "pull_alert: not sent (another routine*") $logged[-1]

    # 6. a broken interpreter never throws into the run
    $r = Invoke-PullAlert -Result "kept" -Warn "WARN: routines NOT updated - x" -Say $W -Python (Join-Path $tmp "nope.exe")
    Check "missing python -> run carries on" ($r -eq "error" -and $logged[-1] -like "pull_alert: could not run*") "$r / $($logged[-1])"
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
if ($script:fails) { Write-Host "$($script:fails) FAILED"; exit 1 } else { Write-Host "all passed"; exit 0 }
