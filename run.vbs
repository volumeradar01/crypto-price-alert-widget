' Silent launcher: double-click to start the widget with no console window.
' Prefers a local .venv if present, otherwise uses pythonw.exe from PATH.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = root

venvPythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")
If fso.FileExists(venvPythonw) Then
    sh.Run """" & venvPythonw & """ -m crypto_price_alert", 0, False
Else
    sh.Run "pythonw.exe -m crypto_price_alert", 0, False
End If
