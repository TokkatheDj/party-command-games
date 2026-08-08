' Auto-start the Cowork Apps local server at Windows login (HANG-PROOF).
'
' SETUP: copy this file into your Startup folder.
'   Press Win+R, type  shell:startup  , press Enter, then drag this file in.
'
' It runs restart-server.bat hidden, which first frees port 8080 (clearing any
' stuck/hung server from a previous run) and then starts a fresh server,
' minimized to the taskbar. This prevents the recurring "site can not be
' reached" problem.
'
' NOTE: this file is copied OUT to the Startup folder, so it must use the
' absolute path to the cowork apps folder on THIS machine (it cannot be
' self-relative). On the Surface machine change  D:\Documents\Claude Local
' to  C:\Users\tokka\Claude Local .
'
' To stop the server: close the minimized "serve_apps" window, or end the
' "python.exe" process in Task Manager.
' To disable auto-start: delete this file from the Startup folder.
CreateObject("WScript.Shell").Run """D:\Documents\Claude Local\cowork apps\restart-server.bat""", 0, False
