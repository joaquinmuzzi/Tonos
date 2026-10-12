"""Segundo método para el compás: ¿cada cuántos pulsos se repite la música?

El detector de primeros tiempos (Beat This!) se entrenó casi solo con música en 4/4 y tiende
a forzar compases de 4 aunque la canción esté en 5/4 o 7/4. Este método no usa ese detector:
mide, pulso por pulso, cuánto se parece la música a sí misma L pulsos después (armonía, bajo
y acentos) y busca qué familia de compases explica mejor las repeticiones:

    3 -> 3, 6, 9, 12...   4 -> 4, 8, 12, 16...   5 -> 5, 10, 15...   7 -> 7, 14, 21...

También ubica dónde empieza cada compás, a partir de los cambios de armonía (sin batería).
"""

from __future__ import annotations

import itertools
from collections import Counter

import librosa
import numpy as np

FAMILIES = {
    3: (3, 6, 9, 12, 15, 18, 21, 24, 27),
    4: (4, 8, 12, 16, 20, 24, 28),
    5: (5, 10, 15, 20, 25),
    7: (7, 14, 21, 28),
}
MAX_LAG = 30  # en pulsos
WEIGHTS = {"armonia": 0.5, "bajo": 0.25, "ataques": 0.25}
CQT_HOP = 512
PHASE_CLARITY_THRESHOLD = 1.0  # por debajo, la grilla de compases se informa como aproximada

# Un desfase compartido por dos familias (12 = 3 y 4) cuenta la mitad para cada una
_SHARED = Counter(L for lags in FAMILIES.values() for L in lags)


def _spectrum(signal: np.ndarray, sr: int) -> np.ndarray:
    """Transformada de Q constante: 7 octavas desde Do1, un bin por semitono."""
    cqt = librosa.cqt(signal, sr=sr, hop_length=CQT_HOP, fmin=librosa.note_to_hz("C1"), n_bins=84)
    return np.abs(cqt).astype(np.float32)


def _per_beat(x: np.ndarray, frames: np.ndarray, start: float = 0.0, end: float = 1.0) -> np.ndarray:
    """Promedio de cada columna de `x` dentro de cada pulso (o de una parte de cada pulso)."""
    length = x.shape[-1]
    columns = []
    for a, b in itertools.pairwise(frames):
        n = max(int(b) - int(a), 1)
        i = min(int(a) + int(start * n), length - 1)
        j = min(max(int(a) + int(end * n), i + 1), length)
        columns.append(x[..., i:j].mean(-1))
    return np.array(columns).T


def _fold(m: np.ndarray) -> np.ndarray:
    """De 84 semitonos (7 octavas) a las 12 notas."""
    return m.reshape(-1, 12, m.shape[-1]).sum(0)


def _similarity(m: np.ndarray, lag: int) -> float:
    a, b = m[:, :-lag], m[:, lag:]
    cos = (a * b).sum(0) / (np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0) + 1e-9)
    return float(cos.mean())


def _prominence(values: np.ndarray, same_parity: bool = False) -> np.ndarray:
    """Cuánto sobresale cada desfase de sus vecinos (los picos quedan positivos).

    Con `misma_paridad`, además tiene que sobresalir de los desfases ±2: así un patrón que
    se repite cada 2 pulsos (bombo y redoblante) no se cuenta como evidencia de 4.
    """
    r = np.zeros(MAX_LAG + 1)
    for L in range(2, MAX_LAG + 1):
        r[L] = values[L] - (values[L - 1] + values[L + 1]) / 2
        if same_parity and L >= 3:
            r[L] = min(r[L], values[L] - (values[L - 2] + values[L + 2]) / 2)
    return r


def _scores(prominence: np.ndarray) -> dict[int, float]:
    """Promedio (en desvíos estándar) del realce sobre los desfases de cada familia."""
    z = prominence / (np.std(prominence[2:]) + 1e-12)
    output = {}
    for family, lags in FAMILIES.items():
        weights = np.array([1 / _SHARED[L] for L in lags])
        output[family] = float(np.sum(weights * z[list(lags)]) / np.sum(weights))
    return output


def analyze(
    signal: np.ndarray, sr: int, beats: np.ndarray, envelope: np.ndarray, envelope_hop: int
) -> tuple[dict | None, np.ndarray | None]:
    """Devuelve (resumen, espectro). El espectro se reutiliza para ubicar los compases.

    resumen = {"puntajes": {3: z, 4: z, 5: z, 7: z}, "armonia": {...}, "ganador": f,
               "margen": diferencia con la segunda familia}; None si la canción tiene
    muy pocos pulsos para medir repeticiones de hasta 30 pulsos.
    """
    if len(beats) < 3 * MAX_LAG + 2:
        return None, None

    spectrum = _spectrum(signal, sr)
    per_beat = _per_beat(spectrum, librosa.time_to_frames(beats, sr=sr, hop_length=CQT_HOP))
    harmony, bass = _fold(per_beat), _fold(per_beat[:36])  # bajo: las 3 octavas graves

    onsets = _per_beat(envelope, librosa.time_to_frames(beats, sr=sr, hop_length=envelope_hop))
    onsets = onsets - np.convolve(onsets, np.ones(9) / 9, mode="same")  # sin cambios lentos de volumen
    onsets = onsets / (onsets.std() + 1e-9)

    lags = range(MAX_LAG + 3)
    series = {
        "armonia": np.array([_similarity(harmony, L) if L else 1.0 for L in lags]),
        "bajo": np.array([_similarity(bass, L) if L else 1.0 for L in lags]),
        "ataques": np.array([float(np.mean(onsets[:-L] * onsets[L:])) if L else 1.0 for L in lags]),
    }
    per_feature = {k: _scores(_prominence(s, same_parity=(k == "ataques"))) for k, s in series.items()}
    total = {f: sum(WEIGHTS[k] * per_feature[k][f] for k in WEIGHTS) for f in FAMILIES}
    order = sorted(total, key=total.get, reverse=True)
    summary = {
        "puntajes": {f: round(v, 2) for f, v in total.items()},
        "armonia": {f: round(v, 2) for f, v in per_feature["armonia"].items()},
        "ganador": order[0],
        "margen": round(total[order[0]] - total[order[1]], 2),
    }
    return summary, spectrum


def _novelty(m: np.ndarray) -> np.ndarray:
    """Cuánto cambia el contenido de cada pulso respecto del anterior (0 = igual)."""
    a, b = m[:, :-1], m[:, 1:]
    cos = (a * b).sum(0) / (np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0) + 1e-9)
    return np.concatenate([[0.0], 1 - cos])


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / x.std() if x.std() > 1e-12 else np.zeros_like(x)


def chord_changes_per_beat(beats: np.ndarray, segments: list[tuple[float, float, str]]) -> np.ndarray:
    """1 en cada pulso donde empieza un acorde distinto del anterior (los acordes ya vienen por pulso)."""
    marks = np.zeros(len(beats))
    for (_, _, previous), (start, _, label) in itertools.pairwise(segments):
        if label in ("N", "X") or label == previous:
            continue
        i = int(np.argmin(np.abs(beats - start)))
        if abs(beats[i] - start) < 0.15:
            marks[i] = 1.0
    return marks


def locate_bars(
    beats: np.ndarray,
    beats_per_bar: int,
    spectrum: np.ndarray,
    sr: int,
    chord_changes: np.ndarray | None = None,
) -> tuple[np.ndarray, float]:
    """Primeros tiempos para compases de `pulsos_por_compas`.

    Dos pistas de dónde empieza cada compás, que se suman:
    - dónde cambian los acordes reconocidos (los acordes suelen cambiar en el primer tiempo);
    - dónde más cambia la armonía de un pulso al siguiente (sin batería y en el centro de
      cada pulso, para que el bombo o el arrastre del sonido no lo corran).
    La segunda sola se equivoca cuando los acordes se anticipan medio pulso (una síncopa muy
    común): por eso pesan las dos. Si quedan saltos en los pulsos, cada tramo se ubica por
    separado; un tramo de menos de dos compases sigue la cuenta del anterior.
    Devuelve (primeros tiempos, claridad): cuánto le gana la mejor posición a la segunda.
    """
    L = beats_per_bar
    harmonic, _ = librosa.decompose.hpss(spectrum, kernel_size=(31, 9))
    center = _per_beat(harmonic, librosa.time_to_frames(beats, sr=sr, hop_length=CQT_HOP), 0.25, 0.85)
    novelty = np.append(_novelty(_fold(center)) + 0.5 * _novelty(_fold(center[:36])), 0.0)
    if chord_changes is None:
        chord_changes = np.zeros(len(beats))

    intervals = np.diff(beats)
    typical = float(np.median(intervals))
    cuts = [0] + [i + 1 for i, d in enumerate(intervals) if not 0.75 * typical <= d <= 1.25 * typical]
    cuts.append(len(beats))

    downbeats, clarities, weights = [], [], []
    for a, b in itertools.pairwise(cuts):
        if b - a < 2 * L and downbeats:
            # Tramo corto: se sigue contando desde el último primer tiempo
            following = int(np.searchsorted(beats, downbeats[-1])) + L
            while following < a:
                following += L
            downbeats.extend(beats[following:b:L])
            continue
        phases = range(min(L, b - a))
        novelty_score = np.array([novelty[a + f : b : L].mean() for f in phases])
        chord_score = np.array([chord_changes[a + f : b : L].mean() for f in phases])
        score = _z(novelty_score) + _z(chord_score)
        order = np.argsort(score)[::-1]
        phase = int(order[0])
        if len(order) > 1:
            clarities.append(float(score[order[0]] - score[order[1]]))
            weights.append(b - a)
        downbeats.extend(beats[a + phase : b : L])
    clarity = float(np.average(clarities, weights=weights)) if weights else 0.0
    return np.asarray(downbeats, dtype=float), clarity
