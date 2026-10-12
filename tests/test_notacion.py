import pytest

from app.analisis.notacion import (
    Ortografia,
    describir_acorde,
    nombre_tonalidad,
    parsear_tonalidad_skey,
    relativa,
)


@pytest.mark.parametrize(
    "etiqueta, esperado",
    [
        ("Bb Major", (10, "mayor")),
        ("D# Major", (3, "mayor")),
        ("G# minor", (8, "menor")),
        ("A minor", (9, "menor")),
    ],
)
def test_parsear_tonalidad_skey(etiqueta, esperado):
    assert parsear_tonalidad_skey(etiqueta) == esperado


def test_nombres_de_tonalidad_con_ortografia_habitual():
    assert nombre_tonalidad(3, "mayor") == {"latino": "Mi♭ mayor", "americano": "E♭"}
    assert nombre_tonalidad(8, "mayor")["latino"] == "La♭ mayor"
    assert nombre_tonalidad(6, "mayor")["latino"] == "Fa# mayor"
    assert nombre_tonalidad(9, "menor") == {"latino": "La menor", "americano": "Am"}
    assert nombre_tonalidad(1, "menor")["latino"] == "Do# menor"
    assert nombre_tonalidad(10, "menor")["latino"] == "Si♭ menor"


def test_relativa():
    assert relativa(0, "mayor") == (9, "menor")
    assert relativa(9, "menor") == (0, "mayor")
    assert relativa(3, "mayor") == (0, "menor")


@pytest.mark.parametrize(
    "etiqueta, latino, americano, simple",
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
def test_describir_acorde(etiqueta, latino, americano, simple):
    d = describir_acorde(etiqueta, Ortografia(0, "mayor"))
    assert d["es_acorde"]
    assert d["latino"] == latino
    assert d["americano"] == americano
    assert d["latino_simple"] == simple


def test_acorde_con_bemoles_en_tonalidad_bemol():
    orto = Ortografia(3, "mayor")  # Mi♭ mayor
    assert describir_acorde("A#:maj", orto)["latino"] == "Si♭"
    assert describir_acorde("D#:maj", orto)["americano"] == "E♭"


def test_acorde_con_sostenidos_en_tonalidad_sostenido():
    orto = Ortografia(4, "mayor")  # Mi mayor
    assert describir_acorde("C#:min", orto)["latino"] == "Do#m"
    assert describir_acorde("G#:min", orto)["americano"] == "G#m"


@pytest.mark.parametrize(
    "tonica, modo, etiqueta, esperado",
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
def test_ortografia_de_fundamentales_y_bajos(tonica, modo, etiqueta, esperado):
    assert describir_acorde(etiqueta, Ortografia(tonica, modo))["americano"] == esperado


def test_acordes_sin_tercera_no_se_muestran_como_mayores():
    orto = Ortografia(0, "mayor")
    quinta = describir_acorde("C:5", orto)
    assert quinta["americano"] == "C5" and quinta["americano_simple"] == "C5"
    assert describir_acorde("C:(1)", orto)["americano"] == "C(sin 3.ª)"
    sus = describir_acorde("D:sus4", orto)
    assert sus["americano"] == "Dsus4" and sus["americano_simple"] == "Dsus4"


@pytest.mark.parametrize(
    "tonica, modo, etiqueta, esperado",
    [
        (8, "menor", "C:min", "Cm"),  # antes salía "B#m"
        (8, "menor", "C:min/5", "Cm/G"),
        (8, "menor", "C:maj", "C"),
        (1, "menor", "C:dim", "B#dim"),  # sensible de Do# menor: se escribe alterada
        (6, "mayor", "F:dim", "E#dim"),  # diatónica en Fa# mayor: se respeta la armadura
        (10, "mayor", "E:maj", "E"),
    ],
)
def test_notas_cromaticas_de_tecla_blanca(tonica, modo, etiqueta, esperado):
    assert describir_acorde(etiqueta, Ortografia(tonica, modo))["americano"] == esperado


def test_sin_acorde():
    d = describir_acorde("N", Ortografia())
    assert not d["es_acorde"]
    assert d["latino"] == "—"
