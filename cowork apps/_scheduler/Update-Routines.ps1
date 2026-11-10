# Update-Routines.ps1
# Brings the Surface's clone up to date with GitHub before a routine reads its prompt
# (29 Oct 2026). Until then nothing on the Surface pulled by itself: three prompt changes
# in one evening (the contrast colour, nine generators moved here, the IDENTITY block)
# each waited on someone typing `git pull` at the Surface.
#
# SAFE BY DESIGN - it only ever fast-forwards:
#   * `git pull --ff-only`: if the Surface has its own unpushed commits, uncommitted
#     edits in the way, or untracked files the pull would overwrite, git refuses and
#     changes NOTHING. We log why and run with the prompt already on disk.
#     One exception (10 Nov 2026): untracked files IDENTICAL to GitHub's copies are moved
#     aside (never deleted) and the pull retried once - see the block near the end.
#   * never checkout/reset/stash - an earlier `git checkout -- Routines` once threw away
#     copied-in prompts that weren't committed yet.
#   * offline or GitHub slow: gives up after ~20 s without data and carries on.
#   * never throws: Windows PowerShell 5.1 (what the tasks run) turns ANY git stderr into
#     a terminating error under -ErrorAction Stop, even with 2>$null, so the whole
#     function runs with Continue and a catch-all.
# Dot-sourced by Run-CoworkRoutine.ps1; test_update_routines.ps1 exercises every case.

function Update-Routines {
    param(
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][scriptblock]$Say,   # not $Log: the runner's W() reads a $Log file path by dynamic scope
        # Where identical untracked copies are moved when they block a pull (gitignored by default).
        [string]$MovedTo = (Join-Path $Repo "cowork apps\_scheduler\Logs\pull-moved")
    )
    $ErrorActionPreference = "Continue"     # local to this function
    # ONE pull at a time (30 Oct 2026): waking the Surface at 14:55 started four missed routines
    # in the same second; their four pulls collided ("Cannot fast-forward to multiple branches")
    # and all four ran with old prompts. A named mutex per clone queues them: the first pulls,
    # the rest find it already up to date. The name comes from a stable hash of the path
    # (string.GetHashCode differs between PowerShell 7 processes).
    $sha = [System.Security.Cryptography.SHA1]::Create()
    $id = -join ($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($Repo.ToLowerInvariant())) | Select-Object -First 8 | ForEach-Object { $_.ToString("x2") })
    $mutex = New-Object System.Threading.Mutex($false, "Global\CoworkRoutinesPull-$id")
    $held = $false
    try {
        try { $held = $mutex.WaitOne(120000) } catch [System.Threading.AbandonedMutexException] { $held = $true }
        if (-not $held) {
            & $Say "WARN: routines NOT updated - another run held the pull for 2 minutes -- using the prompts on disk"
            return "kept"
        }
        $git = (Get-Command git -ErrorAction SilentlyContinue).Source
        if (-not $git) { & $Say "routines: git not found - using the prompts on disk"; return "no-git" }
        $env:GIT_TERMINAL_PROMPT = "0"      # never sit waiting for a password

        $before = (& $git -C $Repo rev-parse --short HEAD 2>&1 | Select-Object -First 1) -as [string]
        $out = & $git -C $Repo -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=20 `
                   pull --ff-only --quiet 2>&1 | ForEach-Object { "$_" }
        if ($LASTEXITCODE -eq 0) {
            $after = (& $git -C $Repo rev-parse --short HEAD 2>&1 | Select-Object -First 1) -as [string]
            if ($after -eq $before) { & $Say "routines up to date ($after)"; return "current" }
            & $Say "routines updated $before -> $after"
            return "updated"
        }
        # IDENTICAL UNTRACKED COPIES (10 Nov 2026). An app the factory wrote here, then committed from
        # the desktop, sits untracked on the Surface and blocks every fast-forward ("untracked working
        # tree files would be overwritten"). It sat 17 commits behind for a week that way. If EVERY
        # blocking file is byte-for-byte what GitHub has (git's own normalised hash, so line endings
        # don't count), they are MOVED (never deleted) into Logs\pull-moved\<time>\ and the pull is tried
        # once more. If even one differs, nothing is touched: that could be real work.
        if (($out -join "`n") -match "untracked working tree files would be overwritten") {
            $paths = @($out | Where-Object { $_ -match "^\t" } | ForEach-Object { $_.Trim().Trim('"') })
            $differ = @()
            foreach ($p in $paths) {
                # Collect ALL output, then read the exit code: in Windows PowerShell 5.1, piping a native
                # command into Select-Object -First 1 stops it early and reports exit code -1.
                $lo = @(& $git -C $Repo hash-object -- $p 2>&1 | ForEach-Object { "$_" }); $lrc = $LASTEXITCODE
                $ro = @(& $git -C $Repo rev-parse "@{u}:$p" 2>&1 | ForEach-Object { "$_" }); $rrc = $LASTEXITCODE
                $local = if ($lo.Count) { $lo[0].Trim() } else { "" }
                $remote = if ($ro.Count) { $ro[0].Trim() } else { "" }
                if ($lrc -ne 0 -or $rrc -ne 0 -or -not $local -or $local -ne $remote) { $differ += $p }
            }
            if ($paths.Count -and -not $differ.Count) {
                $dest = Join-Path $MovedTo (Get-Date -Format "yyyy-MM-dd_HHmmss")
                foreach ($p in $paths) {
                    $to = Join-Path $dest $p
                    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $to) | Out-Null
                    Move-Item -LiteralPath (Join-Path $Repo $p) -Destination $to
                }
                $out = & $git -C $Repo -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=20 `
                           pull --ff-only --quiet 2>&1 | ForEach-Object { "$_" }
                if ($LASTEXITCODE -eq 0) {
                    $after = (& $git -C $Repo rev-parse --short HEAD 2>&1 | Select-Object -First 1) -as [string]
                    & $Say "routines updated $before -> $after (moved $($paths.Count) untracked copies identical to GitHub's aside to $dest)"
                    return "updated"
                }
            } elseif ($differ.Count) {
                & $Say "WARN: routines NOT updated - untracked file(s) differ from GitHub's and were left alone: $($differ -join ', ') -- using the prompts on disk"
                return "kept"
            }
        }
        $why = (($out | Where-Object { $_ -match '\S' }) | Select-Object -First 2) -join " / "
        & $Say "WARN: routines NOT updated - git pull --ff-only refused or failed: $why -- using the prompts on disk"
        return "kept"
    } catch {
        & $Say "WARN: routines NOT updated - $($_.Exception.Message) -- using the prompts on disk"
        return "kept"
    } finally {
        if ($held) { $mutex.ReleaseMutex() }
        $mutex.Dispose()
    }
}
