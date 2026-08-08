' Cowork Apps - manual launcher. Double-click to (re)start the server anytime,
' e.g. the first time, or if a page ever stops loading.
' It frees port 8080 first (clears any stuck/hung server) then starts a fresh
' server minimized to the taskbar. No browser pop-up; the phone/tablet URL is
' shown on the index page (http://192.168.0.248:8080).
Dim fso, here
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run """" & here & "\restart-server.bat""", 0, False
