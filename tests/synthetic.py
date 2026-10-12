"""Generates synthetic songs with known tempo, meter, key and chords."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

FS = 44100
NOTES = {
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


def _midi_to_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _chord(root: str, minor: bool) -> list[int]:
    r = 48 + NOTES[root]  # C3
    return [r - 12, r, r + (3 if minor else 4), r + 7, r + 12]


def _tone(freq: float, dur: float, vol: float) -> np.ndarray:
    t = np.arange(int(dur * FS)) / FS
    wave = sum(np.sin(2 * np.pi * freq * k * t) / k for k in range(1, 6))  # organ-like timbre
    env = np.minimum(1, t / 0.01) * np.exp(-t * 1.2)
    return vol * wave * env


def _kick(dur=0.25) -> np.ndarray:
    t = np.arange(int(dur * FS)) / FS
    return np.sin(2 * np.pi * (50 + 100 * np.exp(-t * 30)) * t) * np.exp(-t * 18)


_SNARE_RNG = np.random.default_rng(0)
_HIHAT_RNG = np.random.default_rng(1)


def _snare(dur=0.18) -> np.ndarray:
    t = np.arange(int(dur * FS)) / FS
    return 0.5 * _SNARE_RNG.standard_normal(len(t)) * np.exp(-t * 25)


def _hihat(dur=0.05) -> np.ndarray:
    t = np.arange(int(dur * FS)) / FS
    noise = _HIHAT_RNG.standard_normal(len(t))
    return 0.25 * np.diff(noise, prepend=0) * np.exp(-t * 80)


def _mix_in(target: np.ndarray, sound: np.ndarray, start: float) -> None:
    i = int(start * FS)
    end = min(len(target), i + len(sound))
    if i < len(target):
        target[i:end] += sound[: end - i]


def song(
    bpm: float,
    beats_per_bar: int,
    progression: list[tuple[str, bool]],
    bars: int,
    subdivision: int = 2,
    anticipation: float = 0.0,
) -> np.ndarray:
    """Drums + chords. Each chord of `progression` lasts one bar, cycling through the list.

    `anticipation`: fraction of a beat by which each chord comes in before the downbeat (syncopation).
    """
    beat = 60.0 / bpm
    meter = beats_per_bar * beat
    total = bars * meter + 1.0
    y = np.zeros(int(total * FS))
    for c in range(bars):
        bar_start = c * meter
        root, minor = progression[c % len(progression)]
        chord_on = bar_start - (anticipation * beat if c > 0 else 0.0)
        chord_off = bar_start + meter - (anticipation * beat if c < bars - 1 else 0.0)
        for note in _chord(root, minor):
            _mix_in(y, _tone(_midi_to_hz(note), chord_off - chord_on, 0.08), chord_on)
        for p in range(beats_per_bar):
            t = bar_start + p * beat
            if p == 0:
                _mix_in(y, 1.0 * _kick(), t)
            elif beats_per_bar == 4 and p == 2:
                _mix_in(y, 0.7 * _kick(), t)
            else:
                _mix_in(y, _snare(), t)
            for s in range(subdivision):
                _mix_in(y, _hihat(), t + s * beat / subdivision)
    return (0.9 * y / np.max(np.abs(y))).astype(np.float32)


def save_mp4(y: np.ndarray, target: Path) -> Path:
    """Saves as MP4 (AAC), like a downloaded video without picture."""
    wav = target.with_suffix(".wav")
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
            str(target),
        ],
        check=True,
    )
    wav.unlink()
    return target
