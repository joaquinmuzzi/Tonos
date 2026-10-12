"""Pruebas de punta a punta con los modelos reales (tardan ~1 minuto en total)."""

import subprocess
from collections import Counter

import numpy as np
import pytest
import soundfile as sf

from app.analisis import pipeline
from app.analisis.audio import ErrorDeAudio
from tests.sintetico import FS, cancion, guardar_mp4

pytestmark = pytest.mark.lento


@pytest.fixture(scope="module")
def pop_en_sol(tmp_path_factory):
    """MP4 a 120 BPM en 4/4, Sol mayor: G - D - Em - C."""
    y = cancion(120, 4, [("G", False), ("D", False), ("E", True), ("C", False)], compases=24)
    ruta = guardar_mp4(y, tmp_path_factory.mktemp("pop") / "pop en sol.mp4")
    return pipeline.analizar(ruta)


@pytest.fixture(scope="module")
def vals_en_re(tmp_path_factory):
    """MP4 a 150 BPM en 3/4, Re mayor: D - G - A - D."""
    y = cancion(150, 3, [("D", False), ("G", False), ("A", False), ("D", False)], compases=32)
    ruta = guardar_mp4(y, tmp_path_factory.mktemp("vals") / "vals.mp4")
    return pipeline.analizar(ruta)


def _bpm_equivalente(medido, real):
    return any(abs(medido - real * f) <= 0.04 * real * f for f in (1, 2, 0.5))


def test_pop_tempo(pop_en_sol):
    assert _bpm_equivalente(pop_en_sol["tempo"]["bpm"], 120)


def test_pop_compas(pop_en_sol):
    assert pop_en_sol["compas"]["pulsos_por_compas"] in (4, 2)


def test_pop_tonalidad(pop_en_sol):
    p = pop_en_sol["tonalidad"]["principal"]
    assert (p["tonica_pc"], p["modo"]) in [(7, "mayor"), (4, "menor")]  # Sol mayor o su relativa


def test_pop_acordes(pop_en_sol):
    usados = Counter()
    for s in pop_en_sol["acordes"]["segmentos"]:
        if s["es_acorde"]:
            usados[s["americano_simple"]] += s["fin"] - s["inicio"]
    principales = {nombre for nombre, _ in usados.most_common(4)}
    assert principales == {"G", "D", "Em", "C"}


def test_pop_reporte_completo(pop_en_sol):
    assert pop_en_sol["compases"], "debería haber compases"
    assert pop_en_sol["acordes"]["resumen_simple"]
    assert pop_en_sol["tonalidad"]["confianza"] in ("alta", "media", "baja")


def test_vals_tempo(vals_en_re):
    assert _bpm_equivalente(vals_en_re["tempo"]["bpm"], 150)


def test_vals_compas(vals_en_re):
    assert vals_en_re["compas"]["pulsos_por_compas"] in (3, 6)


def test_pop_y_vals_confirmados_por_la_armonia(pop_en_sol, vals_en_re):
    assert pop_en_sol["compas"]["fuente"] == "primeros tiempos"
    assert vals_en_re["compas"]["fuente"] == "primeros tiempos"


@pytest.mark.parametrize(
    ("pulsos_por_compas", "progresion"),
    [
        (5, [("A", True), ("F", False), ("C", False), ("G", False)]),
        (7, [("E", True), ("C", False), ("D", False)]),
    ],
)
def test_compas_irregular_de_punta_a_punta(tmp_path, pulsos_por_compas, progresion):
    """El detector de primeros tiempos falla con 5/4 y 7/4; la repetición de la armonía no."""
    y = cancion(130, pulsos_por_compas, progresion, compases=32)
    resultado = pipeline.analizar(guardar_mp4(y, tmp_path / f"en {pulsos_por_compas}.mp4"))
    compas = resultado["compas"]
    assert compas["lectura"] == f"{pulsos_por_compas}/4"
    assert compas["fuente"] == "periodicidad"
    assert not compas["grilla_aproximada"]
    primeros = resultado["primeros_tiempos"]
    assert primeros[0] == pytest.approx(0.0, abs=0.05)
    assert np.median(np.diff(primeros)) == pytest.approx(pulsos_por_compas * 60 / 130, rel=0.03)


def test_vals_tonalidad(vals_en_re):
    p = vals_en_re["tonalidad"]["principal"]
    assert (p["tonica_pc"], p["modo"]) in [(2, "mayor"), (11, "menor")]


def test_pop_final_sin_huecos(pop_en_sol):
    # Los acordes siguen hasta el final, sin "sin acorde" por relleno de silencio
    segmentos = pop_en_sol["acordes"]["segmentos"]
    duracion = pop_en_sol["archivo"]["duracion"]
    ultimos = [s for s in segmentos if s["fin"] > duracion - 8 and s["inicio"] < duracion - 1.5]
    assert all(s["es_acorde"] for s in ultimos)


def test_archivo_sin_audio(tmp_path):
    ruta = tmp_path / "texto.mp4"
    ruta.write_text("esto no es un video")
    with pytest.raises(ErrorDeAudio):
        pipeline.analizar(ruta)


def _ffmpeg(*argumentos):
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *argumentos], check=True)


def test_archivo_demasiado_largo_se_rechaza_sin_decodificarlo_entero(tmp_path):
    ruta = tmp_path / "largo.mp3"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=1500", "-b:a", "32k", str(ruta))
    with pytest.raises(ErrorDeAudio, match="más de 20 minutos"):
        pipeline.analizar(ruta)


def test_primera_pista_muda_usa_la_segunda(tmp_path):
    musica = tmp_path / "musica.wav"
    sf.write(musica, cancion(120, 4, [("A", True), ("F", False)], compases=8), FS)
    ruta = tmp_path / "dos pistas.mp4"
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-i",
        str(musica),
        "-map",
        "0:a",
        "-map",
        "1:a",
        "-shortest",
        "-c:a",
        "aac",
        str(ruta),
    )
    resultado = pipeline.analizar(ruta)
    assert resultado["archivo"]["pista_de_audio"] == 2
    assert resultado["tempo"]["bpm"]
