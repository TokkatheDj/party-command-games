# Run-Tests.ps1 — Mobile test agent for Cowork Apps

param(
    [string]$Category  = "",   # e.g. "kids", "music"
    [string]$App       = "",   # e.g. "star catcher"
    [string]$ServerUrl = "",   # e.g. "http://192.168.0.248:8080"
    [switch]$Install           # Run first-time setup
)

$AppsDir = $PSScriptRoot
$TestScript = "$AppsDir\test_apps.js"

# First-time setup: install Playwright browsers
if ($Install) {
    Write-Host "`n  Installing Playwright Chromium browser..." -ForegroundColor Cyan
    npx playwright install chromium
    Write-Host "  Done! Run .\Run-Tests.ps1 to start testing.`n" -ForegroundColor Green
    exit
}

# Check Playwright is available
$playwrightCheck = npx playwright --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "`n  Playwright not found. Run: .\Run-Tests.ps1 -Install`n" -ForegroundColor Red
    exit 1
}

# Check for browser binaries
$chromiumPath = "$env:USERPROFILE\AppData\Local\ms-playwright"
if (-not (Test-Path $chromiumPath)) {
    Write-Host "`n  Playwright browsers not installed. Running: .\Run-Tests.ps1 -Install`n" -ForegroundColor Yellow
    npx playwright install chromium
}

Write-Host ""
Write-Host "  Cowork Apps — Mobile Test Agent" -ForegroundColor Cyan
Write-Host "  Testing: iPhone 14 + iPad Pro viewports" -ForegroundColor Gray
Write-Host ""

# Build args
$nodeArgs = @($TestScript)
if ($Category) { $nodeArgs += "--category"; $nodeArgs += $Category }
if ($App)      { $nodeArgs += "--app";      $nodeArgs += $App }
if ($ServerUrl){ $nodeArgs += "--url";      $nodeArgs += $ServerUrl }

# Run tests
Set-Location $AppsDir
node @nodeArgs

# Open report
$ReportPath = "$AppsDir\test_reports\index.html"
if (Test-Path $ReportPath) {
    Write-Host "  Opening report..." -ForegroundColor Gray
    Start-Process $ReportPath
}
