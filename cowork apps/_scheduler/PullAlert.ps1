# PullAlert.ps1 (22 Nov 2026)
# After Update-Routines returns "kept" (the pull was refused, the run uses the prompts on disk), hand the
# WARN line to pull_alert.py, which emails Lance at most once a day. Without this the only trace of a
# blocked pull was that WARN line: on 20-21 Nov ~36 factory runs used stale prompts and nobody knew.
# Never throws and never fails the run. Dot-sourced by Run-CoworkRoutine.ps1; test_pull_alert.ps1 tests it.

function Invoke-PullAlert {
    param(
        [string]$Result,                       # what Update-Routines returned
        [string]$Warn,                         # the last "WARN: routines NOT updated ..." line, if any
        [Parameter(Mandatory)][scriptblock]$Say,
        [string]$Python,                       # default: the interpreter the CoworkApps tasks use
        [string]$Script,                       # default: pull_alert.py next to this file
        [string[]]$Extra = @()                 # extra arguments for pull_alert.py (tests: --dry-run, --state)
    )
    $ErrorActionPreference = "Continue"
    try {
        if ($Result -ne "kept" -or -not $Warn) { return "none" }
        if (-not $Python) {
            $Python = if (Test-Path -LiteralPath "C:\Python314\python.exe") { "C:\Python314\python.exe" }
                      else { (Get-Command python -ErrorAction SilentlyContinue).Source }
        }
        if (-not $Python) { & $Say "pull_alert: python not found - no email"; return "no-python" }
        if (-not $Script) { $Script = Join-Path $PSScriptRoot "pull_alert.py" }
        $out = @(& $Python -I $Script @Extra $Warn 2>&1 | ForEach-Object { "$_" })
        $line = $out | Where-Object { $_ -match '^pull_alert:' } | Select-Object -First 1
        if ($line) { & $Say $line } else { & $Say "pull_alert: no result ($($out -join ' / '))" }
        return "called"
    } catch {
        & $Say "pull_alert: could not run - $($_.Exception.Message)"
        return "error"
    }
}
