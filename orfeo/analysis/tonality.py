"""Key detection with S-KEY (Deezer, ICASSP 2025; MIT code) and tuning with librosa."""

from __future__ import annotations

import contextlib
import io
from functools import lru_cache

import librosa
import numpy as np
import torch
import torchaudio

from .notation import key_name, parse_skey_label, relative_key

WINDOW_SECONDS = 30.0  # to see whether the key changes along the song
WINDOW_HOP_SECONDS = 15.0
MAX_WHOLE_SONG_SECONDS = 6 * 60.0  # above this, the global key is the average of the windows


@lru_cache(maxsize=1)
def _model():
    from skey.key_detection import key_map, load_checkpoint, load_model_components

    ckpt = load_checkpoint(None)
    with contextlib.redirect_stdout(io.StringIO()):  # nnAudio prints internal details
        hcqt, chromanet, crop = load_model_components(ckpt, torch.device("cpu"))
    classes = [parse_skey_label(key_map[i]) for i in range(24)]
    return hcqt, chromanet, crop, int(ckpt["audio"]["sr"]), classes


def preload() -> None:
    _model()


def _probabilities(hcqt, chromanet, crop, wave: torch.Tensor) -> np.ndarray:
    """Same as skey.key_detection.infer_key, but returns the 24 probabilities."""
    with torch.no_grad():
        cqt = crop(hcqt(wave.unsqueeze(0)), torch.zeros(1))
        return chromanet(cqt).mean(dim=0).numpy()


def _describe(tonic_pc: int, mode: str, prob: float) -> dict:
    return {
        "tonica_pc": tonic_pc,
        "modo": mode,
        "probabilidad": round(float(prob), 3),
        **key_name(tonic_pc, mode),
    }


def detect_key(signal: np.ndarray, sr: int) -> dict:
    hcqt, chromanet, crop, model_sr, classes = _model()
    wave = torch.from_numpy(np.ascontiguousarray(signal, dtype=np.float32)).unsqueeze(0)
    if sr != model_sr:
        wave = torchaudio.functional.resample(wave, sr, model_sr)
    wave = wave / wave.abs().max().clamp_min(1e-9)
    duration = wave.shape[1] / model_sr

    windows = _windows(wave, model_sr)
    if duration > MAX_WHOLE_SONG_SECONDS and windows:
        # For long songs, the transform of the whole signal takes several GB of memory:
        # use the average of the windows instead (the model was trained on 15 s chunks).
        weights = [end - start for start, end, _ in windows]
        probs = np.average([p for _, _, p in windows], axis=0, weights=weights)
    else:
        probs = _probabilities(hcqt, chromanet, crop, wave)
    order = np.argsort(probs)[::-1]
    tonic, mode = classes[order[0]]
    best = _describe(tonic, mode, probs[order[0]])

    rel = relative_key(tonic, mode)
    relative_idx = classes.index(rel)
    alternatives = [{**_describe(*rel, probs[relative_idx]), "motivo": "relativa"}]
    for i in order[1:3]:
        if i != relative_idx:
            alternatives.append({**_describe(*classes[i], probs[i]), "motivo": "segunda opción del modelo"})
            break

    return {
        "principal": best,
        "confianza": None,  # filled in by assess_confidence() once the chords are known
        # How many times more likely the first choice is than the second
        "ventaja": round(float(probs[order[0]] / max(probs[order[1]], 1e-6)), 2),
        "alternativas": alternatives,
        "por_tramos": _by_section(windows, duration, classes, (tonic, mode)),
    }


# Krumhansl and Kessler (1982) key profiles: how much each scale degree "belongs" to the key
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def key_from_chords(chord_segments: list[tuple[float, float, str]]) -> tuple[int, str] | None:
    """Second method, independent of S-KEY: infers the key from the notes of the chords."""
    import mir_eval

    profile = np.zeros(12)
    for start, end, label in chord_segments:
        if label in ("N", "X"):
            continue
        root, bitmap, _ = mir_eval.chord.encode(label, reduce_extended_chords=True)
        if root < 0:
            continue
        notes = np.roll(bitmap.astype(float), root)
        notes[root] += 1.0  # the root counts double
        profile += (end - start) * notes
    if np.ptp(profile) == 0:  # no chords, or a flat profile: nothing to correlate
        return None
    candidates = [
        (float(np.corrcoef(profile, np.roll(template, tonic))[0, 1]), tonic, mode)
        for tonic in range(12)
        for mode, template in (("mayor", _KK_MAJOR), ("menor", _KK_MINOR))
    ]
    _, tonic, mode = max(candidates)
    return tonic, mode


def assess_confidence(key_result: dict, chord_key: tuple[int, str] | None) -> None:
    """Combines the model's advantage with the agreement of the second method (updates `key_result`)."""
    p = key_result["principal"]
    global_key = (p["tonica_pc"], p["modo"])
    if chord_key is None:
        agreement = None
    elif chord_key == global_key:
        agreement = "igual"
    elif chord_key == relative_key(*global_key):
        agreement = "relativa"
    else:
        agreement = "distinta"

    advantage = key_result["ventaja"]
    if agreement is None:
        # Without chords (percussion only, noise, speech...) a key is meaningless
        confidence = "baja"
    elif agreement == "igual" and advantage >= 1.3:
        confidence = "alta"
    elif agreement == "igual" or (agreement == "relativa" and advantage >= 1.5) or advantage >= 2.5:
        confidence = "media"
    else:
        confidence = "baja"
    # If more than half of the song is in another key, confidence cannot be "alta" (high)
    stretches = key_result["por_tramos"]
    if confidence == "alta" and stretches["acuerdo"] is not None and stretches["acuerdo"] < 0.5:
        confidence = "media"

    key_result["confianza"] = confidence
    key_result["segundo_metodo"] = {"acuerdo": agreement, **key_name(*chord_key)} if chord_key else None


def _windows(wave: torch.Tensor, sr: int) -> list[tuple[float, float, np.ndarray]]:
    """S-KEY probabilities in 30 s windows (every 15 s): [(start, end, probs), ...]."""
    hcqt, chromanet, crop, _, _ = _model()
    n = wave.shape[1]
    length, step = int(WINDOW_SECONDS * sr), int(WINDOW_HOP_SECONDS * sr)
    output = []
    for begin in range(0, max(n - length // 2, 1), step):
        chunk = wave[:, begin : begin + length]
        if chunk.shape[1] < length // 2 or float(chunk.abs().max()) < 1e-3:
            continue
        chunk = chunk / chunk.abs().max()
        output.append((begin / sr, min(begin + length, n) / sr, _probabilities(hcqt, chromanet, crop, chunk)))
    return output


def _by_section(windows: list, duration: float, classes: list, global_key: tuple[int, str]) -> dict:
    """Detects possible key changes along the song."""
    if duration < WINDOW_SECONDS * 1.5:
        return {"tramos": [], "acuerdo": None, "cambios": []}

    rel = relative_key(*global_key)
    stretches = []
    for start, end, probs in windows:
        i = int(np.argmax(probs))
        tonic, mode = classes[i]
        stretches.append(
            {
                "inicio": round(start, 1),
                "fin": round(end, 1),
                "tonica_pc": tonic,
                "modo": mode,
                "probabilidad": round(float(probs[i]), 3),
                **key_name(tonic, mode),
            }
        )

    def same_or_relative(t):
        return (t["tonica_pc"], t["modo"]) in (global_key, rel)

    agreement = sum(same_or_relative(t) for t in stretches) / len(stretches) if stretches else None

    # A change: at least 3 consecutive windows (~60 s) in a key other than the relative one
    changes = []
    i = 0
    while i < len(stretches):
        if same_or_relative(stretches[i]):
            i += 1
            continue
        stretch_key = (stretches[i]["tonica_pc"], stretches[i]["modo"])
        j = i
        while (
            j + 1 < len(stretches)
            and (stretches[j + 1]["tonica_pc"], stretches[j + 1]["modo"]) == stretch_key
        ):
            j += 1
        if j - i + 1 >= 3:
            changes.append(
                {k: stretches[i][k] for k in ("inicio", "tonica_pc", "modo", "latino", "americano")}
                | {"fin": stretches[j]["fin"]}
            )
        i = j + 1

    return {
        "tramos": stretches,
        "acuerdo": round(agreement, 2) if agreement is not None else None,
        "cambios": changes,
    }


def estimate_tuning(signal: np.ndarray, sr: int) -> dict:
    """Deviation from A = 440 Hz, in cents (hundredths of a semitone)."""
    chunk = signal[: sr * 90]  # the first minute and a half is enough
    deviation = float(librosa.estimate_tuning(y=chunk, sr=sr)) * 100
    warning = None
    if abs(deviation) >= 25:
        direction = "más aguda" if deviation > 0 else "más grave"
        warning = (
            f"La grabación está {abs(deviation):.0f} cents {direction} que la afinación estándar "
            "(La = 440 Hz). Con un desvío así, la tonalidad y los acordes pueden salir "
            "corridos medio tono."
        )
    return {"cents": round(deviation), "aviso": warning}
