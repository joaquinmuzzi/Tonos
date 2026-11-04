"""Command-line options for serving the web app and exporting an analysis."""

import json
import os
import subprocess
import sys
from pathlib import Path

import mido
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


def test_midi_option_writes_a_file_alongside_json_output(tmp_path, monkeypatch, capsys):
    from tonos.analysis import pipeline

    song = tmp_path / "song.wav"
    song.touch()
    midi = tmp_path / "song.mid"
    report = {
        "file": {"duration": 1.0},
        "beats": [],
        "meter": {"beats_per_bar": None},
        "tempo": {"bpm": None},
        "chords": {"segments": []},
    }
    monkeypatch.setattr(pipeline, "analyze", lambda path, progress: report)
    monkeypatch.setattr(sys, "argv", ["tonos", str(song), "--json", "--midi", str(midi)])
    cli.main()
    assert json.loads(capsys.readouterr().out) == report
    assert [track.name for track in mido.MidiFile(midi).tracks] == ["Beat grid", "Chords"]


def test_midi_output_cannot_overwrite_the_input(tmp_path, monkeypatch):
    song = tmp_path / "song.wav"
    song.write_bytes(b"audio")
    output = tmp_path / "song.mid"
    output.symlink_to(song)
    monkeypatch.setattr(sys, "argv", ["tonos", str(song), "--midi", str(output)])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert song.read_bytes() == b"audio"


def test_midi_option_requires_an_audio_file(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["tonos", "--midi", "song.mid"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
