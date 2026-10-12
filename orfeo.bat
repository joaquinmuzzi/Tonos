@echo off
rem Opens orfeo in the browser. Close this window to stop it.
rem With a file, analyzes it in the terminal:  orfeo.bat "C:\path\to\song.mp4"  [--json]
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\orfeo\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo orfeo is not installed yet. Run install.ps1 first.
  pause
  exit /b 1
)
"%PY%" -m orfeo %*
if errorlevel 1 pause
