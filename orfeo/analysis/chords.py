"""Acordes con Consonance-ACE (Poltronieri, Serra y Rocamora, ISMIR 2025; código MIT).

Sigue `ACE.inference.run_inference`, con tres cambios:
- devuelve los acordes en memoria y usa los pulsos que ya calculó Beat This!;
- el último trozo de 20 s se toma hacia atrás desde el final (en vez de rellenarlo con
  silencio, que hace que el modelo conteste "sin acorde" aunque haya música);
- un acorde por pulso solo donde hay pulsos: en una intro libre o en una pausa se
  conservan los acordes tal como los detectó el modelo.
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

import numpy as np

FRECUENCIA = 22050
SALTO = 512
TROZO = 20.0  # segundos: el modelo se entrenó con trozos de 20 s y no admite otro largo
MINIMO_SIN_PULSOS = 0.5  # duración mínima de un acorde donde no hay pulsos para agrupar

Segmento = tuple[float, float, str]


@lru_cache(maxsize=1)
def _modelo():
    import ACE
    from ACE.inference import load_model

    ckpt = Path(ACE.__file__).parent / "checkpoints" / "conformer_decomposed_smooth.ckpt"
    with contextlib.redirect_stdout(io.StringIO()):
        return load_model(str(ckpt), model_name="conformer_decomposed")


def precargar() -> None:
    _modelo()


def _inicios_de_trozos(duracion: float) -> list[float]:
    if duracion <= TROZO:
        return [0.0]
    inicios = [i * TROZO for i in range(int(duracion // TROZO))]
    if duracion - (inicios[-1] + TROZO) > 0.05:
        inicios.append(duracion - TROZO)  # último trozo completo, superpuesto con el anterior
    return inicios


def detectar_acordes(
    ruta_wav: Path,
    duracion: float,
    pulsos: np.ndarray,
    progreso: Callable[[float], None] | None = None,
) -> list[Segmento]:
    """Devuelve [(inicio, fin, etiqueta_harte), ...] ordenados y sin repetidos consecutivos."""
    from ACE.inference import predict
    from ACE.mir_evaluation import convert_predictions_decomposed
    from ACE.preprocess.audio_processor import AudioChunkProcessor
    from ACE.preprocess.transforms import CQTransform

    modelo = _modelo()
    trozos = AudioChunkProcessor(
        audio_path=ruta_wav,
        target_sample_rate=FRECUENCIA,
        hop_length=SALTO,
        max_sequence_length=TROZO,
        device="cpu",
        transform=CQTransform(FRECUENCIA, SALTO),
        normalize=True,
    )
    largo = int(TROZO * FRECUENCIA)
    if trozos.base_signal.shape[1] < largo:
        # Canción más corta que un trozo: se repite en lugar de rellenar con silencio
        veces = int(np.ceil(largo / trozos.base_signal.shape[1]))
        trozos.base_signal = trozos.base_signal.repeat(1, veces)[:, :largo]

    crudos: list[Segmento] = []
    cubierto = 0.0
    inicios = _inicios_de_trozos(duracion)
    for k, inicio in enumerate(inicios):
        caracteristicas = trozos.process_chunk(onset=inicio)
        if caracteristicas.ndim == 2:
            caracteristicas = caracteristicas.unsqueeze(0).unsqueeze(0)
        elif caracteristicas.ndim == 3:
            caracteristicas = caracteristicas.unsqueeze(0)
        pred = predict(modelo, caracteristicas)
        tramo, nombres = convert_predictions_decomposed(
            root_predictions=pred["root"],
            bass_predictions=pred["bass"],
            chord_predictions=pred["chord"],
            segment_duration=TROZO,
            threshold=0.5,
            # Solo se quita el parpadeo (< 0,1 s). Más que eso borraría acordes de un pulso
            # en tempos rápidos (a 125 BPM un pulso dura 0,48 s); el agrupado por pulsos
            # de abajo ya suaviza.
            remove_short_min_duration=0.1,
        )
        for (a, b), etiqueta in zip(np.asarray(tramo, dtype=float) + inicio, nombres):
            a, b = max(a, cubierto), min(b, duracion)
            if b - a > 1e-3:
                crudos.append((a, b, str(etiqueta)))
        cubierto = min(inicio + TROZO, duracion)
        if progreso:
            progreso((k + 1) / len(inicios))

    return _unir_iguales(agrupar_por_pulsos(crudos, pulsos, duracion))


def _mayoritario(crudos: list[Segmento], a: float, b: float, desde: int = 0) -> str | None:
    """El acorde que más suena dentro de [a, b). `crudos` tiene que estar ordenado."""
    tiempos: dict[str, float] = {}
    for s, e, etiqueta in crudos[desde:]:
        if s >= b:
            break
        solapa = min(e, b) - max(s, a)
        if solapa > 0:
            tiempos[etiqueta] = tiempos.get(etiqueta, 0.0) + solapa
    return max(tiempos, key=tiempos.get) if tiempos else None


def _sin_cortos(segmentos: list[Segmento], minimo: float) -> list[Segmento]:
    """Absorbe los segmentos de menos de `minimo` segundos en el anterior (o el siguiente)."""
    salida: list[Segmento] = []
    pendiente = None  # inicio de un segmento corto al principio, que se pasa al siguiente
    for a, b, etiqueta in segmentos:
        if pendiente is not None:
            a, pendiente = pendiente, None
        if b - a < minimo:
            if salida:
                salida[-1] = (salida[-1][0], b, salida[-1][2])
            else:
                pendiente = a
            continue
        salida.append((a, b, etiqueta))
    if pendiente is not None and segmentos:
        salida.append((pendiente, segmentos[-1][1], segmentos[-1][2]))
    return salida


def agrupar_por_pulsos(crudos: list[Segmento], pulsos: np.ndarray, duracion: float) -> list[Segmento]:
    """Un acorde por pulso (el que más suena en ese pulso) donde los pulsos son regulares.

    Donde no hay pulsos (antes del primero, después del último, o en huecos de más de dos
    pulsos) se dejan los segmentos del modelo, quitando solo los de menos de medio segundo.
    """
    pulsos = np.asarray([p for p in pulsos if 0 < p < duracion], dtype=float)
    if len(pulsos) < 4:
        return _sin_cortos(crudos, MINIMO_SIN_PULSOS)

    tipico = float(np.median(np.diff(pulsos)))
    celdas = [(0.0, float(pulsos[0])), *list(zip(pulsos[:-1].tolist(), pulsos[1:].tolist()))]
    celdas.append((float(pulsos[-1]), duracion))

    salida: list[Segmento] = []
    desde = 0  # primer segmento que todavía puede tocar la celda actual
    for a, b in celdas:
        if b - a <= 0:
            continue
        while desde < len(crudos) and crudos[desde][1] <= a:
            desde += 1
        if b - a <= 2 * tipico:
            etiqueta = _mayoritario(crudos, a, b, desde)
            if etiqueta is not None:
                salida.append((a, b, etiqueta))
        else:
            dentro = [(max(s, a), min(e, b), et) for s, e, et in crudos if min(e, b) - max(s, a) > 0]
            salida.extend(_sin_cortos(dentro, MINIMO_SIN_PULSOS))
    return salida


def _unir_iguales(segmentos: list[Segmento]) -> list[Segmento]:
    salida: list[Segmento] = []
    for a, b, etiqueta in segmentos:
        if salida and salida[-1][2] == etiqueta and abs(salida[-1][1] - a) < 1e-6:
            salida[-1] = (salida[-1][0], b, etiqueta)
        else:
            salida.append((a, b, etiqueta))
    return salida
