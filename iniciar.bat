@echo off
rem Abre el Analizador musical en el navegador. Cerrá esta ventana para apagarlo.
cd /d "%~dp0"
set "PY=%LOCALAPPDATA%\analizador-musical\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Todavia no esta instalado. Ejecuta primero instalar.ps1
  pause
  exit /b 1
)
"%PY%" -m orfeo %*
if errorlevel 1 pause
