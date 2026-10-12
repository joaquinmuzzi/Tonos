"""Beats, downbeats, tempo and meter.

- Beats and downbeats: Beat This! (CPJKU, ISMIR 2024; MIT).
- Tempo: computed from the beats (mean of the valid intervals) and compared with a second,
  independent method (librosa).
- Meter: no open tool gives it directly. We count the beats between consecutive downbeats,
  check that against how often the harmony repeats (periodicity.py) and look at whether
  each beat is divided in 2 or in 3.
"""

from __future__ import annotations

import itertools
from collections import Counter
from functools import lru_cache

import librosa
import numpy as np

HOP_LENGTH = 256  # samples per frame of the onset envelope (~11.6 ms at 22050 Hz)


@lru_cache(maxsize=1)
def _model():
    from beat_this.inference import Audio2Beats

    return Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)


def preload() -> None:
    _model()


def detect_beats(signal: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    beats, downbeats = _model()(signal, sr)
    return np.asarray(beats, dtype=float), np.asarray(downbeats, dtype=float)


def onset_envelope(signal: np.ndarray, sr: int) -> np.ndarray:
    return librosa.onset.onset_strength(y=signal, sr=sr, hop_length=HOP_LENGTH)


def unify_beats(beats: np.ndarray, downbeats: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Leaves a single beat grid, at the tempo that dominates the song.

    The detector sometimes marks twice as many beats in a stretch (210 BPM in a song at 105),
    skips a beat, or misplaces them during a drum fill. Bars cannot be counted on an uneven
    grid, so only those errors are corrected:
    1. Extra beat (less than 0.7 beats after the previous one): of the two, keep the one that
       follows the grid so far. In a double-time stretch one beat out of two is kept, without
       drifting to the swung eighth. (Downbeat marks are ignored here: in those stretches the
       detector also puts downbeats on the off-beats.)
    2. Mis-tracked fill: a short stretch (up to 8 beats) that mixes short and long intervals
       (0.42 / 0.40 / 0.72 / 0.68 s where 4 of 0.555 belong) and lasts as long as that many
       beats is evened out.
    3. Missed beats: a gap of 2 to 8 beats is filled in.
    Real tempo changes are left alone (ritardando, accelerando, rubato, a section at another
    tempo: their intervals are all slow or all fast), and so are shifts that are not a whole
    number of beats (a fermata, a bar that is half a beat shorter).
    """
    if len(beats) < 8:
        return beats, downbeats, {"quitados": 0, "agregados": 0}
    typical = float(np.median(np.diff(beats)))
    downbeats = np.asarray(downbeats, dtype=float)

    # 1. Extra beats
    deduped = [float(beats[0])]
    removed = added = 0
    for t in (float(x) for x in beats[1:]):
        last = deduped[-1]
        if t - last >= 0.7 * typical:
            deduped.append(t)
            continue
        removed += 1
        expected = deduped[-2] + typical if len(deduped) > 1 else last
        if abs(t - expected) < abs(last - expected):
            deduped[-1] = t
    grid = np.asarray(deduped)

    def regular(d: float) -> bool:
        return 0.85 * typical <= d <= 1.15 * typical

    output = [float(grid[0])]
    moved: dict[float, float] = {}  # beat that was moved -> its new position
    i = 0
    while i < len(grid) - 1:
        if regular(grid[i + 1] - grid[i]):
            output.append(float(grid[i + 1]))
            i += 1
            continue
        # Irregular stretch: from grid[i] to the beat from which the grid is regular again.
        # A single regular interval between two irregular ones stays in the same stretch
        # (0.44 / 0.56 / 0.68 s is one mis-tracked fill).
        j = i + 1
        while j < len(grid) - 1:
            if not regular(grid[j + 1] - grid[j]):
                j += 1
            elif j + 2 < len(grid) and not regular(grid[j + 2] - grid[j + 1]):
                j += 2
            else:
                break
        intervals = np.diff(grid[i : j + 1])
        duration = float(grid[j] - grid[i])
        is_fill = (
            len(intervals) <= 8
            and bool(np.any(intervals < 0.85 * typical))
            and bool(np.any(intervals > 1.15 * typical))
            and abs(duration / len(intervals) - typical) <= 0.15 * typical
        )
        if is_fill:  # 2. same number of beats, evenly spaced
            even = grid[i] + duration * np.arange(1, len(intervals)) / len(intervals)
            moved.update(zip(grid[i + 1 : j].tolist(), even.tolist()))
            output.extend(even.tolist())
        else:  # 3. only fill the gaps left by missed beats
            # An isolated gap is accepted even if the band comes back a little late; inside a run
            # of slow beats (a ritardando) it must be almost exact, or it is part of the ritardando
            tolerance = 0.15 if len(intervals) == 1 else 0.06
            for a, b in zip(grid[i:j], grid[i + 1 : j + 1]):
                gap = float(b - a)
                m = round(gap / typical)
                if 2 <= m <= 8 and abs(gap / m - typical) <= tolerance * typical:
                    output.extend((a + gap * np.arange(1, m) / m).tolist())
                    added += m - 1
                if b != grid[j]:
                    output.append(float(b))
        output.append(float(grid[j]))
        i = j
    new = np.asarray(output)
    # Downbeats follow their beat (if it moved) and snap to the nearest beat
    target = [moved.get(float(p), float(p)) for p in downbeats]
    nearest = [float(new[np.argmin(np.abs(new - p))]) for p in target]
    new_downbeats = np.unique([c for c, p in zip(nearest, target) if abs(c - p) <= 0.25 * typical])
    return new, new_downbeats, {"quitados": removed, "agregados": added}


# --- Tempo --------------------------------------------------------------------


def _period(intervals: np.ndarray) -> float:
    """Mean of the intervals within ±10 % of the median (ignores skipped or extra beats)."""
    median = float(np.median(intervals))
    valid = intervals[np.abs(intervals - median) <= 0.10 * median]
    return float(np.mean(valid)) if len(valid) else median


def analyze_tempo(beats: np.ndarray, envelope: np.ndarray, sr: int) -> dict:
    if len(beats) < 8:
        return {"bpm": None, "motivo": "Se detectaron muy pocos pulsos para estimar el tempo."}

    intervals = np.diff(beats)
    median = float(np.median(intervals))
    # Beat This! returns beats on a 20 ms grid, so every interval is rounded and so is the
    # median (170 BPM would come out as 166.7). The mean of the valid intervals does not
    # carry that rounding: the errors of the individual beats cancel out.
    bpm = 60.0 / _period(intervals)

    # Local tempo: same computation over windows of 8 intervals
    local_bpms = np.array([60.0 / _period(intervals[max(0, i - 4) : i + 4]) for i in range(len(intervals))])
    p10, p90 = (float(x) for x in np.percentile(local_bpms, [10, 90]))
    variation = (p90 - p10) / bpm
    # Regularity: share of beats within ±10 % of the typical interval
    regularity = float(np.mean(np.abs(intervals - median) <= 0.10 * median))

    step = max(1, len(local_bpms) // 150)
    curve = [[round(float(t), 2), round(float(b), 1)] for t, b in zip(beats[1::step], local_bpms[::step])]

    # Second, independent method (autocorrelation of the onset envelope)
    librosa_bpm = float(librosa.feature.tempo(onset_envelope=envelope, sr=sr, hop_length=HOP_LENGTH)[0])
    relation = None
    for factor, name in ((1, "igual"), (2, "doble"), (0.5, "mitad"), (3, "triple"), (1 / 3, "tercio")):
        if abs(librosa_bpm - bpm * factor) <= 0.04 * bpm * factor:
            relation = name
            break

    # Outside the usual range, it is most likely felt at double or half the tempo
    suggestion = "doble" if bpm < 55 else "mitad" if bpm > 200 else None

    if regularity >= 0.85 and relation in ("igual", "doble", "mitad"):
        confidence = "alta"
    elif regularity >= 0.7:
        confidence = "media"
    else:
        confidence = "baja"

    return {
        "bpm": round(bpm, 1),
        "confianza": confidence,
        "alternativas": {"mitad": round(bpm / 2, 1), "doble": round(bpm * 2, 1)},
        "sugerencia": suggestion,
        "rango": [round(p10, 1), round(p90, 1)],
        "estable": bool(variation < 0.08),
        "regularidad": round(regularity, 2),
        "curva": curve,
        "segundo_metodo": {"bpm": round(librosa_bpm, 1), "relacion": relation},
    }


# --- Meter --------------------------------------------------------------------


def beats_per_bar(beats: np.ndarray, downbeats: np.ndarray) -> list[int]:
    """Number of beats in each complete bar (between two downbeats)."""
    if len(downbeats) < 2:
        return []
    indices = np.searchsorted(beats, downbeats)
    bar_lengths = np.diff(indices)
    return [int(c) for c in bar_lengths if c > 0]


def regularize_bars(beats: np.ndarray, downbeats: np.ndarray, n: int | None) -> tuple[np.ndarray, int]:
    """Fixes bars split by an extra, missing or misplaced downbeat.

    Only groups of consecutive bars that add up to a multiple of n and are an obvious detector
    error, not a change of meter, are regrouped (into even bars of n beats): a double bar (8),
    an uneven pair (3+1, 1+3, 3+5) or a group with bars of 1 or 2 beats (2+2, 3+3+2), as long
    as they add up to at most two bars. A single different bar (a 3 among bars of 4) or a run
    of equal bars (a bridge in 3/4: 3+3+3+3) is left as it is.
    Returns (downbeats, number of regrouped groups).
    """
    if not n or n < 2 or len(downbeats) < 3:
        return downbeats, 0
    indices = np.searchsorted(beats, downbeats)
    lengths = np.diff(indices)
    new = [int(indices[0])]
    regrouped = 0
    k = 0
    while k < len(lengths):
        if lengths[k] == n:
            new.append(int(indices[k + 1]))
            k += 1
            continue
        total, m = 0, k
        while m < len(lengths) and lengths[m] != n:
            total += int(lengths[m])
            m += 1
            if total % n == 0:
                break
        group = [int(x) for x in lengths[k:m]]
        obvious_error = total <= 2 * n and (len(group) == 1 or len(set(group)) > 1 or min(group) <= n // 2)
        if total % n == 0 and obvious_error:
            new.extend(range(int(indices[k]) + n, int(indices[k]) + total + 1, n))
            regrouped += 1
        else:
            new.extend(int(i) for i in indices[k + 1 : m + 1])
        k = m
    return beats[np.asarray(new)], regrouped


def _onset_peak(envelope: np.ndarray, t: float, sr: int) -> float:
    """Maximum of the envelope within ±2 frames (±23 ms) around time t."""
    center = round(t * sr / HOP_LENGTH)
    begin, end = max(0, center - 2), min(len(envelope), center + 3)
    return float(envelope[begin:end].max()) if end > begin else 0.0


def analyze_subdivision(beats: np.ndarray, envelope: np.ndarray, sr: int) -> dict:
    """Is each beat divided in 2 (binary) or in 3 (ternary)?

    Compares the onset energy at 1/2 of the beat with the energy at 1/3 and 2/3.
    It is a hint, not a verdict: swing and shuffle also sound ternary.
    """
    binary, ternary, off_grid = [], [], []
    for b0, b1 in itertools.pairwise(beats):
        d = b1 - b0
        if not 0.15 < d < 2.0:
            continue
        binary.append(_onset_peak(envelope, b0 + d / 2, sr))
        ternary.append(
            (_onset_peak(envelope, b0 + d / 3, sr) + _onset_peak(envelope, b0 + 2 * d / 3, sr)) / 2
        )
        # Reference: points that fall on neither grid (not 1/3, 1/2, 2/3, nor 1/4, 3/4)
        off_grid.append(
            (_onset_peak(envelope, b0 + 0.42 * d, sr) + _onset_peak(envelope, b0 + 0.58 * d, sr)) / 2
        )
    if len(binary) < 8:
        return {"tipo": "no clara", "razon": None}

    b, t = float(np.median(binary)), float(np.median(ternary))
    background = float(np.median(off_grid)) + 1e-6  # same statistic (max over ±2 frames) as b and t
    ratio = (t + 1e-6) / (b + 1e-6)
    if max(b, t) < 1.15 * background:
        kind = "no clara"
    elif ratio >= 1.25:
        kind = "ternaria"
    elif ratio <= 0.80:
        kind = "binaria"
    else:
        kind = "no clara"
    return {"tipo": kind, "razon": round(ratio, 2)}


_READINGS = {
    (4, "binaria"): ("4/4", None),
    (4, "no clara"): ("4/4", None),
    # (4, "ternaria") depends on the tempo: see _reading()
    (2, "binaria"): ("2/4", "o 4/4 contado más rápido"),
    (2, "no clara"): ("2/4", "o 6/8"),
    (2, "ternaria"): ("6/8", "o 2/4 con tresillos"),
    (3, "binaria"): ("3/4", "o 6/8"),
    (3, "no clara"): ("3/4", "o 6/8"),
    (3, "ternaria"): ("3/4", "o 9/8, o 6/8"),
    (6, "binaria"): ("6/8", "o 3/4"),
    (6, "no clara"): ("6/8", "o 3/4"),
    (6, "ternaria"): ("6/8", "o 3/4"),
}

TERNARY_WARNING = (
    "El 3/4 y el 6/8 se confunden con mucha facilidad (y en la chacarera o la zamba se "
    "alternan a propósito). Ninguna herramienta automática los distingue bien: escuchá si "
    "el pulso que marcás con el pie se divide en 2 o en 3."
)


def _reading(n: int, subdivision: str, bpm: float | None) -> tuple[str, str | None]:
    if n == 4 and subdivision == "ternaria":
        # Fast with beats in three = swing/shuffle (written in 4/4); slow = a 12/8 ballad
        if bpm is not None and bpm < 80:
            return "12/8", "o 4/4 con tresillos"
        return "4/4 con swing", "o shuffle; también se puede escribir en 12/8"
    if (n, subdivision) in _READINGS:
        return _READINGS[(n, subdivision)]
    if n in (5, 7):
        return f"{n}/4", f"o {n}/8 (compás irregular)"
    return f"{n} pulsos por compás", "compás poco común: tomalo con pinzas"


def _no_meter(subdivision: dict, reason: str, second_method: dict | None = None) -> dict:
    return {
        "pulsos_por_compas": None,
        "lectura": None,
        "alternativa": None,
        "confianza": "baja",
        "motivo": reason,
        "subdivision": subdivision,
        "avisos": [],
        "fuente": None,
        "segundo_metodo": second_method,
    }


_LEVELS = ["baja", "media", "alta"]
# Meters the periodicity method cannot tell apart (2 and 4 both repeat every 4 beats)
_FAMILY = {2: 4, 4: 4, 8: 4, 3: 3, 6: 3, 9: 3, 5: 5, 10: 5, 7: 7}


def compare_with_periodicity(n: int | None, periodicity: dict | None) -> dict | None:
    """Does the second method (repetition of the harmony) confirm, contradict or complete the count?

    The downbeat detector tells 3/4 from 4/4 well, but it saw almost no bars of 5 or 7 during
    training and forces them into 4. So the second method only takes over when it finds 5 or 7
    (or when the count was unusable), and only with clear evidence: it must win by a wide
    margin and the harmony must be on its side too. Between 3 and 4 it can only warn.
    """
    if periodicity is None:
        return None
    scores, harmony, winner = periodicity["puntajes"], periodicity["armonia"], periodicity["ganador"]
    family = _FAMILY.get(n) if n else None
    output = {
        "pulsos": winner,
        "puntajes": scores,
        "confirma": False,
        "reemplaza": False,
        "contradice": False,
        "fuerte": False,
    }
    if family == winner:
        output["confirma"] = periodicity["margen"] >= 0.5
        return output
    if family is None:  # the count was unusable (or gave an odd meter): a clear win is enough
        advantage = periodicity["margen"]
        clear = scores[winner] >= 0.3 and advantage >= 0.3
    else:
        advantage = scores[winner] - scores[family]
        clear = scores[winner] >= 0.3 and advantage >= 0.6 and harmony[winner] > harmony[family]
    output["reemplaza"] = clear and (family is None or winner in (5, 7))
    output["contradice"] = clear and not output["reemplaza"]
    output["fuerte"] = advantage >= 1.0 and harmony[winner] >= 0.8
    return output


def cap_confidence(confidence: str, cap: str | None) -> str:
    if cap in _LEVELS:
        return _LEVELS[min(_LEVELS.index(confidence), _LEVELS.index(cap))]
    return confidence


def analyze_meter(
    beats: np.ndarray,
    downbeats: np.ndarray,
    subdivision: dict,
    bpm: float | None = None,
    tempo_confidence: str | None = None,
    periodicity: dict | None = None,
) -> dict:
    bar_lengths = beats_per_bar(beats, downbeats)
    counts = Counter(bar_lengths)
    n, count = counts.most_common(1)[0] if bar_lengths else (None, 0)
    agreement = count / len(bar_lengths) if bar_lengths else 0.0
    count_is_valid = len(bar_lengths) >= 4 and n is not None and n >= 2
    second = compare_with_periodicity(n if count_is_valid else None, periodicity)
    replaces = bool(second and second["reemplaza"])

    if not count_is_valid and not replaces:
        if len(bar_lengths) < 4:
            reason = "No se detectaron suficientes primeros tiempos para estimar el compás."
        else:
            reason = (
                "Casi todos los pulsos detectados quedaron marcados como primer tiempo, así que "
                "no se pudo contar el compás. Pasa con música muy libre o con mucho rubato."
            )
        return _no_meter(subdivision, reason, second)

    warnings = []
    if replaces:
        # The downbeat count is discarded: the repetition of the harmony decides
        g = second["pulsos"]
        reading, alternative = _reading(g, subdivision["tipo"], bpm)
        confidence = "media" if second["fuerte"] else "baja"
        if count_is_valid:
            warnings.append(
                f"El detector de primeros tiempos marcó compases de {n} pulsos, pero la armonía y el "
                f"bajo se repiten cada {g} pulsos: lo más probable es que el compás sea de {g}. Los "
                "detectores automáticos se entrenaron casi solo con música en 4/4 y tienden a forzarlo."
            )
        else:
            warnings.append(
                f"Los primeros tiempos detectados no alcanzaron para contar el compás, pero la armonía "
                f"y el bajo se repiten cada {g} pulsos."
            )
        number, source = g, "periodicidad"
    else:
        reading, alternative = _reading(n, subdivision["tipo"], bpm)
        if agreement >= 0.85:
            confidence = "alta"
        elif agreement >= 0.6:
            confidence = "media"
        else:
            confidence = "baja"
        if second and second["confirma"] and confidence != "alta":
            confidence = _LEVELS[_LEVELS.index(confidence) + 1]  # two independent methods agree
        if second and second["contradice"]:
            confidence = _LEVELS[max(_LEVELS.index(confidence) - 1, 0)]
            warnings.append(
                f"Un segundo método (cada cuántos pulsos se repite la armonía) sugiere compases de "
                f"{second['pulsos']} pulsos: escuchalo con el clic activado para decidir."
            )
        if agreement < 0.6:
            warnings.append(
                "Los compases detectados no cuentan siempre lo mismo: puede que el compás cambie "
                "durante la canción o que los primeros tiempos estén mal ubicados."
            )
        number, source = n, "primeros tiempos"
    # If the beats themselves are doubtful, the meter (counted from them) cannot be more certain
    confidence = cap_confidence(confidence, tempo_confidence)
    if number in (2, 3, 6):
        warnings.insert(0, TERNARY_WARNING)

    return {
        "pulsos_por_compas": number,
        "lectura": reading,
        "alternativa": alternative,
        "fuente": source,
        "acuerdo": round(agreement, 2),
        "confianza": confidence,
        "compases_contados": len(bar_lengths),
        "conteo_primeros_tiempos": n,
        "distribucion": {str(k): round(v / len(bar_lengths), 2) for k, v in sorted(counts.items())},
        "subdivision": subdivision,
        "segundo_metodo": second,
        "avisos": warnings,
    }


def bar_grid(beats: np.ndarray, downbeats: np.ndarray, duration: float) -> list[dict]:
    """Cells [start, end) to show the chords bar by bar.

    - With downbeats: one bar between each pair. What sounds before the first one is the
      pickup (if it is shorter than a bar) or the intro (bar 0).
    - Without downbeats: stretches of 4 beats, or of 4 seconds if there are no beats either,
      so that the chords can still be shown.
    """
    if len(downbeats):
        edges = [float(x) for x in downbeats]
        kind = "compás"
        typical_bar_length = float(np.median(np.diff(downbeats))) if len(downbeats) > 1 else 2.0
    elif len(beats) >= 4:
        edges = [float(x) for x in beats[::4]]
        kind = "tramo"
        typical_bar_length = 4 * float(np.median(np.diff(beats)))
    else:
        edges = [float(x) for x in np.arange(0.0, duration, 4.0)]
        kind = "tramo"
        typical_bar_length = 4.0

    output = []
    if edges and edges[0] > 0.3:
        label = "anacrusa" if kind == "compás" and edges[0] < 1.05 * typical_bar_length else "intro"
        output.append({"numero": 0, "etiqueta": label, "inicio": 0.0, "fin": edges[0]})
    edges.append(duration)
    for i, (begin, end) in enumerate(itertools.pairwise(edges), start=1):
        if end - begin > 0.05:
            output.append({"numero": i, "etiqueta": f"{kind} {i}", "inicio": begin, "fin": end})
    return output
