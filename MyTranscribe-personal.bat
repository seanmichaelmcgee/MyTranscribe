@echo off
rem MyTranscribe Medical with the owner's dictation options switched on for this start,
rem whatever is saved in Options:
rem   pause-aware dictation, spoken punctuation, Extra corrections (readings, drug names),
rem   and only the commas that are dictated. English, Whisper large-v3 ("Best accuracy").
rem Remove a line below to go back to the saved choice for that option.
rem Otherwise the same as MyTranscribe.bat: no console window; messages go to
rem Options -> Show log and to %LOCALAPPDATA%\MyTranscribe\mytranscribe.log.
cd /d "%~dp0"
if not exist venv1060\Scripts\pythonw.exe (
    echo venv1060 was not found. Run scripts\setup_1060.bat first.
    pause
    exit /b 1
)
set MYTRANSCRIBE_LANGUAGE=en
set MYTRANSCRIBE_ENGINE=whisper
set MYTRANSCRIBE_PAUSE_AWARE=1
set MYTRANSCRIBE_SPOKEN_PUNCTUATION=1
set MYTRANSCRIBE_EXTRA_FIXES=1
set MYTRANSCRIBE_ONLY_DICTATED_COMMAS=1
start "" "venv1060\Scripts\pythonw.exe" "src\gui_med.py"
