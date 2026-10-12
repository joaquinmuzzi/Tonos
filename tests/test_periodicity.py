"""Meter from the repetition of the harmony, with synthetic songs and known beats."""

import librosa
import numpy as np
import pytest

from orfeo.analysis import periodicity, rhythm
from orfeo.messages import message
from tests.synthetic import FS, _midi_to_hz, _mix_in, _tone, song

PROGRESSIONS = {
    3: [("D", False), ("G", False), ("A", False), ("D", False)],
    4: [("G", False), ("D", False), ("E", True), ("C", False)],
    5: [("A", True), ("F", False), ("C", False), ("G", False)],
    7: [("E", True), ("C", False), ("D", False)],
}


def _synthetic(beats_per_bar, bpm=130, bars=48):
    y = song(bpm, beats_per_bar, PROGRESSIONS[beats_per_bar], bars=bars)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    beats = np.arange(bars * beats_per_bar) * 60.0 / bpm
    return y, beats


@pytest.mark.parametrize("beats_per_bar", [3, 4, 5, 7])
def test_detects_meter_from_repetition(beats_per_bar):
    y, beats = _synthetic(beats_per_bar)
    envelope = rhythm.onset_envelope(y, 22050)
    summary, _spectrum = periodicity.analyze(y, 22050, beats, envelope, rhythm.HOP_LENGTH)
    assert summary["winner"] == beats_per_bar
    if beats_per_bar in (5, 7):  # the only cases where the method can take over
        assert summary["margin"] > 0.3


@pytest.mark.parametrize("beats_per_bar", [3, 5, 7])
def test_locates_the_downbeat(beats_per_bar):
    y, beats = _synthetic(beats_per_bar)
    envelope = rhythm.onset_envelope(y, 22050)
    _, spectrum = periodicity.analyze(y, 22050, beats, envelope, rhythm.HOP_LENGTH)
    downbeats, clarity = periodicity.locate_bars(beats, beats_per_bar, spectrum, 22050)
    assert downbeats[0] == pytest.approx(0.0)
    assert np.allclose(np.diff(downbeats), beats_per_bar * 60 / 130)
    assert clarity >= periodicity.PHASE_CLARITY_THRESHOLD


def test_anticipated_chords_do_not_shift_the_downbeat():
    """If chords come in half a beat early, the harmony alone puts the downbeat one beat
    early; the recognized chord changes (on beat 1) correct it."""
    L, bpm = 7, 105
    y = song(bpm, L, PROGRESSIONS[7], bars=36, anticipation=0.5)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    beats = np.arange(36 * L) * 60.0 / bpm
    envelope = rhythm.onset_envelope(y, 22050)
    _, spectrum = periodicity.analyze(y, 22050, beats, envelope, rhythm.HOP_LENGTH)
    changes = np.zeros(len(beats))
    changes[::L] = 1.0  # where the chord recognizer marks the change
    changes[0] = 0.0
    downbeats, _ = periodicity.locate_bars(beats, L, spectrum, 22050, changes)
    assert downbeats[0] == pytest.approx(0.0)


@pytest.mark.parametrize("L", [5, 7])
def test_anticipated_chords_marked_on_the_beat_before(L):
    """The real chord recognizer marks a chord that comes in half a beat early on the beat
    BEFORE the downbeat; it must still count for the downbeat it anticipates."""
    bpm = 105
    y = song(bpm, L, PROGRESSIONS[L], bars=36, anticipation=0.5)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    beats = np.arange(36 * L) * 60.0 / bpm
    envelope = rhythm.onset_envelope(y, 22050)
    _, spectrum = periodicity.analyze(y, 22050, beats, envelope, rhythm.HOP_LENGTH)
    changes = np.zeros(len(beats))
    changes[L - 1 :: L] = 1.0  # one beat early, as the recognizer marks them
    downbeats, _ = periodicity.locate_bars(beats, L, spectrum, 22050, changes)
    assert np.all(np.searchsorted(beats, downbeats) % L == 0)


def test_bass_on_beat_one_beats_a_melodic_accent():
    """A 5/4 vamp like Machinarium's "The Castle": the bass lands hardest on beat 1 (E, already
    played on beat 5 of the previous bar, then A on beats 2-4), while the loudest pitched attack is
    a melody note on beat 4. The bar starts on the bass, not on the melodic accent."""
    L, bpm, bars = 5, 120, 30
    beat = 60.0 / bpm
    y = np.zeros(int((bars * L * beat + 1) * FS))
    for b in range(bars):
        start = b * L * beat
        for note in (62, 65, 69):  # D minor pad, soft and held for the bar
            _mix_in(y, _tone(_midi_to_hz(note), L * beat, 0.03), start)
        for k, note in enumerate((40, 45, 45, 45, 40)):  # bass E A A A E, strongest on beat 1
            _mix_in(y, _tone(_midi_to_hz(note), beat, 0.2 if k == 0 else 0.08), start + k * beat)
        _mix_in(y, _tone(_midi_to_hz(74), beat, 0.15), start + 3 * beat)  # melody accent on beat 4
    y = librosa.resample((0.9 * y / np.abs(y).max()).astype(np.float32), orig_sr=FS, target_sr=22050)
    beats = np.arange(bars * L) * beat
    envelope = rhythm.onset_envelope(y, 22050)
    _, spectrum = periodicity.analyze(y, 22050, beats, envelope, rhythm.HOP_LENGTH)
    downbeats, _ = periodicity.locate_bars(beats, L, spectrum, 22050)
    assert np.all(np.searchsorted(beats, downbeats) % L == 0)


def test_perfectly_regular_chord_marks_decide_on_silence():
    """A cue with no variation between bars must not get a zero (or huge) vote."""
    L = 5
    beats = np.arange(100) * 0.5
    changes = np.zeros(len(beats))
    changes[::L] = 1.0
    spectrum = np.zeros((84, 2500), dtype=np.float32)
    downbeats, _ = periodicity.locate_bars(beats, L, spectrum, 22050, changes)
    assert np.all(np.searchsorted(beats, downbeats) % L == 0)


def test_short_stretch_continues_the_count():
    L = 5
    beats = np.concatenate(
        [
            np.arange(60) * 0.5,
            30.0 + 0.8 + np.arange(6) * 0.5,  # jump and short stretch
            33.8 + 0.8 + np.arange(60) * 0.5,
        ]
    )
    spectrum = np.random.default_rng(0).random((84, 4000)).astype(np.float32)
    changes = np.zeros(len(beats))
    changes[::L] = 1.0
    downbeats, _ = periodicity.locate_bars(beats, L, spectrum, 22050, changes)
    bar_lengths = np.diff(np.searchsorted(beats, downbeats))
    assert len(downbeats) >= 20  # the short stretch does not leave a gap without bars
    assert np.all(bar_lengths <= 2 * L)


def test_short_song_is_not_analyzed():
    beats = np.arange(40) * 0.5
    assert periodicity.analyze(np.zeros(22050 * 20), 22050, beats, np.zeros(2000), rhythm.HOP_LENGTH) == (
        None,
        None,
    )


def _repetition(winner, scores, harmony):
    others = sorted((v for f, v in scores.items() if f != winner), reverse=True)
    return {
        "winner": winner,
        "scores": scores,
        "harmony": harmony,
        "margin": round(scores[winner] - others[0], 2),
    }


FIVE = _repetition(5, {3: -0.4, 4: -0.66, 5: 0.36, 7: -0.47}, {3: -0.49, 4: -0.58, 5: 0.91, 7: -0.36})


def test_harmony_in_five_replaces_count_of_four():
    beats = np.arange(400) * 0.5
    result = rhythm.analyze_meter(beats, beats[::4], {"kind": "binary"}, 120, "high", FIVE)
    assert result["time_signature"] == "5/4"
    assert result["source"] == "periodicity"
    assert result["beats_per_bar"] == 5
    assert result["downbeat_count"] == 4
    assert result["confidence"] == "medium"  # advantage of 1.02 with the harmony in favour
    assert message("meter_from_harmony", counted=4, beats=5) in result["warnings"]


def test_weak_evidence_does_not_replace_count():
    weak = _repetition(5, {3: -0.3, 4: 0.0, 5: 0.4, 7: -0.5}, {3: 0.0, 4: 0.1, 5: 0.2, 7: 0.0})
    beats = np.arange(400) * 0.5
    result = rhythm.analyze_meter(beats, beats[::4], {"kind": "binary"}, 120, "high", weak)
    assert result["time_signature"] == "4/4"
    assert result["source"] == "downbeats"


def test_does_not_replace_without_harmony_support():
    against = _repetition(5, {3: -0.4, 4: -0.5, 5: 0.6, 7: -0.5}, {3: 0.0, 4: 0.5, 5: 0.1, 7: 0.0})
    beats = np.arange(400) * 0.5
    result = rhythm.analyze_meter(beats, beats[::4], {"kind": "binary"}, 120, "high", against)
    assert result["source"] == "downbeats"


def test_agreement_raises_confidence():
    four = _repetition(4, {3: -0.4, 4: 0.9, 5: -0.5, 7: -0.4}, {3: -0.3, 4: 1.1, 5: -0.4, 7: -0.3})
    beats = np.arange(200) * 0.5
    downbeats, i = [], 0
    for n in [4] * 30 + [3, 5] * 5:  # 75 % of the bars count 4: medium confidence
        downbeats.append(beats[i])
        i += n
    result = rhythm.analyze_meter(beats, np.array(downbeats), {"kind": "binary"}, 120, "high", four)
    assert result["second_method"]["confirms"]
    assert result["confidence"] == "high"


def test_between_three_and_four_only_warns():
    three = _repetition(3, {3: 0.9, 4: -0.2, 5: -0.5, 7: -0.5}, {3: 0.9, 4: -0.1, 5: -0.4, 7: -0.4})
    beats = np.arange(400) * 0.5
    result = rhythm.analyze_meter(beats, beats[::4], {"kind": "binary"}, 120, "high", three)
    assert result["time_signature"] == "4/4"  # the detector tells 3 from 4 well: no replacement
    assert result["confidence"] == "medium"  # but the confidence drops
    assert message("harmony_suggests", beats=3) in result["warnings"]


def test_invalid_count_but_clear_harmony():
    beats = np.arange(300) * 0.46
    result = rhythm.analyze_meter(beats, beats, {"kind": "binary"}, 130, "high", FIVE)
    assert result["time_signature"] == "5/4"
    assert result["source"] == "periodicity"
