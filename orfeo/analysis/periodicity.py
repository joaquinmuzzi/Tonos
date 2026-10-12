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
# Bar phase (locate_bars). Below PHASE_CLARITY_THRESHOLD standard errors the bar grid is reported
# as approximate: with random cues the gap between the two best positions is often above 1.
PHASE_CLARITY_THRESHOLD = 2.0
ATTACK_RADIUS = 0.035  # s: an attack is "on" a beat within +-35 ms (beat-tracker jitter + 1 frame)
LOG_GAIN = 100  # log compression of the harmonic CQT for attacks: a ~40 dB range
ACTIVATION_FPS = 50  # frame rate of Beat This!'s activations

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


def _box_novelty(chroma: np.ndarray, width: int) -> np.ndarray:
    """Per frame: how different the chroma just after it is from the chroma just before it.

    Cosine distance between the sums over [t - width, t) and [t, t + width); 0 at the edges.
    """
    c = np.cumsum(np.pad(chroma, ((0, 0), (1, 0))), axis=1)
    n = chroma.shape[1]
    t = np.arange(n)
    before = c[:, t] - c[:, np.maximum(t - width, 0)]
    after = c[:, np.minimum(t + width, n)] - c[:, t]
    norms = np.linalg.norm(before, axis=0) * np.linalg.norm(after, axis=0)
    out = 1 - (before * after).sum(0) / (norms + 1e-9)
    out[:width] = 0.0
    out[max(n - width, 0) :] = 0.0
    return out


def _peak_near(curve: np.ndarray, fps: float, times: np.ndarray, radius: float) -> np.ndarray:
    """Maximum of `curve` within +-radius seconds of each time."""
    r = max(1, round(radius * fps))
    out = np.zeros(len(times))
    for i, c in enumerate(np.round(np.asarray(times) * fps).astype(int)):
        lo, hi = max(c - r, 0), min(c + r + 1, len(curve))
        out[i] = curve[lo:hi].max() if hi > lo else 0.0
    return out


def _previous(x: np.ndarray) -> np.ndarray:
    """The value of the previous beat (0 for the first)."""
    return np.concatenate([[0.0], x[:-1]])


def _phase_cues(
    beats: np.ndarray,
    spectrum: np.ndarray,
    sr: int,
    chord_changes: np.ndarray | None,
    downbeat_activation: np.ndarray | None,
) -> dict[str, np.ndarray]:
    """Per-beat evidence that a beat is a downbeat. Each cue later votes on its own.

    Harmonic events are placed on a grid of two points per beat (the beat and the off-beat half
    way to the next one), so that syncopation can be handled: a chord struck on the off-beat and
    held through the next beat (an anticipation) belongs to that next beat.
    """
    fps = sr / CQT_HOP
    intervals = np.diff(beats)
    typical = float(np.median(intervals)) if len(intervals) else 0.5
    # Off-beat after each beat; after the last beat of a stretch (before a gap), half a typical beat
    gap = np.append(intervals, typical)
    offbeats = beats + np.minimum(gap, typical) / 2

    harmonic, _ = librosa.decompose.hpss(spectrum, kernel_size=(31, 9))
    # Harmonic change, with half-beat windows on each side: chroma plus bass chroma (lowest 3 octaves)
    width = max(2, round(0.5 * typical * fps))
    change = _box_novelty(_fold(harmonic), width) + 0.5 * _box_novelty(_fold(harmonic[:36]), width)
    # Attacks of pitched notes: positive flux of the log-compressed harmonic part (~40 dB range)
    log_harmonic = np.log1p(LOG_GAIN * harmonic / (harmonic.max() + 1e-12))
    flux = np.maximum(np.diff(log_harmonic, axis=1, prepend=log_harmonic[:, :1]), 0).sum(0)

    attack_on = _peak_near(flux, fps, beats, ATTACK_RADIUS)
    attack_off = _peak_near(flux, fps, offbeats, ATTACK_RADIUS)
    change_on = change[np.clip(np.round(beats * fps).astype(int), 0, len(change) - 1)]
    change_off = change[np.clip(np.round(offbeats * fps).astype(int), 0, len(change) - 1)]

    cues = {}
    # 1. The attack on the beat, or the one on the off-beat before it when it is an anticipation:
    #    it counts for the next beat in the share of its harmonic change that is held through that
    #    beat (not renewed by a new change on the beat, as an arpeggio or a melody would).
    held = np.clip(change_off - np.append(change_on[1:], 0.0), 0.0, None) / (change_off + 1e-12)
    cues["attack"] = np.maximum(attack_on, _previous(attack_off * held))
    # 2. Chord changes, retimed. The recognizer works beat by beat, so a change marked on beat i
    #    happened at the off-beat before it, on the beat or at the off-beat after it. The mark is
    #    split by the attacked change at those three points; the share of the off-beat after the
    #    beat goes to beat i + 1, so an anticipated chord moves to the downbeat it anticipates.
    if chord_changes is not None and np.any(chord_changes):
        before = _previous(attack_off * change_off)
        on, after = attack_on * change_on, attack_off * change_off
        share = after / (before + on + after + 1e-12)
        marks = np.asarray(chord_changes, dtype=float)
        retimed = marks * (1 - share)
        retimed[1:] += (marks * share)[:-1]
        cues["chords"] = retimed
    # 3. The beat tracker's own downbeat activation (trained mostly on 4/4: it is often flat in
    #    5/4 or 7/4, and then it simply gets no weight)
    if downbeat_activation is not None and len(downbeat_activation):
        cues["downbeat"] = _peak_near(np.asarray(downbeat_activation, float), ACTIVATION_FPS, beats, 0.04)
    return cues


def _votes(x: np.ndarray, L: int) -> np.ndarray:
    """Per-phase t statistic over the bars: how consistently each beat of the bar stands out.

    For every bar, each beat is compared with the mean of the other beats of the bar; the vote is
    the mean of that difference over the bars divided by its standard error (variance pooled over
    the phases). A cue that is noise in this song gets votes close to 0, so no weights are needed.
    """
    n = len(x) // L
    if n < 2:
        return np.zeros(L)
    m = x[: n * L].reshape(n, L)
    d = m - (m.sum(1, keepdims=True) - m) / (L - 1)
    # Floor at 1 % of the cue's own variance: a perfectly regular cue would otherwise get 0 (or,
    # with one stray value, an enormous vote)
    pooled = max(float(d.var(0, ddof=1).mean()), 0.01 * float(x.var()))
    if pooled <= 1e-18:
        return np.zeros(L)
    return d.mean(0) / np.sqrt(pooled / n)


def locate_bars(
    beats: np.ndarray,
    beats_per_bar: int,
    spectrum: np.ndarray,
    sr: int,
    chord_changes: np.ndarray | None = None,
    downbeat_activation: np.ndarray | None = None,
) -> tuple[np.ndarray, float]:
    """Downbeats for bars of `beats_per_bar` beats.

    Up to three cues vote for where each bar starts (see _phase_cues): the attack of pitched
    notes, the chord changes (both aware of chords anticipated by half a beat) and, if given, the
    beat tracker's downbeat activation (frames at 50 per second). Each cue votes with how
    consistently it marks one beat of the bar (_votes), so the cue that is clearest in this song
    decides: in a vamp whose bass moves on beat 2, the accent on beat 1; in a song with clear
    chord changes, the chords.

    If the beats have jumps, each stretch is located separately; a stretch shorter than two bars
    continues the previous count, and short stretches at the start are counted backwards from the
    first located one. Returns (downbeats, clarity): the gap between the best and the second-best
    position, in standard errors (below PHASE_CLARITY_THRESHOLD the grid is approximate).
    """
    L = beats_per_bar
    beats = np.asarray(beats, dtype=float)
    if len(beats) == 0:
        return beats, 0.0
    cues = _phase_cues(beats, spectrum, sr, chord_changes, downbeat_activation)

    intervals = np.diff(beats)
    typical = float(np.median(intervals)) if len(intervals) else 0.5
    cuts = [0] + [i + 1 for i, d in enumerate(intervals) if not 0.75 * typical <= d <= 1.25 * typical]
    cuts.append(len(beats))
    stretches = list(itertools.pairwise(cuts))
    if all(b - a < 2 * L for a, b in stretches):  # no stretch is long enough: ignore the cuts
        stretches = [(0, len(beats))]

    indices, clarities, weights = [], [], []  # indices of the downbeats in `beats`
    for a, b in stretches:
        if b - a < 2 * L:
            if indices:  # short stretch: keep counting from the last downbeat
                following = indices[-1] + L
                while following < a:
                    following += L
                indices.extend(range(following, b, L))
            continue  # short stretches before the first located one are filled in below
        score = sum(_votes(x[a:b], L) for x in cues.values())
        order = np.argsort(score)[::-1]
        clarities.append(float(score[order[0]] - score[order[1]]) / np.sqrt(len(cues)))
        weights.append(b - a)
        first = a + int(order[0])
        if not indices:  # beats before the first located stretch: count backwards from it
            indices.extend(range(first % L, first, L))
        indices.extend(range(first, b, L))
    if not indices:  # fewer than two bars of beats in total
        indices = list(range(0, len(beats), L))
    clarity = float(np.average(clarities, weights=weights)) if weights else 0.0
    return beats[np.asarray(indices, dtype=int)], clarity
