# Installs Tonos on Windows.
# Usage: right-click > "Run with PowerShell", or in a terminal:  .\install.ps1
# Creates a Python environment in %LOCALAPPDATA%\tonos\venv (~1.5 GB).
# (This file is plain ASCII on purpose: Windows PowerShell 5.1 misreads UTF-8 without a BOM.)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$data = Join-Path $env:LOCALAPPDATA "tonos"
$venv = Join-Path $data "venv"
$py = Join-Path $venv "Scripts\python.exe"
$oldData = Join-Path $env:LOCALAPPDATA "analizador-musical"  # used before version 0.1.0, not migrated
$orfeoData = Join-Path $env:LOCALAPPDATA "orfeo"  # version 0.1.0, when the project was called orfeo

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Run {
    param([string]$exe, [string[]]$arguments)
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { throw "Failed: $exe $($arguments -join ' ')" }
}

Step "Checking requirements"
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Install it with:  winget install Python.Python.3.12"
}
& py -3.12 --version
if ($LASTEXITCODE -ne 0) { throw "Python 3.12 is required. Install it with:  winget install Python.Python.3.12" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    throw "ffmpeg was not found. Install it with:  winget install Gyan.FFmpeg  (and open a new terminal)"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git was not found. Install it with:  winget install Git.Git  (and open a new terminal)"
}

if ((Test-Path $orfeoData) -and -not (Test-Path $data)) {
    # The environment only uses relative paths with "python -m", so it can be moved as is
    Step "Moving $orfeoData to $data (the project was renamed)"
    Move-Item $orfeoData $data
}

if (-not (Test-Path $py)) {
    Step "Creating the Python environment in $venv"
    Run py @("-3.12", "-m", "venv", $venv)
}

Step "Installing PyTorch (CPU version, ~220 MB)"
Run $py @("-m", "pip", "install", "--upgrade", "pip")
Run $py @("-m", "pip", "install", "torch==2.7.1", "torchaudio==2.7.1", "--index-url", "https://download.pytorch.org/whl/cpu")

Step "Installing the analysis models and the web server"
Run $py @("-m", "pip", "install", "-r", "requirements.txt", "-c", "constraints.txt")
Run $py @("-m", "pip", "install", "--no-deps",
    "consonance-ace @ git+https://github.com/andreamust/consonance-ACE@d17633aea4e68e616e735d09df97b97ae3428e71")

Step "Downloading and testing the models (the first time downloads ~77 MB)"
Run $py @("-m", "tonos", "--preload")

Write-Host "`nDone. To use it, double-click tonos.bat" -ForegroundColor Green
if (Test-Path $oldData) {
    Write-Host "The folder $oldData is from an older version and is no longer used: you can delete it." -ForegroundColor Yellow
}
