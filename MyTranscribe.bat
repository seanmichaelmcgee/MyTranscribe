@echo off
rem MyTranscribe Medical without a console window.
rem This window closes at once; the app keeps running on its own. For a start with no
rem flash at all, run scripts\make_shortcut.ps1 once and use the desktop shortcut.
rem Messages go to Options -> Show log and to %LOCALAPPDATA%\MyTranscribe\mytranscribe.log.
rem Use run_1060.bat instead when you want the log in a console (debugging).
cd /d "%~dp0"
if not exist venv1060\Scripts\pythonw.exe (
    echo venv1060 was not found. Run scripts\setup_1060.bat first.
    pause
    exit /b 1
)
start "" "venv1060\Scripts\pythonw.exe" "src\gui_med.py"
