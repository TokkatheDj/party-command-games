# test_run_outcome.ps1 - RunOutcome.ps1 against the real endings of this factory's runs (19 Nov 2026).
# Exits 1 on any failure.
#   powershell -NoProfile -File test_run_outcome.ps1      (Windows PowerShell 5.1, like the tasks)
#   pwsh -NoProfile -File test_run_outcome.ps1
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "RunOutcome.ps1")

$script:fails = 0
function Check([string]$name, [bool]$ok, [string]$detail = "") {
    if ($ok) { Write-Host "PASS  $name" } else { Write-Host "FAIL  $name  -- $detail"; $script:fails++ }
}
$pad = ("I built an app and tested it on a phone-sized screen. " * 8)      # a normal, long-enough reply
$hook = 'SessionEnd hook [bash ${CLAUDE_PLUGIN_ROOT}/viz/hooks/session_end.sh] failed: Error occurred while executing hook command: Executable not found in $PATH: "bash"'
$warn = "Warning: this sign-in ends between 2026-11-22 and 2026-11-25 (in 3 days at the earliest). Renewing it does not move those dates. Run claude auth login before then, or use claude setup-token for unattended jobs."

# --- the two runs that logged a clean Completed and left an empty page ---
$nov19 = "$warn`nHeads up: another session already has Cowork Apps open (it started at 09:26).`n`nSeven new apps haven't been committed to git yet.`n`nWhat do you want to do in this session?`n`nYou've hit your 5-hour limit $([char]0xB7) resets 12:10pm (America/New_York)`n$hook"
Check "19 Nov Table games: 'hit your 5-hour limit' is a failed run (the old pattern missed the hyphen)" ((Get-RunOutcome $nov19) -eq '5-hour-limit') "got '$(Get-RunOutcome $nov19)'"
$nov17 = "$warn`nWhat would you like to work on? I'm in the cowork apps folder, on master.`n`nI can commit the four apps and clear out the screenshots, build something new, or pick up another task.`n`nAPI Error: Output blocked by content filtering policy`n$hook"
Check "17 Nov Inspirational: 'API Error: Output blocked...' is a failed run" ((Get-RunOutcome $nov17) -eq 'api-error') "got '$(Get-RunOutcome $nov17)'"

# --- what was already caught must still be caught ---
Check "weekly limit (12 Oct)" ((Get-RunOutcome "$pad`nYou've hit your weekly limit $([char]0xB7) resets Monday`n$hook") -eq 'weekly-limit')
Check "session limit" ((Get-RunOutcome "$pad`nYou've hit your session limit") -eq 'session-limit')
Check "a limit with no word in front" ((Get-RunOutcome "$pad`nYou have hit your limit for now.") -eq 'usage-limit')
Check "max turns" ((Get-RunOutcome "$pad`nError: Reached max turns (60)") -eq 'max-turns')
Check "an empty reply padded only by the hook error is still empty" ((Get-RunOutcome $hook) -eq 'empty-output') "got '$(Get-RunOutcome $hook)'"
Check "null text is empty-output, not a crash" ((Get-RunOutcome $null) -eq 'empty-output')

# --- healthy runs must stay healthy ---
$good = "$warn`nI built **Three Good Things**, an evening watercolour daybook, and saved it.`n$pad`nThere were no console errors.`n$hook"
Check "a healthy run that prints the sign-in WARNING is not flagged" ($null -eq (Get-RunOutcome $good)) "got '$(Get-RunOutcome $good)'"
$report = "$pad`nBug check: the tutor chat shows 'API Error: 500' in red when the server is down; I added a retry. The limit you hit your head on is the 60-turn cap.`n$pad"
Check "a report that only TALKS about API errors mid-line is not flagged" ($null -eq (Get-RunOutcome $report)) "got '$(Get-RunOutcome $report)'"
$nov9 = "API Error: Can't reach the API server - check your internet or DNS (ENOTFOUND)`n`nI built **Resin Pour Bench**, a new Crafts app.`n$pad`nThere were no console errors.`n$hook"
Check "9 Nov Crafts: an API error FIRST, then a finished app, is a healthy run" ($null -eq (Get-RunOutcome $nov9)) "got '$(Get-RunOutcome $nov9)'"
$lost = "$pad`nAPI Error: Connection lost mid-response. The response above may be incomplete.`n$hook"
Check "an API error on the last real line (before the hook noise) is a failed run" ((Get-RunOutcome $lost) -eq 'api-error')
Check "the catch-up pattern reads the new tags" (("degraded=5-hour-limit" -match "degraded=(empty-output|api-error|[\w-]*limit)") -and ("degraded=api-error" -match "degraded=(empty-output|api-error|[\w-]*limit)") -and -not ("degraded=signed-out" -match "degraded=(empty-output|api-error|[\w-]*limit)") -and -not ("degraded=max-turns" -match "degraded=(empty-output|api-error|[\w-]*limit)"))

# --- signed out ---
Check "'Please run /login' is signed-out" ((Get-RunOutcome "Invalid API key $([char]0xB7) Please run /login") -eq 'signed-out')
Check "an expired token is signed-out" ((Get-RunOutcome "$pad`nOAuth token has expired. $pad") -eq 'signed-out')

# --- the sign-in warning's dates ---
$e = Get-SignInExpiry $good
Check "sign-in expiry dates are read from the warning" ($e -and $e.From -eq '2026-11-22' -and $e.To -eq '2026-11-25')
Check "no warning, no dates" ($null -eq (Get-SignInExpiry $pad))

# --- setting an unfinished page aside ---
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("runoutcome-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path "$tmp\table_games_apps", "$tmp\kids_apps", "$tmp\_scheduler\Parked", "$tmp\node_modules\x" | Out-Null
try {
    $shell = "<!DOCTYPE html><title>Ibex Pass</title><script>`n/*__JS1__*/`n/*__JS2__*/`n</script>"
    $done  = "<!DOCTYPE html><title>Finished</title><script>const a = 1; /* a normal comment */</script>"
    Set-Content -LiteralPath "$tmp\table_games_apps\old-shell.html" -Value $shell -Encoding UTF8
    (Get-Item "$tmp\table_games_apps\old-shell.html").CreationTime = (Get-Date).AddDays(-3)
    $since = Get-Date
    Start-Sleep -Milliseconds 1200
    Set-Content -LiteralPath "$tmp\table_games_apps\2026-11-19-halma.html" -Value $shell -Encoding UTF8
    Set-Content -LiteralPath "$tmp\kids_apps\2026-11-19-finished.html" -Value $done -Encoding UTF8
    Set-Content -LiteralPath "$tmp\_scheduler\Parked\template.html" -Value $shell -Encoding UTF8
    Set-Content -LiteralPath "$tmp\node_modules\x\page.html" -Value $shell -Encoding UTF8
    $said = New-Object System.Collections.ArrayList
    $moved = Rename-UnfinishedApps -Root $tmp -Since $since -Say { param($m) [void]$said.Add($m) }
    Check "the page this run left unfinished is renamed .unfinished" ((Test-Path "$tmp\table_games_apps\2026-11-19-halma.html.unfinished") -and -not (Test-Path "$tmp\table_games_apps\2026-11-19-halma.html"))
    Check "exactly one page was set aside, and it was logged" (@($moved).Count -eq 1 -and $said.Count -eq 1 -and "$($said[0])" -match 'unfinished page set aside') "moved=$(@($moved).Count) said=$($said.Count)"
    Check "a finished page made in the same run is untouched" (Test-Path "$tmp\kids_apps\2026-11-19-finished.html")
    Check "an OLDER shell is untouched (only this run's pages)" (Test-Path "$tmp\table_games_apps\old-shell.html")
    Check "_scheduler and node_modules are never searched" ((Test-Path "$tmp\_scheduler\Parked\template.html") -and (Test-Path "$tmp\node_modules\x\page.html"))
    $again = Rename-UnfinishedApps -Root $tmp -Since $since
    Check "running it twice does nothing more" (@($again).Count -eq 0)
} finally { Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }

if ($script:fails) { Write-Host "`n$($script:fails) FAILED"; exit 1 }
Write-Host "`nall passed"; exit 0
