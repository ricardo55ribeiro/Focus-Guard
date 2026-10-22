$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcut = $shell.CreateShortcut((Join-Path $desktop 'FocusGuard.lnk'))
$shortcut.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
$shortcut.Arguments = '"' + (Join-Path $PSScriptRoot 'launch_focusguard.vbs') + '"'
$shortcut.WorkingDirectory = Join-Path $PSScriptRoot 'agent'
$shortcut.WindowStyle = 1
$shortcut.IconLocation = Join-Path $PSScriptRoot 'agent\icon.ico'
$shortcut.Description = 'Launch FocusGuard'
$shortcut.Save()
