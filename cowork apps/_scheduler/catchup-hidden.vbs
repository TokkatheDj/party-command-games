' catchup-hidden.vbs
' Launches Invoke-CatchUp.ps1 with NO visible console window, forwarding arguments.
' Mirrors run-hidden.vbs (which is hardcoded to the routine wrapper) rather than
' generalising it -- the routine launcher is load-bearing for 18 tasks and is not
' worth changing to save one file.
'
' Runs in the user's interactive session so the G: mount and user PATH stay
' available, and waits, so the task's ExecutionTimeLimit still applies.
'
' Usage (from Task Scheduler Arguments):
'   "...\catchup-hidden.vbs" -Apply -MaxRuns 3

Option Explicit
Dim a, i, x, tail
Set a = WScript.Arguments
tail = ""
For i = 0 To a.Count - 1
    x = a(i)
    If InStr(x, " ") > 0 Then x = """" & x & """"
    tail = tail & " " & x
Next

Dim ps, script, cmd
ps     = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
script = "C:\Users\tokka\Claude Local\cowork apps\_scheduler\Invoke-CatchUp.ps1"
cmd = """" & ps & """ -NoProfile -ExecutionPolicy Bypass -File """ & script & """" & tail

' 0 = hidden window, True = wait. Propagate the exit code so a failed sweep is
' visible in Task Scheduler's LastTaskResult rather than always reporting 0.
Dim rc
rc = CreateObject("WScript.Shell").Run(cmd, 0, True)
WScript.Quit rc
