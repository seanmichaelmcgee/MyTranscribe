@echo off
rem MyTranscribe Medical / GTX 1060 edition (faster-whisper, no PyTorch).
rem Optional settings: remove "rem " from a "set" line to use it.
rem
rem Paste into the focused app after a Ctrl+Alt+Q stop:
rem set MYTRANSCRIBE_AUTOPASTE=1
rem
rem Model (default on the GPU is large-v3-turbo):
rem set MYTRANSCRIBE_MODEL=large-v3
rem
rem Your own vocabulary prompt:
rem set MYTRANSCRIBE_PROMPT_FILE=C:\path\to\my_prompt.txt
rem
rem After the first run has downloaded the model, never contact Hugging Face:
rem set HF_HUB_OFFLINE=1
cd /d "%~dp0"
call venv1060\Scripts\activate.bat
python src\gui_med.py
