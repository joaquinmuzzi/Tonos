@echo off
rem Opens Tonos in the browser. Close this window to stop it.
rem With a file, analyzes it in the terminal:  tonos.bat "C:\path\to\song.mp4"  [--json]
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\tonos\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Tonos is not installed yet. Run install.ps1 first.
  pause
  exit /b 1
)
"%PY%" -m tonos %*
if errorlevel 1 pause
