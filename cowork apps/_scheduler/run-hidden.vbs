' run-hidden.vbs
' Launches Run-CoworkRoutine.ps1 with NO visible console window, forwarding all
' arguments through to it. Scheduled tasks point wscript.exe at this file so the
' cowork routines stop popping a terminal window on every run. Runs in the user's
' interactive session (keeps the G: Google Drive mount + user PATH available) and
' waits for the routine to finish, so the task's ExecutionTimeLimit and
' MultipleInstances=IgnoreNew still apply.
'
' Usage (from Task Scheduler Arguments):
'   "...\run-hidden.vbs" -Name "Routine" [-Root "..."] [-OutReport "..."]

Option Explicit
Dim a, i, x, tail
Set a = WScript.Arguments
tail = ""
For i = 0 To a.Count - 1
    x = a(i)
    ' WScript strips the surrounding quotes; re-quote any token containing spaces
    ' so paths like "G:\My Drive\Netlify Apps" survive to PowerShell intact.
    If InStr(x, " ") > 0 Then x = """" & x & """"
    tail = tail & " " & x
Next

Dim ps, wrapper, cmd
ps      = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
wrapper = "C:\Users\tokka\Claude Local\cowork apps\_scheduler\Run-CoworkRoutine.ps1"
cmd = """" & ps & """ -NoProfile -ExecutionPolicy Bypass -File """ & wrapper & """" & tail

' 0 = hidden window, True = wait for the routine to complete.
' Propagate the wrapper's exit code instead of discarding it: the wrapper exits 3
' when a run finished DEGRADED (max-turns / session limit / empty output). Without
' WScript.Quit, wscript.exe always exits 0 and Task Scheduler reports LastTaskResult
' 0 for runs that produced no app at all -- which is what hid these failures.
Dim rc
rc = CreateObject("WScript.Shell").Run(cmd, 0, True)
WScript.Quit rc
