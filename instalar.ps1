# Instala el Analizador musical en Windows.
# Uso:  clic derecho > "Ejecutar con PowerShell", o en una terminal:  .\instalar.ps1
# Crea un entorno de Python en %LOCALAPPDATA%\analizador-musical\venv (~1,5 GB).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$venv = Join-Path $env:LOCALAPPDATA "analizador-musical\venv"
$py = Join-Path $venv "Scripts\python.exe"

function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Correr {
    param([string]$exe, [string[]]$argumentos)
    & $exe @argumentos
    if ($LASTEXITCODE -ne 0) { throw "Falló: $exe $($argumentos -join ' ')" }
}

Paso "Revisando requisitos"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "No encontré Python. Instalalo con:  winget install Python.Python.3.12"
}
& py -3.12 --version
if ($LASTEXITCODE -ne 0) { throw "Hace falta Python 3.12. Instalalo con:  winget install Python.Python.3.12" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "No encontré ffmpeg. Instalalo con:  winget install Gyan.FFmpeg  (y abrí una terminal nueva)"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "No encontré git. Instalalo con:  winget install Git.Git  (y abrí una terminal nueva)"
}

if (-not (Test-Path $py)) {
    Paso "Creando el entorno de Python en $venv"
    Correr py @("-3.12", "-m", "venv", $venv)
}

Paso "Instalando PyTorch (versión para procesador, ~220 MB)"
Correr $py @("-m", "pip", "install", "--upgrade", "pip")
Correr $py @("-m", "pip", "install", "torch==2.7.1", "torchaudio==2.7.1", "--index-url", "https://download.pytorch.org/whl/cpu")

Paso "Instalando los modelos de análisis y el servidor"
Correr $py @("-m", "pip", "install", "-r", "requirements.txt", "-c", "constraints.txt")
Correr $py @("-m", "pip", "install", "--no-deps",
    "consonance-ace @ git+https://github.com/andreamust/consonance-ACE@d17633aea4e68e616e735d09df97b97ae3428e71")

Paso "Descargando y probando los modelos (la primera vez baja ~77 MB)"
Correr $py @("-m", "orfeo", "--preload")

Write-Host "`nListo. Para usarlo, hacé doble clic en iniciar.bat" -ForegroundColor Green
