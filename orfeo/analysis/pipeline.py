"""Runs every analysis and builds the report (a dict ready for JSON)."""

from __future__ import annotations

import logging
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import numpy as np

from .. import __version__
from ..messages import message
from . import chords, periodicity, rhythm, tonality
from .audio import read_audio
from .notation import Speller, describe_chord

VERSION = 9  # version of the report format; bumping it invalidates the cached analyses

ProgressCallback = Callable[[str, float], None]  # (step code, fraction done)


def preload() -> None:
    """Loads the three models into memory (the first time it downloads the beat model, ~77 MB)."""
    rhythm.preload()
    tonality.preload()
    chords.preload()
    # Some libraries set the root logger to INFO on import: turn it back down to warnings.
    logging.getLogger().setLevel(logging.WARNING)


def analyze(path: Path, progress: ProgressCallback | None = None) -> dict:
    notify = progress or (lambda step, fraction: None)
    start = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="orfeo-") as tmp:
        wav = Path(tmp) / "audio.wav"
        notify("extracting_audio", 0.02)
        signal, sr, track = read_audio(path, wav)
        duration = len(signal) / sr

        notify("finding_beats", 0.08)
        beats, downbeats, downbeat_activation = rhythm.detect_beats(signal, sr)
        beats, downbeats, unified = rhythm.unify_beats(beats, downbeats)
        envelope = rhythm.onset_envelope(signal, sr)

        notify("tempo_and_meter", 0.25)
        tempo = rhythm.analyze_tempo(beats, envelope, sr)
        tempo["unified_beats"] = unified
        corrected = unified["removed"] + unified["added"]
        tempo["warning"] = message("beats_corrected", count=corrected) if corrected >= 8 else None
        subdivision = rhythm.analyze_subdivision(beats, envelope, sr)
        repetition, spectrum = periodicity.analyze(signal, sr, beats, envelope, rhythm.HOP_LENGTH)
        meter = rhythm.analyze_meter(
            beats, downbeats, subdivision, tempo.get("bpm"), tempo.get("confidence", "low"), repetition
        )
        del envelope

        notify("finding_key", 0.32)
        key_result = tonality.detect_key(signal, sr)
        tuning = tonality.estimate_tuning(signal, sr)

        notify("recognizing_chords", 0.45)
        raw_segments = chords.detect_chords(
            wav,
            duration,
            beats,
            progress=lambda f: notify("recognizing_chords", 0.45 + 0.5 * f),
        )

        if meter["source"] == "downbeats":
            # Bars split wrongly by an extra or missing downbeat (3+1, 3+5...)
            downbeats, regrouped = rhythm.regularize_bars(beats, downbeats, meter["beats_per_bar"])
            meter["regrouped_bars"] = regrouped
        elif meter["source"] == "periodicity":
            # The detector's downbeats are unusable: rebuild them for the new meter, where
            # the chords and the harmony change
            notify("locating_bars", 0.96)
            changes = periodicity.chord_changes_per_beat(beats, raw_segments)
            downbeats, clarity = periodicity.locate_bars(
                beats, meter["beats_per_bar"], spectrum, sr, changes, downbeat_activation
            )
            _finish_grid(meter, clarity, tempo)
        del spectrum

    notify("building_report", 0.97)
    tonality.assess_confidence(key_result, tonality.key_from_chords(raw_segments))
    best = key_result["best"]
    speller = Speller(best["tonic_pc"], best["mode"])
    segments = [
        {"start": round(a, 3), "end": round(b, 3), "label": e, **describe_chord(e, speller)}
        for a, b, e in raw_segments
    ]
    bar_cells = rhythm.bar_grid(beats, downbeats, duration)

    return {
        "version": VERSION,
        "orfeo_version": __version__,
        "file": {"name": path.name, "duration": round(duration, 2), "audio_track": track + 1},
        "analysis_seconds": round(time.perf_counter() - start, 1),
        "tempo": tempo,
        "meter": meter,
        "key": key_result,
        "tuning": tuning,
        "chords": {
            "segments": segments,
            "summary": _summary(segments, ""),
            "summary_simple": _summary(segments, "_simple"),
        },
        "bars": _chords_per_bar(bar_cells, segments, beats),
        "beats": [round(float(p), 3) for p in beats],
        "downbeats": [round(float(p), 3) for p in downbeats],
    }


def _finish_grid(meter: dict, clarity: float, tempo: dict) -> None:
    """Confidence and warnings for a bar grid rebuilt from periodicity."""
    meter["approximate_grid"] = clarity < periodicity.PHASE_CLARITY_THRESHOLD
    if clarity >= 2 * periodicity.PHASE_CLARITY_THRESHOLD and meter["confidence"] == "low":
        # The chords always change on the same beat of the bar: the structure is clear
        meter["confidence"] = rhythm.cap_confidence("medium", tempo.get("confidence", "low"))
    if meter["approximate_grid"]:
        meter["warnings"].append(message("approximate_grid"))


def _summary(segments: list[dict], suffix: str, max_count: int = 10) -> list[dict]:
    """Most used chords, by the total time they sound (suffix "" or "_simple" picks the names)."""
    total = defaultdict(float)
    names = {}
    for s in segments:
        if not s["is_chord"]:
            continue
        total[s["solfege" + suffix]] += s["end"] - s["start"]
        names[s["solfege" + suffix]] = s["letter" + suffix]
    grand_total = sum(total.values()) or 1.0
    order = sorted(total.items(), key=lambda kv: kv[1], reverse=True)[:max_count]
    return [{"solfege": k, "letter": names[k], "share": round(v / grand_total, 3)} for k, v in order]


def _chords_per_bar(bar_cells: list[dict], segments: list[dict], beats) -> list[dict]:
    """For each bar, the indices of the chords that sound in it (in order)."""
    typical_beat = float(np.median(np.diff(beats))) if len(beats) > 1 else 0.5
    output = []
    j = 0
    for c in bar_cells:
        while j < len(segments) and segments[j]["end"] <= c["start"]:
            j += 1
        indices = []
        k = j
        while k < len(segments) and segments[k]["start"] < c["end"]:
            s = segments[k]
            overlap = min(s["end"], c["end"]) - max(s["start"], c["start"])
            # Ignore chords that reach less than a third of a beat into the bar
            if overlap >= typical_beat / 3:
                indices.append(k)
            k += 1
        output.append({**c, "chords": indices})
    return output
