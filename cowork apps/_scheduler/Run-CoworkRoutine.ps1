# Run-CoworkRoutine.ps1
# Runs one cowork "routine" locally via headless `claude -p`, so it can read/write
# files under the cowork apps folder -- the thing the cloud routines could NOT do.
#
# Mirrors the hardened invocation used by serve_apps.py's builder:
#   claude --permission-mode dontAsk -p <prompt> --allowedTools "Edit(root\**),Read(root\**),..."
# File writes land via the globally pre-approved mcp-filesystem tool (built-in Write
# is denied in dontAsk mode; only Edit(...) allow-rules gate file tools).
#
# Usage:  pwsh -File Run-CoworkRoutine.ps1 -Name Kids-game-developer
#         (Name = a file <Name>.txt in .\Routines)

[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Name,
    [string]$Root      = "C:\Users\tokka\Claude Local\cowork apps",
    # For report-style routines: the wrapper writes the model's full output here,
    # so persistence does not depend on the model choosing to call a write tool
    # (it reliably produces the report text but ends by asking "want me to fix?").
    # A literal {date} in the path is replaced with today's yyyy-MM-dd.
    [string]$OutReport = "",
    # 40m/40turns was too tight once the collection grew: Action-games, Adult-puzzles
    # and Shooting-games hit "Reached max turns (40)" every day, losing their summary.
    [int]$TimeoutMin   = 50,
    [int]$MaxTurns     = 60,
    # Skip the pre-run registry rebuild (for hand-testing a prompt against a
    # deliberately stale registry).
    [switch]$NoRegistry,
    # Skip the GitHub pull before the run (for hand-testing an uncommitted prompt).
    [switch]$NoPull,
    # Late-start guard (below): how far past its slot a SCHEDULED run may start, and a
    # switch to run regardless (the guard already ignores catch-up and hand runs).
    [int]$LateMin      = 30,
    [switch]$AnyTime
)

$ErrorActionPreference = "Stop"
# Wrapper + prompts + logs always live under the cowork apps scheduler home,
# even when a routine targets a different workspace via -Root (e.g. G:\My Drive\...).
$SchedHome  = "C:\Users\tokka\Claude Local\cowork apps\_scheduler"
$PromptFile = Join-Path $SchedHome "Routines\$Name.txt"
$LogDir     = Join-Path $SchedHome "Logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir "$Name.log"

function W([string]$m) {
    $ts   = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "$ts  $m"
    Write-Host $line
    Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
}

# LATE-START GUARD (2 Nov 2026). This Surface uses Modern Standby: a task that comes due while it
# sleeps is not skipped, it fires on the next wake - all of them at once, with no stagger. On
# 30 Oct 13 routines started together at 14:54, and on 2 Nov the whole weekend's 27 at 07:54, the
# same pile-up -StartWhenAvailable caused in August. A run started by its scheduled task (parent
# wscript.exe, via run-hidden.vbs) more than $LateMin minutes after its slot - or before it, i.e. a
# previous day's run - logs SKIP and exits. That leaves no "=== START" line, so Invoke-CatchUp
# counts the routine as missed and reruns it later, one at a time (max 3). Catch-up and hand runs
# call this script directly and are never skipped.
if (-not $AnyTime) {
    $skip = $false
    try {
        $parentId = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
        $parentName = (Get-Process -Id $parentId -ErrorAction Stop).ProcessName
        if ($parentName -eq "wscript") {
            # Assign first, then loop: Windows PowerShell 5.1 sends a JSON array down a pipeline as
            # ONE object, so piping ConvertFrom-Json into Where-Object returned every routine at once.
            $manifestItems = Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $SchedHome "manifest.json") | ConvertFrom-Json
            $entry = $null
            foreach ($mi in $manifestItems) { if ($mi.safeName -eq $Name) { $entry = $mi; break } }
            if ($entry -and $entry.localAt) {
                $slot = [datetime]::ParseExact([string]$entry.localAt, "HH:mm", $null)
                $late = ((Get-Date) - (Get-Date).Date.AddHours($slot.Hour).AddMinutes($slot.Minute)).TotalMinutes
                if ($late -gt $LateMin -or $late -lt -5) {
                    W ("SKIP: late start ({0:+0;-0} min from its {1} slot) - the machine was asleep when it was due; Invoke-CatchUp reruns missed routines one at a time" -f $late, $entry.localAt)
                    $skip = $true
                }
            }
        }
    } catch {
        # never let the guard itself stop a run
        W "WARN: late-start guard failed ($($_.Exception.Message)) - running anyway"
    }
    if ($skip) { exit 0 }
}

# Fast-forward to GitHub first, so a prompt change pushed from the desktop is the one
# this run reads (29 Oct 2026). Never blocks the run: see Update-Routines.ps1.
if (-not $NoPull) {
    . (Join-Path $SchedHome "Update-Routines.ps1")
    $null = Update-Routines -Repo (Split-Path -Parent (Split-Path -Parent $SchedHome)) -Say ${function:W}
}

if (-not (Test-Path -LiteralPath $PromptFile)) {
    W "ERROR: prompt file not found: $PromptFile"
    exit 1
}
# -Encoding UTF8: Windows PowerShell 5.1 reads a BOM-less file as ANSI, so an em dash or accented letter in a prompt
# reached the model garbled.
$prompt = Get-Content -Raw -Encoding UTF8 -LiteralPath $PromptFile

$claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $claude) { $claude = "C:\Users\tokka\.local\bin\claude" }
if (-not (Test-Path -LiteralPath $claude)) {
    W "ERROR: claude CLI not found (looked on PATH and at $claude)"
    exit 1
}

# Edit(...) is scoped to the workspace so an unattended run can only modify files
# in here; Read/Glob/Grep/LS let it survey the collection like the cloud run did.
$allow = "Edit($Root\**),Read($Root\**),Glob,Grep,LS"

# Refresh the concept registry the prompts read in STEP 1. Done per-run rather
# than once nightly because several confirmed duplicate pairs were generated on
# the SAME day -- a stale registry would not have caught them.
if (-not $NoRegistry) {
    $rebuild = Join-Path $SchedHome "Rebuild-Registry.ps1"
    if (Test-Path -LiteralPath $rebuild) {
        try {
            $rstat = & $rebuild -Quiet:$false 2>&1
            W "registry: $($rstat -join '; ')"
        } catch {
            # A stale registry is far better than no run at all.
            W "WARN: registry rebuild failed ($($_.Exception.Message)) -- continuing with existing registry"
        }
    } else {
        W "WARN: Rebuild-Registry.ps1 not found at $rebuild -- STEP 1 will fall back to a folder listing"
    }
}

W "=== START '$Name'  (timeout ${TimeoutMin}m, max-turns $MaxTurns) ==="
$sw = [System.Diagnostics.Stopwatch]::StartNew()

$job = Start-Job -ScriptBlock {
    param($claude, $prompt, $allow, $root, $maxturns)
    Set-Location -LiteralPath $root
    # The prompt goes in on STDIN, not as an argument. Windows PowerShell 5.1 does not escape a " inside
    # a native-command argument, so every prompt was cut off at its first double quote: on 29 Oct the
    # Data-viz prompt reached the model as 43 of its 141 lines (it stopped at  "WHAT IF"), and the house
    # rules, style cards and accessibility block further down never arrived. UTF-8 both ways.
    $OutputEncoding = New-Object System.Text.UTF8Encoding $false
    try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch {}
    $prompt | & $claude --permission-mode dontAsk -p --allowedTools $allow --max-turns $maxturns 2>&1
} -ArgumentList $claude, $prompt, $allow, $Root, $MaxTurns

if (Wait-Job $job -Timeout ($TimeoutMin * 60)) {
    $out  = Receive-Job $job
    # Persist the FULL run output — the summary/findings live here, and a 25-line
    # tail once nearly lost a bug report. The .log keeps a readable tail.
    $OutFile = Join-Path $LogDir "$Name.out.txt"
    $fullOut = ($out -join "`n")
    $fullOut | Set-Content -LiteralPath $OutFile -Encoding UTF8
    # Deterministically persist the report for report-style routines.
    if ($OutReport) {
        $reportPath = $OutReport -replace '\{date\}', (Get-Date -Format 'yyyy-MM-dd')
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath) | Out-Null
        $fullOut | Set-Content -LiteralPath $reportPath -Encoding UTF8
        W "saved report -> $reportPath ($($fullOut.Length) chars)"
    }
    $tail = ($out | Select-Object -Last 25) -join "`n"
    $sw.Stop()
    W "--- claude output (tail; full output in $Name.out.txt) ---`n$tail"

    # The job "completing" says nothing about whether the routine produced anything.
    # Both of these exited 0 for weeks while writing no app at all, so Task Scheduler
    # reported LastTaskResult 0 and the failures stayed invisible.
    $degraded = $null
    if ($fullOut -match '(?i)Reached max turns')        { $degraded = 'max-turns' }
    # Any usage cap: "session", "weekly", ... On 12 Oct "You've hit your weekly limit"
    # slipped past a session-only match AND past the empty-output floor (a plugin's
    # SessionEnd hook error padded it to 231 chars), so every run "succeeded".
    elseif ($fullOut -match "(?i)hit your (\w+ )?limit") { $degraded = if ($Matches[1]) { "$($Matches[1].Trim())-limit" } else { 'usage-limit' } }
    elseif ($fullOut.Trim().Length -lt 200)              { $degraded = 'empty-output' }

    if ($degraded) {
        W "WARN: '$Name' finished DEGRADED ($degraded) -- may not have produced an app"
        W "=== DONE '$Name'  state=$($job.State)  degraded=$degraded  elapsed=$([int]$sw.Elapsed.TotalSeconds)s ==="
        Remove-Job $job -Force
        exit 3
    }

    W "=== DONE '$Name'  state=$($job.State)  elapsed=$([int]$sw.Elapsed.TotalSeconds)s ==="
    Remove-Job $job -Force
    exit 0
} else {
    Stop-Job $job
    Remove-Job $job -Force
    $sw.Stop()
    W "=== TIMEOUT '$Name' after ${TimeoutMin}m -- job stopped ==="
    exit 2
}
