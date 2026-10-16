"""Separation into stems (issue #56): the module with the real model, and the server's stem folders."""

import os
import time

import numpy as np
import pytest
import soundfile as sf

from tests.synthetic import FS, song
from tonos import server
from tonos.analysis import separation


@pytest.fixture(scope="module")
def short_song(tmp_path_factory):
    path = tmp_path_factory.mktemp("stems") / "song.wav"
    signal = song(120, 4, [("G", False), ("C", False), ("D", False)], bars=4)[: 8 * FS]
    sf.write(path, signal, FS)
    return path


@pytest.mark.slow
def test_separation_writes_one_mp3_per_stem(short_song, tmp_path):
    reported = []
    paths = separation.separate(short_song, tmp_path / "stems", reported.append)
    assert list(paths) == list(separation.STEMS)
    for path in paths.values():
        audio, sr = sf.read(path)
        assert sr == separation.SAMPLE_RATE
        assert len(audio) / sr == pytest.approx(8, abs=0.2)
    assert reported[-1] == 1.0
    assert reported == sorted(reported)


@pytest.mark.slow
def test_separation_can_be_cancelled(short_song, tmp_path):
    with pytest.raises(separation.Cancelled):
        separation.separate(short_song, tmp_path / "stems", cancelled=lambda: True)
    assert not (tmp_path / "stems").exists()


def test_only_the_most_recent_stems_are_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STEMS_DIR", tmp_path)
    monkeypatch.setattr(server, "MAX_STEM_SONGS", 3)
    now = time.time()
    for i in range(5):
        folder = tmp_path / f"song{i}"
        folder.mkdir()
        os.utime(folder, (now - 100 + i, now - 100 + i))  # song4 is the most recent
    server._prune_stems(keep=tmp_path / "song0")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["song0", "song3", "song4"]


def test_stems_are_complete_only_with_every_file(tmp_path):
    for stem in separation.STEMS[:-1]:
        (tmp_path / f"{stem}.mp3").write_bytes(b"x")
    assert not server._stems_ready(tmp_path)
    (tmp_path / f"{separation.STEMS[-1]}.mp3").write_bytes(b"x")
    assert server._stems_ready(tmp_path)
    assert np.all([url.endswith(".mp3") for url in server._stems_result("a" * 64)["stems"].values()])
