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
        ("Bb Major", (10, "mayor")),
        ("D# Major", (3, "mayor")),
        ("G# minor", (8, "menor")),
        ("A minor", (9, "menor")),
    ],
)
def test_parse_skey_label(label, expected):
    assert parse_skey_label(label) == expected


def test_key_names_use_usual_spelling():
    assert key_name(3, "mayor") == {"latino": "Mi♭ mayor", "americano": "E♭"}
    assert key_name(8, "mayor")["latino"] == "La♭ mayor"
    assert key_name(6, "mayor")["latino"] == "Fa# mayor"
    assert key_name(9, "menor") == {"latino": "La menor", "americano": "Am"}
    assert key_name(1, "menor")["latino"] == "Do# menor"
    assert key_name(10, "menor")["latino"] == "Si♭ menor"


def test_relative_key():
    assert relative_key(0, "mayor") == (9, "menor")
    assert relative_key(9, "menor") == (0, "mayor")
    assert relative_key(3, "mayor") == (0, "menor")


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
        ("E:(1,b3,5,b7,11)", "Mim7", "Em7", "Mim"),  # extensión rara: se queda con el núcleo
    ],
)
def test_describe_chord(label, solfege_name, letter_name, simple):
    d = describe_chord(label, Speller(0, "mayor"))
    assert d["es_acorde"]
    assert d["latino"] == solfege_name
    assert d["americano"] == letter_name
    assert d["latino_simple"] == simple


def test_chord_uses_flats_in_flat_key():
    speller = Speller(3, "mayor")  # Mi♭ mayor
    assert describe_chord("A#:maj", speller)["latino"] == "Si♭"
    assert describe_chord("D#:maj", speller)["americano"] == "E♭"


def test_chord_uses_sharps_in_sharp_key():
    speller = Speller(4, "mayor")  # Mi mayor
    assert describe_chord("C#:min", speller)["latino"] == "Do#m"
    assert describe_chord("G#:min", speller)["americano"] == "G#m"


@pytest.mark.parametrize(
    ("tonic", "mode", "label", "expected"),
    [
        (5, "mayor", "D:maj/3", "D/F#"),  # nunca D/G♭
        (2, "menor", "A:maj/3", "A/C#"),  # dominante de Re menor en primera inversión
        (2, "menor", "A:7/3", "A7/C#"),
        (9, "menor", "E:maj/3", "E/G#"),
        (9, "menor", "G#:dim7", "G#dim7"),  # sensible de La menor
        (0, "mayor", "A:maj/3", "A/C#"),
        (7, "mayor", "A#:maj", "B♭"),  # ♭III prestado en Sol mayor
        (7, "mayor", "D#:maj", "E♭"),  # ♭VI prestado
        (2, "mayor", "A#:maj", "B♭"),
        (5, "mayor", "A#:maj", "B♭"),
        (5, "mayor", "C:7", "C7"),
        (4, "mayor", "B:maj/5", "B/F#"),
        (3, "mayor", "A#:maj/3", "B♭/D"),
    ],
)
def test_spelling_of_roots_and_basses(tonic, mode, label, expected):
    assert describe_chord(label, Speller(tonic, mode))["americano"] == expected


def test_chords_without_third_are_not_shown_as_major():
    speller = Speller(0, "mayor")
    fifth = describe_chord("C:5", speller)
    assert fifth["americano"] == "C5"
    assert fifth["americano_simple"] == "C5"
    assert describe_chord("C:(1)", speller)["americano"] == "C(sin 3.ª)"
    sus = describe_chord("D:sus4", speller)
    assert sus["americano"] == "Dsus4"
    assert sus["americano_simple"] == "Dsus4"


@pytest.mark.parametrize(
    ("tonic", "mode", "label", "expected"),
    [
        (8, "menor", "C:min", "Cm"),  # antes salía "B#m"
        (8, "menor", "C:min/5", "Cm/G"),
        (8, "menor", "C:maj", "C"),
        (1, "menor", "C:dim", "B#dim"),  # sensible de Do# menor: se escribe alterada
        (6, "mayor", "F:dim", "E#dim"),  # diatónica en Fa# mayor: se respeta la armadura
        (10, "mayor", "E:maj", "E"),
    ],
)
def test_out_of_key_white_key_notes(tonic, mode, label, expected):
    assert describe_chord(label, Speller(tonic, mode))["americano"] == expected


def test_no_chord():
    d = describe_chord("N", Speller())
    assert not d["es_acorde"]
    assert d["latino"] == "—"
