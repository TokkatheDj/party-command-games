# apply-server-boot-hidden.ps1  --  RUN IN AN ELEVATED (Admin) PowerShell.
# Repoints CoworkApps-Server-Boot to launch via wscript + boot-hidden.vbs so the
# app-server's cmd/python console is hidden. Requires elevation because the task
# is registered S4U (run-whether-logged-on-or-not); an unelevated Set-ScheduledTask
# returns "Access is denied". Takes effect at the next boot; does not disturb the
# currently running server instance.
$ErrorActionPreference = 'Stop'
$WS   = "$env:SystemRoot\System32\wscript.exe"
$VBS  = "C:\Users\tokka\Claude Local\cowork apps\_scheduler\boot-hidden.vbs"
$Root = "C:\Users\tokka\Claude Local\cowork apps"
$action = New-ScheduledTaskAction -Execute $WS -Argument ('"{0}"' -f $VBS) -WorkingDirectory $Root
Set-ScheduledTask -TaskName 'CoworkApps-Server-Boot' -Action $action | Out-Null
$t = Get-ScheduledTask -TaskName 'CoworkApps-Server-Boot'
$t.Actions | Format-List Execute,Arguments,WorkingDirectory
Write-Host "Done. Execute should now read wscript.exe with boot-hidden.vbs. Effective next boot."
