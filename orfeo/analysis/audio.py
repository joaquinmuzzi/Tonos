"""Audio extraction with ffmpeg (works for MP4, M4A, MP3, WAV, FLAC, OGG, MKV, MOV...)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 22050  # Hz: the rate Beat This!, S-KEY and Consonance-ACE use internally
MAX_DURATION = 20 * 60  # seconds


class AudioError(Exception):
    """Error whose message is meant to be shown to the user."""


class SilentAudioError(AudioError):
    pass


def find_ffmpeg(program: str = "ffmpeg") -> str:
    path = shutil.which(program)
    if path:
        return path
    raise AudioError(
        "No encontré ffmpeg. Instalalo con:  winget install Gyan.FFmpeg  y volvé a abrir la terminal."
    )


def count_audio_tracks(input_path: Path) -> int:
    """Number of audio tracks in the file (1 if it cannot be determined)."""
    try:
        result = subprocess.run(
            [
                find_ffmpeg("ffprobe"),
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(input_path),
            ],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
    except (AudioError, OSError, subprocess.TimeoutExpired):
        return 1
    return max(1, len([line for line in result.stdout.splitlines() if line.strip()]))


def extract_audio(input_path: Path, wav_path: Path, track: int = 0) -> None:
    """Converts any file with audio into a mono 22050 Hz WAV.

    The output is cut at MAX_DURATION + 1 s, so an hours-long file cannot fill the disk or
    the memory before we get to say that it is too long.
    """
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
        f"0:a:{track}",  # some MP4 files carry several audio tracks
        "-vn",
        "-ac",
        "1",
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
        detail = result.stderr.strip()
        if "matches no streams" in detail:
            raise AudioError("El archivo no tiene ninguna pista de audio.")
        if "drm" in detail.lower() or "protected" in detail.lower():
            raise AudioError("El archivo está protegido con DRM y no se puede leer.")
        if "Invalid data found" in detail or "could not find codec" in detail.lower():
            raise AudioError("No pude leer el archivo: no parece ser audio o video válido.")
        raise AudioError(f"ffmpeg no pudo leer el archivo: {detail[-300:]}")


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    """Loads the generated WAV and checks its duration and that it is not silent."""
    duration = sf.info(str(path)).duration
    if duration < 5:
        raise AudioError("El audio dura menos de 5 segundos: es muy corto para analizarlo.")
    if duration > MAX_DURATION:
        raise AudioError(
            f"El audio dura más de {MAX_DURATION // 60} minutos, que es el máximo "
            "(para mezclas largas, cortá la canción que te interesa)."
        )
    signal, sr = sf.read(str(path), dtype="float32")
    if signal.ndim > 1:
        signal = signal.mean(axis=1)
    if float(np.max(np.abs(signal))) < 1e-4:
        raise SilentAudioError("El audio está en silencio.")
    return signal, sr


def read_audio(input_path: Path, wav_path: Path) -> tuple[np.ndarray, int, int]:
    """Extracts and loads the first audio track that is not silent.

    Returns (signal, sample rate, index of the track used).
    """
    tracks = count_audio_tracks(input_path)
    for track in range(tracks):
        extract_audio(input_path, wav_path, track)
        try:
            signal, sr = load_wav(wav_path)
            return signal, sr, track
        except SilentAudioError:
            if track == tracks - 1:
                if tracks > 1:
                    raise SilentAudioError(
                        f"Las {tracks} pistas de audio del archivo están en silencio."
                    ) from None
                raise
    raise AudioError("El archivo no tiene ninguna pista de audio.")
