"""Second method for the meter: how many beats does it take for the music to repeat?

The downbeat detector (Beat This!) was trained almost only on 4/4 music and tends to force
bars of 4 even when the song is in 5/4 or 7/4. This method does not use that detector: it
measures, beat by beat, how similar the music is to itself L beats later (harmony, bass and
accents) and looks for the family of bar lengths that best explains the repetitions:

    3 -> 3, 6, 9, 12...   4 -> 4, 8, 12, 16...   5 -> 5, 10, 15...   7 -> 7, 14, 21...

It also finds where each bar starts, from the harmonic changes (without the drums).
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
MAX_LAG = 30  # in beats
WEIGHTS = {"harmony": 0.5, "bass": 0.25, "onsets": 0.25}
CQT_HOP = 512
PHASE_CLARITY_THRESHOLD = 1.0  # below this, the bar grid is reported as approximate

# A lag shared by two families (12 = 3 and 4) counts half for each of them
_SHARED = Counter(L for lags in FAMILIES.values() for L in lags)


def _spectrum(signal: np.ndarray, sr: int) -> np.ndarray:
    """Constant-Q transform: 7 octaves from C1, one bin per semitone."""
    cqt = librosa.cqt(signal, sr=sr, hop_length=CQT_HOP, fmin=librosa.note_to_hz("C1"), n_bins=84)
    return np.abs(cqt).astype(np.float32)


def _per_beat(x: np.ndarray, frames: np.ndarray, start: float = 0.0, end: float = 1.0) -> np.ndarray:
    """Mean of the columns of `x` within each beat (or within a part of each beat)."""
    length = x.shape[-1]
    columns = []
    for a, b in itertools.pairwise(frames):
        n = max(int(b) - int(a), 1)
        i = min(int(a) + int(start * n), length - 1)
        j = min(max(int(a) + int(end * n), i + 1), length)
        columns.append(x[..., i:j].mean(-1))
    return np.array(columns).T


def _fold(m: np.ndarray) -> np.ndarray:
    """From 84 semitones (7 octaves) to the 12 pitch classes."""
    return m.reshape(-1, 12, m.shape[-1]).sum(0)


def _similarity(m: np.ndarray, lag: int) -> float:
    a, b = m[:, :-lag], m[:, lag:]
    cos = (a * b).sum(0) / (np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0) + 1e-9)
    return float(cos.mean())


def _prominence(values: np.ndarray, same_parity: bool = False) -> np.ndarray:
    """How much each lag stands out from its neighbours (peaks come out positive).

    With `same_parity`, it must also stand out from the lags ±2: that way a pattern that
    repeats every 2 beats (kick and snare) is not counted as evidence for 4.
    """
    r = np.zeros(MAX_LAG + 1)
    for L in range(2, MAX_LAG + 1):
        r[L] = values[L] - (values[L - 1] + values[L + 1]) / 2
        if same_parity and L >= 3:
            r[L] = min(r[L], values[L] - (values[L - 2] + values[L + 2]) / 2)
    return r


def _scores(prominence: np.ndarray) -> dict[int, float]:
    """Mean prominence (in standard deviations) over the lags of each family."""
    z = prominence / (np.std(prominence[2:]) + 1e-12)
    output = {}
    for family, lags in FAMILIES.items():
        weights = np.array([1 / _SHARED[L] for L in lags])
        output[family] = float(np.sum(weights * z[list(lags)]) / np.sum(weights))
    return output


def analyze(
    signal: np.ndarray, sr: int, beats: np.ndarray, envelope: np.ndarray, envelope_hop: int
) -> tuple[dict | None, np.ndarray | None]:
    """Returns (summary, spectrum). The spectrum is reused to locate the bars.

    summary = {"scores": {3: z, 4: z, 5: z, 7: z}, "harmony": {...}, "winner": f,
               "margin": difference with the runner-up family}; None if the song has too
    few beats to measure repetitions of up to 30 beats.
    """
    if len(beats) < 3 * MAX_LAG + 2:
        return None, None

    spectrum = _spectrum(signal, sr)
    per_beat = _per_beat(spectrum, librosa.time_to_frames(beats, sr=sr, hop_length=CQT_HOP))
    harmony, bass = _fold(per_beat), _fold(per_beat[:36])  # bass: the 3 lowest octaves

    onsets = _per_beat(envelope, librosa.time_to_frames(beats, sr=sr, hop_length=envelope_hop))
    onsets = onsets - np.convolve(onsets, np.ones(9) / 9, mode="same")  # remove slow volume changes
    onsets = onsets / (onsets.std() + 1e-9)

    lags = range(MAX_LAG + 3)
    series = {
        "harmony": np.array([_similarity(harmony, L) if L else 1.0 for L in lags]),
        "bass": np.array([_similarity(bass, L) if L else 1.0 for L in lags]),
        "onsets": np.array([float(np.mean(onsets[:-L] * onsets[L:])) if L else 1.0 for L in lags]),
    }
    per_feature = {k: _scores(_prominence(s, same_parity=(k == "onsets"))) for k, s in series.items()}
    total = {f: sum(WEIGHTS[k] * per_feature[k][f] for k in WEIGHTS) for f in FAMILIES}
    order = sorted(total, key=total.get, reverse=True)
    summary = {
        "scores": {f: round(v, 2) for f, v in total.items()},
        "harmony": {f: round(v, 2) for f, v in per_feature["harmony"].items()},
        "winner": order[0],
        "margin": round(total[order[0]] - total[order[1]], 2),
    }
    return summary, spectrum


def _novelty(m: np.ndarray) -> np.ndarray:
    """How much the content of each beat changes from the previous one (0 = the same)."""
    a, b = m[:, :-1], m[:, 1:]
    cos = (a * b).sum(0) / (np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0) + 1e-9)
    return np.concatenate([[0.0], 1 - cos])


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / x.std() if x.std() > 1e-12 else np.zeros_like(x)


def chord_changes_per_beat(beats: np.ndarray, segments: list[tuple[float, float, str]]) -> np.ndarray:
    """1 on each beat where a chord different from the previous one starts (chords are already per beat)."""
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
    """Downbeats for bars of `beats_per_bar` beats.

    Two cues for where each bar starts, added together:
    - where the recognized chords change (chords usually change on the downbeat);
    - where the harmony changes the most from one beat to the next (without the drums and in
      the middle of each beat, so that the kick or the decay of the sound does not shift it).
    The second cue alone fails when chords are anticipated by half a beat (a very common
    syncopation): that is why both count. If the beats still have jumps, each stretch is
    located separately; a stretch shorter than two bars continues the previous count.
    Returns (downbeats, clarity): how much the best position beats the second best.
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
            # Short stretch: keep counting from the last downbeat
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
