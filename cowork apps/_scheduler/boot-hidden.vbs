' boot-hidden.vbs
' Launches serve-boot.cmd (python serve_apps.py) with NO visible console window.
' The server runs for the machine's uptime, so we Run(..., True) = WAIT: wscript
' stays alive as long as the server does, which keeps the CoworkApps-Server-Boot
' task in the Running state exactly as it was before -- the only change is that the
' cmd/python console is hidden (0 = SW_HIDE) instead of popping a terminal at boot.
' Runs in the user's interactive session (same as before) so the G: mount + PATH
' remain available to the served apps.
Option Explicit
CreateObject("WScript.Shell").Run """C:\Users\tokka\Claude Local\cowork apps\_scheduler\serve-boot.cmd""", 0, True
