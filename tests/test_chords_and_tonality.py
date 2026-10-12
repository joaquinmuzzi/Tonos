import numpy as np

from orfeo.analysis import chords, tonality


def test_chunks_cover_the_end_without_padding():
    assert chords._chunk_starts(15.0) == [0.0]
    assert chords._chunk_starts(40.0) == [0.0, 20.0]
    # 49 s: the last chunk starts at 29 s (a full 20 s up to the end), not at 40 s
    assert chords._chunk_starts(49.0) == [0.0, 20.0, 29.0]


def test_one_beat_chord_is_kept():
    beat = 60 / 140  # 0.43 s
    beats = np.arange(0, 20, beat)
    raw_segments = [(0.0, 4 * beat, "C:maj"), (4 * beat, 5 * beat, "G:maj"), (5 * beat, 20.0, "F:maj")]
    output = chords._merge_equal(chords.group_by_beats(raw_segments, beats, 20.0))
    assert [e for _, _, e in output] == ["C:maj", "G:maj", "F:maj"]


def test_intro_without_beats_keeps_its_chords():
    raw_segments = [
        (0, 5, "A:min"),
        (5, 10, "F:maj"),
        (10, 15, "C:maj"),
        (15, 20, "G:maj"),
        (20, 22, "A:min"),
        (22, 24, "G:maj"),
        (24, 30, "F:maj"),
    ]
    beats = np.arange(20, 30, 0.5)
    output = chords._merge_equal(chords.group_by_beats(raw_segments, beats, 30.0))
    assert [e for _, _, e in output] == ["A:min", "F:maj", "C:maj", "G:maj", "A:min", "G:maj", "F:maj"]
    assert output[0][:2] == (0, 5)


def test_short_segments_without_beats_are_absorbed():
    raw_segments = [(0.0, 0.2, "C:maj"), (0.2, 3.0, "G:maj"), (3.0, 3.1, "D:maj"), (3.1, 6.0, "G:maj")]
    output = chords._merge_equal(chords.group_by_beats(raw_segments, np.array([]), 6.0))
    assert output == [(0.0, 6.0, "G:maj")]


def test_key_from_chords():
    progression = [(0, 2, "G:maj"), (2, 4, "D:maj"), (4, 6, "E:min"), (6, 8, "C:maj")] * 4
    assert tonality.key_from_chords(progression) == (7, "major")
    assert tonality.key_from_chords([(0, 10, "N")]) is None
    assert tonality.key_from_chords([]) is None


def _key_result(advantage, tonic=7, mode="major"):
    return {
        "best": {"tonic_pc": tonic, "mode": mode},
        "advantage": advantage,
        "sections": {"agreement": None},
    }


def test_key_without_chords_has_low_confidence():
    key_result = _key_result(advantage=3.0)
    tonality.assess_confidence(key_result, None)
    assert key_result["confidence"] == "low"


def test_high_confidence_when_both_methods_agree():
    key_result = _key_result(advantage=1.5)
    tonality.assess_confidence(key_result, (7, "major"))
    assert key_result["confidence"] == "high"
    assert key_result["second_method"]["agreement"] == "same"
