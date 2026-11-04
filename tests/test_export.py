import mido
import pytest

from tonos.export import write_midi


def _notes(midi):
    starts = {}
    notes = []
    seconds = 0.0
    # MidiFile iteration merges tracks and converts ticks using the tempo in effect.
    for message in midi:
        seconds += message.time
        if message.type == "note_on" and message.velocity > 0:
            starts[message.note] = seconds
        elif message.type == "note_off":
            notes.append((message.note, starts.pop(message.note), seconds))
    assert not starts
    return sorted(notes)


def test_midi_follows_a_drifting_compound_beat_grid(tmp_path):
    report = {
        "file": {"duration": 3.0},
        "beats": [0.25, 0.75, 1.35, 2.0],
        "tempo": {"bpm": 100},
        "meter": {"beats_per_bar": 2, "time_signature": "6/8"},
        "chords": {
            "segments": [
                {"start": 0.25, "end": 0.75, "label": "F:maj6", "is_chord": True},
                {"start": 0.75, "end": 1.35, "label": "N", "is_chord": False},
                {"start": 1.35, "end": 2.35, "label": "G:maj/3", "is_chord": True},
            ]
        },
    }
    path = tmp_path / "song.mid"
    write_midi(report, path)
    midi = mido.MidiFile(path)
    assert midi.length == pytest.approx(3.0, abs=0.001)
    (signature,) = (m for track in midi.tracks for m in track if m.type == "time_signature")
    assert (signature.numerator, signature.denominator) == (6, 8)
    assert [m.tempo for m in midi.tracks[0] if m.type == "set_tempo"][-3:] == [
        333333,
        400000,
        433333,
    ]
    # F A C D, then B D G with B in the bass. No notes sound in the intervening rest.
    notes = _notes(midi)
    assert [pitch for pitch, _, _ in notes] == [53, 57, 59, 60, 62, 62, 67]
    for pitch, start, end in notes:
        if start < 1:
            assert pitch in (53, 57, 60, 62)
            assert (start, end) == pytest.approx((0.25, 0.75), abs=0.001)
        else:
            assert pitch in (59, 62, 67)
            assert (start, end) == pytest.approx((1.35, 2.35), abs=0.001)


def test_export_without_a_detected_grid_preserves_seconds(tmp_path):
    path = tmp_path / "no-grid.mid"
    report = {
        "file": {"duration": 2.0},
        "beats": [],
        "tempo": {"bpm": None},
        "meter": {"beats_per_bar": None},
        "chords": {"segments": [{"start": 0.3, "end": 1.7, "label": "C:1", "is_chord": True}]},
    }
    write_midi(report, path)
    (note,) = _notes(mido.MidiFile(path))
    assert note == pytest.approx((48, 0.3, 1.7), abs=0.001)


def test_long_lead_in_and_gap_fit_the_midi_tempo_range(tmp_path):
    path = tmp_path / "slow.mid"
    report = {
        "file": {"duration": 60},
        "beats": [20, 40, 60],
        "tempo": {"bpm": 3},
        "meter": {"beats_per_bar": 4, "time_signature": "4/4"},
        "chords": {"segments": [{"start": 20, "end": 40, "label": "C:1", "is_chord": True}]},
    }
    write_midi(report, path)
    midi = mido.MidiFile(path)
    (note,) = _notes(midi)
    assert note == pytest.approx((48, 20, 40))
    assert midi.length == pytest.approx(60)
