"""Compás por repetición de la armonía, con canciones sintéticas y pulsos conocidos."""

import librosa
import numpy as np
import pytest

from orfeo.analysis import periodicity, rhythm
from tests.synthetic import FS, song

PROGRESSIONS = {
    3: [("D", False), ("G", False), ("A", False), ("D", False)],
    4: [("G", False), ("D", False), ("E", True), ("C", False)],
    5: [("A", True), ("F", False), ("C", False), ("G", False)],
    7: [("E", True), ("C", False), ("D", False)],
}


def _synthetic(beats_per_bar, bpm=130, bars=48):
    y = song(bpm, beats_per_bar, PROGRESSIONS[beats_per_bar], bars=bars)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    beats = np.arange(bars * beats_per_bar) * 60.0 / bpm
    return y, beats


@pytest.mark.parametrize("beats_per_bar", [3, 4, 5, 7])
def test_detects_meter_from_repetition(beats_per_bar):
    y, beats = _synthetic(beats_per_bar)
    envelope = rhythm.onset_envelope(y, 22050)
    summary, _spectrum = periodicity.analyze(y, 22050, beats, envelope, rhythm.HOP_LENGTH)
    assert summary["ganador"] == beats_per_bar
    if beats_per_bar in (5, 7):  # los únicos casos en que el método puede imponerse
        assert summary["margen"] > 0.3


@pytest.mark.parametrize("beats_per_bar", [3, 5, 7])
def test_locates_the_downbeat(beats_per_bar):
    y, beats = _synthetic(beats_per_bar)
    envelope = rhythm.onset_envelope(y, 22050)
    _, spectrum = periodicity.analyze(y, 22050, beats, envelope, rhythm.HOP_LENGTH)
    downbeats, clarity = periodicity.locate_bars(beats, beats_per_bar, spectrum, 22050)
    assert downbeats[0] == pytest.approx(0.0)
    assert np.allclose(np.diff(downbeats), beats_per_bar * 60 / 130)
    assert clarity >= periodicity.PHASE_CLARITY_THRESHOLD


def test_anticipated_chords_do_not_shift_the_downbeat():
    """Si los acordes entran medio pulso antes, la armonía sola marca el primer tiempo un
    pulso antes de tiempo; los cambios de acorde reconocidos (en el pulso 1) lo corrigen."""
    L, bpm = 7, 105
    y = song(bpm, L, PROGRESSIONS[7], bars=36, anticipation=0.5)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    beats = np.arange(36 * L) * 60.0 / bpm
    envelope = rhythm.onset_envelope(y, 22050)
    _, spectrum = periodicity.analyze(y, 22050, beats, envelope, rhythm.HOP_LENGTH)
    changes = np.zeros(len(beats))
    changes[::L] = 1.0  # donde el reconocedor de acordes marca el cambio
    changes[0] = 0.0
    downbeats, _ = periodicity.locate_bars(beats, L, spectrum, 22050, changes)
    assert downbeats[0] == pytest.approx(0.0)


def test_short_stretch_continues_the_count():
    L = 5
    beats = np.concatenate(
        [
            np.arange(60) * 0.5,
            30.0 + 0.8 + np.arange(6) * 0.5,  # salto y tramo corto
            33.8 + 0.8 + np.arange(60) * 0.5,
        ]
    )
    spectrum = np.random.default_rng(0).random((84, 4000)).astype(np.float32)
    changes = np.zeros(len(beats))
    changes[::L] = 1.0
    downbeats, _ = periodicity.locate_bars(beats, L, spectrum, 22050, changes)
    bar_lengths = np.diff(np.searchsorted(beats, downbeats))
    assert len(downbeats) >= 20  # el tramo corto no deja un hueco sin compases
    assert np.all(bar_lengths <= 2 * L)


def test_short_song_is_not_analyzed():
    beats = np.arange(40) * 0.5
    assert periodicity.analyze(np.zeros(22050 * 20), 22050, beats, np.zeros(2000), rhythm.HOP_LENGTH) == (
        None,
        None,
    )


def _repetition(winner, scores, harmony):
    others = sorted((v for f, v in scores.items() if f != winner), reverse=True)
    return {
        "ganador": winner,
        "puntajes": scores,
        "armonia": harmony,
        "margen": round(scores[winner] - others[0], 2),
    }


FIVE = _repetition(5, {3: -0.4, 4: -0.66, 5: 0.36, 7: -0.47}, {3: -0.49, 4: -0.58, 5: 0.91, 7: -0.36})


def test_harmony_in_five_replaces_count_of_four():
    beats = np.arange(400) * 0.5
    result = rhythm.analyze_meter(beats, beats[::4], {"tipo": "binaria"}, 120, "alta", FIVE)
    assert result["lectura"] == "5/4"
    assert result["fuente"] == "periodicidad"
    assert result["pulsos_por_compas"] == 5
    assert result["conteo_primeros_tiempos"] == 4
    assert result["confianza"] == "media"  # ventaja de 1,02 con la armonía a favor
    assert any("se repiten cada 5" in a for a in result["avisos"])


def test_weak_evidence_does_not_replace_count():
    weak = _repetition(5, {3: -0.3, 4: 0.0, 5: 0.4, 7: -0.5}, {3: 0.0, 4: 0.1, 5: 0.2, 7: 0.0})
    beats = np.arange(400) * 0.5
    result = rhythm.analyze_meter(beats, beats[::4], {"tipo": "binaria"}, 120, "alta", weak)
    assert result["lectura"] == "4/4"
    assert result["fuente"] == "primeros tiempos"


def test_does_not_replace_without_harmony_support():
    against = _repetition(5, {3: -0.4, 4: -0.5, 5: 0.6, 7: -0.5}, {3: 0.0, 4: 0.5, 5: 0.1, 7: 0.0})
    beats = np.arange(400) * 0.5
    result = rhythm.analyze_meter(beats, beats[::4], {"tipo": "binaria"}, 120, "alta", against)
    assert result["fuente"] == "primeros tiempos"


def test_agreement_raises_confidence():
    four = _repetition(4, {3: -0.4, 4: 0.9, 5: -0.5, 7: -0.4}, {3: -0.3, 4: 1.1, 5: -0.4, 7: -0.3})
    beats = np.arange(200) * 0.5
    downbeats, i = [], 0
    for n in [4] * 30 + [3, 5] * 5:  # 75 % de los compases cuentan 4: confianza media
        downbeats.append(beats[i])
        i += n
    result = rhythm.analyze_meter(beats, np.array(downbeats), {"tipo": "binaria"}, 120, "alta", four)
    assert result["segundo_metodo"]["confirma"]
    assert result["confianza"] == "alta"


def test_between_three_and_four_only_warns():
    three = _repetition(3, {3: 0.9, 4: -0.2, 5: -0.5, 7: -0.5}, {3: 0.9, 4: -0.1, 5: -0.4, 7: -0.4})
    beats = np.arange(400) * 0.5
    result = rhythm.analyze_meter(beats, beats[::4], {"tipo": "binaria"}, 120, "alta", three)
    assert result["lectura"] == "4/4"  # el detector distingue bien 3 de 4: no se reemplaza
    assert result["confianza"] == "media"  # pero baja la confianza
    assert any("sugiere compases de 3" in a for a in result["avisos"])


def test_invalid_count_but_clear_harmony():
    beats = np.arange(300) * 0.46
    result = rhythm.analyze_meter(beats, beats, {"tipo": "binaria"}, 130, "alta", FIVE)
    assert result["lectura"] == "5/4"
    assert result["fuente"] == "periodicidad"
