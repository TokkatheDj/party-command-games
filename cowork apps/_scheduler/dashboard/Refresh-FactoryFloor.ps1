# Refresh-FactoryFloor.ps1
# Rebuilds the "App Factory Floor" dashboard from the live registry and logs.
#
# Everything the page shows is derived here -- no figure is ever hand-typed.
# Three steps, in order:
#   1. Rebuild-Registry.ps1  -- rescan every app folder for <!-- CONCEPT: --> headers
#   2. build_data.py         -- schedule + last-run health + overlap  -> factory.json
#   3. render.py             -- inject data and the OKLCH colour scale -> app-factory-floor.html
#
# Publishing is deliberately NOT done here: it needs Claude Code's Artifact tool.
# See the reminder printed at the end -- the shared-version step is easy to miss.
#
# Usage:  pwsh -File Refresh-FactoryFloor.ps1  [-SkipRegistry] [-Check]

[CmdletBinding()]
param(
    # The scheduled routines already rebuild the registry before every run, so
    # skipping is safe if one has run since the last app was written.
    [switch]$SkipRegistry,
    # Run the static CSS/theme checks over the rendered page.
    [switch]$Check
)

$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Sched = Split-Path -Parent $Here

function Resolve-Python {
    foreach ($c in @("python", "python3", "py")) {
        $p = (Get-Command $c -ErrorAction SilentlyContinue)
        if ($p) { return $p.Source }
    }
    foreach ($p in @("C:\Python314\python.exe", "C:\Python313\python.exe", "C:\Python312\python.exe")) {
        if (Test-Path -LiteralPath $p) { return $p }
    }
    throw "No Python interpreter found (looked on PATH and in C:\PythonNNN)."
}
$py = Resolve-Python

function Step([string]$label, [scriptblock]$body) {
    Write-Host "==> $label" -ForegroundColor Cyan
    & $body
    if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
        throw "$label failed (exit $LASTEXITCODE)"
    }
}

if (-not $SkipRegistry) {
    Step "Rebuilding concept registry" {
        & (Join-Path $Sched "Rebuild-Registry.ps1")
    }
} else {
    Write-Host "==> Skipping registry rebuild (-SkipRegistry)" -ForegroundColor DarkGray
}

Step "Extracting schedule, run health and overlap" {
    & $py (Join-Path $Here "build_data.py")
}

Step "Rendering the page" {
    & $py (Join-Path $Here "render.py")
}

if ($Check) {
    Step "Checking theme tokens and page structure" {
        & $py (Join-Path $Here "check.py")
    }
}

$html = Join-Path $Here "app-factory-floor.html"
$size = (Get-Item -LiteralPath $html).Length

Write-Host ""
Write-Host "Rebuilt: $html ($('{0:N0}' -f $size) bytes)" -ForegroundColor Green
Write-Host ""
Write-Host "To publish the refreshed page, ask Claude Code:" -ForegroundColor Yellow
Write-Host "    update the App Factory Floor artifact at"
Write-Host "    https://claude.ai/code/artifact/e16b5725-991d-410e-a1c1-eacc97d51224"
Write-Host "    from $html"
Write-Host "  (Name that URL. Publishing this path WITHOUT it forks a second artifact" -ForegroundColor DarkGray
Write-Host "   rather than updating the one you already shared.)" -ForegroundColor DarkGray
Write-Host ""
Write-Host "Then re-pin the shared version, or the public link keeps serving the old one:" -ForegroundColor Yellow
Write-Host "    Share -> Shared version -> pick the newest"
Write-Host "  (A publicly shared artifact cannot track 'Latest' -- it must be pinned each time.)"
