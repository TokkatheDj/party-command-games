@echo off
REM run-server-loop.bat -- keeps AppVerse up. Started (minimized) by
REM restart-server.bat.
REM
REM WHY NOT Start-AppServer.ps1 (28 Sep 2026): PowerShell itself was hanging at
REM start-up on this machine - even pwsh -NoProfile - so the server window sat
REM there forever without ever reaching Python, and AppVerse was down ("502"
REM through Tailscale). This does the same job without PowerShell: run the
REM server with the desktop's own Python, and restart it if it crashes.
cd /d "%~dp0"
title serve_apps
:loop
"C:\Python314\python.exe" "%~dp0serve_apps.py"
if %ERRORLEVEL%==0 goto :eof
echo.
echo   Server exited (code %ERRORLEVEL%) - restarting in 3s...
timeout /t 3 >nul
goto loop
