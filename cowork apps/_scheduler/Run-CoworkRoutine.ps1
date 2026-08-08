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
    [int]$TimeoutMin   = 40,
    [int]$MaxTurns     = 40
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

if (-not (Test-Path -LiteralPath $PromptFile)) {
    W "ERROR: prompt file not found: $PromptFile"
    exit 1
}
$prompt = Get-Content -Raw -LiteralPath $PromptFile

$claude = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $claude) { $claude = "C:\Users\tokka\.local\bin\claude" }
if (-not (Test-Path -LiteralPath $claude)) {
    W "ERROR: claude CLI not found (looked on PATH and at $claude)"
    exit 1
}

# Edit(...) is scoped to the workspace so an unattended run can only modify files
# in here; Read/Glob/Grep/LS let it survey the collection like the cloud run did.
$allow = "Edit($Root\**),Read($Root\**),Glob,Grep,LS"

W "=== START '$Name'  (timeout ${TimeoutMin}m, max-turns $MaxTurns) ==="
$sw = [System.Diagnostics.Stopwatch]::StartNew()

$job = Start-Job -ScriptBlock {
    param($claude, $prompt, $allow, $root, $maxturns)
    Set-Location -LiteralPath $root
    & $claude --permission-mode dontAsk -p $prompt --allowedTools $allow --max-turns $maxturns 2>&1
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
