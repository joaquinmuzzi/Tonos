"""Pruebas de punta a punta con los modelos reales (tardan ~1 minuto en total)."""

import subprocess
from collections import Counter

import numpy as np
import pytest
import soundfile as sf

from orfeo.analysis import pipeline
from orfeo.analysis.audio import AudioError
from tests.synthetic import FS, save_mp4, song

pytestmark = pytest.mark.lento


@pytest.fixture(scope="module")
def pop_in_g(tmp_path_factory):
    """MP4 a 120 BPM en 4/4, Sol mayor: G - D - Em - C."""
    y = song(120, 4, [("G", False), ("D", False), ("E", True), ("C", False)], bars=24)
    path = save_mp4(y, tmp_path_factory.mktemp("pop") / "pop en sol.mp4")
    return pipeline.analyze(path)


@pytest.fixture(scope="module")
def waltz_in_d(tmp_path_factory):
    """MP4 a 150 BPM en 3/4, Re mayor: D - G - A - D."""
    y = song(150, 3, [("D", False), ("G", False), ("A", False), ("D", False)], bars=32)
    path = save_mp4(y, tmp_path_factory.mktemp("vals") / "vals.mp4")
    return pipeline.analyze(path)


def _bpm_equivalent(measured, real):
    return any(abs(measured - real * f) <= 0.04 * real * f for f in (1, 2, 0.5))


def test_pop_tempo(pop_in_g):
    assert _bpm_equivalent(pop_in_g["tempo"]["bpm"], 120)


def test_pop_meter(pop_in_g):
    assert pop_in_g["compas"]["pulsos_por_compas"] in (4, 2)


def test_pop_key(pop_in_g):
    p = pop_in_g["tonalidad"]["principal"]
    assert (p["tonica_pc"], p["modo"]) in [(7, "mayor"), (4, "menor")]  # Sol mayor o su relativa


def test_pop_chords(pop_in_g):
    used = Counter()
    for s in pop_in_g["acordes"]["segmentos"]:
        if s["es_acorde"]:
            used[s["americano_simple"]] += s["fin"] - s["inicio"]
    top_chords = {name for name, _ in used.most_common(4)}
    assert top_chords == {"G", "D", "Em", "C"}


def test_pop_report_is_complete(pop_in_g):
    assert pop_in_g["compases"], "debería haber compases"
    assert pop_in_g["acordes"]["resumen_simple"]
    assert pop_in_g["tonalidad"]["confianza"] in ("alta", "media", "baja")


def test_waltz_tempo(waltz_in_d):
    assert _bpm_equivalent(waltz_in_d["tempo"]["bpm"], 150)


def test_waltz_meter(waltz_in_d):
    assert waltz_in_d["compas"]["pulsos_por_compas"] in (3, 6)


def test_pop_and_waltz_confirmed_by_harmony(pop_in_g, waltz_in_d):
    assert pop_in_g["compas"]["fuente"] == "primeros tiempos"
    assert waltz_in_d["compas"]["fuente"] == "primeros tiempos"


@pytest.mark.parametrize(
    ("beats_per_bar", "progression"),
    [
        (5, [("A", True), ("F", False), ("C", False), ("G", False)]),
        (7, [("E", True), ("C", False), ("D", False)]),
    ],
)
def test_odd_meter_end_to_end(tmp_path, beats_per_bar, progression):
    """El detector de primeros tiempos falla con 5/4 y 7/4; la repetición de la armonía no."""
    y = song(130, beats_per_bar, progression, bars=32)
    result = pipeline.analyze(save_mp4(y, tmp_path / f"en {beats_per_bar}.mp4"))
    meter = result["compas"]
    assert meter["lectura"] == f"{beats_per_bar}/4"
    assert meter["fuente"] == "periodicidad"
    assert not meter["grilla_aproximada"]
    downbeats = result["primeros_tiempos"]
    assert downbeats[0] == pytest.approx(0.0, abs=0.05)
    assert np.median(np.diff(downbeats)) == pytest.approx(beats_per_bar * 60 / 130, rel=0.03)


def test_waltz_key(waltz_in_d):
    p = waltz_in_d["tonalidad"]["principal"]
    assert (p["tonica_pc"], p["modo"]) in [(2, "mayor"), (11, "menor")]


def test_pop_ending_has_no_gaps(pop_in_g):
    # Los acordes siguen hasta el final, sin "sin acorde" por relleno de silencio
    segments = pop_in_g["acordes"]["segmentos"]
    duration = pop_in_g["archivo"]["duracion"]
    last_segments = [s for s in segments if s["fin"] > duration - 8 and s["inicio"] < duration - 1.5]
    assert all(s["es_acorde"] for s in last_segments)


def test_file_without_audio(tmp_path):
    path = tmp_path / "texto.mp4"
    path.write_text("esto no es un video")
    with pytest.raises(AudioError):
        pipeline.analyze(path)


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-y", *args], check=True)


def test_too_long_file_is_rejected_early(tmp_path):
    path = tmp_path / "largo.mp3"
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=220:duration=1500", "-b:a", "32k", str(path))
    with pytest.raises(AudioError, match="más de 20 minutos"):
        pipeline.analyze(path)


def test_silent_first_track_uses_the_second(tmp_path):
    music = tmp_path / "musica.wav"
    sf.write(music, song(120, 4, [("A", True), ("F", False)], bars=8), FS)
    path = tmp_path / "dos pistas.mp4"
    _ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-i",
        str(music),
        "-map",
        "0:a",
        "-map",
        "1:a",
        "-shortest",
        "-c:a",
        "aac",
        str(path),
    )
    result = pipeline.analyze(path)
    assert result["archivo"]["pista_de_audio"] == 2
    assert result["tempo"]["bpm"]
