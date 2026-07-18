# Setup-ServerBootTask.ps1
# Registers a Windows Task Scheduler job that starts the Cowork Apps (AppVerse)
# server at BOOT, before login ("run whether user is logged on or not").
# Requires admin. Prints every step to the console AND writes the outcome to
# %LOCALAPPDATA%\CoworkApps\setup-result.txt so success/failure is inspectable.

$ErrorActionPreference = 'Stop'
$LogDir = Join-Path $env:LOCALAPPDATA 'CoworkApps'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Result = Join-Path $LogDir 'setup-result.txt'

function Write-Result($msg) {
    "$([DateTime]::Now.ToString('s'))  $msg" | Set-Content -Path $Result -Encoding UTF8
    Write-Host $msg
}

# --- report elevation state ---
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
Write-Host ("RunningAs = {0}   IsAdmin = {1}   LOCALAPPDATA = {2}" -f (whoami), $isAdmin, $env:LOCALAPPDATA)

if (-not $isAdmin) {
    Write-Host "Not elevated -- this must be run from an Administrator PowerShell."
    Write-Host "Right-click Start -> Terminal (Admin), then re-run this script."
    Write-Result "SKIPPED: not elevated (no registration attempted)"
    return
}

try {
    # Project was relocated OUT of OneDrive to this plain local path. A non-OneDrive
    # path is required for a pre-login/session-0 task (OneDrive placeholders can
    # report ERROR_DIRECTORY before the profile is hydrated).
    $Dir = 'C:\Users\tokka\Claude Local\cowork apps'
    Write-Host "Target dir: $Dir  (exists = $(Test-Path -LiteralPath $Dir))"

    # Resolve python without depending on PATH (elevated -NoProfile PATH can differ).
    $Py = $null
    foreach ($cand in @('C:\Python314\python.exe','C:\Python313\python.exe','C:\Python312\python.exe')) {
        if (Test-Path $cand) { $Py = $cand; break }
    }
    if (-not $Py) { $Py = (Get-Command python -ErrorAction SilentlyContinue)?.Source }
    if (-not $Py) { Write-Result "FAIL: python.exe not found"; return }
    Write-Host "Python: $Py"

    $TaskName = 'CoworkApps-Server-Boot'
    $Me  = whoami
    $Log = Join-Path $LogDir 'server-boot.log'

    # cmd wrapper cd's into the app dir itself (not relying on the scheduler's
    # working-directory field) and redirects stdout+stderr so the server never
    # needs a console in session 0.
    $ArgLine = '/c "cd /d "' + $Dir + '" && "' + $Py + '" serve_apps.py >> "' + $Log + '" 2>&1"'

    $Action    = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument $ArgLine -WorkingDirectory $Dir
    $Trigger   = New-ScheduledTaskTrigger -AtStartup
    $Settings  = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -MultipleInstances IgnoreNew -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    $Principal = New-ScheduledTaskPrincipal -UserId $Me -LogonType S4U -RunLevel Limited

    Write-Host "Unregistering any existing task..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Registering $TaskName ..."
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
        -Settings $Settings -Principal $Principal -Force | Out-Null

    $chk = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($chk) {
        Write-Result ("OK: registered $TaskName (AtStartup, S4U) dir=$Dir python=$Py")
    } else {
        Write-Result "FAIL: task missing after Register-ScheduledTask"
    }
} catch {
    Write-Result ("FAIL: " + $_.Exception.Message)
}
