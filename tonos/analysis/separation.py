"""Separation of a song into stems (vocals, drums, bass, other) with Demucs v4 (htdemucs).

It is optional and separate from the analysis: on a CPU it takes about a third of the song's
length (issue #56). The stems are saved as MP3, which every browser plays and which soundfile can
write without ffmpeg (the Docker image's ffmpeg only writes WAV).
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
import types
from collections.abc import Callable
from pathlib import Path

import numpy as np
import soundfile as sf

from .audio import MAX_DURATION, AudioError, SilentAudioError, count_audio_tracks, find_ffmpeg

MODEL = "htdemucs"
STEMS = ("vocals", "drums", "bass", "other")  # in the order the player shows them
SAMPLE_RATE = 44100  # the rate Demucs works at

_model = None
_model_lock = threading.Lock()


class Cancelled(Exception):
    """The user cancelled the separation."""


def _load_model():
    global _model
    with _model_lock:
        if _model is None:
            from demucs.pretrained import get_model

            # The first time it downloads the weights (80 MB) to the torch hub cache
            _model = get_model(MODEL)
            _model.eval()
        return _model


def preload() -> None:
    _load_model()


def _read_stereo(input_path: Path, wav_path: Path) -> np.ndarray:
    """The first audio track that is not silent, as the analysis picks it: 44.1 kHz stereo float32,
    shape (2, samples)."""
    tracks = count_audio_tracks(input_path)
    for track in range(tracks):
        audio = _read_track(input_path, wav_path, track)
        if float(np.max(np.abs(audio), initial=0.0)) >= 1e-4:
            return audio
    # The same messages the analysis gives for a silent file
    raise SilentAudioError("all_tracks_silent", tracks=tracks) if tracks > 1 else SilentAudioError("silent")


def _read_track(input_path: Path, wav_path: Path, track: int) -> np.ndarray:
    command = [
        find_ffmpeg(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-map",
        f"0:a:{track}",
        "-vn",
        "-ac",
        "2",
        "-ar",
        str(SAMPLE_RATE),
        "-c:a",
        "pcm_s16le",
        "-t",
        str(MAX_DURATION + 1),
        str(wav_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        raise AudioError("ffmpeg_failed", detail=result.stderr.strip()[-300:])
    audio, _ = sf.read(wav_path, dtype="float32", always_2d=True)
    if len(audio) / SAMPLE_RATE > MAX_DURATION:
        raise AudioError("too_long", minutes=MAX_DURATION // 60)
    return audio.T


def _progress_bar(report: Callable[[float], None], cancelled: Callable[[], bool]):
    """Stands in for tqdm inside Demucs, to report progress and to stop when cancelled."""

    def tqdm(iterable, **_kwargs):
        items = list(iterable)
        for i, item in enumerate(items):
            if cancelled():
                raise Cancelled
            yield item
            report((i + 1) / len(items))

    return types.SimpleNamespace(tqdm=tqdm)


def separate(
    input_path: Path,
    out_dir: Path,
    progress: Callable[[float], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Path]:
    """Writes <stem>.mp3 for each of STEMS into out_dir and returns their paths."""
    import torch
    from demucs import apply

    report = progress or (lambda fraction: None)
    stop = cancelled or (lambda: False)
    model = _load_model()
    with tempfile.TemporaryDirectory(prefix="tonos-stems-") as tmp:
        mix = torch.from_numpy(_read_stereo(input_path, Path(tmp) / "audio.wav"))
    report(0.02)

    # Demucs expects a normalized mix, and the stems are scaled back afterwards
    reference = mix.mean(0)
    mean, std = reference.mean(), reference.std() + 1e-8
    original_tqdm = apply.tqdm
    apply.tqdm = _progress_bar(lambda f: report(0.02 + 0.9 * f), stop)
    try:
        with torch.no_grad():
            sources = apply.apply_model(
                model, ((mix - mean) / std)[None], split=True, overlap=0.25, progress=True
            )
    finally:
        apply.tqdm = original_tqdm
    sources = (sources[0] * std + mean).numpy()

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for stem in STEMS:
        if stop():
            raise Cancelled
        data = sources[model.sources.index(stem)].T
        paths[stem] = out_dir / f"{stem}.mp3"
        sf.write(paths[stem], np.clip(data, -1.0, 1.0), SAMPLE_RATE, format="MP3")
    report(1.0)
    return paths
