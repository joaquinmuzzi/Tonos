"""Chords with Consonance-ACE (Poltronieri, Serra and Rocamora, ISMIR 2025; MIT code).

Follows `ACE.inference.run_inference`, with three changes:
- returns the chords in memory and reuses the beats Beat This! already found;
- the last 20 s chunk is taken backwards from the end (instead of padding it with silence,
  which makes the model answer "no chord" even when there is music);
- one chord per beat only where there are beats: in a free-time intro or in a pause the
  chords are kept as the model detected them.
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import numpy as np

SAMPLE_RATE = 22050
HOP_LENGTH = 512
CHUNK_SECONDS = 20.0  # the model was trained on 20 s chunks and accepts no other length
MIN_SECONDS_WITHOUT_BEATS = 0.5  # shortest chord kept where there are no beats to group by

Segment = tuple[float, float, str]


@lru_cache(maxsize=1)
def _model():
    import ACE
    from ACE.inference import load_model

    ckpt = Path(ACE.__file__).parent / "checkpoints" / "conformer_decomposed_smooth.ckpt"
    with contextlib.redirect_stdout(io.StringIO()):
        return load_model(str(ckpt), model_name="conformer_decomposed")


def preload() -> None:
    _model()


def _chunk_starts(duration: float) -> list[float]:
    if duration <= CHUNK_SECONDS:
        return [0.0]
    starts = [i * CHUNK_SECONDS for i in range(int(duration // CHUNK_SECONDS))]
    if duration - (starts[-1] + CHUNK_SECONDS) > 0.05:
        starts.append(duration - CHUNK_SECONDS)  # a full last chunk, overlapping the previous one
    return starts


def detect_chords(
    wav_path: Path,
    duration: float,
    beats: np.ndarray,
    progress: Callable[[float], None] | None = None,
) -> list[Segment]:
    """Returns [(start, end, harte_label), ...], sorted and without consecutive repeats."""
    from ACE.inference import predict
    from ACE.mir_evaluation import convert_predictions_decomposed
    from ACE.preprocess.audio_processor import AudioChunkProcessor
    from ACE.preprocess.transforms import CQTransform

    model = _model()
    chunker = AudioChunkProcessor(
        audio_path=wav_path,
        target_sample_rate=SAMPLE_RATE,
        hop_length=HOP_LENGTH,
        max_sequence_length=CHUNK_SECONDS,
        device="cpu",
        transform=CQTransform(SAMPLE_RATE, HOP_LENGTH),
        normalize=True,
    )
    length = int(CHUNK_SECONDS * SAMPLE_RATE)
    if chunker.base_signal.shape[1] < length:
        # Song shorter than one chunk: loop it instead of padding with silence
        count = int(np.ceil(length / chunker.base_signal.shape[1]))
        chunker.base_signal = chunker.base_signal.repeat(1, count)[:, :length]

    raw_segments: list[Segment] = []
    covered = 0.0
    starts = _chunk_starts(duration)
    for k, start in enumerate(starts):
        features = chunker.process_chunk(onset=start)
        if features.ndim == 2:
            features = features.unsqueeze(0).unsqueeze(0)
        elif features.ndim == 3:
            features = features.unsqueeze(0)
        pred = predict(model, features)
        stretch, names = convert_predictions_decomposed(
            root_predictions=pred["root"],
            bass_predictions=pred["bass"],
            chord_predictions=pred["chord"],
            segment_duration=CHUNK_SECONDS,
            threshold=0.5,
            # Only flicker (< 0.1 s) is removed. More than that would delete one-beat chords
            # at fast tempos (at 125 BPM a beat lasts 0.48 s); grouping by beats below
            # already smooths the result.
            remove_short_min_duration=0.1,
        )
        for (a, b), label in zip(np.asarray(stretch, dtype=float) + start, names):
            a, b = max(a, covered), min(b, duration)
            if b - a > 1e-3:
                raw_segments.append((a, b, str(label)))
        covered = min(start + CHUNK_SECONDS, duration)
        if progress:
            progress((k + 1) / len(starts))

    return _merge_equal(group_by_beats(raw_segments, beats, duration))


def _majority_label(raw_segments: list[Segment], a: float, b: float, start: int = 0) -> str | None:
    """The chord that sounds the longest within [a, b). `raw_segments` must be sorted."""
    times: dict[str, float] = {}
    for s, e, label in raw_segments[start:]:
        if s >= b:
            break
        overlap = min(e, b) - max(s, a)
        if overlap > 0:
            times[label] = times.get(label, 0.0) + overlap
    return max(times, key=times.get) if times else None


def _absorb_short(segments: list[Segment], minimum: float) -> list[Segment]:
    """Merges segments shorter than `minimum` seconds into the previous (or next) one."""
    output: list[Segment] = []
    pending = None  # start of a short leading segment, handed over to the next one
    for a, b, label in segments:
        if pending is not None:
            a, pending = pending, None
        if b - a < minimum:
            if output:
                output[-1] = (output[-1][0], b, output[-1][2])
            else:
                pending = a
            continue
        output.append((a, b, label))
    if pending is not None and segments:
        output.append((pending, segments[-1][1], segments[-1][2]))
    return output


def group_by_beats(raw_segments: list[Segment], beats: np.ndarray, duration: float) -> list[Segment]:
    """One chord per beat (the one that sounds the longest in it) where the beats are regular.

    Where there are no beats (before the first, after the last, or in gaps longer than two
    beats) the model's segments are kept, removing only those shorter than half a second.
    """
    beats = np.asarray([p for p in beats if 0 < p < duration], dtype=float)
    if len(beats) < 4:
        return _absorb_short(raw_segments, MIN_SECONDS_WITHOUT_BEATS)

    typical = float(np.median(np.diff(beats)))
    cells = [(0.0, float(beats[0])), *list(zip(beats[:-1].tolist(), beats[1:].tolist()))]
    cells.append((float(beats[-1]), duration))

    output: list[Segment] = []
    start = 0  # first segment that can still overlap the current cell
    for a, b in cells:
        if b - a <= 0:
            continue
        while start < len(raw_segments) and raw_segments[start][1] <= a:
            start += 1
        if b - a <= 2 * typical:
            label = _majority_label(raw_segments, a, b, start)
            if label is not None:
                output.append((a, b, label))
        else:
            inside = [(max(s, a), min(e, b), lab) for s, e, lab in raw_segments if min(e, b) - max(s, a) > 0]
            output.extend(_absorb_short(inside, MIN_SECONDS_WITHOUT_BEATS))
    return output


def _merge_equal(segments: list[Segment]) -> list[Segment]:
    output: list[Segment] = []
    for a, b, label in segments:
        if output and output[-1][2] == label and abs(output[-1][1] - a) < 1e-6:
            output[-1] = (output[-1][0], b, label)
        else:
            output.append((a, b, label))
    return output
