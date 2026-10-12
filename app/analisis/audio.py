"""Extracción de audio con ffmpeg (sirve para MP4, M4A, MP3, WAV, FLAC, OGG, MKV, MOV...)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

FRECUENCIA = 22050  # Hz: la que usan internamente Beat This!, S-KEY y Consonance-ACE
DURACION_MAXIMA = 20 * 60  # segundos


class ErrorDeAudio(Exception):
    """Error con un mensaje pensado para mostrarle al usuario."""


class AudioEnSilencio(ErrorDeAudio):
    pass


def buscar_ffmpeg(programa: str = "ffmpeg") -> str:
    ruta = shutil.which(programa)
    if ruta:
        return ruta
    raise ErrorDeAudio(
        "No encontré ffmpeg. Instalalo con:  winget install Gyan.FFmpeg  y volvé a abrir la terminal."
    )


def contar_pistas_de_audio(entrada: Path) -> int:
    """Cantidad de pistas de audio del archivo (1 si no se puede averiguar)."""
    try:
        resultado = subprocess.run(
            [
                buscar_ffmpeg("ffprobe"),
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(entrada),
            ],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=60,
        )
    except (ErrorDeAudio, OSError, subprocess.TimeoutExpired):
        return 1
    return max(1, len([linea for linea in resultado.stdout.splitlines() if linea.strip()]))


def extraer_audio(entrada: Path, salida_wav: Path, pista: int = 0) -> None:
    """Convierte cualquier archivo con audio en un WAV mono a 22050 Hz.

    Corta en DURACION_MAXIMA + 1 s, así un archivo de horas no llena el disco ni la memoria
    antes de poder avisar que es demasiado largo.
    """
    comando = [
        buscar_ffmpeg(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(entrada),
        "-map",
        f"0:a:{pista}",  # algunos MP4 traen varias pistas de audio
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(FRECUENCIA),
        "-c:a",
        "pcm_s16le",
        "-t",
        str(DURACION_MAXIMA + 1),
        str(salida_wav),
    ]
    resultado = subprocess.run(comando, capture_output=True, text=True, errors="replace")
    if resultado.returncode != 0:
        detalle = resultado.stderr.strip()
        if "matches no streams" in detalle:
            raise ErrorDeAudio("El archivo no tiene ninguna pista de audio.")
        if "drm" in detalle.lower() or "protected" in detalle.lower():
            raise ErrorDeAudio("El archivo está protegido con DRM y no se puede leer.")
        if "Invalid data found" in detalle or "could not find codec" in detalle.lower():
            raise ErrorDeAudio("No pude leer el archivo: no parece ser audio o video válido.")
        raise ErrorDeAudio(f"ffmpeg no pudo leer el archivo: {detalle[-300:]}")


def cargar_wav(ruta: Path) -> tuple[np.ndarray, int]:
    """Carga el WAV generado y valida duración y silencio."""
    duracion = sf.info(str(ruta)).duration
    if duracion < 5:
        raise ErrorDeAudio("El audio dura menos de 5 segundos: es muy corto para analizarlo.")
    if duracion > DURACION_MAXIMA:
        raise ErrorDeAudio(
            f"El audio dura más de {DURACION_MAXIMA // 60} minutos, que es el máximo "
            "(para mezclas largas, cortá la canción que te interesa)."
        )
    senal, fs = sf.read(str(ruta), dtype="float32")
    if senal.ndim > 1:
        senal = senal.mean(axis=1)
    if float(np.max(np.abs(senal))) < 1e-4:
        raise AudioEnSilencio("El audio está en silencio.")
    return senal, fs


def obtener_audio(entrada: Path, salida_wav: Path) -> tuple[np.ndarray, int, int]:
    """Extrae y carga la primera pista de audio que no esté en silencio.

    Devuelve (señal, frecuencia, número de pista usada).
    """
    pistas = contar_pistas_de_audio(entrada)
    for pista in range(pistas):
        extraer_audio(entrada, salida_wav, pista)
        try:
            senal, fs = cargar_wav(salida_wav)
            return senal, fs, pista
        except AudioEnSilencio:
            if pista == pistas - 1:
                if pistas > 1:
                    raise AudioEnSilencio(
                        f"Las {pistas} pistas de audio del archivo están en silencio."
                    ) from None
                raise
    raise ErrorDeAudio("El archivo no tiene ninguna pista de audio.")
