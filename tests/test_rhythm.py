import numpy as np
import pytest

from tests.synthetic import FS, song
from tonos.analysis import rhythm
from tonos.messages import message


def _beats(bpm, n):
    return np.arange(n) * 60.0 / bpm


def test_beats_per_bar():
    beats = _beats(120, 33)
    downbeats = beats[1::4]  # one-beat pickup, then bars of 4
    assert rhythm.beats_per_bar(beats, downbeats) == [4] * 7


def test_meter_in_four():
    beats = _beats(120, 65)
    result = rhythm.analyze_meter(beats, beats[::4], {"kind": "binary"}, 120)
    assert result["beats_per_bar"] == 4
    assert result["time_signature"] == "4/4"
    assert result["confidence"] == "high"
    assert result["warnings"] == []


def test_meter_in_three_warns_about_ambiguity():
    beats = _beats(150, 61)
    result = rhythm.analyze_meter(beats, beats[::3], {"kind": "unclear"}, 150)
    assert result["time_signature"] == "3/4"
    assert result["alternative"] == message("or", signature="6/8")
    assert result["warnings"] == [message("ternary_ambiguity")]


def test_fast_swing_reads_as_four_four_swing():
    beats = _beats(200, 65)
    result = rhythm.analyze_meter(beats, beats[::4], {"kind": "ternary"}, 200)
    assert result["time_signature"] == "4/4"
    assert result["swing"]


def test_slow_ternary_ballad_reads_as_twelve_eight():
    beats = _beats(60, 65)
    result = rhythm.analyze_meter(beats, beats[::4], {"kind": "ternary"}, 60)
    assert result["time_signature"] == "12/8"


def test_one_beat_per_bar_is_not_reported_as_meter():
    beats = _beats(40, 30)
    result = rhythm.analyze_meter(beats, beats, {"kind": "ternary"}, 40)
    assert result["time_signature"] is None
    assert result["confidence"] == "low"


def test_mixed_bar_lengths_lower_confidence():
    beats = _beats(120, 200)
    downbeats, i = [], 0
    for n in [4, 3, 4, 3, 3, 4, 3, 4, 4, 3] * 4:  # 50/50
        downbeats.append(beats[i])
        i += n
    result = rhythm.analyze_meter(beats, np.array(downbeats), {"kind": "binary"}, 120)
    assert result["confidence"] == "low"
    assert len(result["warnings"]) >= 1


def test_tempo_from_beats():
    beats = _beats(96, 100)
    envelope = np.zeros(4000)
    t = rhythm.analyze_tempo(beats, envelope, 22050)
    assert abs(t["bpm"] - 96) < 0.5
    assert t["alternatives"] == {"half": 48.0, "double": 192.0}
    assert t["stable"]
    assert t["regularity"] == 1.0


@pytest.mark.parametrize("bpm", [123, 128, 133, 140, 170, 174, 180, 193.5])
def test_tempo_has_no_20_ms_grid_error(bpm):
    # Beat This! returns beats rounded to 20 ms frames
    beats = np.round(_beats(bpm, 200) * 50) / 50
    t = rhythm.analyze_tempo(beats, np.zeros(4000), 22050)
    assert abs(t["bpm"] - bpm) < 0.5
    assert t["range"][0] - 1 <= t["bpm"] <= t["range"][1] + 1


def test_unify_double_time_section():
    # 105 BPM, with a stretch in the middle where the detector marked twice as many beats
    normal = _beats(105, 40)
    double = normal[-1] + np.arange(1, 41) * (60 / 210)
    final = double[-1] + np.arange(1, 21) * (60 / 105)
    beats = np.concatenate([normal, double, final])
    downbeats = beats[::4]
    unified, unified_downbeats, info = rhythm.unify_beats(beats, downbeats)
    intervals = np.diff(unified)
    assert np.allclose(intervals, 60 / 105, rtol=0.02)
    assert info["removed"] == 20
    assert set(unified_downbeats) <= set(unified)


def test_unify_fills_missed_beats():
    beats = np.delete(_beats(120, 40), [10, 20, 21])  # one and two missed beats
    unified, _, info = rhythm.unify_beats(beats, np.array([]))
    assert info["added"] == 3
    assert np.allclose(unified, _beats(120, 40))


def test_unify_keeps_a_real_tempo_change():
    beats = np.concatenate([_beats(90, 40), _beats(90, 40)[-1] + np.arange(1, 41) * 60 / 140])
    unified, _, info = rhythm.unify_beats(beats, np.array([]))
    assert info == {"removed": 0, "added": 0}
    assert np.array_equal(unified, beats)


def test_unify_evens_a_mis_tracked_fill():
    # As in Resident Evil (bar 9): 4 beats marked 0.42 / 0.40 / 0.72 / 0.68 s
    beat = 2.22 / 4
    beats = list(np.arange(20) * beat)
    t = beats[-1]
    for d in (0.42, 0.40, 0.72, 0.68):
        t += d
        beats.append(t)
    beats += list(t + np.arange(1, 21) * beat)
    unified, _, _ = rhythm.unify_beats(np.array(beats), np.array([]))
    assert len(unified) == len(beats)
    assert np.allclose(np.diff(unified), beat, atol=0.01)


def test_unify_evens_fill_with_regular_beat():
    beat = 0.556
    intervals = [1.0] * 20 + [0.79, 1.0, 1.22] + [1.0] * 20
    beats = _from_intervals(intervals, beat)
    unified, _, _info = rhythm.unify_beats(beats, np.array([]))
    assert len(unified) == len(beats)
    assert np.allclose(np.diff(unified), beat, rtol=0.02)


def test_unify_keeps_a_real_shift():
    # An interval of 1.46 beats (a fermata or a half-beat shift) is left alone
    beats = np.concatenate([np.arange(20) * 0.56, 19 * 0.56 + 0.82 + np.arange(20) * 0.56])
    unified, _, info = rhythm.unify_beats(beats, np.array([]))
    assert np.array_equal(unified, beats)
    assert info == {"removed": 0, "added": 0}


def test_unify_fills_gap_next_to_short_bar():
    # An interval of 1.5 beats (a real 7/8 bar) followed by a missed beat (2.0)
    beat = 0.56
    intervals = [1.0] * 15 + [1.5, 2.0] + [1.0] * 15
    beats = np.concatenate([[0.0], np.cumsum(np.array(intervals) * beat)])
    unified, _, info = rhythm.unify_beats(beats, np.array([]))
    relative_intervals = np.round(np.diff(unified) / beat, 2).tolist()
    assert relative_intervals == [1.0] * 15 + [1.5, 1.0, 1.0] + [1.0] * 15
    assert info["added"] == 1


def _from_intervals(intervals, beat=0.5):
    return np.concatenate([[0.0], np.cumsum(np.array(intervals, dtype=float) * beat)])


@pytest.mark.parametrize(
    ("name", "intervals"),
    [
        ("one-bar ritardando", [1.0] * 16 + [1.2] * 4 + [1.0] * 16),
        ("two slower beats", [1.0] * 16 + [1.4] * 2 + [1.0] * 16),
        ("one-bar accelerando", [1.0] * 16 + [0.8] * 4 + [1.0] * 16),
        ("free-time intro", [1.3, 1.4, 1.2] + [1.0] * 30),
        ("final ritardando", [1.0] * 30 + [1.2, 1.4, 1.6, 1.8]),
    ],
)
def test_unify_respects_real_tempo_changes(name, intervals):
    beats = _from_intervals(intervals)
    unified, _, info = rhythm.unify_beats(beats, beats[::4])
    assert np.allclose(unified, beats), name
    assert info == {"removed": 0, "added": 0}


@pytest.mark.parametrize("gap", [2.28, 3.35, 4.4, 6.4, 8.35])
def test_unify_fills_gaps_when_band_returns_late(gap):
    beats = _from_intervals([1.0] * 16 + [gap] + [1.0] * 16)
    _unified, _, info = rhythm.unify_beats(beats, np.array([]))
    assert info["added"] == round(gap) - 1


@pytest.mark.parametrize("eighth", [0.6, 0.64, 0.67, 0.75])
def test_unify_double_time_swing_keeps_the_grid(eighth):
    # Stretch where the detector also marks the swung eighth note
    quarter_notes = np.arange(64) * 0.5
    swing = quarter_notes[16:32] + eighth * 0.5
    beats = np.sort(np.concatenate([quarter_notes, swing]))
    unified, downbeats, _ = rhythm.unify_beats(beats, quarter_notes[::4])
    assert np.allclose(unified, quarter_notes)
    assert np.allclose(downbeats, quarter_notes[::4])


def _bars(*lengths, start=0):
    """Beats every 0.5 s and downbeats that make bars of those lengths."""
    total = start + sum(lengths) + 4
    beats = np.arange(total) * 0.5
    indices = np.cumsum((start, *lengths))
    return beats, beats[indices]


@pytest.mark.parametrize(
    ("lengths", "expected_lengths"),
    [
        ((4, 4, 3, 1, 4, 4), [4, 4, 4, 4, 4]),  # Resident Evil: 3 + 1
        ((4, 1, 3, 4), [4, 4, 4]),  # 1 + 3
        ((4, 3, 5, 4), [4, 4, 4, 4]),  # shifted downbeat: 3 + 5
        ((4, 8, 4), [4, 4, 4, 4]),  # missed downbeat
        ((4, 2, 2, 4), [4, 4, 4]),
        ((4, 4, 3, 4, 4), [4, 4, 3, 4, 4]),  # a single bar of 3 may be real
        ((4, 3, 3, 4), [4, 3, 3, 4]),  # 6 is not a multiple of 4: left alone
        ((4, 3, 3, 2, 4), [4, 4, 4, 4]),  # 3+3+2 with a bar of 2: an error
        ((4, 4, 3, 3, 3, 3, 4), [4, 4, 3, 3, 3, 3, 4]),  # a real bridge in 3/4
        ((4, 5, 5, 5, 5, 4), [4, 5, 5, 5, 5, 4]),  # a real section in 5/4
        ((4, 5, 7, 4), [4, 5, 7, 4]),  # adds up to 12: more than two bars
    ],
)
def test_regularize_bars(lengths, expected_lengths):
    beats, downbeats = _bars(*lengths)
    new, _ = rhythm.regularize_bars(beats, downbeats, 4)
    assert np.diff(np.searchsorted(beats, new)).tolist() == expected_lengths


def test_regularize_keeps_four_beat_bars_in_waltz():
    beats, downbeats = _bars(3, 3, 4, 4, 4, 3, 3)
    new, regrouped = rhythm.regularize_bars(beats, downbeats, 3)
    assert np.diff(np.searchsorted(beats, new)).tolist() == [3, 3, 4, 4, 4, 3, 3]
    assert regrouped == 0


def test_regularize_does_nothing_without_meter():
    beats, downbeats = _bars(3, 1, 4)
    new, regrouped = rhythm.regularize_bars(beats, downbeats, None)
    assert np.array_equal(new, downbeats)
    assert regrouped == 0


def test_bar_grid_with_pickup():
    beats = _beats(120, 17)
    bar_cells = rhythm.bar_grid(beats, beats[1::4], duration=9.0)
    assert bar_cells[0]["number"] == 0
    assert bar_cells[0]["kind"] == "pickup"
    assert bar_cells[1]["number"] == 1
    assert abs(bar_cells[1]["start"] - 0.5) < 1e-9
    assert bar_cells[1]["kind"] == "bar"
    assert abs(bar_cells[-1]["end"] - 9.0) < 1e-9


def test_intro_without_beats_appears_in_grid():
    beats = 20 + _beats(120, 40)  # the drums come in at 20 s
    bar_cells = rhythm.bar_grid(beats, beats[::4], duration=40.0)
    assert bar_cells[0] == {"number": 0, "kind": "intro", "start": 0.0, "end": 20.0}


def test_without_downbeats_groups_four_beats():
    beats = _beats(120, 33)
    bar_cells = rhythm.bar_grid(beats, np.array([]), duration=17.0)
    assert bar_cells[0]["kind"] == "section"
    assert abs(bar_cells[1]["start"] - 2.0) < 1e-9


def test_without_beats_groups_every_four_seconds():
    bar_cells = rhythm.bar_grid(np.array([]), np.array([]), duration=10.0)
    assert [c["start"] for c in bar_cells] == [0.0, 4.0, 8.0]


def test_meter_is_not_more_confident_than_beats():
    beats = _beats(120, 65)
    result = rhythm.analyze_meter(beats, beats[::4], {"kind": "binary"}, 120, "low")
    assert result["confidence"] == "low"


def test_unclear_subdivision_without_onsets():
    # Envelope without onsets between beats (sustained chords): must not invent a subdivision
    rng = np.random.default_rng(3)
    envelope = 1 + 0.05 * rng.random(int(60 * 22050 / rhythm.HOP_LENGTH))
    beats = _beats(60, 55)
    assert rhythm.analyze_subdivision(beats, envelope, 22050)["kind"] == "unclear"


def _subdivision(sub):
    import librosa

    y = song(100, 4, [("C", False)], bars=16, subdivision=sub)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    beats = np.arange(0, 16 * 4) * 0.6
    env = rhythm.onset_envelope(y, 22050)
    return rhythm.analyze_subdivision(beats, env, 22050)["kind"]


def test_binary_subdivision():
    assert _subdivision(2) == "binary"


def test_ternary_subdivision():
    assert _subdivision(3) == "ternary"


def _triplet_tracking(bpm, seconds, rng):
    """What Beat This! does on a lone instrument with a triplet feel: an activation that peaks on
    every note of the triplet, and detected beats that jump between those notes and the real beats."""
    triplet = 60.0 / bpm / 3
    notes = np.arange(0, seconds, triplet)
    frames = np.arange(int(seconds * 50)) / 50
    activation = np.full(len(frames), -6.0)
    for t in notes:
        activation[np.abs(frames - t) < 0.011] = 4.0 if round(t / triplet) % 3 == 0 else 2.0
    beats, i = [], 0
    while i < len(notes):
        beats.append(notes[i])
        i += int(rng.choice([1, 1, 3]))  # mostly the triplet notes, sometimes the real beat
    return np.array(beats), activation


def test_steady_beat_grids_include_the_real_beat():
    beats, activation = _triplet_tracking(80, 60, np.random.default_rng(0))
    grids = dict(rhythm.steady_beat_grids(beats, activation))
    assert 3 in grids or 2 in grids  # multiples of the triplet note that fall in 55-170 BPM
    slow = [g for g in grids.values() if abs(60 / np.median(np.diff(g)) - 80) < 4]
    assert slow, "no grid near the real 80 BPM"
    assert np.std(np.diff(slow[0])) < 0.02  # steady


def test_irregular_triplet_tracking_is_replaced_by_the_real_beat():
    from tonos.analysis import pipeline

    bpm, bars = 80, 40
    y = song(bpm, 4, [("C", False), ("A", True), ("F", False), ("G", False)], bars=bars, subdivision=3)
    y = librosa_resample(y)
    beats, activation = _triplet_tracking(bpm, bars * 4 * 60 / bpm, np.random.default_rng(1))
    envelope = rhythm.onset_envelope(y, 22050)
    steady, _ = pipeline._steady_beats(y, 22050, beats, activation, envelope)
    assert steady is not None
    assert 60 / np.median(np.diff(steady)) == pytest.approx(bpm, rel=0.05)


def librosa_resample(y):
    import librosa

    return librosa.resample(y, orig_sr=FS, target_sr=22050)
