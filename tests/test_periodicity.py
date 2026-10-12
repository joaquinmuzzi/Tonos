"""Compás por repetición de la armonía, con canciones sintéticas y pulsos conocidos."""

import librosa
import numpy as np
import pytest

from orfeo.analysis import periodicity, rhythm
from tests.synthetic import FS, cancion

PROGRESIONES = {
    3: [("D", False), ("G", False), ("A", False), ("D", False)],
    4: [("G", False), ("D", False), ("E", True), ("C", False)],
    5: [("A", True), ("F", False), ("C", False), ("G", False)],
    7: [("E", True), ("C", False), ("D", False)],
}


def _sintetica(pulsos_por_compas, bpm=130, compases=48):
    y = cancion(bpm, pulsos_por_compas, PROGRESIONES[pulsos_por_compas], compases=compases)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    pulsos = np.arange(compases * pulsos_por_compas) * 60.0 / bpm
    return y, pulsos


@pytest.mark.parametrize("pulsos_por_compas", [3, 4, 5, 7])
def test_detecta_el_compas_por_repeticion(pulsos_por_compas):
    y, pulsos = _sintetica(pulsos_por_compas)
    envolvente = rhythm.envolvente_de_ataques(y, 22050)
    resumen, _espectro = periodicity.analizar(y, 22050, pulsos, envolvente, rhythm.SALTO)
    assert resumen["ganador"] == pulsos_por_compas
    if pulsos_por_compas in (5, 7):  # los únicos casos en que el método puede imponerse
        assert resumen["margen"] > 0.3


@pytest.mark.parametrize("pulsos_por_compas", [3, 5, 7])
def test_ubica_el_primer_tiempo(pulsos_por_compas):
    y, pulsos = _sintetica(pulsos_por_compas)
    envolvente = rhythm.envolvente_de_ataques(y, 22050)
    _, espectro = periodicity.analizar(y, 22050, pulsos, envolvente, rhythm.SALTO)
    primeros, claridad = periodicity.ubicar_compases(pulsos, pulsos_por_compas, espectro, 22050)
    assert primeros[0] == pytest.approx(0.0)
    assert np.allclose(np.diff(primeros), pulsos_por_compas * 60 / 130)
    assert claridad >= periodicity.CLARIDAD_FASE


def test_acordes_anticipados_no_corren_el_primer_tiempo():
    """Si los acordes entran medio pulso antes, la armonía sola marca el primer tiempo un
    pulso antes de tiempo; los cambios de acorde reconocidos (en el pulso 1) lo corrigen."""
    L, bpm = 7, 105
    y = cancion(bpm, L, PROGRESIONES[7], compases=36, anticipo=0.5)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    pulsos = np.arange(36 * L) * 60.0 / bpm
    envolvente = rhythm.envolvente_de_ataques(y, 22050)
    _, espectro = periodicity.analizar(y, 22050, pulsos, envolvente, rhythm.SALTO)
    cambios = np.zeros(len(pulsos))
    cambios[::L] = 1.0  # donde el reconocedor de acordes marca el cambio
    cambios[0] = 0.0
    primeros, _ = periodicity.ubicar_compases(pulsos, L, espectro, 22050, cambios)
    assert primeros[0] == pytest.approx(0.0)


def test_tramo_corto_sigue_la_cuenta():
    L = 5
    pulsos = np.concatenate(
        [
            np.arange(60) * 0.5,
            30.0 + 0.8 + np.arange(6) * 0.5,  # salto y tramo corto
            33.8 + 0.8 + np.arange(60) * 0.5,
        ]
    )
    espectro = np.random.default_rng(0).random((84, 4000)).astype(np.float32)
    cambios = np.zeros(len(pulsos))
    cambios[::L] = 1.0
    primeros, _ = periodicity.ubicar_compases(pulsos, L, espectro, 22050, cambios)
    cuentas = np.diff(np.searchsorted(pulsos, primeros))
    assert len(primeros) >= 20  # el tramo corto no deja un hueco sin compases
    assert np.all(cuentas <= 2 * L)


def test_cancion_corta_no_se_analiza():
    pulsos = np.arange(40) * 0.5
    assert periodicity.analizar(np.zeros(22050 * 20), 22050, pulsos, np.zeros(2000), rhythm.SALTO) == (
        None,
        None,
    )


def _repeticion(ganador, puntajes, armonia):
    otros = sorted((v for f, v in puntajes.items() if f != ganador), reverse=True)
    return {
        "ganador": ganador,
        "puntajes": puntajes,
        "armonia": armonia,
        "margen": round(puntajes[ganador] - otros[0], 2),
    }


CINCO = _repeticion(5, {3: -0.4, 4: -0.66, 5: 0.36, 7: -0.47}, {3: -0.49, 4: -0.58, 5: 0.91, 7: -0.36})


def test_la_armonia_en_cinco_reemplaza_a_un_conteo_de_cuatro():
    pulsos = np.arange(400) * 0.5
    resultado = rhythm.analizar_compas(pulsos, pulsos[::4], {"tipo": "binaria"}, 120, "alta", CINCO)
    assert resultado["lectura"] == "5/4"
    assert resultado["fuente"] == "periodicidad"
    assert resultado["pulsos_por_compas"] == 5
    assert resultado["conteo_primeros_tiempos"] == 4
    assert resultado["confianza"] == "media"  # ventaja de 1,02 con la armonía a favor
    assert any("se repiten cada 5" in a for a in resultado["avisos"])


def test_evidencia_debil_no_reemplaza_al_conteo():
    debil = _repeticion(5, {3: -0.3, 4: 0.0, 5: 0.4, 7: -0.5}, {3: 0.0, 4: 0.1, 5: 0.2, 7: 0.0})
    pulsos = np.arange(400) * 0.5
    resultado = rhythm.analizar_compas(pulsos, pulsos[::4], {"tipo": "binaria"}, 120, "alta", debil)
    assert resultado["lectura"] == "4/4"
    assert resultado["fuente"] == "primeros tiempos"


def test_sin_la_armonia_a_favor_no_reemplaza():
    contra = _repeticion(5, {3: -0.4, 4: -0.5, 5: 0.6, 7: -0.5}, {3: 0.0, 4: 0.5, 5: 0.1, 7: 0.0})
    pulsos = np.arange(400) * 0.5
    resultado = rhythm.analizar_compas(pulsos, pulsos[::4], {"tipo": "binaria"}, 120, "alta", contra)
    assert resultado["fuente"] == "primeros tiempos"


def test_si_coinciden_sube_la_confianza():
    cuatro = _repeticion(4, {3: -0.4, 4: 0.9, 5: -0.5, 7: -0.4}, {3: -0.3, 4: 1.1, 5: -0.4, 7: -0.3})
    pulsos = np.arange(200) * 0.5
    primeros, i = [], 0
    for n in [4] * 30 + [3, 5] * 5:  # 75 % de los compases cuentan 4: confianza media
        primeros.append(pulsos[i])
        i += n
    resultado = rhythm.analizar_compas(pulsos, np.array(primeros), {"tipo": "binaria"}, 120, "alta", cuatro)
    assert resultado["segundo_metodo"]["confirma"]
    assert resultado["confianza"] == "alta"


def test_entre_tres_y_cuatro_solo_avisa():
    tres = _repeticion(3, {3: 0.9, 4: -0.2, 5: -0.5, 7: -0.5}, {3: 0.9, 4: -0.1, 5: -0.4, 7: -0.4})
    pulsos = np.arange(400) * 0.5
    resultado = rhythm.analizar_compas(pulsos, pulsos[::4], {"tipo": "binaria"}, 120, "alta", tres)
    assert resultado["lectura"] == "4/4"  # el detector distingue bien 3 de 4: no se reemplaza
    assert resultado["confianza"] == "media"  # pero baja la confianza
    assert any("sugiere compases de 3" in a for a in resultado["avisos"])


def test_conteo_imposible_pero_armonia_clara():
    pulsos = np.arange(300) * 0.46
    resultado = rhythm.analizar_compas(pulsos, pulsos, {"tipo": "binaria"}, 130, "alta", CINCO)
    assert resultado["lectura"] == "5/4"
    assert resultado["fuente"] == "periodicidad"
