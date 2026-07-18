# Add-BackupTestTrigger.ps1
# TEMPORARY: adds an AtLogon trigger (with a delay to let Google Drive mount G:)
# to "Backup Cowork Content" so a reboot+login exercises the backup from the
# scheduler. Keeps the existing daily 14:00 trigger. Requires admin.
# Remove afterward with:  -Remove
#   pwsh -NoProfile -ExecutionPolicy Bypass -File "<thisfile>" -Remove
param([switch]$Remove)

$ErrorActionPreference = 'Stop'
$LogDir = Join-Path $env:LOCALAPPDATA 'CoworkApps'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Result = Join-Path $LogDir 'backup-trigger-result.txt'
function Write-Result($msg) {
    "$([DateTime]::Now.ToString('s'))  $msg" | Set-Content -Path $Result -Encoding UTF8
    Write-Host $msg
}

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
Write-Host ("RunningAs = {0}   IsAdmin = {1}   Mode = {2}" -f (whoami), $isAdmin, $(if($Remove){'REMOVE'}else{'ADD'}))
if (-not $isAdmin) { Write-Host "Not elevated -- run from an Administrator PowerShell."; Write-Result "SKIPPED: not elevated"; return }

try {
    $TaskName = 'Backup Cowork Content'
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $t) { Write-Result "FAIL: task '$TaskName' not found"; return }

    $Me = whoami
    # Keep only NON-logon triggers (the daily one); we manage the AtLogon one here.
    $daily = @($t.Triggers | Where-Object { $_.CimClass.CimClassName -ne 'MSFT_TaskLogonTrigger' })
    Write-Host ("Existing non-logon triggers kept: {0}" -f $daily.Count)

    if ($Remove) {
        Set-ScheduledTask -TaskName $TaskName -Trigger $daily | Out-Null
        $after = Get-ScheduledTask -TaskName $TaskName
        Write-Host ("Triggers now: {0}" -f (($after.Triggers | ForEach-Object { $_.CimClass.CimClassName }) -join ', '))
        Write-Result "OK: removed temporary AtLogon trigger (daily trigger retained)"
        return
    }

    # Build the temporary AtLogon trigger with a 3-minute delay (Drive mount grace).
    $logon = New-ScheduledTaskTrigger -AtLogOn -User $Me
    $logon.Delay = 'PT3M'

    Set-ScheduledTask -TaskName $TaskName -Trigger ($daily + $logon) | Out-Null

    $after = Get-ScheduledTask -TaskName $TaskName
    $names = ($after.Triggers | ForEach-Object { $_.CimClass.CimClassName }) -join ', '
    Write-Host ("Triggers now: {0}" -f $names)
    Write-Host ("Principal:    {0} / {1}" -f $after.Principal.LogonType, $after.Principal.UserId)
    if ($names -match 'MSFT_TaskLogonTrigger') {
        Write-Result "OK: added temporary AtLogon trigger (delay 3m). Remove later with -Remove."
    } else {
        Write-Result "FAIL: AtLogon trigger not present after Set-ScheduledTask"
    }
} catch {
    Write-Result ("FAIL: " + $_.Exception.Message)
}
