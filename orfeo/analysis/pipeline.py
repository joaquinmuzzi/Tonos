"""Une todos los análisis y arma el reporte (un dict listo para JSON)."""

from __future__ import annotations

import logging
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import numpy as np

from . import chords, periodicity, rhythm, tonality
from .audio import read_audio
from .notation import Speller, describe_chord

VERSION = 5  # subirla invalida los análisis guardados en caché

ProgressCallback = Callable[[str, float], None]


def preload() -> None:
    """Carga los tres modelos en memoria (la primera vez descarga el de pulsos, ~77 MB)."""
    rhythm.preload()
    tonality.preload()
    chords.preload()
    # Algunas librerías configuran el log en modo INFO al importarse: lo bajamos a avisos.
    logging.getLogger().setLevel(logging.WARNING)


def analyze(path: Path, progress: ProgressCallback | None = None) -> dict:
    notify = progress or (lambda step, fraction: None)
    start = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="analizador-") as tmp:
        wav = Path(tmp) / "audio.wav"
        notify("Extrayendo el audio", 0.02)
        signal, sr, track = read_audio(path, wav)
        duration = len(signal) / sr

        notify("Buscando los pulsos y los primeros tiempos", 0.08)
        beats, downbeats = rhythm.detect_beats(signal, sr)
        beats, downbeats, unified = rhythm.unify_beats(beats, downbeats)
        envelope = rhythm.onset_envelope(signal, sr)

        notify("Calculando el tempo y el compás", 0.25)
        tempo = rhythm.analyze_tempo(beats, envelope, sr)
        tempo["pulsos_unificados"] = unified
        corrected = unified["quitados"] + unified["agregados"]
        if corrected >= 8:
            tempo["aviso"] = (
                f"En algunos tramos el detector marcó pulsos de más (el doble) o de menos: se "
                f"corrigieron {corrected} pulsos para que la grilla quede pareja y se puedan "
                "contar los compases."
            )
        subdivision = rhythm.analyze_subdivision(beats, envelope, sr)
        repetition, spectrum = periodicity.analyze(signal, sr, beats, envelope, rhythm.HOP_LENGTH)
        meter = rhythm.analyze_meter(
            beats, downbeats, subdivision, tempo.get("bpm"), tempo.get("confianza", "baja"), repetition
        )
        del envelope

        notify("Buscando la tonalidad", 0.32)
        key_result = tonality.detect_key(signal, sr)
        tuning = tonality.estimate_tuning(signal, sr)

        notify("Reconociendo los acordes", 0.45)
        raw_segments = chords.detect_chords(
            wav,
            duration,
            beats,
            progress=lambda f: notify("Reconociendo los acordes", 0.45 + 0.5 * f),
        )

        if meter["fuente"] == "primeros tiempos":
            # Compases mal cortados por un primer tiempo de más o de menos (3+1, 3+5...)
            downbeats, regrouped = rhythm.regularize_bars(beats, downbeats, meter["pulsos_por_compas"])
            meter["compases_rearmados"] = regrouped
        elif meter["fuente"] == "periodicidad":
            # Los primeros tiempos del detector no sirven: se rearman con el compás nuevo,
            # donde cambian los acordes y la armonía
            notify("Ubicando los compases", 0.96)
            changes = periodicity.chord_changes_per_beat(beats, raw_segments)
            downbeats, clarity = periodicity.locate_bars(
                beats, meter["pulsos_por_compas"], spectrum, sr, changes
            )
            _finish_grid(meter, clarity, tempo)
        del spectrum

    notify("Armando el reporte", 0.97)
    tonality.assess_confidence(key_result, tonality.key_from_chords(raw_segments))
    best = key_result["principal"]
    speller = Speller(best["tonica_pc"], best["modo"])
    segments = [
        {"inicio": round(a, 3), "fin": round(b, 3), "etiqueta": e, **describe_chord(e, speller)}
        for a, b, e in raw_segments
    ]
    bar_cells = rhythm.bar_grid(beats, downbeats, duration)

    return {
        "version": VERSION,
        "archivo": {"nombre": path.name, "duracion": round(duration, 2), "pista_de_audio": track + 1},
        "segundos_de_analisis": round(time.perf_counter() - start, 1),
        "tempo": tempo,
        "compas": meter,
        "tonalidad": key_result,
        "afinacion": tuning,
        "acordes": {
            "segmentos": segments,
            "resumen": _summary(segments, "latino", "americano"),
            "resumen_simple": _summary(segments, "latino_simple", "americano_simple"),
        },
        "compases": _chords_per_bar(bar_cells, segments, beats),
        "pulsos": [round(float(p), 3) for p in beats],
        "primeros_tiempos": [round(float(p), 3) for p in downbeats],
    }


def _finish_grid(meter: dict, clarity: float, tempo: dict) -> None:
    """Confianza y avisos de la grilla de compases rearmada por periodicidad."""
    meter["grilla_aproximada"] = clarity < periodicity.PHASE_CLARITY_THRESHOLD
    if clarity >= 2 * periodicity.PHASE_CLARITY_THRESHOLD and meter["confianza"] == "baja":
        # Los acordes cambian siempre en el mismo pulso del compás: la estructura es clara
        meter["confianza"] = rhythm.cap_confidence("media", tempo.get("confianza", "baja"))
    if meter["grilla_aproximada"]:
        meter["avisos"].append(
            "No se pudo determinar con seguridad en qué pulso empieza cada compás: la grilla "
            "de compases es aproximada (puede estar corrida algunos pulsos)."
        )


def _summary(segments: list[dict], solfege_key: str, letter_key: str, max_count: int = 10) -> list[dict]:
    """Acordes más usados, por tiempo total que suenan."""
    total = defaultdict(float)
    names = {}
    for s in segments:
        if not s["es_acorde"]:
            continue
        total[s[solfege_key]] += s["fin"] - s["inicio"]
        names[s[solfege_key]] = s[letter_key]
    grand_total = sum(total.values()) or 1.0
    order = sorted(total.items(), key=lambda kv: kv[1], reverse=True)[:max_count]
    return [{"latino": k, "americano": names[k], "proporcion": round(v / grand_total, 3)} for k, v in order]


def _chords_per_bar(bar_cells: list[dict], segments: list[dict], beats) -> list[dict]:
    """Para cada compás, los índices de los acordes que suenan en él (en orden)."""
    typical_beat = float(np.median(np.diff(beats))) if len(beats) > 1 else 0.5
    output = []
    j = 0
    for c in bar_cells:
        while j < len(segments) and segments[j]["fin"] <= c["inicio"]:
            j += 1
        indices = []
        k = j
        while k < len(segments) and segments[k]["inicio"] < c["fin"]:
            s = segments[k]
            overlap = min(s["fin"], c["fin"]) - max(s["inicio"], c["inicio"])
            # Se ignoran acordes que asoman menos de un tercio de pulso en el compás
            if overlap >= typical_beat / 3:
                indices.append(k)
            k += 1
        output.append({**c, "acordes": indices})
    return output
