#!/usr/bin/env bash
# Installs Tonos on macOS and Linux.
# Usage, in a terminal inside this folder:  ./install.sh
# Creates a Python environment in ~/.local/share/tonos/venv (~1.5 GB). Running it again updates
# that environment instead of creating it from scratch.

set -euo pipefail

# Versions pinned like in install.ps1 (and requirements.txt / constraints.txt)
TORCH_VERSION="2.7.1"
TORCH_INDEX="https://download.pytorch.org/whl/cpu"
DEMUCS="demucs==4.0.1"  # separation into stems, optional (issue #56)
CONSONANCE_ACE="consonance-ace @ git+https://github.com/andreamust/consonance-ACE@d17633aea4e68e616e735d09df97b97ae3428e71"

DATA="${XDG_DATA_HOME:-$HOME/.local/share}/tonos"
VENV="$DATA/venv"
PY="$VENV/bin/python"

if [[ -t 1 ]]; then BOLD=$'\033[1;36m' RED=$'\033[1;31m' GREEN=$'\033[1;32m' RESET=$'\033[0m'
else BOLD="" RED="" GREEN="" RESET=""; fi

step() { printf '\n%s==> %s%s\n' "$BOLD" "$1" "$RESET"; }
fail() { printf '\n%sERROR: %s%s\n' "$RED" "$1" "$RESET" >&2; exit 1; }
# Any other command that fails stops the script with the line it was on
trap 'fail "the command on line $LINENO of install.sh failed (see the output above)."' ERR

# How to install a missing tool on this system
how_to_install() {
    local brew="$1" apt="$2"
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "brew install $brew"
    elif command -v apt-get > /dev/null; then
        echo "sudo apt install $apt"
    else
        echo "your distribution's package manager (on Debian or Ubuntu: sudo apt install $apt)"
    fi
}

cd "$(dirname "${BASH_SOURCE[0]}")"

step "Checking requirements"
if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" != "arm64" ]]; then
    fail "PyTorch $TORCH_VERSION has no build for Intel Macs: Tonos needs a Mac with Apple silicon."
fi

python=""
for candidate in python3.12 python3; do
    if command -v "$candidate" > /dev/null \
        && "$candidate" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' 2> /dev/null; then
        python="$candidate"
        break
    fi
done
if [[ -z "$python" ]]; then
    hint="$(how_to_install python@3.12 "python3.12 python3.12-venv")"
    # Newer Ubuntu releases only package a newer Python
    [[ "$hint" == sudo\ apt* ]] && hint="$hint  (if your release does not have it: https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa)"
    fail "Python 3.12 is required. Install it with:  $hint"
fi
"$python" --version
# Debian and Ubuntu ship venv (with ensurepip) in a separate package
"$python" -c 'import ensurepip, venv' 2> /dev/null \
    || fail "The venv module of Python 3.12 is missing. Install it with:  $(how_to_install python@3.12 python3.12-venv)"
command -v ffmpeg > /dev/null || fail "ffmpeg was not found. Install it with:  $(how_to_install ffmpeg ffmpeg)"
command -v git > /dev/null || fail "git was not found. Install it with:  $(how_to_install git git)"

# An environment left half-created, or made with another Python, is created again
if [[ -e "$VENV" ]] && ! "$PY" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))' 2> /dev/null; then
    step "Removing the unusable Python environment in $VENV"
    rm -rf "$VENV"
fi
if [[ ! -e "$VENV" ]]; then
    step "Creating the Python environment in $VENV"
    mkdir -p "$DATA"
    "$python" -m venv "$VENV"
fi

step "Installing PyTorch (CPU version, ~200 MB)"
"$PY" -m pip install --upgrade pip
"$PY" -m pip install "torch==$TORCH_VERSION" "torchaudio==$TORCH_VERSION" --index-url "$TORCH_INDEX"

step "Installing the analysis models and the web server"
"$PY" -m pip install -r requirements.txt -c constraints.txt
"$PY" -m pip install --no-deps "$CONSONANCE_ACE" "$DEMUCS"

step "Downloading and testing the models (the first time downloads ~77 MB)"
"$PY" -m tonos --preload

printf '\n%sDone. To use it, run ./tonos.sh%s\n' "$GREEN" "$RESET"
