@echo off
rem setup_1060.bat - one-time setup of the Medical / GTX 1060 edition on Windows.
rem Creates venv1060, installs requirements-1060.txt, downloads models, runs preflight.
rem Run from anywhere:  scripts\setup_1060.bat
setlocal
cd /d "%~dp0\.."

if exist venv1060\Scripts\python.exe goto :have_venv
echo Creating venv1060 ...
py -3.11 -m venv venv1060 2>nul
if not exist venv1060\Scripts\python.exe python -m venv venv1060
if not exist venv1060\Scripts\python.exe (
    echo Could not create a virtual environment. Install Python 3.11 from python.org
    echo ^(tick "Add python.exe to PATH"^) and run this again.
    exit /b 1
)
:have_venv
set PY=venv1060\Scripts\python.exe
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements-1060.txt
if errorlevel 1 (
    echo pip install failed - see messages above.
    exit /b 1
)
echo.
echo Running preflight checks (first run downloads ~6 GB of models) ...
%PY% scripts\preflight_1060.py
exit /b %errorlevel%
