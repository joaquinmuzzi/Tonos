"""Segundo método para el compás: ¿cada cuántos pulsos se repite la música?

El detector de primeros tiempos (Beat This!) se entrenó casi solo con música en 4/4 y tiende
a forzar compases de 4 aunque la canción esté en 5/4 o 7/4. Este método no usa ese detector:
mide, pulso por pulso, cuánto se parece la música a sí misma L pulsos después (armonía, bajo
y acentos) y busca qué familia de compases explica mejor las repeticiones:

    3 -> 3, 6, 9, 12...   4 -> 4, 8, 12, 16...   5 -> 5, 10, 15...   7 -> 7, 14, 21...

También ubica dónde empieza cada compás, a partir de los cambios de armonía (sin batería).
"""

from __future__ import annotations

from collections import Counter

import librosa
import numpy as np

FAMILIAS = {
    3: (3, 6, 9, 12, 15, 18, 21, 24, 27),
    4: (4, 8, 12, 16, 20, 24, 28),
    5: (5, 10, 15, 20, 25),
    7: (7, 14, 21, 28),
}
DESFASE_MAXIMO = 30  # en pulsos
PESOS = {"armonia": 0.5, "bajo": 0.25, "ataques": 0.25}
SALTO_CQT = 512
CLARIDAD_FASE = 1.0  # por debajo, la grilla de compases se informa como aproximada

# Un desfase compartido por dos familias (12 = 3 y 4) cuenta la mitad para cada una
_COMPARTIDOS = Counter(L for desfases in FAMILIAS.values() for L in desfases)


def _espectro(senal: np.ndarray, fs: int) -> np.ndarray:
    """Transformada de Q constante: 7 octavas desde Do1, un bin por semitono."""
    cqt = librosa.cqt(senal, sr=fs, hop_length=SALTO_CQT, fmin=librosa.note_to_hz("C1"), n_bins=84)
    return np.abs(cqt).astype(np.float32)


def _por_pulso(x: np.ndarray, cuadros: np.ndarray, desde: float = 0.0, hasta: float = 1.0) -> np.ndarray:
    """Promedio de cada columna de `x` dentro de cada pulso (o de una parte de cada pulso)."""
    largo = x.shape[-1]
    columnas = []
    for a, b in zip(cuadros[:-1], cuadros[1:]):
        n = max(int(b) - int(a), 1)
        i = min(int(a) + int(desde * n), largo - 1)
        j = min(max(int(a) + int(hasta * n), i + 1), largo)
        columnas.append(x[..., i:j].mean(-1))
    return np.array(columnas).T


def _plegar(m: np.ndarray) -> np.ndarray:
    """De 84 semitonos (7 octavas) a las 12 notas."""
    return m.reshape(-1, 12, m.shape[-1]).sum(0)


def _similitud(m: np.ndarray, desfase: int) -> float:
    a, b = m[:, :-desfase], m[:, desfase:]
    cos = (a * b).sum(0) / (np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0) + 1e-9)
    return float(cos.mean())


def _realce(serie: np.ndarray, misma_paridad: bool = False) -> np.ndarray:
    """Cuánto sobresale cada desfase de sus vecinos (los picos quedan positivos).

    Con `misma_paridad`, además tiene que sobresalir de los desfases ±2: así un patrón que
    se repite cada 2 pulsos (bombo y redoblante) no se cuenta como evidencia de 4.
    """
    r = np.zeros(DESFASE_MAXIMO + 1)
    for L in range(2, DESFASE_MAXIMO + 1):
        r[L] = serie[L] - (serie[L - 1] + serie[L + 1]) / 2
        if misma_paridad and L >= 3:
            r[L] = min(r[L], serie[L] - (serie[L - 2] + serie[L + 2]) / 2)
    return r


def _puntajes(realce: np.ndarray) -> dict[int, float]:
    """Promedio (en desvíos estándar) del realce sobre los desfases de cada familia."""
    z = realce / (np.std(realce[2:]) + 1e-12)
    salida = {}
    for familia, desfases in FAMILIAS.items():
        pesos = np.array([1 / _COMPARTIDOS[L] for L in desfases])
        salida[familia] = float(np.sum(pesos * z[list(desfases)]) / np.sum(pesos))
    return salida


def analizar(senal: np.ndarray, fs: int, pulsos: np.ndarray, envolvente: np.ndarray,
             salto_envolvente: int) -> tuple[dict | None, np.ndarray | None]:
    """Devuelve (resumen, espectro). El espectro se reutiliza para ubicar los compases.

    resumen = {"puntajes": {3: z, 4: z, 5: z, 7: z}, "armonia": {...}, "ganador": f,
               "margen": diferencia con la segunda familia}; None si la canción tiene
    muy pocos pulsos para medir repeticiones de hasta 30 pulsos.
    """
    if len(pulsos) < 3 * DESFASE_MAXIMO + 2:
        return None, None

    espectro = _espectro(senal, fs)
    por_pulso = _por_pulso(espectro, librosa.time_to_frames(pulsos, sr=fs, hop_length=SALTO_CQT))
    armonia, bajo = _plegar(por_pulso), _plegar(por_pulso[:36])  # bajo: las 3 octavas graves

    ataques = _por_pulso(envolvente, librosa.time_to_frames(pulsos, sr=fs, hop_length=salto_envolvente))
    ataques = ataques - np.convolve(ataques, np.ones(9) / 9, mode="same")  # sin cambios lentos de volumen
    ataques = ataques / (ataques.std() + 1e-9)

    desfases = range(DESFASE_MAXIMO + 3)
    series = {
        "armonia": np.array([_similitud(armonia, L) if L else 1.0 for L in desfases]),
        "bajo": np.array([_similitud(bajo, L) if L else 1.0 for L in desfases]),
        "ataques": np.array([float(np.mean(ataques[:-L] * ataques[L:])) if L else 1.0 for L in desfases]),
    }
    por_rasgo = {k: _puntajes(_realce(s, misma_paridad=(k == "ataques"))) for k, s in series.items()}
    total = {f: sum(PESOS[k] * por_rasgo[k][f] for k in PESOS) for f in FAMILIAS}
    orden = sorted(total, key=total.get, reverse=True)
    resumen = {
        "puntajes": {f: round(v, 2) for f, v in total.items()},
        "armonia": {f: round(v, 2) for f, v in por_rasgo["armonia"].items()},
        "ganador": orden[0],
        "margen": round(total[orden[0]] - total[orden[1]], 2),
    }
    return resumen, espectro


def _novedad(m: np.ndarray) -> np.ndarray:
    """Cuánto cambia el contenido de cada pulso respecto del anterior (0 = igual)."""
    a, b = m[:, :-1], m[:, 1:]
    cos = (a * b).sum(0) / (np.linalg.norm(a, axis=0) * np.linalg.norm(b, axis=0) + 1e-9)
    return np.concatenate([[0.0], 1 - cos])


def _z(x: np.ndarray) -> np.ndarray:
    return (x - x.mean()) / x.std() if x.std() > 1e-12 else np.zeros_like(x)


def cambios_de_acorde_por_pulso(pulsos: np.ndarray, segmentos: list[tuple[float, float, str]]) -> np.ndarray:
    """1 en cada pulso donde empieza un acorde distinto del anterior (los acordes ya vienen por pulso)."""
    marcas = np.zeros(len(pulsos))
    for (_, _, anterior), (inicio, _, etiqueta) in zip(segmentos[:-1], segmentos[1:]):
        if etiqueta in ("N", "X") or etiqueta == anterior:
            continue
        i = int(np.argmin(np.abs(pulsos - inicio)))
        if abs(pulsos[i] - inicio) < 0.15:
            marcas[i] = 1.0
    return marcas


def ubicar_compases(pulsos: np.ndarray, pulsos_por_compas: int, espectro: np.ndarray, fs: int,
                    cambios_de_acorde: np.ndarray | None = None) -> tuple[np.ndarray, float]:
    """Primeros tiempos para compases de `pulsos_por_compas`.

    Dos pistas de dónde empieza cada compás, que se suman:
    - dónde cambian los acordes reconocidos (los acordes suelen cambiar en el primer tiempo);
    - dónde más cambia la armonía de un pulso al siguiente (sin batería y en el centro de
      cada pulso, para que el bombo o el arrastre del sonido no lo corran).
    La segunda sola se equivoca cuando los acordes se anticipan medio pulso (una síncopa muy
    común): por eso pesan las dos. Si quedan saltos en los pulsos, cada tramo se ubica por
    separado; un tramo de menos de dos compases sigue la cuenta del anterior.
    Devuelve (primeros tiempos, claridad): cuánto le gana la mejor posición a la segunda.
    """
    L = pulsos_por_compas
    armonico, _ = librosa.decompose.hpss(espectro, kernel_size=(31, 9))
    centro = _por_pulso(armonico, librosa.time_to_frames(pulsos, sr=fs, hop_length=SALTO_CQT), 0.25, 0.85)
    novedad = np.append(_novedad(_plegar(centro)) + 0.5 * _novedad(_plegar(centro[:36])), 0.0)
    if cambios_de_acorde is None:
        cambios_de_acorde = np.zeros(len(pulsos))

    intervalos = np.diff(pulsos)
    tipico = float(np.median(intervalos))
    cortes = [0] + [i + 1 for i, d in enumerate(intervalos) if not 0.75 * tipico <= d <= 1.25 * tipico]
    cortes.append(len(pulsos))

    primeros, claridades, pesos = [], [], []
    for a, b in zip(cortes[:-1], cortes[1:]):
        if b - a < 2 * L and primeros:
            # Tramo corto: se sigue contando desde el último primer tiempo
            siguiente = int(np.searchsorted(pulsos, primeros[-1])) + L
            while siguiente < a:
                siguiente += L
            primeros.extend(pulsos[siguiente:b:L])
            continue
        fases = range(min(L, b - a))
        nov = np.array([novedad[a + f:b:L].mean() for f in fases])
        aco = np.array([cambios_de_acorde[a + f:b:L].mean() for f in fases])
        puntaje = _z(nov) + _z(aco)
        orden = np.argsort(puntaje)[::-1]
        fase = int(orden[0])
        if len(orden) > 1:
            claridades.append(float(puntaje[orden[0]] - puntaje[orden[1]]))
            pesos.append(b - a)
        primeros.extend(pulsos[a + fase: b: L])
    claridad = float(np.average(claridades, weights=pesos)) if pesos else 0.0
    return np.asarray(primeros, dtype=float), claridad
