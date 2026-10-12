import pytest

from orfeo.analysis.notation import (
    Speller,
    describe_chord,
    key_name,
    parse_skey_label,
    relative_key,
)


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Bb Major", (10, "major")),
        ("D# Major", (3, "major")),
        ("G# minor", (8, "minor")),
        ("A minor", (9, "minor")),
    ],
)
def test_parse_skey_label(label, expected):
    assert parse_skey_label(label) == expected


def test_key_names_use_usual_spelling():
    assert key_name(3, "major") == {"solfege": "Mi♭", "letter": "E♭"}
    assert key_name(8, "major")["solfege"] == "La♭"
    assert key_name(6, "major")["solfege"] == "Fa#"
    assert key_name(9, "minor") == {"solfege": "La", "letter": "A"}
    assert key_name(1, "minor")["solfege"] == "Do#"
    assert key_name(10, "minor")["solfege"] == "Si♭"


def test_relative_key():
    assert relative_key(0, "major") == (9, "minor")
    assert relative_key(9, "minor") == (0, "major")
    assert relative_key(3, "major") == (0, "minor")


@pytest.mark.parametrize(
    ("label", "solfege_name", "letter_name", "simple"),
    [
        ("A:min", "Lam", "Am", "Lam"),
        ("C:maj", "Do", "C", "Do"),
        ("G:7", "Sol7", "G7", "Sol"),
        ("D:min7", "Rem7", "Dm7", "Rem"),
        ("F:maj7", "Famaj7", "Fmaj7", "Fa"),
        ("C:maj/3", "Do/Mi", "C/E", "Do"),
        ("B:hdim7", "Sim7(♭5)", "Bm7(♭5)", "Sidim"),
        ("E:(1,b3,5,b7,11)", "Mim7", "Em7", "Mim"),  # unusual extension: keeps the core chord
    ],
)
def test_describe_chord(label, solfege_name, letter_name, simple):
    d = describe_chord(label, Speller(0, "major"))
    assert d["is_chord"]
    assert d["solfege"] == solfege_name
    assert d["letter"] == letter_name
    assert d["solfege_simple"] == simple


def test_chord_uses_flats_in_flat_key():
    speller = Speller(3, "major")  # E♭ major
    assert describe_chord("A#:maj", speller)["solfege"] == "Si♭"
    assert describe_chord("D#:maj", speller)["letter"] == "E♭"


def test_chord_uses_sharps_in_sharp_key():
    speller = Speller(4, "major")  # E major
    assert describe_chord("C#:min", speller)["solfege"] == "Do#m"
    assert describe_chord("G#:min", speller)["letter"] == "G#m"


@pytest.mark.parametrize(
    ("tonic", "mode", "label", "expected"),
    [
        (5, "major", "D:maj/3", "D/F#"),  # never D/G♭
        (2, "minor", "A:maj/3", "A/C#"),  # dominant of D minor in first inversion
        (2, "minor", "A:7/3", "A7/C#"),
        (9, "minor", "E:maj/3", "E/G#"),
        (9, "minor", "G#:dim7", "G#dim7"),  # leading tone of A minor
        (0, "major", "A:maj/3", "A/C#"),
        (7, "major", "A#:maj", "B♭"),  # borrowed ♭III in G major
        (7, "major", "D#:maj", "E♭"),  # borrowed ♭VI
        (2, "major", "A#:maj", "B♭"),
        (5, "major", "A#:maj", "B♭"),
        (5, "major", "C:7", "C7"),
        (4, "major", "B:maj/5", "B/F#"),
        (3, "major", "A#:maj/3", "B♭/D"),
    ],
)
def test_spelling_of_roots_and_basses(tonic, mode, label, expected):
    assert describe_chord(label, Speller(tonic, mode))["letter"] == expected


def test_chords_without_third_are_not_shown_as_major():
    speller = Speller(0, "major")
    fifth = describe_chord("C:5", speller)
    assert fifth["letter"] == "C5"
    assert fifth["letter_simple"] == "C5"
    assert describe_chord("C:(1)", speller)["letter"] == "C(no3)"
    sus = describe_chord("D:sus4", speller)
    assert sus["letter"] == "Dsus4"
    assert sus["letter_simple"] == "Dsus4"


@pytest.mark.parametrize(
    ("tonic", "mode", "label", "expected"),
    [
        (8, "minor", "C:min", "Cm"),  # used to come out as "B#m"
        (8, "minor", "C:min/5", "Cm/G"),
        (8, "minor", "C:maj", "C"),
        (1, "minor", "C:dim", "B#dim"),  # leading tone of C# minor: keeps its accidental
        (6, "major", "F:dim", "E#dim"),  # diatonic in F# major: follows the key signature
        (10, "major", "E:maj", "E"),
    ],
)
def test_out_of_key_white_key_notes(tonic, mode, label, expected):
    assert describe_chord(label, Speller(tonic, mode))["letter"] == expected


def test_no_chord():
    d = describe_chord("N", Speller())
    assert not d["is_chord"]
    assert d["solfege"] == "—"
