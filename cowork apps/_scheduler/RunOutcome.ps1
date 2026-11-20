# RunOutcome.ps1 - did this routine run really produce something? (19 Nov 2026)
# Dot-sourced by Run-CoworkRoutine.ps1; tested by test_run_outcome.ps1.
#
# Why this exists: a finished job says nothing about whether an app was written. The wrapper already
# caught "Reached max turns", a usage limit and an empty reply, but two runs that week still logged a
# clean "state=Completed" while leaving an EMPTY page shell behind:
#   - 17 Nov, Inspirational: the run ended on "API Error: Output blocked by content filtering policy".
#   - 19 Nov, Table games:   "You've hit your 5-hour limit", six minutes in. The old pattern
#     (hit your (\w+ )?limit) could not match "5-hour" because of the hyphen.
# Each had written the page's layout with /*__JS__*/-style placeholders and stopped before the code.
# The nightly check on the desktop noticed (unfinished build); nothing here did.
#
# Get-RunOutcome  : $null for a healthy run, or a short tag for the DONE line (degraded=<tag>).
# Get-SignInExpiry: the two dates from the CLI's "this sign-in ends between A and B" warning, or $null.
# Rename-UnfinishedApps: a page this run left with placeholders is renamed <name>.html.unfinished,
#                   in place, so the app server and the registry stop listing an empty app.

function Get-RunOutcome {
    param([string]$Text)
    if ($null -eq $Text) { $Text = "" }
    if ($Text -match '(?i)Reached max turns') { return 'max-turns' }
    # Any usage cap: "session", "weekly", "5-hour", ... (12 Oct: "weekly" slipped past a session-only match.)
    if ($Text -match "(?i)hit your ([\w-]+ )?limit") {
        if ($Matches[1]) { return "$($Matches[1].Trim().ToLower())-limit" } else { return 'usage-limit' }
    }
    # Signed out. NOT the routine "this sign-in ends between ... Run claude auth login before then"
    # warning, which every healthy run prints in the days before it lapses.
    if ($Text -match '(?i)please run /login|not logged in|oauth token (has )?expired|authentication_error|invalid api key') { return 'signed-out' }
    # The CLI prints a fatal API error on a line of its own, and the run ENDS there. Only the last few
    # lines count: on 9 Nov the Crafts run printed "API Error: Can't reach the API server" first, got
    # through on a retry and built Resin Pour Bench; flagging that would have had catch-up build a second
    # app. Line-start only, so a report that merely talks about API errors is not flagged either.
    $last = @($Text -split "`r?`n" | Where-Object { $_.Trim() -and $_ -notmatch '^SessionEnd hook' } | Select-Object -Last 3)
    if (@($last | Where-Object { $_ -match '^API Error\b' }).Count) { return 'api-error' }
    if ($Text.Trim().Length -lt 200) { return 'empty-output' }
    return $null
}

function Get-SignInExpiry {
    param([string]$Text)
    if ($Text -match 'sign-in ends between (\d{4}-\d{2}-\d{2}) and (\d{4}-\d{2}-\d{2})') { return @{ From = $Matches[1]; To = $Matches[2] } }
    return $null
}

function Rename-UnfinishedApps {
    # Only pages CREATED since this run began and still holding a placeholder: an older file, or one a
    # person is editing by hand, is never touched. Returns the new paths.
    param(
        [Parameter(Mandatory)][string]$Root,
        [Parameter(Mandatory)][datetime]$Since,
        [scriptblock]$Say = $null
    )
    $skip = '\\(node_modules|_scheduler|\.git|_backups|test_reports|test_screens)\\'
    $done = @()
    $files = @(Get-ChildItem -LiteralPath $Root -Recurse -File -Filter *.html -ErrorAction SilentlyContinue |
        Where-Object { $_.CreationTime -ge $Since -and $_.FullName -notmatch $skip })
    foreach ($f in $files) {
        $text = $null
        try { $text = [System.IO.File]::ReadAllText($f.FullName) } catch { continue }
        if ($text -notmatch '/\*__[A-Z0-9_]+__\*/') { continue }
        $to = $f.FullName + ".unfinished"
        if (Test-Path -LiteralPath $to) { $to = $f.FullName + "." + (Get-Date -Format 'HHmmss') + ".unfinished" }
        try {
            Move-Item -LiteralPath $f.FullName -Destination $to -ErrorAction Stop
            $done += $to
            if ($Say) { & $Say "WARN: unfinished page set aside (placeholders left, no code written): $to" }
        } catch {
            if ($Say) { & $Say "WARN: could not set aside unfinished page $($f.FullName): $($_.Exception.Message)" }
        }
    }
    return ,$done
}
