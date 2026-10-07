@echo off
rem MyTranscribe Medical (faster-whisper, no PyTorch).
rem Keys, hold-to-talk, accuracy and start-up view: use the gear (Options) in the app.
rem Optional settings: remove "rem " from a "set" line to use it.
rem
rem Paste into the focused app after a hotkey stop:
rem set MYTRANSCRIBE_AUTOPASTE=1
rem
rem Force a model (default: large-v3 on GPUs with >= 5 GB, set by Options -> Accuracy):
rem set MYTRANSCRIBE_MODEL=large-v3-turbo
rem
rem Your own style example / extra vocabulary:
rem set MYTRANSCRIBE_PROMPT_FILE=C:\path\to\my_prompt.txt
rem set MYTRANSCRIBE_VOCAB_FILES=C:\path\to\my_terms.txt
rem
rem Never contact the internet: models were downloaded by scripts\setup_1060.bat.
rem (If you ever need to re-download, run setup again or put "rem " in front of this line.)
set HF_HUB_OFFLINE=1
cd /d "%~dp0"
call venv1060\Scripts\activate.bat
python src\gui_med.py
