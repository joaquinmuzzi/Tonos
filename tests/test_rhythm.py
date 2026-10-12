import numpy as np
import pytest

from orfeo.analysis import rhythm
from tests.synthetic import FS, cancion


def _pulsos(bpm, n):
    return np.arange(n) * 60.0 / bpm


def test_pulsos_por_compas():
    pulsos = _pulsos(120, 33)
    primeros = pulsos[1::4]  # anacrusa de un pulso, después compases de 4
    assert rhythm.pulsos_por_compas(pulsos, primeros) == [4] * 7


def test_compas_en_cuatro():
    pulsos = _pulsos(120, 65)
    resultado = rhythm.analizar_compas(pulsos, pulsos[::4], {"tipo": "binaria"}, 120)
    assert resultado["pulsos_por_compas"] == 4
    assert resultado["lectura"] == "4/4"
    assert resultado["confianza"] == "alta"
    assert resultado["avisos"] == []


def test_compas_en_tres_avisa_de_la_ambiguedad():
    pulsos = _pulsos(150, 61)
    resultado = rhythm.analizar_compas(pulsos, pulsos[::3], {"tipo": "no clara"}, 150)
    assert resultado["lectura"] == "3/4"
    assert "6/8" in resultado["alternativa"]
    assert any("6/8" in a for a in resultado["avisos"])


def test_swing_rapido_se_lee_como_cuatro_con_swing():
    pulsos = _pulsos(200, 65)
    resultado = rhythm.analizar_compas(pulsos, pulsos[::4], {"tipo": "ternaria"}, 200)
    assert resultado["lectura"] == "4/4 con swing"


def test_balada_lenta_ternaria_se_lee_como_doce_octavos():
    pulsos = _pulsos(60, 65)
    resultado = rhythm.analizar_compas(pulsos, pulsos[::4], {"tipo": "ternaria"}, 60)
    assert resultado["lectura"] == "12/8"


def test_un_pulso_por_compas_no_se_informa_como_compas():
    pulsos = _pulsos(40, 30)
    resultado = rhythm.analizar_compas(pulsos, pulsos, {"tipo": "ternaria"}, 40)
    assert resultado["lectura"] is None
    assert resultado["confianza"] == "baja"


def test_compas_mezclado_baja_la_confianza():
    pulsos = _pulsos(120, 200)
    primeros, i = [], 0
    for n in [4, 3, 4, 3, 3, 4, 3, 4, 4, 3] * 4:  # 50/50
        primeros.append(pulsos[i])
        i += n
    resultado = rhythm.analizar_compas(pulsos, np.array(primeros), {"tipo": "binaria"}, 120)
    assert resultado["confianza"] == "baja"
    assert len(resultado["avisos"]) >= 1


def test_tempo_desde_pulsos():
    pulsos = _pulsos(96, 100)
    envolvente = np.zeros(4000)
    t = rhythm.analizar_tempo(pulsos, envolvente, 22050)
    assert abs(t["bpm"] - 96) < 0.5
    assert t["alternativas"] == {"mitad": 48.0, "doble": 192.0}
    assert t["estable"]
    assert t["regularidad"] == 1.0


@pytest.mark.parametrize("bpm", [123, 128, 133, 140, 170, 174, 180, 193.5])
def test_tempo_sin_error_por_la_grilla_de_20_ms(bpm):
    # Beat This! devuelve los pulsos redondeados a cuadros de 20 ms
    pulsos = np.round(_pulsos(bpm, 200) * 50) / 50
    t = rhythm.analizar_tempo(pulsos, np.zeros(4000), 22050)
    assert abs(t["bpm"] - bpm) < 0.5
    assert t["rango"][0] - 1 <= t["bpm"] <= t["rango"][1] + 1


def test_unificar_tramo_al_doble():
    # 105 BPM, con un tramo en el medio donde el detector marcó el doble de pulsos
    normal = _pulsos(105, 40)
    doble = normal[-1] + np.arange(1, 41) * (60 / 210)
    final = doble[-1] + np.arange(1, 21) * (60 / 105)
    pulsos = np.concatenate([normal, doble, final])
    primeros = pulsos[::4]
    unificados, primeros_u, info = rhythm.unificar_pulsos(pulsos, primeros)
    intervalos = np.diff(unificados)
    assert np.allclose(intervalos, 60 / 105, rtol=0.02)
    assert info["quitados"] == 20
    assert set(primeros_u) <= set(unificados)


def test_unificar_rellena_pulsos_perdidos():
    pulsos = np.delete(_pulsos(120, 40), [10, 20, 21])  # uno y dos pulsos perdidos
    unificados, _, info = rhythm.unificar_pulsos(pulsos, np.array([]))
    assert info["agregados"] == 3
    assert np.allclose(unificados, _pulsos(120, 40))


def test_unificar_no_toca_un_cambio_de_tempo_real():
    pulsos = np.concatenate([_pulsos(90, 40), _pulsos(90, 40)[-1] + np.arange(1, 41) * 60 / 140])
    unificados, _, info = rhythm.unificar_pulsos(pulsos, np.array([]))
    assert info == {"quitados": 0, "agregados": 0}
    assert np.array_equal(unificados, pulsos)


def test_unificar_reparte_un_tramo_desparejo():
    # Como en Resident Evil (compás 9): 4 pulsos marcados 0,42 / 0,40 / 0,72 / 0,68 s
    pulso = 2.22 / 4
    pulsos = list(np.arange(20) * pulso)
    t = pulsos[-1]
    for d in (0.42, 0.40, 0.72, 0.68):
        t += d
        pulsos.append(t)
    pulsos += list(t + np.arange(1, 21) * pulso)
    unificados, _, _ = rhythm.unificar_pulsos(np.array(pulsos), np.array([]))
    assert len(unificados) == len(pulsos)
    assert np.allclose(np.diff(unificados), pulso, atol=0.01)


def test_unificar_reparte_un_redoble_con_un_pulso_normal_en_medio():
    pulso = 0.556
    intervalos = [1.0] * 20 + [0.79, 1.0, 1.22] + [1.0] * 20
    pulsos = _desde_intervalos(intervalos, pulso)
    unificados, _, _info = rhythm.unificar_pulsos(pulsos, np.array([]))
    assert len(unificados) == len(pulsos)
    assert np.allclose(np.diff(unificados), pulso, rtol=0.02)


def test_unificar_no_reparte_un_corrimiento_real():
    # Un intervalo de 1,46 pulsos (un calderón o un corrimiento de medio pulso) no se toca
    pulsos = np.concatenate([np.arange(20) * 0.56, 19 * 0.56 + 0.82 + np.arange(20) * 0.56])
    unificados, _, info = rhythm.unificar_pulsos(pulsos, np.array([]))
    assert np.array_equal(unificados, pulsos)
    assert info == {"quitados": 0, "agregados": 0}


def test_unificar_rellena_un_hueco_junto_a_un_compas_mas_corto():
    # Un intervalo de 1,5 pulsos (compás de 7/8, real) seguido de un pulso perdido (2,0)
    pulso = 0.56
    intervalos = [1.0] * 15 + [1.5, 2.0] + [1.0] * 15
    pulsos = np.concatenate([[0.0], np.cumsum(np.array(intervalos) * pulso)])
    unificados, _, info = rhythm.unificar_pulsos(pulsos, np.array([]))
    relativos = np.round(np.diff(unificados) / pulso, 2).tolist()
    assert relativos == [1.0] * 15 + [1.5, 1.0, 1.0] + [1.0] * 15
    assert info["agregados"] == 1


def _desde_intervalos(intervalos, pulso=0.5):
    return np.concatenate([[0.0], np.cumsum(np.array(intervalos, dtype=float) * pulso)])


@pytest.mark.parametrize(
    ("nombre", "intervalos"),
    [
        ("ritardando de un compás", [1.0] * 16 + [1.2] * 4 + [1.0] * 16),
        ("dos pulsos más lentos", [1.0] * 16 + [1.4] * 2 + [1.0] * 16),
        ("accelerando de un compás", [1.0] * 16 + [0.8] * 4 + [1.0] * 16),
        ("intro libre", [1.3, 1.4, 1.2] + [1.0] * 30),
        ("ritardando final", [1.0] * 30 + [1.2, 1.4, 1.6, 1.8]),
    ],
)
def test_unificar_respeta_los_cambios_de_tempo_reales(nombre, intervalos):
    pulsos = _desde_intervalos(intervalos)
    unificados, _, info = rhythm.unificar_pulsos(pulsos, pulsos[::4])
    assert np.allclose(unificados, pulsos), nombre
    assert info == {"quitados": 0, "agregados": 0}


@pytest.mark.parametrize("hueco", [2.28, 3.35, 4.4, 6.4, 8.35])
def test_unificar_rellena_huecos_con_la_banda_un_poco_tarde(hueco):
    pulsos = _desde_intervalos([1.0] * 16 + [hueco] + [1.0] * 16)
    _unificados, _, info = rhythm.unificar_pulsos(pulsos, np.array([]))
    assert info["agregados"] == round(hueco) - 1


@pytest.mark.parametrize("corchea", [0.6, 0.64, 0.67, 0.75])
def test_unificar_con_swing_al_doble_no_corre_la_grilla(corchea):
    # Tramo donde el detector marca también la corchea del swing
    negras = np.arange(64) * 0.5
    swing = negras[16:32] + corchea * 0.5
    pulsos = np.sort(np.concatenate([negras, swing]))
    unificados, primeros, _ = rhythm.unificar_pulsos(pulsos, negras[::4])
    assert np.allclose(unificados, negras)
    assert np.allclose(primeros, negras[::4])


def _compases(*largos, inicio=0):
    """Pulsos cada 0,5 s y primeros tiempos que dejan compases de esos largos."""
    total = inicio + sum(largos) + 4
    pulsos = np.arange(total) * 0.5
    indices = np.cumsum((inicio, *largos))
    return pulsos, pulsos[indices]


@pytest.mark.parametrize(
    ("largos", "esperados"),
    [
        ((4, 4, 3, 1, 4, 4), [4, 4, 4, 4, 4]),  # Resident Evil: 3 + 1
        ((4, 1, 3, 4), [4, 4, 4]),  # 1 + 3
        ((4, 3, 5, 4), [4, 4, 4, 4]),  # primer tiempo corrido: 3 + 5
        ((4, 8, 4), [4, 4, 4, 4]),  # primer tiempo perdido
        ((4, 2, 2, 4), [4, 4, 4]),
        ((4, 4, 3, 4, 4), [4, 4, 3, 4, 4]),  # un compás de 3 aislado puede ser real
        ((4, 3, 3, 4), [4, 3, 3, 4]),  # 6 no es múltiplo de 4: no se toca
        ((4, 3, 3, 2, 4), [4, 4, 4, 4]),  # 3+3+2 con un compás de 2: error
        ((4, 4, 3, 3, 3, 3, 4), [4, 4, 3, 3, 3, 3, 4]),  # puente real en 3/4
        ((4, 5, 5, 5, 5, 4), [4, 5, 5, 5, 5, 4]),  # sección real en 5/4
        ((4, 5, 7, 4), [4, 5, 7, 4]),  # suman 12: más de dos compases
    ],
)
def test_regularizar_compases(largos, esperados):
    pulsos, primeros = _compases(*largos)
    nuevos, _ = rhythm.regularizar_compases(pulsos, primeros, 4)
    assert np.diff(np.searchsorted(pulsos, nuevos)).tolist() == esperados


def test_regularizar_respeta_compases_de_4_en_un_vals():
    pulsos, primeros = _compases(3, 3, 4, 4, 4, 3, 3)
    nuevos, rearmados = rhythm.regularizar_compases(pulsos, primeros, 3)
    assert np.diff(np.searchsorted(pulsos, nuevos)).tolist() == [3, 3, 4, 4, 4, 3, 3]
    assert rearmados == 0


def test_regularizar_no_hace_nada_sin_compas():
    pulsos, primeros = _compases(3, 1, 4)
    nuevos, rearmados = rhythm.regularizar_compases(pulsos, primeros, None)
    assert np.array_equal(nuevos, primeros)
    assert rearmados == 0


def test_compases_con_anacrusa():
    pulsos = _pulsos(120, 17)
    lista = rhythm.compases(pulsos, pulsos[1::4], duracion=9.0)
    assert lista[0]["numero"] == 0
    assert lista[0]["etiqueta"] == "anacrusa"
    assert lista[1]["numero"] == 1
    assert abs(lista[1]["inicio"] - 0.5) < 1e-9
    assert lista[1]["etiqueta"] == "compás 1"
    assert abs(lista[-1]["fin"] - 9.0) < 1e-9


def test_intro_sin_pulsos_aparece_en_la_grilla():
    pulsos = 20 + _pulsos(120, 40)  # la batería entra a los 20 s
    lista = rhythm.compases(pulsos, pulsos[::4], duracion=40.0)
    assert lista[0] == {"numero": 0, "etiqueta": "intro", "inicio": 0.0, "fin": 20.0}


def test_sin_primeros_tiempos_se_agrupa_de_a_cuatro_pulsos():
    pulsos = _pulsos(120, 33)
    lista = rhythm.compases(pulsos, np.array([]), duracion=17.0)
    assert lista[0]["etiqueta"] == "tramo 1"
    assert abs(lista[1]["inicio"] - 2.0) < 1e-9


def test_sin_pulsos_se_agrupa_cada_cuatro_segundos():
    lista = rhythm.compases(np.array([]), np.array([]), duracion=10.0)
    assert [c["inicio"] for c in lista] == [0.0, 4.0, 8.0]


def test_compas_no_es_mas_seguro_que_el_pulso():
    pulsos = _pulsos(120, 65)
    resultado = rhythm.analizar_compas(pulsos, pulsos[::4], {"tipo": "binaria"}, 120, "baja")
    assert resultado["confianza"] == "baja"


def test_subdivision_no_clara_sin_ataques():
    # Envolvente sin ataques entre pulsos (acordes sostenidos): no debe inventar subdivisión
    rng = np.random.default_rng(3)
    envolvente = 1 + 0.05 * rng.random(int(60 * 22050 / rhythm.SALTO))
    pulsos = _pulsos(60, 55)
    assert rhythm.analizar_subdivision(pulsos, envolvente, 22050)["tipo"] == "no clara"


def _subdivision(sub):
    import librosa

    y = cancion(100, 4, [("C", False)], compases=16, subdivision=sub)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    pulsos = np.arange(0, 16 * 4) * 0.6
    env = rhythm.envolvente_de_ataques(y, 22050)
    return rhythm.analizar_subdivision(pulsos, env, 22050)["tipo"]


def test_subdivision_binaria():
    assert _subdivision(2) == "binaria"


def test_subdivision_ternaria():
    assert _subdivision(3) == "ternaria"
