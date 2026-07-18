# Verify-BootTask.ps1  --  run AFTER a reboot to prove ONLY the boot task starts
# the server (login VBS is disabled). Read-only. No admin needed. Run:
#   pwsh -NoProfile -ExecutionPolicy Bypass -File "C:\Users\tokka\AppData\Local\CoworkApps\Verify-BootTask.ps1"

$baseline = [datetime]'2026-07-18 07:00:28'   # anything booted after this = a real reboot happened

$os   = Get-CimInstance Win32_OperatingSystem
$boot = $os.LastBootUpTime
$rebooted = $boot -gt $baseline

Write-Host "==================== BOOT TASK VERIFICATION ===================="
Write-Host ("Last boot time        : {0}" -f $boot)
Write-Host ("Reboot since staging? : {0}" -f $(if ($rebooted) {'YES'} else {'NO -- machine has NOT rebooted yet'}))
Write-Host ""

# 1. Did the boot task run, and when relative to boot?
$info = Get-ScheduledTaskInfo -TaskName 'CoworkApps-Server-Boot' -ErrorAction SilentlyContinue
$task = Get-ScheduledTask     -TaskName 'CoworkApps-Server-Boot' -ErrorAction SilentlyContinue
$bootTaskRan = $info.LastRunTime -gt $baseline
Write-Host ("Boot task state       : {0}" -f $task.State)
Write-Host ("Boot task LastRunTime : {0}  (after reboot: {1})" -f $info.LastRunTime, $bootTaskRan)
Write-Host ("Boot task LastResult  : 0x{0:X8}" -f ([uint32]$info.LastRunResult))

# 2. Is the server up, and in which session? SessionId 0 = started pre-login by the task.
$conn = Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue
$serverSession0 = $false
if ($conn) {
    $pidn = ($conn.OwningProcess | Select-Object -First 1)
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$pidn"
    $serverSession0 = ($proc.SessionId -eq 0)
    Write-Host ("Server on 8080        : PID {0}  SessionId {1}  (created {2})" -f $pidn, $proc.SessionId, $proc.CreationDate)
    Write-Host ("  -> started by boot task (Session 0)? {0}" -f $serverSession0)
    try { $code = (Invoke-WebRequest http://localhost:8080/ -UseBasicParsing -TimeoutSec 6).StatusCode } catch { $code = "ERR $($_.Exception.Message)" }
    Write-Host ("GET / -> {0}" -f $code)
} else {
    Write-Host "Server on 8080        : NOT LISTENING"
}

# 3. Login VBS must be DISABLED -- no runnable CoworkApps .vbs in the Startup folder.
$startup  = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"
$runnable = @(Get-ChildItem $startup -Filter 'CoworkApps*.vbs' -ErrorAction SilentlyContinue)
$vbsDisabled = ($runnable.Count -eq 0)
Write-Host ""
Write-Host ("Login VBS disabled?   : {0}  (runnable CoworkApps .vbs in Startup: {1})" -f `
    $vbsDisabled, $(if ($runnable.Count) { ($runnable.Name -join ', ') } else { 'none' }))

# 4. Fresh boot-log evidence
$log = 'C:\Users\tokka\AppData\Local\CoworkApps\server-boot.log'
Write-Host ""
Write-Host "--- server-boot.log (tail 6) ---"
if (Test-Path $log) { Get-Content $log -Tail 6 } else { Write-Host "(no boot log)" }

# 5. Backup task -- informational only. NOTE: the temporary AtLogon test trigger was
#    removed, so the backup does NOT fire on reboot; it runs on its daily 14:00 schedule.
Write-Host ""
Write-Host "--- backup task (informational; fires daily 14:00, NOT on reboot) ---"
$binfo = Get-ScheduledTaskInfo -TaskName 'Backup Cowork Content' -EA SilentlyContinue
Write-Host ("Backup LastRunTime : {0}   LastResult 0x{1:X8}   NextRun {2}" -f `
    $binfo.LastRunTime, ([uint32]$binfo.LastRunResult), $binfo.NextRunTime)

# Verdict -- the whole point of THIS reboot: only the boot task brings the server up.
Write-Host ""
$pass = $rebooted -and $conn -and $serverSession0 -and $bootTaskRan -and $vbsDisabled
if ($pass) {
    Write-Host "VERDICT: PASS -- reboot happened, server is served from Session 0 by the boot task,"
    Write-Host "               and the login VBS is disabled (no duplicate login-time launch)."
} elseif (-not $rebooted) {
    Write-Host "VERDICT: INCONCLUSIVE -- no reboot detected yet."
} else {
    Write-Host "VERDICT: CHECK -- see the flags above:"
    Write-Host ("   rebooted={0}  serverUp={1}  session0={2}  bootTaskRan={3}  vbsDisabled={4}" -f `
        $rebooted, [bool]$conn, $serverSession0, $bootTaskRan, $vbsDisabled)
}
Write-Host "==============================================================="
