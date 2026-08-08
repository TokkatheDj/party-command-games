# Run-DailyDJApp.ps1
# Worker: builds today's DJ app via the local Claude CLI and saves it into dj_music_apps.
# Invoked by the "CoworkApps-DailyDJApp" scheduled task (see Setup-DailyDJApp.ps1),
# or run manually to build one on demand:  powershell -File .\Run-DailyDJApp.ps1

$AppsDir    = $PSScriptRoot
$PromptFile = Join-Path $AppsDir 'dj_daily_prompt.txt'
$LogFile    = Join-Path $AppsDir 'dj_daily.log'
$Claude     = Join-Path $env:USERPROFILE '.local\bin\claude.exe'

$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$date  = Get-Date -Format 'yyyy-MM-dd'

Add-Content $LogFile "`n===== DJ daily build $stamp ====="

if (-not (Test-Path $Claude)) {
    Add-Content $LogFile "ERROR: claude CLI not found at $Claude"
    exit 1
}
if (-not (Test-Path $PromptFile)) {
    Add-Content $LogFile "ERROR: prompt file not found at $PromptFile"
    exit 1
}

# Inject today's date into the prompt template.
$prompt = (Get-Content $PromptFile -Raw) -replace '\{\{DATE\}\}', $date

# Run Claude headless, scoped to the apps folder, with permissions bypassed so it can
# read the folder and write the new file unattended. Append all output to the log.
Push-Location $AppsDir
try {
    $prompt | & $Claude -p --permission-mode bypassPermissions 2>&1 | Add-Content $LogFile
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

Add-Content $LogFile "===== done $stamp (exit $code) ====="
exit $code
