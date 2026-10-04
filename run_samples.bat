@echo off
rem Explicit fictional-test capture. Close ordinary MyTranscribe first.
cd /d "%~dp0"
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
set HF_HUB_DISABLE_TELEMETRY=1
start "" "%~dp0venv1060\Scripts\pythonw.exe" "%~dp0scripts\clinical_sample_capture.py"
