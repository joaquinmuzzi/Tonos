import numpy as np
import pytest

from orfeo.analysis import rhythm
from tests.synthetic import FS, song


def _beats(bpm, n):
    return np.arange(n) * 60.0 / bpm


def test_beats_per_bar():
    beats = _beats(120, 33)
    downbeats = beats[1::4]  # anacrusa de un pulso, después compases de 4
    assert rhythm.beats_per_bar(beats, downbeats) == [4] * 7


def test_meter_in_four():
    beats = _beats(120, 65)
    result = rhythm.analyze_meter(beats, beats[::4], {"tipo": "binaria"}, 120)
    assert result["pulsos_por_compas"] == 4
    assert result["lectura"] == "4/4"
    assert result["confianza"] == "alta"
    assert result["avisos"] == []


def test_meter_in_three_warns_about_ambiguity():
    beats = _beats(150, 61)
    result = rhythm.analyze_meter(beats, beats[::3], {"tipo": "no clara"}, 150)
    assert result["lectura"] == "3/4"
    assert "6/8" in result["alternativa"]
    assert any("6/8" in a for a in result["avisos"])


def test_fast_swing_reads_as_four_four_swing():
    beats = _beats(200, 65)
    result = rhythm.analyze_meter(beats, beats[::4], {"tipo": "ternaria"}, 200)
    assert result["lectura"] == "4/4 con swing"


def test_slow_ternary_ballad_reads_as_twelve_eight():
    beats = _beats(60, 65)
    result = rhythm.analyze_meter(beats, beats[::4], {"tipo": "ternaria"}, 60)
    assert result["lectura"] == "12/8"


def test_one_beat_per_bar_is_not_reported_as_meter():
    beats = _beats(40, 30)
    result = rhythm.analyze_meter(beats, beats, {"tipo": "ternaria"}, 40)
    assert result["lectura"] is None
    assert result["confianza"] == "baja"


def test_mixed_bar_lengths_lower_confidence():
    beats = _beats(120, 200)
    downbeats, i = [], 0
    for n in [4, 3, 4, 3, 3, 4, 3, 4, 4, 3] * 4:  # 50/50
        downbeats.append(beats[i])
        i += n
    result = rhythm.analyze_meter(beats, np.array(downbeats), {"tipo": "binaria"}, 120)
    assert result["confianza"] == "baja"
    assert len(result["avisos"]) >= 1


def test_tempo_from_beats():
    beats = _beats(96, 100)
    envelope = np.zeros(4000)
    t = rhythm.analyze_tempo(beats, envelope, 22050)
    assert abs(t["bpm"] - 96) < 0.5
    assert t["alternativas"] == {"mitad": 48.0, "doble": 192.0}
    assert t["estable"]
    assert t["regularidad"] == 1.0


@pytest.mark.parametrize("bpm", [123, 128, 133, 140, 170, 174, 180, 193.5])
def test_tempo_has_no_20_ms_grid_error(bpm):
    # Beat This! devuelve los pulsos redondeados a cuadros de 20 ms
    beats = np.round(_beats(bpm, 200) * 50) / 50
    t = rhythm.analyze_tempo(beats, np.zeros(4000), 22050)
    assert abs(t["bpm"] - bpm) < 0.5
    assert t["rango"][0] - 1 <= t["bpm"] <= t["rango"][1] + 1


def test_unify_double_time_section():
    # 105 BPM, con un tramo en el medio donde el detector marcó el doble de pulsos
    normal = _beats(105, 40)
    double = normal[-1] + np.arange(1, 41) * (60 / 210)
    final = double[-1] + np.arange(1, 21) * (60 / 105)
    beats = np.concatenate([normal, double, final])
    downbeats = beats[::4]
    unified, unified_downbeats, info = rhythm.unify_beats(beats, downbeats)
    intervals = np.diff(unified)
    assert np.allclose(intervals, 60 / 105, rtol=0.02)
    assert info["quitados"] == 20
    assert set(unified_downbeats) <= set(unified)


def test_unify_fills_missed_beats():
    beats = np.delete(_beats(120, 40), [10, 20, 21])  # uno y dos pulsos perdidos
    unified, _, info = rhythm.unify_beats(beats, np.array([]))
    assert info["agregados"] == 3
    assert np.allclose(unified, _beats(120, 40))


def test_unify_keeps_a_real_tempo_change():
    beats = np.concatenate([_beats(90, 40), _beats(90, 40)[-1] + np.arange(1, 41) * 60 / 140])
    unified, _, info = rhythm.unify_beats(beats, np.array([]))
    assert info == {"quitados": 0, "agregados": 0}
    assert np.array_equal(unified, beats)


def test_unify_evens_a_mis_tracked_fill():
    # Como en Resident Evil (compás 9): 4 pulsos marcados 0,42 / 0,40 / 0,72 / 0,68 s
    beat = 2.22 / 4
    beats = list(np.arange(20) * beat)
    t = beats[-1]
    for d in (0.42, 0.40, 0.72, 0.68):
        t += d
        beats.append(t)
    beats += list(t + np.arange(1, 21) * beat)
    unified, _, _ = rhythm.unify_beats(np.array(beats), np.array([]))
    assert len(unified) == len(beats)
    assert np.allclose(np.diff(unified), beat, atol=0.01)


def test_unify_evens_fill_with_regular_beat():
    beat = 0.556
    intervals = [1.0] * 20 + [0.79, 1.0, 1.22] + [1.0] * 20
    beats = _from_intervals(intervals, beat)
    unified, _, _info = rhythm.unify_beats(beats, np.array([]))
    assert len(unified) == len(beats)
    assert np.allclose(np.diff(unified), beat, rtol=0.02)


def test_unify_keeps_a_real_shift():
    # Un intervalo de 1,46 pulsos (un calderón o un corrimiento de medio pulso) no se toca
    beats = np.concatenate([np.arange(20) * 0.56, 19 * 0.56 + 0.82 + np.arange(20) * 0.56])
    unified, _, info = rhythm.unify_beats(beats, np.array([]))
    assert np.array_equal(unified, beats)
    assert info == {"quitados": 0, "agregados": 0}


def test_unify_fills_gap_next_to_short_bar():
    # Un intervalo de 1,5 pulsos (compás de 7/8, real) seguido de un pulso perdido (2,0)
    beat = 0.56
    intervals = [1.0] * 15 + [1.5, 2.0] + [1.0] * 15
    beats = np.concatenate([[0.0], np.cumsum(np.array(intervals) * beat)])
    unified, _, info = rhythm.unify_beats(beats, np.array([]))
    relative_intervals = np.round(np.diff(unified) / beat, 2).tolist()
    assert relative_intervals == [1.0] * 15 + [1.5, 1.0, 1.0] + [1.0] * 15
    assert info["agregados"] == 1


def _from_intervals(intervals, beat=0.5):
    return np.concatenate([[0.0], np.cumsum(np.array(intervals, dtype=float) * beat)])


@pytest.mark.parametrize(
    ("name", "intervals"),
    [
        ("ritardando de un compás", [1.0] * 16 + [1.2] * 4 + [1.0] * 16),
        ("dos pulsos más lentos", [1.0] * 16 + [1.4] * 2 + [1.0] * 16),
        ("accelerando de un compás", [1.0] * 16 + [0.8] * 4 + [1.0] * 16),
        ("intro libre", [1.3, 1.4, 1.2] + [1.0] * 30),
        ("ritardando final", [1.0] * 30 + [1.2, 1.4, 1.6, 1.8]),
    ],
)
def test_unify_respects_real_tempo_changes(name, intervals):
    beats = _from_intervals(intervals)
    unified, _, info = rhythm.unify_beats(beats, beats[::4])
    assert np.allclose(unified, beats), name
    assert info == {"quitados": 0, "agregados": 0}


@pytest.mark.parametrize("gap", [2.28, 3.35, 4.4, 6.4, 8.35])
def test_unify_fills_gaps_when_band_returns_late(gap):
    beats = _from_intervals([1.0] * 16 + [gap] + [1.0] * 16)
    _unified, _, info = rhythm.unify_beats(beats, np.array([]))
    assert info["agregados"] == round(gap) - 1


@pytest.mark.parametrize("eighth", [0.6, 0.64, 0.67, 0.75])
def test_unify_double_time_swing_keeps_the_grid(eighth):
    # Tramo donde el detector marca también la corchea del swing
    quarter_notes = np.arange(64) * 0.5
    swing = quarter_notes[16:32] + eighth * 0.5
    beats = np.sort(np.concatenate([quarter_notes, swing]))
    unified, downbeats, _ = rhythm.unify_beats(beats, quarter_notes[::4])
    assert np.allclose(unified, quarter_notes)
    assert np.allclose(downbeats, quarter_notes[::4])


def _bars(*lengths, start=0):
    """Pulsos cada 0,5 s y primeros tiempos que dejan compases de esos largos."""
    total = start + sum(lengths) + 4
    beats = np.arange(total) * 0.5
    indices = np.cumsum((start, *lengths))
    return beats, beats[indices]


@pytest.mark.parametrize(
    ("lengths", "expected_lengths"),
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
def test_regularize_bars(lengths, expected_lengths):
    beats, downbeats = _bars(*lengths)
    new, _ = rhythm.regularize_bars(beats, downbeats, 4)
    assert np.diff(np.searchsorted(beats, new)).tolist() == expected_lengths


def test_regularize_keeps_four_beat_bars_in_waltz():
    beats, downbeats = _bars(3, 3, 4, 4, 4, 3, 3)
    new, regrouped = rhythm.regularize_bars(beats, downbeats, 3)
    assert np.diff(np.searchsorted(beats, new)).tolist() == [3, 3, 4, 4, 4, 3, 3]
    assert regrouped == 0


def test_regularize_does_nothing_without_meter():
    beats, downbeats = _bars(3, 1, 4)
    new, regrouped = rhythm.regularize_bars(beats, downbeats, None)
    assert np.array_equal(new, downbeats)
    assert regrouped == 0


def test_bar_grid_with_pickup():
    beats = _beats(120, 17)
    bar_cells = rhythm.bar_grid(beats, beats[1::4], duration=9.0)
    assert bar_cells[0]["numero"] == 0
    assert bar_cells[0]["etiqueta"] == "anacrusa"
    assert bar_cells[1]["numero"] == 1
    assert abs(bar_cells[1]["inicio"] - 0.5) < 1e-9
    assert bar_cells[1]["etiqueta"] == "compás 1"
    assert abs(bar_cells[-1]["fin"] - 9.0) < 1e-9


def test_intro_without_beats_appears_in_grid():
    beats = 20 + _beats(120, 40)  # la batería entra a los 20 s
    bar_cells = rhythm.bar_grid(beats, beats[::4], duration=40.0)
    assert bar_cells[0] == {"numero": 0, "etiqueta": "intro", "inicio": 0.0, "fin": 20.0}


def test_without_downbeats_groups_four_beats():
    beats = _beats(120, 33)
    bar_cells = rhythm.bar_grid(beats, np.array([]), duration=17.0)
    assert bar_cells[0]["etiqueta"] == "tramo 1"
    assert abs(bar_cells[1]["inicio"] - 2.0) < 1e-9


def test_without_beats_groups_every_four_seconds():
    bar_cells = rhythm.bar_grid(np.array([]), np.array([]), duration=10.0)
    assert [c["inicio"] for c in bar_cells] == [0.0, 4.0, 8.0]


def test_meter_is_not_more_confident_than_beats():
    beats = _beats(120, 65)
    result = rhythm.analyze_meter(beats, beats[::4], {"tipo": "binaria"}, 120, "baja")
    assert result["confianza"] == "baja"


def test_unclear_subdivision_without_onsets():
    # Envolvente sin ataques entre pulsos (acordes sostenidos): no debe inventar subdivisión
    rng = np.random.default_rng(3)
    envelope = 1 + 0.05 * rng.random(int(60 * 22050 / rhythm.HOP_LENGTH))
    beats = _beats(60, 55)
    assert rhythm.analyze_subdivision(beats, envelope, 22050)["tipo"] == "no clara"


def _subdivision(sub):
    import librosa

    y = song(100, 4, [("C", False)], bars=16, subdivision=sub)
    y = librosa.resample(y, orig_sr=FS, target_sr=22050)
    beats = np.arange(0, 16 * 4) * 0.6
    env = rhythm.onset_envelope(y, 22050)
    return rhythm.analyze_subdivision(beats, env, 22050)["tipo"]


def test_binary_subdivision():
    assert _subdivision(2) == "binaria"


def test_ternary_subdivision():
    assert _subdivision(3) == "ternaria"
