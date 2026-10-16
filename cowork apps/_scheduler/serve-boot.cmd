@echo off
rem serve-boot.cmd
rem Starts the cowork apps HTTP server. Body of the CoworkApps-Server-Boot task,
rem factored out of the task's inline cmd string so boot-hidden.vbs can launch it
rem with no visible console window (the inline command used to pop a terminal on
rem every boot). Redirection lives here because it needs the cmd interpreter.
cd /d "C:\Users\tokka\Claude Local\cowork apps"
"C:\Python314\python.exe" serve_apps.py >> "C:\Users\tokka\AppData\Local\CoworkApps\server-boot.log" 2>&1
