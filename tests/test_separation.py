"""Separation into stems (issue #56): the module with the real model, and the server's stem folders."""

import os
import subprocess
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


def test_a_finished_song_is_not_separated_again(tmp_path, monkeypatch):
    """A second job for a song whose stems another job has just written reuses them."""
    monkeypatch.setattr(server, "STEMS_DIR", tmp_path)
    digest = "b" * 64
    for stem in separation.STEMS:
        (tmp_path / digest).mkdir(exist_ok=True)
        (tmp_path / digest / f"{stem}.mp3").write_bytes(b"x")
    upload = tmp_path / "upload" / "input.mp3"
    upload.parent.mkdir()
    upload.write_bytes(b"x")

    def must_not_run(*args, **kwargs):
        raise AssertionError("separated again")

    monkeypatch.setattr(separation, "separate", must_not_run)
    server._register_job("job1", name="song", digest=digest, cancel=server.threading.Event())
    server._run_separation("job1", upload, "song", digest)
    assert server._jobs["job1"]["status"] == "done"
    assert not upload.parent.exists()


def test_a_job_dropped_from_the_list_does_not_run(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "STEMS_DIR", tmp_path)
    upload = tmp_path / "upload" / "input.mp3"
    upload.parent.mkdir()
    upload.write_bytes(b"x")
    monkeypatch.setattr(separation, "separate", lambda *a, **k: pytest.fail("ran a dropped job"))
    server._run_separation("never-registered", upload, "song", "c" * 64)
    assert not upload.parent.exists()


def test_separation_reads_the_first_track_that_is_not_silent(tmp_path):
    """Like the analysis: a video whose first audio track is silent uses the second one."""
    path = tmp_path / "two tracks.mka"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=stereo:d=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=44100:duration=3",
            "-map",
            "0:a",
            "-map",
            "1:a",
            "-c:a",
            "flac",
            str(path),
        ],
        check=True,
    )
    audio = separation._read_stereo(path, tmp_path / "out.wav")
    assert audio.shape[0] == 2
    assert np.abs(audio).max() > 0.05  # ffmpeg's sine source peaks at about 0.09
