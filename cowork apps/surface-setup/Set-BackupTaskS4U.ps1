# Set-BackupTaskS4U.ps1
# Switches the existing "Backup Cowork Content" scheduled task from an Interactive
# principal to S4U ("run whether user is logged on or not"), preserving its existing
# daily trigger, action, and settings. Requires admin. Prints every step and writes
# the outcome to %LOCALAPPDATA%\CoworkApps\backup-s4u-result.txt.
#
# NOTE: the backup writes to Google Drive (G:), a per-user mount. When this runs
# while logged OFF, G: is absent and the script skips (logs "G: not mounted");
# when logged ON it runs normally. S4U therefore only broadens coverage -- it does
# not, by itself, make backups happen while signed out.

$ErrorActionPreference = 'Stop'
$LogDir = Join-Path $env:LOCALAPPDATA 'CoworkApps'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Result = Join-Path $LogDir 'backup-s4u-result.txt'

function Write-Result($msg) {
    "$([DateTime]::Now.ToString('s'))  $msg" | Set-Content -Path $Result -Encoding UTF8
    Write-Host $msg
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
Write-Host ("RunningAs = {0}   IsAdmin = {1}" -f (whoami), $isAdmin)
if (-not $isAdmin) {
    Write-Host "Not elevated -- run from an Administrator PowerShell (Start -> Terminal (Admin))."
    Write-Result "SKIPPED: not elevated"
    return
}

try {
    $TaskName = 'Backup Cowork Content'
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) { Write-Result "FAIL: task '$TaskName' not found"; return }

    Write-Host ("Before: LogonType = {0}, UserId = {1}" -f $t.Principal.LogonType, $t.Principal.UserId)

    $Me = whoami
    $Principal = New-ScheduledTaskPrincipal -UserId $Me -LogonType S4U -RunLevel Limited

    # Update ONLY the principal; action/trigger/settings are retained.
    Set-ScheduledTask -TaskName $TaskName -Principal $Principal | Out-Null

    $after = Get-ScheduledTask -TaskName $TaskName
    Write-Host ("After:  LogonType = {0}, UserId = {1}" -f $after.Principal.LogonType, $after.Principal.UserId)
    Write-Host ("Trigger preserved: {0}" -f $after.Triggers[0].CimClass.CimClassName)
    Write-Host ("Action preserved:  {0} {1}" -f $after.Actions[0].Execute, $after.Actions[0].Arguments)

    if ($after.Principal.LogonType -eq 'S4U') {
        Write-Result "OK: '$TaskName' switched to S4U (RunLevel Limited)"
    } else {
        Write-Result ("FAIL: LogonType is {0}, expected S4U" -f $after.Principal.LogonType)
    }
} catch {
    Write-Result ("FAIL: " + $_.Exception.Message)
}
