"""Genera canciones sintéticas con tempo, compás, tonalidad y acordes conocidos."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

FS = 44100
NOTAS = {
    "C": 0,
    "C#": 1,
    "D": 2,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "F#": 6,
    "G": 7,
    "Ab": 8,
    "A": 9,
    "Bb": 10,
    "B": 11,
}


def _midi_a_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _acorde(raiz: str, menor: bool) -> list[int]:
    r = 48 + NOTAS[raiz]  # Do3
    return [r - 12, r, r + (3 if menor else 4), r + 7, r + 12]


def _tono(frec: float, dur: float, vol: float) -> np.ndarray:
    t = np.arange(int(dur * FS)) / FS
    onda = sum(np.sin(2 * np.pi * frec * k * t) / k for k in range(1, 6))  # timbre tipo órgano
    env = np.minimum(1, t / 0.01) * np.exp(-t * 1.2)
    return vol * onda * env


def _bombo(dur=0.25) -> np.ndarray:
    t = np.arange(int(dur * FS)) / FS
    return np.sin(2 * np.pi * (50 + 100 * np.exp(-t * 30)) * t) * np.exp(-t * 18)


_RNG_REDOBLANTE = np.random.default_rng(0)
_RNG_PLATILLO = np.random.default_rng(1)


def _redoblante(dur=0.18) -> np.ndarray:
    t = np.arange(int(dur * FS)) / FS
    return 0.5 * _RNG_REDOBLANTE.standard_normal(len(t)) * np.exp(-t * 25)


def _platillo(dur=0.05) -> np.ndarray:
    t = np.arange(int(dur * FS)) / FS
    ruido = _RNG_PLATILLO.standard_normal(len(t))
    return 0.25 * np.diff(ruido, prepend=0) * np.exp(-t * 80)


def _sumar(destino: np.ndarray, sonido: np.ndarray, inicio: float) -> None:
    i = int(inicio * FS)
    fin = min(len(destino), i + len(sonido))
    if i < len(destino):
        destino[i:fin] += sonido[: fin - i]


def cancion(
    bpm: float,
    pulsos_por_compas: int,
    progresion: list[tuple[str, bool]],
    compases: int,
    subdivision: int = 2,
    anticipo: float = 0.0,
) -> np.ndarray:
    """Batería + acordes. Cada acorde de `progresion` dura un compás y se repite en ciclo.

    `anticipo`: fracción de pulso que cada acorde entra antes del primer tiempo (síncopa).
    """
    pulso = 60.0 / bpm
    compas = pulsos_por_compas * pulso
    total = compases * compas + 1.0
    y = np.zeros(int(total * FS))
    for c in range(compases):
        inicio_compas = c * compas
        raiz, menor = progresion[c % len(progresion)]
        entra = inicio_compas - (anticipo * pulso if c > 0 else 0.0)
        sale = inicio_compas + compas - (anticipo * pulso if c < compases - 1 else 0.0)
        for nota in _acorde(raiz, menor):
            _sumar(y, _tono(_midi_a_hz(nota), sale - entra, 0.08), entra)
        for p in range(pulsos_por_compas):
            t = inicio_compas + p * pulso
            if p == 0:
                _sumar(y, 1.0 * _bombo(), t)
            elif pulsos_por_compas == 4 and p == 2:
                _sumar(y, 0.7 * _bombo(), t)
            else:
                _sumar(y, _redoblante(), t)
            for s in range(subdivision):
                _sumar(y, _platillo(), t + s * pulso / subdivision)
    return (0.9 * y / np.max(np.abs(y))).astype(np.float32)


def guardar_mp4(y: np.ndarray, destino: Path) -> Path:
    """Guarda como MP4 (AAC), igual que un video descargado sin imagen."""
    wav = destino.with_suffix(".wav")
    sf.write(wav, y, FS)
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(wav),
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(destino),
        ],
        check=True,
    )
    wav.unlink()
    return destino
