# Creates a desktop shortcut that starts MyTranscribe Medical with no console window.
# Run once from PowerShell:   .\scripts\make_shortcut.ps1
# Optional: -Venv <folder> if your environment is not venv1060, -Name for the shortcut's name.
param([string]$Venv = "venv1060", [string]$Name = "MyTranscribe")
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$pythonw = Join-Path $root "$Venv\Scripts\pythonw.exe"
if (!(Test-Path -LiteralPath $pythonw)) { throw "Not found: $pythonw. Run scripts\setup_1060.bat first, or pass -Venv." }
$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop "$Name.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = $pythonw
$shortcut.Arguments = '"' + (Join-Path $root "src\gui_med.py") + '"'
$shortcut.WorkingDirectory = $root
$shortcut.Description = "MyTranscribe Medical (no console window; Options -> Show log for messages)"
$shortcut.Save()
Write-Host "Created $link"
