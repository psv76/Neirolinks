Option Explicit

Dim shell, fso, root, pythonw, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(root, ".venv\Scripts\pythonw.exe")

If Not fso.FileExists(pythonw) Then
    MsgBox "Среда NL Project 2.0 не подготовлена. Выполните tools\bootstrap.ps1.", 16, "NL Project 2.0"
    WScript.Quit 2
End If

shell.CurrentDirectory = root
shell.Environment("PROCESS")("PYTHONPATH") = fso.BuildPath(root, "src")
command = Chr(34) & pythonw & Chr(34) & " -m nl_project_2"
shell.Run command, 0, False

