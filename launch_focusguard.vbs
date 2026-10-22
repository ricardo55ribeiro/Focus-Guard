Set oShell = CreateObject("WScript.Shell")
sDir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
oShell.CurrentDirectory = sDir & "agent"
command = "pythonw.exe app.pyw"
If WScript.Arguments.Count > 0 Then
    command = command & " " & Chr(34) & WScript.Arguments(0) & Chr(34)
End If
oShell.Run command, 1, False
