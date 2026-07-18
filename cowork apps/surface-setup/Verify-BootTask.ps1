# Verify-BootTask.ps1  --  run AFTER a reboot to prove the server boot task fired.
# Read-only. No admin needed. Run:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File "C:\Users\tokka\AppData\Local\CoworkApps\Verify-BootTask.ps1"

$baseline = [datetime]'2026-07-18 05:28:10'   # anything booted after this = a real reboot happened

$os   = Get-CimInstance Win32_OperatingSystem
$boot = $os.LastBootUpTime
$rebooted = $boot -gt $baseline

Write-Host "==================== BOOT TASK VERIFICATION ===================="
Write-Host ("Last boot time : {0}" -f $boot)
Write-Host ("Reboot since staging? : {0}" -f $(if ($rebooted) {'YES'} else {'NO -- machine has NOT rebooted yet'}))
Write-Host ""

# 1. Did the boot task run, and when relative to boot?
$info = Get-ScheduledTaskInfo -TaskName 'CoworkApps-Server-Boot' -ErrorAction SilentlyContinue
$task = Get-ScheduledTask     -TaskName 'CoworkApps-Server-Boot' -ErrorAction SilentlyContinue
Write-Host ("Boot task state       : {0}" -f $task.State)
Write-Host ("Boot task LastRunTime : {0}" -f $info.LastRunTime)
Write-Host ("Boot task LastResult  : 0x{0:X8}" -f ([uint32]$info.LastRunResult))

# 2. Is the server up, and in which session? SessionId 0 = started pre-login by the task.
$conn = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $pidn = ($conn.OwningProcess | Select-Object -First 1)
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidn"
    Write-Host ("Server on 8080        : PID {0}  SessionId {1}  (created {2})" -f $pidn, $proc.SessionId, $proc.CreationDate)
    try { $code = (Invoke-WebRequest http://localhost:8080/ -UseBasicParsing -TimeoutSec 6).StatusCode } catch { $code = "ERR $($_.Exception.Message)" }
    Write-Host ("GET / -> {0}" -f $code)
} else {
    Write-Host "Server on 8080        : NOT LISTENING"
}

# 3. Fresh boot-log evidence
$log = 'C:\Users\tokka\AppData\Local\CoworkApps\server-boot.log'
Write-Host ""
Write-Host "--- server-boot.log (tail 6) ---"
if (Test-Path $log) { Get-Content $log -Tail 6 } else { Write-Host "(no boot log)" }

# 4. Login VBS still present (session-1 fallback)
$vbs = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\CoworkApps-Server.vbs"
Write-Host ""
Write-Host ("Login-VBS fallback present : {0}" -f (Test-Path $vbs))

# 4b. Backup task: did a NEW snapshot appear after the baseline (i.e. from the
#     temporary AtLogon trigger)? That trigger fires ~3 min after logon, so if you
#     run this sooner it may not have fired yet.
Write-Host ""
Write-Host "--- backup task (temporary AtLogon trigger) ---"
$dest = 'G:\My Drive\Backups\cowork-apps-content'
$gOk  = Test-Path 'G:\'
Write-Host ("Google Drive G: mounted : {0}" -f $gOk)
$newSnap = $null
if ($gOk) {
    $newest = Get-ChildItem $dest -Filter 'cowork-content-*.zip' -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($newest) {
        $newSnap = $newest.LastWriteTime -gt $baseline
        Write-Host ("Newest snapshot         : {0}  ({1})" -f $newest.Name, $newest.LastWriteTime)
        Write-Host ("Newer than baseline?    : {0}" -f $(if ($newSnap) {'YES -- backup fired since reboot'} else {'no -- AtLogon backup has not fired yet (wait ~3 min after login) or was skipped'}))
    } else { Write-Host "Newest snapshot         : (none found)" }
}
$binfo = Get-ScheduledTaskInfo -TaskName 'Backup Cowork Content' -EA SilentlyContinue
Write-Host ("Backup task LastRunTime : {0}   LastResult 0x{1:X8}" -f $binfo.LastRunTime, ([uint32]$binfo.LastRunResult))
Write-Host "--- backup log tail (3) ---"
$blog = 'C:\Users\tokka\bin\Backup-CoworkContent.log'
if (Test-Path $blog) { Get-Content $blog -Tail 3 }

# Verdict
Write-Host ""
$pass = $rebooted -and $conn -and ($info.LastRunTime -gt $baseline)
Write-Host ("VERDICT: {0}" -f $(if ($pass) {'PASS -- boot task fired after reboot and server is serving'} `
                                elseif (-not $rebooted) {'INCONCLUSIVE -- no reboot detected yet'} `
                                else {'CHECK -- reboot happened but server/boot-task evidence is missing (see above)'}))
Write-Host "==============================================================="
