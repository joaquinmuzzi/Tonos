"""End-to-end tests with the real models (about 1 minute in total)."""

import subprocess
from collections import Counter

import numpy as np
import pytest
import soundfile as sf

from tests.synthetic import FS, save_mp4, song
from tonos.analysis import pipeline
from tonos.analysis.audio import AudioError

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def pop_in_g(tmp_path_factory):
    """MP4 at 120 BPM in 4/4, G major: G - D - Em - C."""
    y = song(120, 4, [("G", False), ("D", False), ("E", True), ("C", False)], bars=24)
    path = save_mp4(y, tmp_path_factory.mktemp("pop") / "pop in g.mp4")
    return pipeline.analyze(path)


@pytest.fixture(scope="module")
def waltz_in_d(tmp_path_factory):
    """MP4 at 150 BPM in 3/4, D major: D - G - A - D."""
    y = song(150, 3, [("D", False), ("G", False), ("A", False), ("D", False)], bars=32)
    path = save_mp4(y, tmp_path_factory.mktemp("waltz") / "waltz.mp4")
    return pipeline.analyze(path)


def _bpm_equivalent(measured, real):
    return any(abs(measured - real * f) <= 0.04 * real * f for f in (1, 2, 0.5))


def test_pop_tempo(pop_in_g):
    assert _bpm_equivalent(pop_in_g["tempo"]["bpm"], 120)


def test_pop_meter(pop_in_g):
    assert pop_in_g["meter"]["beats_per_bar"] in (4, 2)


def test_pop_key(pop_in_g):
    p = pop_in_g["key"]["best"]
    assert (p["tonic_pc"], p["mode"]) in [(7, "major"), (4, "minor")]  # G major or its relative minor


def test_pop_chords(pop_in_g):
    used = Counter()
    for s in pop_in_g["chords"]["segments"]:
        if s["is_chord"]:
            used[s["letter_simple"]] += s["end"] - s["start"]
    top_chords = {name for name, _ in used.most_common(4)}
    assert top_chords == {"G", "D", "Em", "C"}


def test_pop_report_is_complete(pop_in_g):
    assert pop_in_g["bars"], "there should be bars"
    assert pop_in_g["chords"]["summary_simple"]
    assert pop_in_g["key"]["confidence"] in ("high", "medium", "low")


def test_waltz_tempo(waltz_in_d):
    assert _bpm_equivalent(waltz_in_d["tempo"]["bpm"], 150)


def test_waltz_meter(waltz_in_d):
    assert waltz_in_d["meter"]["beats_per_bar"] in (3, 6)


def test_pop_and_waltz_confirmed_by_harmony(pop_in_g, waltz_in_d):
    assert pop_in_g["meter"]["source"] == "downbeats"
    assert waltz_in_d["meter"]["source"] == "downbeats"


@pytest.mark.parametrize(
    ("beats_per_bar", "progression"),
    [
        (5, [("A", True), ("F", False), ("C", False), ("G", False)]),
        (7, [("E", True), ("C", False), ("D", False)]),
    ],
)
def test_odd_meter_end_to_end(tmp_path, beats_per_bar, progression):
    """The downbeat detector fails on 5/4 and 7/4; the repetition of the harmony does not."""
    y = song(130, beats_per_bar, progression, bars=32)
    result = pipeline.analyze(save_mp4(y, tmp_path / f"in {beats_per_bar}.mp4"))
    meter = result["meter"]
    assert meter["time_signature"] == f"{beats_per_bar}/4"
    assert meter["source"] == "periodicity"
    assert not meter["approximate_grid"]
    downbeats = result["downbeats"]
    assert downbeats[0] == pytest.approx(0.0, abs=0.05)
    assert np.median(np.diff(downbeats)) == pytest.approx(beats_per_bar * 60 / 130, rel=0.03)


def test_waltz_key(waltz_in_d):
    p = waltz_in_d["key"]["best"]
    assert (p["tonic_pc"], p["mode"]) in [(2, "major"), (11, "minor")]


def test_pop_ending_has_no_gaps(pop_in_g):
    # Chords continue up to the end, with no "no chord" caused by silence padding
    segments = pop_in_g["chords"]["segments"]
    duration = pop_in_g["file"]["duration"]
    last_segments = [s for s in segments if s["end"] > duration - 8 and s["start"] < duration - 1.5]
    assert all(s["is_chord"] for s in last_segments)


def test_file_without_audio(tmp_path):
    path = tmp_path / "text.mp4"
    path.write_text("this is not a video")
    with pytest.raises(AudioError):
        pipeline.analyze(path)


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *args], check=True)


def test_too_long_file_is_rejected_early(tmp_path):
    path = tmp_path / "long.mp3"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=1500", "-b:a", "32k", str(path))
    with pytest.raises(AudioError, match="longer than 20 minutes"):
        pipeline.analyze(path)


def test_silent_first_track_uses_the_second(tmp_path):
    music = tmp_path / "music.wav"
    sf.write(music, song(120, 4, [("A", True), ("F", False)], bars=8), FS)
    path = tmp_path / "two tracks.mp4"
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-i",
        str(music),
        "-map",
        "0:a",
        "-map",
        "1:a",
        "-shortest",
        "-c:a",
        "aac",
        str(path),
    )
    result = pipeline.analyze(path)
    assert result["file"]["audio_track"] == 2
    assert result["tempo"]["bpm"]


def test_text_report(pop_in_g):
    from tonos.__main__ import _text_report

    text = _text_report(pop_in_g)
    for heading in ("File:", "Tempo:", "Meter:", "Key:", "Most used chords:", "First 16 bars:"):
        assert heading in text


def test_lab_report(pop_in_g, tmp_path):
    from tonos.__main__ import _lab_report

    text = _lab_report(pop_in_g)
    path = tmp_path / "chords.lab"
    path.write_text(text + "\n", encoding="utf-8")
    intervals, labels = mir_eval.io.load_labeled_intervals(path)

    segments = pop_in_g["chords"]["segments"]
    assert len(intervals) == len(labels)
    assert intervals[0, 0] == pytest.approx(segments[0]["start"], abs=0.001)
    assert intervals[-1, 1] == pytest.approx(segments[-1]["end"], abs=0.001)
    assert np.all(intervals[1:, 0] >= intervals[:-1, 1])
    assert all(a != b for a, b in zip(labels, labels[1:]))
