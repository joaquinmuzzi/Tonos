import numpy as np

from orfeo.analysis import chords, tonality


def test_trozos_cubren_el_final_sin_relleno():
    assert chords._inicios_de_trozos(15.0) == [0.0]
    assert chords._inicios_de_trozos(40.0) == [0.0, 20.0]
    # 49 s: el último trozo arranca en 29 s (20 s completos hasta el final), no en 40 s
    assert chords._inicios_de_trozos(49.0) == [0.0, 20.0, 29.0]


def test_acorde_de_un_pulso_no_se_pierde():
    pulso = 60 / 140  # 0,43 s
    pulsos = np.arange(0, 20, pulso)
    crudos = [(0.0, 4 * pulso, "C:maj"), (4 * pulso, 5 * pulso, "G:maj"), (5 * pulso, 20.0, "F:maj")]
    salida = chords._unir_iguales(chords.agrupar_por_pulsos(crudos, pulsos, 20.0))
    assert [e for _, _, e in salida] == ["C:maj", "G:maj", "F:maj"]


def test_intro_sin_pulsos_conserva_sus_acordes():
    crudos = [
        (0, 5, "A:min"),
        (5, 10, "F:maj"),
        (10, 15, "C:maj"),
        (15, 20, "G:maj"),
        (20, 22, "A:min"),
        (22, 24, "G:maj"),
        (24, 30, "F:maj"),
    ]
    pulsos = np.arange(20, 30, 0.5)
    salida = chords._unir_iguales(chords.agrupar_por_pulsos(crudos, pulsos, 30.0))
    assert [e for _, _, e in salida] == ["A:min", "F:maj", "C:maj", "G:maj", "A:min", "G:maj", "F:maj"]
    assert salida[0][:2] == (0, 5)


def test_segmentos_cortos_sin_pulsos_se_absorben():
    crudos = [(0.0, 0.2, "C:maj"), (0.2, 3.0, "G:maj"), (3.0, 3.1, "D:maj"), (3.1, 6.0, "G:maj")]
    salida = chords._unir_iguales(chords.agrupar_por_pulsos(crudos, np.array([]), 6.0))
    assert salida == [(0.0, 6.0, "G:maj")]


def test_tonalidad_desde_acordes():
    progresion = [(0, 2, "G:maj"), (2, 4, "D:maj"), (4, 6, "E:min"), (6, 8, "C:maj")] * 4
    assert tonality.tonalidad_desde_acordes(progresion) == (7, "mayor")
    assert tonality.tonalidad_desde_acordes([(0, 10, "N")]) is None
    assert tonality.tonalidad_desde_acordes([]) is None


def _ton(ventaja, tonica=7, modo="mayor"):
    return {
        "principal": {"tonica_pc": tonica, "modo": modo},
        "ventaja": ventaja,
        "por_tramos": {"acuerdo": None},
    }


def test_sin_acordes_la_tonalidad_es_poco_confiable():
    ton = _ton(ventaja=3.0)
    tonality.evaluar_confianza(ton, None)
    assert ton["confianza"] == "baja"


def test_confianza_alta_cuando_coinciden_los_dos_metodos():
    ton = _ton(ventaja=1.5)
    tonality.evaluar_confianza(ton, (7, "mayor"))
    assert ton["confianza"] == "alta"
    assert ton["segundo_metodo"]["acuerdo"] == "igual"
