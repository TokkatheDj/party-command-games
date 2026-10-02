@echo off
cd /d "%~dp0"
echo ==== PORT 8080 BEFORE ==== > restart_log.txt
netstat -ano | findstr ":8080" >> restart_log.txt 2>&1
echo ==== PYTHON PROCS ==== >> restart_log.txt
tasklist | findstr /i "python.exe" >> restart_log.txt 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8080" ^| findstr LISTENING') do (
  echo Killing PID %%a >> restart_log.txt
  taskkill /F /PID %%a >> restart_log.txt 2>&1
)
timeout /t 2 >nul
echo ==== PORT 8080 AFTER KILL ==== >> restart_log.txt
netstat -ano | findstr ":8080" >> restart_log.txt 2>&1
REM Was: pwsh ... Start-AppServer.ps1 - PowerShell hung at start-up (28 Sep 2026).
start "serve_apps" /min "%~dp0run-server-loop.bat"
echo ==== STARTED NEW SERVER ==== >> restart_log.txt
