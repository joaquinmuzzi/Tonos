"""Pulsos, primeros tiempos, tempo y compás.

- Pulsos y primeros tiempos: Beat This! (CPJKU, ISMIR 2024; MIT).
- Tempo: se calcula a partir de los pulsos (promedio de los intervalos válidos) y se
  compara con un segundo método independiente (librosa).
- Compás: ninguna herramienta abierta lo da directamente. Se cuenta cuántos pulsos hay
  entre primeros tiempos consecutivos, se contrasta con cada cuántos pulsos se repite la
  armonía (periodicity.py) y se mira si cada pulso se divide en 2 o en 3.
"""

from __future__ import annotations

import itertools
from collections import Counter
from functools import lru_cache

import librosa
import numpy as np

HOP_LENGTH = 256  # muestras por cuadro de la envolvente de ataques (~11.6 ms a 22050 Hz)


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
    """Deja una sola grilla de pulsos, al tempo que domina la canción.

    El detector a veces marca el doble de pulsos en un tramo (210 BPM en una canción a 105), se
    saltea alguno o los pone corridos en un redoble. Con la grilla despareja no se pueden contar
    compases, así que se corrigen solo esos errores:
    1. Pulso de más (a menos de 0,7 pulsos del anterior): de los dos queda el que sigue la
       grilla que venía. En un tramo al doble queda un pulso de cada dos, sin correrse a la
       corchea del swing. (No se mira si alguno es primer tiempo: en esos tramos el detector
       también marca primeros tiempos sobre los contratiempos.)
    2. Redoble mal marcado: un tramo corto (hasta 8 pulsos) que mezcla intervalos cortos y
       largos (0,42 / 0,40 / 0,72 / 0,68 s donde van 4 de 0,555) y dura lo mismo que esa
       cantidad de pulsos se reparte parejo.
    3. Pulsos perdidos: un hueco de 2 a 8 pulsos se rellena.
    No se tocan los cambios de tempo reales (ritardando, accelerando, rubato, una sección a
    otro tempo: sus intervalos son todos lentos o todos rápidos) ni los corrimientos que no son
    un número entero de pulsos (un calderón, un compás medio pulso más corto).
    """
    if len(beats) < 8:
        return beats, downbeats, {"quitados": 0, "agregados": 0}
    typical = float(np.median(np.diff(beats)))
    downbeats = np.asarray(downbeats, dtype=float)

    # 1. Pulsos de más
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
    moved: dict[float, float] = {}  # pulso que se corrió -> su nueva posición
    i = 0
    while i < len(grid) - 1:
        if regular(grid[i + 1] - grid[i]):
            output.append(float(grid[i + 1]))
            i += 1
            continue
        # Tramo irregular: de grilla[i] hasta el pulso desde el que la grilla vuelve a ser regular.
        # Un único intervalo normal entre dos irregulares queda dentro del mismo tramo
        # (0,44 / 0,56 / 0,68 s es un solo redoble mal marcado).
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
        if is_fill:  # 2. misma cantidad de pulsos, repartidos parejo
            even = grid[i] + duration * np.arange(1, len(intervals)) / len(intervals)
            moved.update(zip(grid[i + 1 : j].tolist(), even.tolist()))
            output.extend(even.tolist())
        else:  # 3. solo se rellenan los huecos de pulsos perdidos
            # Un hueco aislado se acepta aunque la banda vuelva un poco tarde; dentro de una serie
            # de pulsos lentos (un ritardando) tiene que ser casi exacto, o es parte del ritardando
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
    # Los primeros tiempos siguen a su pulso (si se corrió) y quedan en el pulso más cercano
    target = [moved.get(float(p), float(p)) for p in downbeats]
    nearest = [float(new[np.argmin(np.abs(new - p))]) for p in target]
    new_downbeats = np.unique([c for c, p in zip(nearest, target) if abs(c - p) <= 0.25 * typical])
    return new, new_downbeats, {"quitados": removed, "agregados": added}


# --- Tempo -------------------------------------------------------------------


def _period(intervals: np.ndarray) -> float:
    """Promedio de los intervalos a ±10 % de la mediana (ignora pulsos salteados o de más)."""
    median = float(np.median(intervals))
    valid = intervals[np.abs(intervals - median) <= 0.10 * median]
    return float(np.mean(valid)) if len(valid) else median


def analyze_tempo(beats: np.ndarray, envelope: np.ndarray, sr: int) -> dict:
    if len(beats) < 8:
        return {"bpm": None, "motivo": "Se detectaron muy pocos pulsos para estimar el tempo."}

    intervals = np.diff(beats)
    median = float(np.median(intervals))
    # Beat This! entrega los pulsos en una grilla de 20 ms, así que cada intervalo viene
    # redondeado y la mediana también (170 BPM saldría 166,7). El promedio de los intervalos
    # válidos no arrastra ese redondeo: los errores de cada pulso se compensan.
    bpm = 60.0 / _period(intervals)

    # Tempo local: misma cuenta sobre ventanas de 8 intervalos
    local_bpms = np.array([60.0 / _period(intervals[max(0, i - 4) : i + 4]) for i in range(len(intervals))])
    p10, p90 = (float(x) for x in np.percentile(local_bpms, [10, 90]))
    variation = (p90 - p10) / bpm
    # Regularidad: proporción de pulsos a ±10 % del intervalo típico
    regularity = float(np.mean(np.abs(intervals - median) <= 0.10 * median))

    step = max(1, len(local_bpms) // 150)
    curve = [[round(float(t), 2), round(float(b), 1)] for t, b in zip(beats[1::step], local_bpms[::step])]

    # Segundo método independiente (autocorrelación de la envolvente de ataques)
    librosa_bpm = float(librosa.feature.tempo(onset_envelope=envelope, sr=sr, hop_length=HOP_LENGTH)[0])
    relation = None
    for factor, name in ((1, "igual"), (2, "doble"), (0.5, "mitad"), (3, "triple"), (1 / 3, "tercio")):
        if abs(librosa_bpm - bpm * factor) <= 0.04 * bpm * factor:
            relation = name
            break

    # Fuera del rango habitual, lo más probable es que se sienta al doble o a la mitad
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


# --- Compás ------------------------------------------------------------------


def beats_per_bar(beats: np.ndarray, downbeats: np.ndarray) -> list[int]:
    """Cantidad de pulsos de cada compás completo (entre dos primeros tiempos)."""
    if len(downbeats) < 2:
        return []
    indices = np.searchsorted(beats, downbeats)
    bar_lengths = np.diff(indices)
    return [int(c) for c in bar_lengths if c > 0]


def regularize_bars(beats: np.ndarray, downbeats: np.ndarray, n: int | None) -> tuple[np.ndarray, int]:
    """Arregla compases cortados por un primer tiempo de más, de menos o corrido.

    Solo se rearman (en compases parejos de n pulsos) los grupos de compases seguidos que
    suman un múltiplo de n y que son un error evidente del detector, no un cambio de compás:
    un compás del doble (8), un par desparejo (3+1, 1+3, 3+5) o uno con compases de 1 o 2
    pulsos (2+2, 3+3+2), siempre que no sumen más de dos compases. Un compás distinto aislado
    (un 3 entre compases de 4) o una serie de compases iguales (un puente en 3/4: 3+3+3+3) se
    dejan como están. Devuelve (primeros tiempos, grupos rearmados).
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
    """Máximo de la envolvente en ±2 cuadros (±23 ms) alrededor del instante t."""
    center = round(t * sr / HOP_LENGTH)
    begin, end = max(0, center - 2), min(len(envelope), center + 3)
    return float(envelope[begin:end].max()) if end > begin else 0.0


def analyze_subdivision(beats: np.ndarray, envelope: np.ndarray, sr: int) -> dict:
    """¿Cada pulso se divide en 2 (binaria) o en 3 (ternaria)?

    Compara la energía de ataques a 1/2 del pulso contra la de 1/3 y 2/3.
    Es una pista, no un veredicto: el swing y el shuffle también suenan ternarios.
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
        # Referencia: puntos que no caen en ninguna de las dos grillas (ni 1/3, 1/2, 2/3, ni 1/4, 3/4)
        off_grid.append(
            (_onset_peak(envelope, b0 + 0.42 * d, sr) + _onset_peak(envelope, b0 + 0.58 * d, sr)) / 2
        )
    if len(binary) < 8:
        return {"tipo": "no clara", "razon": None}

    b, t = float(np.median(binary)), float(np.median(ternary))
    background = float(np.median(off_grid)) + 1e-6  # mismo estadístico (máximo en ±2 cuadros) que b y t
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
    # (4, "ternaria") depende del tempo: ver _lectura()
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
        # Rápido con pulso en tres = swing/shuffle (se escribe 4/4); lento = balada en 12/8
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
# Compases que el método de periodicidad no distingue entre sí (2 y 4 se repiten igual cada 4)
_FAMILY = {2: 4, 4: 4, 8: 4, 3: 3, 6: 3, 9: 3, 5: 5, 10: 5, 7: 7}


def compare_with_periodicity(n: int | None, periodicity: dict | None) -> dict | None:
    """¿El segundo método (repetición de la armonía) confirma, contradice o completa el conteo?

    El detector de primeros tiempos distingue bien 3/4 de 4/4, pero casi no vio compases de
    5 ni de 7 al entrenarse y los fuerza a 4. Por eso el segundo método solo se impone cuando
    encuentra 5 o 7 (o cuando el conteo no sirvió), y con evidencia clara: que gane por
    bastante y que la armonía también esté de su lado. Entre 3 y 4 solo puede avisar.
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
    if family is None:  # el conteo no sirvió (o dio un compás raro): alcanza con que gane claro
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
        # El conteo de primeros tiempos se descarta: manda la repetición de la armonía
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
            confidence = _LEVELS[_LEVELS.index(confidence) + 1]  # dos métodos independientes coinciden
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
    # Si los pulsos mismos son dudosos, el compás (que se cuenta con ellos) no puede ser más seguro
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
    """Celdas [inicio, fin) para mostrar los acordes compás por compás.

    - Con primeros tiempos: un compás entre cada par. Lo que suena antes del primero es la
      anacrusa (si dura menos de un compás) o la intro (compás 0).
    - Sin primeros tiempos: tramos de 4 pulsos, o de 4 segundos si tampoco hay pulsos, para
      que los acordes se puedan ver igual.
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
