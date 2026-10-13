"""Command-line options that change how the web app is served."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import uvicorn

from tonos import __main__ as cli

ROOT = Path(__file__).parents[1]


@pytest.fixture
def served(monkeypatch):
    """Runs `python -m tonos` with some options and returns what uvicorn was asked to serve."""
    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **options: calls.append(options))
    monkeypatch.setattr(cli, "_port_in_use", lambda port: False)

    def run(*options):
        monkeypatch.setattr(sys, "argv", ["tonos", "--no-browser", *options])
        cli.main()
        return calls[-1]

    return run


def test_the_app_listens_only_on_this_computer_by_default(served):
    assert served()["host"] == "127.0.0.1"


def test_host_option(served, capsys):
    options = served("--host", "0.0.0.0", "--port", "9000")
    assert options["host"] == "0.0.0.0"
    assert options["port"] == 9000
    assert "other devices" in capsys.readouterr().out


def test_data_dir_can_be_chosen():
    code = "from tonos import server; print(server.DATA_DIR, server.CACHE_DIR, sep='|')"
    env = {**os.environ, "TONOS_DATA_DIR": str(ROOT / "somewhere")}
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out.split("|") == [str(ROOT / "somewhere"), str(ROOT / "somewhere" / "cache")]
