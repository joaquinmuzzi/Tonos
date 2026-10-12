"""Pulsos, primeros tiempos, tempo y compás.

- Pulsos y primeros tiempos: Beat This! (CPJKU, ISMIR 2024; MIT).
- Tempo: se calcula a partir de los pulsos (promedio de los intervalos válidos) y se
  compara con un segundo método independiente (librosa).
- Compás: ninguna herramienta abierta lo da directamente. Se cuenta cuántos pulsos hay
  entre primeros tiempos consecutivos, se contrasta con cada cuántos pulsos se repite la
  armonía (periodicidad.py) y se mira si cada pulso se divide en 2 o en 3.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

import librosa
import numpy as np

SALTO = 256  # muestras por cuadro de la envolvente de ataques (~11.6 ms a 22050 Hz)


@lru_cache(maxsize=1)
def _modelo():
    from beat_this.inference import Audio2Beats

    return Audio2Beats(checkpoint_path="final0", device="cpu", dbn=False)


def precargar() -> None:
    _modelo()


def detectar_pulsos(senal: np.ndarray, fs: int) -> tuple[np.ndarray, np.ndarray]:
    pulsos, primeros = _modelo()(senal, fs)
    return np.asarray(pulsos, dtype=float), np.asarray(primeros, dtype=float)


def envolvente_de_ataques(senal: np.ndarray, fs: int) -> np.ndarray:
    return librosa.onset.onset_strength(y=senal, sr=fs, hop_length=SALTO)


def unificar_pulsos(pulsos: np.ndarray, primeros: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict]:
    """Deja una sola grilla de pulsos, al tempo que domina la canción.

    El detector a veces pasa a marcar el doble de pulsos en un tramo (210 BPM en una canción
    a 105), se saltea algunos o los pone corridos en un redoble. Con la grilla despareja no se
    pueden contar compases, así que:
    1. en los tramos al doble se deja un pulso de cada dos (el que sigue la cuenta que venía);
    2. si entre dos pulsos regulares hay un tramo irregular corto (hasta 8 pulsos) que dura un
       número entero de pulsos (por ejemplo 2,22 s = 4 pulsos de 0,555 s, marcados 0,42 / 0,40 /
       0,72 / 0,68), esos pulsos se reparten parejos; así también se rellenan los salteados.
    Un tramo que no dura un número entero de pulsos (un calderón, un corrimiento real) y las
    secciones a otro tempo no se tocan.
    """
    if len(pulsos) < 8:
        return pulsos, primeros, {"quitados": 0, "agregados": 0}
    tipico = float(np.median(np.diff(pulsos)))

    sin_dobles = [float(pulsos[0])]
    quitados = agregados = 0
    for t in pulsos[1:]:
        if float(t) - sin_dobles[-1] < 0.6 * tipico:  # pulso de más
            quitados += 1
            continue
        sin_dobles.append(float(t))
    grilla = np.asarray(sin_dobles)

    def regular(d: float) -> bool:
        return 0.85 * tipico <= d <= 1.15 * tipico

    salida = [float(grilla[0])]
    i = 0
    while i < len(grilla) - 1:
        if regular(grilla[i + 1] - grilla[i]):
            salida.append(float(grilla[i + 1]))
            i += 1
            continue
        # Tramo irregular: de grilla[i] hasta el pulso desde el que la grilla vuelve a ser regular
        j = i + 1
        while j < len(grilla) - 1 and not regular(grilla[j + 1] - grilla[j]):
            j += 1
        duracion = float(grilla[j] - grilla[i])
        k = round(duracion / tipico)
        # Solo tramos cortos: uno largo es una sección a otro tempo (y cualquier duración larga
        # "entra" en un número entero de pulsos)
        if 1 <= k <= 8 and abs(duracion - k * tipico) <= 0.25 * tipico:
            salida.extend((grilla[i] + duracion * np.arange(1, k) / k).tolist())
            agregados += max(0, (k - 1) - (j - i - 1))
            quitados += max(0, (j - i - 1) - (k - 1))
        else:
            # El tramo entero no cierra (por ejemplo, un compás medio pulso más corto junto a
            # un pulso perdido): se rellenan solo los huecos que sí son un número entero de pulsos
            for a, b in zip(grilla[i:j], grilla[i + 1: j + 1]):
                hueco = float(b - a)
                m = round(hueco / tipico)
                if 2 <= m <= 8 and abs(hueco - m * tipico) <= 0.25 * tipico:
                    salida.extend((a + hueco * np.arange(1, m) / m).tolist())
                    agregados += m - 1
                if b != grilla[j]:
                    salida.append(float(b))
        salida.append(float(grilla[j]))
        i = j
    nuevos = np.asarray(salida)
    # Cada primer tiempo pasa al pulso más cercano de la grilla nueva
    cercanos = [float(nuevos[np.argmin(np.abs(nuevos - p))]) for p in primeros]
    primeros_nuevos = np.unique([c for c, p in zip(cercanos, primeros) if abs(c - p) <= 0.25 * tipico])
    return nuevos, primeros_nuevos, {"quitados": quitados, "agregados": agregados}


# --- Tempo -------------------------------------------------------------------


def _periodo(intervalos: np.ndarray) -> float:
    """Promedio de los intervalos a ±10 % de la mediana (ignora pulsos salteados o de más)."""
    mediana = float(np.median(intervalos))
    validos = intervalos[np.abs(intervalos - mediana) <= 0.10 * mediana]
    return float(np.mean(validos)) if len(validos) else mediana


def analizar_tempo(pulsos: np.ndarray, envolvente: np.ndarray, fs: int) -> dict:
    if len(pulsos) < 8:
        return {"bpm": None, "motivo": "Se detectaron muy pocos pulsos para estimar el tempo."}

    intervalos = np.diff(pulsos)
    mediana = float(np.median(intervalos))
    # Beat This! entrega los pulsos en una grilla de 20 ms, así que cada intervalo viene
    # redondeado y la mediana también (170 BPM saldría 166,7). El promedio de los intervalos
    # válidos no arrastra ese redondeo: los errores de cada pulso se compensan.
    bpm = 60.0 / _periodo(intervalos)

    # Tempo local: misma cuenta sobre ventanas de 8 intervalos
    locales = np.array([60.0 / _periodo(intervalos[max(0, i - 4): i + 4]) for i in range(len(intervalos))])
    p10, p90 = (float(x) for x in np.percentile(locales, [10, 90]))
    variacion = (p90 - p10) / bpm
    # Regularidad: proporción de pulsos a ±10 % del intervalo típico
    regularidad = float(np.mean(np.abs(intervalos - mediana) <= 0.10 * mediana))

    paso = max(1, len(locales) // 150)
    curva = [[round(float(t), 2), round(float(b), 1)] for t, b in zip(pulsos[1::paso], locales[::paso])]

    # Segundo método independiente (autocorrelación de la envolvente de ataques)
    bpm_librosa = float(
        librosa.feature.tempo(onset_envelope=envolvente, sr=fs, hop_length=SALTO)[0]
    )
    relacion = None
    for factor, nombre in ((1, "igual"), (2, "doble"), (0.5, "mitad"), (3, "triple"), (1 / 3, "tercio")):
        if abs(bpm_librosa - bpm * factor) <= 0.04 * bpm * factor:
            relacion = nombre
            break

    # Fuera del rango habitual, lo más probable es que se sienta al doble o a la mitad
    sugerencia = "doble" if bpm < 55 else "mitad" if bpm > 200 else None

    if regularidad >= 0.85 and relacion in ("igual", "doble", "mitad"):
        confianza = "alta"
    elif regularidad >= 0.7:
        confianza = "media"
    else:
        confianza = "baja"

    return {
        "bpm": round(bpm, 1),
        "confianza": confianza,
        "alternativas": {"mitad": round(bpm / 2, 1), "doble": round(bpm * 2, 1)},
        "sugerencia": sugerencia,
        "rango": [round(p10, 1), round(p90, 1)],
        "estable": bool(variacion < 0.08),
        "regularidad": round(regularidad, 2),
        "curva": curva,
        "segundo_metodo": {"bpm": round(bpm_librosa, 1), "relacion": relacion},
    }


# --- Compás ------------------------------------------------------------------


def pulsos_por_compas(pulsos: np.ndarray, primeros: np.ndarray) -> list[int]:
    """Cantidad de pulsos de cada compás completo (entre dos primeros tiempos)."""
    if len(primeros) < 2:
        return []
    indices = np.searchsorted(pulsos, primeros)
    cuentas = np.diff(indices)
    return [int(c) for c in cuentas if c > 0]


def regularizar_compases(pulsos: np.ndarray, primeros: np.ndarray, n: int | None) -> tuple[np.ndarray, int]:
    """Arregla compases cortados por un primer tiempo de más, de menos o corrido.

    Si varios compases seguidos no tienen `n` pulsos pero entre todos suman un múltiplo de n
    (3+1, 1+3, 3+5, 2+2, uno de 8...), se rearman en compases parejos de n pulsos desde el
    primero. Un compás distinto aislado (un 3 entre compases de 4) se deja como está, porque
    puede ser un cambio de compás real. Devuelve (primeros tiempos, tramos rearmados).
    """
    if not n or n < 2 or len(primeros) < 3:
        return primeros, 0
    indices = np.searchsorted(pulsos, primeros)
    largos = np.diff(indices)
    nuevos = [int(indices[0])]
    rearmados = 0
    k = 0
    while k < len(largos):
        if largos[k] == n:
            nuevos.append(int(indices[k + 1]))
            k += 1
            continue
        total, m = 0, k
        while m < len(largos) and largos[m] != n:
            total += int(largos[m])
            m += 1
            if total % n == 0:
                break
        if total % n == 0:
            nuevos.extend(range(int(indices[k]) + n, int(indices[k]) + total + 1, n))
            rearmados += 1
        else:
            nuevos.extend(int(i) for i in indices[k + 1: m + 1])
        k = m
    return pulsos[np.asarray(nuevos)], rearmados


def _valor(envolvente: np.ndarray, t: float, fs: int) -> float:
    """Máximo de la envolvente en ±2 cuadros (±23 ms) alrededor del instante t."""
    centro = int(round(t * fs / SALTO))
    ini, fin = max(0, centro - 2), min(len(envolvente), centro + 3)
    return float(envolvente[ini:fin].max()) if fin > ini else 0.0


def analizar_subdivision(pulsos: np.ndarray, envolvente: np.ndarray, fs: int) -> dict:
    """¿Cada pulso se divide en 2 (binaria) o en 3 (ternaria)?

    Compara la energía de ataques a 1/2 del pulso contra la de 1/3 y 2/3.
    Es una pista, no un veredicto: el swing y el shuffle también suenan ternarios.
    """
    binaria, ternaria, entre = [], [], []
    for b0, b1 in zip(pulsos[:-1], pulsos[1:]):
        d = b1 - b0
        if not 0.15 < d < 2.0:
            continue
        binaria.append(_valor(envolvente, b0 + d / 2, fs))
        ternaria.append((_valor(envolvente, b0 + d / 3, fs) + _valor(envolvente, b0 + 2 * d / 3, fs)) / 2)
        # Referencia: puntos que no caen en ninguna de las dos grillas (ni 1/3, 1/2, 2/3, ni 1/4, 3/4)
        entre.append((_valor(envolvente, b0 + 0.42 * d, fs) + _valor(envolvente, b0 + 0.58 * d, fs)) / 2)
    if len(binaria) < 8:
        return {"tipo": "no clara", "razon": None}

    b, t = float(np.median(binaria)), float(np.median(ternaria))
    fondo = float(np.median(entre)) + 1e-6  # mismo estadístico (máximo en ±2 cuadros) que b y t
    razon = (t + 1e-6) / (b + 1e-6)
    if max(b, t) < 1.15 * fondo:
        tipo = "no clara"
    elif razon >= 1.25:
        tipo = "ternaria"
    elif razon <= 0.80:
        tipo = "binaria"
    else:
        tipo = "no clara"
    return {"tipo": tipo, "razon": round(razon, 2)}


_LECTURAS = {
    (4, "binaria"): ("4/4", None),
    (4, "no clara"): ("4/4", None),
    # (4, "ternaria") depende del tempo: ver _lectura()
    (2, "binaria"): ("2/4", "o 4/4 contado más rápido"),
    (2, "no clara"): ("2/4", "o 6/8"),
    (2, "ternaria"): ("6/8", "o 2/4 con tresillos"),
    (3, "binaria"): ("3/4", "o 6/8"),
    (3, "no clara"): ("3/4", "o 6/8"),
    (3, "ternaria"): ("3/4", "o 9/8, o 6/8"),
    (6, "binaria"): ("6/8", "o 3/4"),
    (6, "no clara"): ("6/8", "o 3/4"),
    (6, "ternaria"): ("6/8", "o 3/4"),
}

AVISO_TERNARIO = (
    "El 3/4 y el 6/8 se confunden con mucha facilidad (y en la chacarera o la zamba se "
    "alternan a propósito). Ninguna herramienta automática los distingue bien: escuchá si "
    "el pulso que marcás con el pie se divide en 2 o en 3."
)


def _lectura(n: int, subdivision: str, bpm: float | None) -> tuple[str, str | None]:
    if n == 4 and subdivision == "ternaria":
        # Rápido con pulso en tres = swing/shuffle (se escribe 4/4); lento = balada en 12/8
        if bpm is not None and bpm < 80:
            return "12/8", "o 4/4 con tresillos"
        return "4/4 con swing", "o shuffle; también se puede escribir en 12/8"
    if (n, subdivision) in _LECTURAS:
        return _LECTURAS[(n, subdivision)]
    if n in (5, 7):
        return f"{n}/4", f"o {n}/8 (compás irregular)"
    return f"{n} pulsos por compás", "compás poco común: tomalo con pinzas"


def _sin_compas(subdivision: dict, motivo: str, segundo_metodo: dict | None = None) -> dict:
    return {"pulsos_por_compas": None, "lectura": None, "alternativa": None, "confianza": "baja",
            "motivo": motivo, "subdivision": subdivision, "avisos": [], "fuente": None,
            "segundo_metodo": segundo_metodo}


_NIVELES = ["baja", "media", "alta"]
# Compases que el método de periodicidad no distingue entre sí (2 y 4 se repiten igual cada 4)
_FAMILIA = {2: 4, 4: 4, 8: 4, 3: 3, 6: 3, 9: 3, 5: 5, 10: 5, 7: 7}


def comparar_con_periodicidad(n: int | None, periodicidad: dict | None) -> dict | None:
    """¿El segundo método (repetición de la armonía) confirma, contradice o completa el conteo?

    El detector de primeros tiempos distingue bien 3/4 de 4/4, pero casi no vio compases de
    5 ni de 7 al entrenarse y los fuerza a 4. Por eso el segundo método solo se impone cuando
    encuentra 5 o 7 (o cuando el conteo no sirvió), y con evidencia clara: que gane por
    bastante y que la armonía también esté de su lado. Entre 3 y 4 solo puede avisar.
    """
    if periodicidad is None:
        return None
    puntajes, armonia, ganador = periodicidad["puntajes"], periodicidad["armonia"], periodicidad["ganador"]
    familia = _FAMILIA.get(n) if n else None
    salida = {"pulsos": ganador, "puntajes": puntajes, "confirma": False, "reemplaza": False,
              "contradice": False, "fuerte": False}
    if familia == ganador:
        salida["confirma"] = periodicidad["margen"] >= 0.5
        return salida
    if familia is None:  # el conteo no sirvió (o dio un compás raro): alcanza con que gane claro
        ventaja = periodicidad["margen"]
        clara = puntajes[ganador] >= 0.3 and ventaja >= 0.3
    else:
        ventaja = puntajes[ganador] - puntajes[familia]
        clara = puntajes[ganador] >= 0.3 and ventaja >= 0.6 and armonia[ganador] > armonia[familia]
    salida["reemplaza"] = clara and (familia is None or ganador in (5, 7))
    salida["contradice"] = clara and not salida["reemplaza"]
    salida["fuerte"] = ventaja >= 1.0 and armonia[ganador] >= 0.8
    return salida


def limitar_confianza(confianza: str, tope: str | None) -> str:
    if tope in _NIVELES:
        return _NIVELES[min(_NIVELES.index(confianza), _NIVELES.index(tope))]
    return confianza


def analizar_compas(pulsos: np.ndarray, primeros: np.ndarray, subdivision: dict,
                    bpm: float | None = None, confianza_tempo: str | None = None,
                    periodicidad: dict | None = None) -> dict:
    cuentas = pulsos_por_compas(pulsos, primeros)
    conteo = Counter(cuentas)
    n, veces = conteo.most_common(1)[0] if cuentas else (None, 0)
    acuerdo = veces / len(cuentas) if cuentas else 0.0
    conteo_valido = len(cuentas) >= 4 and n is not None and n >= 2
    segundo = comparar_con_periodicidad(n if conteo_valido else None, periodicidad)
    reemplaza = bool(segundo and segundo["reemplaza"])

    if not conteo_valido and not reemplaza:
        if len(cuentas) < 4:
            motivo = "No se detectaron suficientes primeros tiempos para estimar el compás."
        else:
            motivo = ("Casi todos los pulsos detectados quedaron marcados como primer tiempo, así que "
                      "no se pudo contar el compás. Pasa con música muy libre o con mucho rubato.")
        return _sin_compas(subdivision, motivo, segundo)

    avisos = []
    if reemplaza:
        # El conteo de primeros tiempos se descarta: manda la repetición de la armonía
        g = segundo["pulsos"]
        lectura, alternativa = _lectura(g, subdivision["tipo"], bpm)
        confianza = "media" if segundo["fuerte"] else "baja"
        if conteo_valido:
            avisos.append(
                f"El detector de primeros tiempos marcó compases de {n} pulsos, pero la armonía y el "
                f"bajo se repiten cada {g} pulsos: lo más probable es que el compás sea de {g}. Los "
                "detectores automáticos se entrenaron casi solo con música en 4/4 y tienden a forzarlo."
            )
        else:
            avisos.append(
                f"Los primeros tiempos detectados no alcanzaron para contar el compás, pero la armonía "
                f"y el bajo se repiten cada {g} pulsos."
            )
        numero, fuente = g, "periodicidad"
    else:
        lectura, alternativa = _lectura(n, subdivision["tipo"], bpm)
        if acuerdo >= 0.85:
            confianza = "alta"
        elif acuerdo >= 0.6:
            confianza = "media"
        else:
            confianza = "baja"
        if segundo and segundo["confirma"] and confianza != "alta":
            confianza = _NIVELES[_NIVELES.index(confianza) + 1]  # dos métodos independientes coinciden
        if segundo and segundo["contradice"]:
            confianza = _NIVELES[max(_NIVELES.index(confianza) - 1, 0)]
            avisos.append(
                f"Un segundo método (cada cuántos pulsos se repite la armonía) sugiere compases de "
                f"{segundo['pulsos']} pulsos: escuchalo con el clic activado para decidir."
            )
        if acuerdo < 0.6:
            avisos.append(
                "Los compases detectados no cuentan siempre lo mismo: puede que el compás cambie "
                "durante la canción o que los primeros tiempos estén mal ubicados."
            )
        numero, fuente = n, "primeros tiempos"
    # Si los pulsos mismos son dudosos, el compás (que se cuenta con ellos) no puede ser más seguro
    confianza = limitar_confianza(confianza, confianza_tempo)
    if numero in (2, 3, 6):
        avisos.insert(0, AVISO_TERNARIO)

    return {
        "pulsos_por_compas": numero,
        "lectura": lectura,
        "alternativa": alternativa,
        "fuente": fuente,
        "acuerdo": round(acuerdo, 2),
        "confianza": confianza,
        "compases_contados": len(cuentas),
        "conteo_primeros_tiempos": n,
        "distribucion": {str(k): round(v / len(cuentas), 2) for k, v in sorted(conteo.items())},
        "subdivision": subdivision,
        "segundo_metodo": segundo,
        "avisos": avisos,
    }


def compases(pulsos: np.ndarray, primeros: np.ndarray, duracion: float) -> list[dict]:
    """Celdas [inicio, fin) para mostrar los acordes compás por compás.

    - Con primeros tiempos: un compás entre cada par. Lo que suena antes del primero es la
      anacrusa (si dura menos de un compás) o la intro (compás 0).
    - Sin primeros tiempos: tramos de 4 pulsos, o de 4 segundos si tampoco hay pulsos, para
      que los acordes se puedan ver igual.
    """
    if len(primeros):
        bordes = [float(x) for x in primeros]
        tipo = "compás"
        largo_tipico = float(np.median(np.diff(primeros))) if len(primeros) > 1 else 2.0
    elif len(pulsos) >= 4:
        bordes = [float(x) for x in pulsos[::4]]
        tipo = "tramo"
        largo_tipico = 4 * float(np.median(np.diff(pulsos)))
    else:
        bordes = [float(x) for x in np.arange(0.0, duracion, 4.0)]
        tipo = "tramo"
        largo_tipico = 4.0

    salida = []
    if bordes and bordes[0] > 0.3:
        etiqueta = "anacrusa" if tipo == "compás" and bordes[0] < 1.05 * largo_tipico else "intro"
        salida.append({"numero": 0, "etiqueta": etiqueta, "inicio": 0.0, "fin": bordes[0]})
    bordes.append(duracion)
    for i, (ini, fin) in enumerate(zip(bordes[:-1], bordes[1:]), start=1):
        if fin - ini > 0.05:
            salida.append({"numero": i, "etiqueta": f"{tipo} {i}", "inicio": ini, "fin": fin})
    return salida
