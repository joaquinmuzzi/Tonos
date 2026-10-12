"""Tonalidad con S-KEY (Deezer, ICASSP 2025; código MIT) y afinación con librosa."""

from __future__ import annotations

import contextlib
import io
from functools import lru_cache

import librosa
import numpy as np
import torch
import torchaudio

from .notation import nombre_tonalidad, parsear_tonalidad_skey, relativa

VENTANA = 30.0  # segundos, para ver si la tonalidad cambia a lo largo de la canción
SALTO_VENTANA = 15.0
LARGO_DE_UNA_VEZ = 6 * 60.0  # más largo que esto, la tonalidad global sale del promedio de ventanas


@lru_cache(maxsize=1)
def _modelo():
    from skey.key_detection import key_map, load_checkpoint, load_model_components

    ckpt = load_checkpoint(None)
    with contextlib.redirect_stdout(io.StringIO()):  # nnAudio imprime detalles internos
        hcqt, chromanet, recorte = load_model_components(ckpt, torch.device("cpu"))
    clases = [parsear_tonalidad_skey(key_map[i]) for i in range(24)]
    return hcqt, chromanet, recorte, int(ckpt["audio"]["sr"]), clases


def precargar() -> None:
    _modelo()


def _probabilidades(hcqt, chromanet, recorte, onda: torch.Tensor) -> np.ndarray:
    """Igual que skey.key_detection.infer_key, pero devuelve las 24 probabilidades."""
    with torch.no_grad():
        cqt = recorte(hcqt(onda.unsqueeze(0)), torch.zeros(1))
        return chromanet(cqt).mean(dim=0).numpy()


def _describir(tonica_pc: int, modo: str, prob: float) -> dict:
    return {
        "tonica_pc": tonica_pc,
        "modo": modo,
        "probabilidad": round(float(prob), 3),
        **nombre_tonalidad(tonica_pc, modo),
    }


def detectar_tonalidad(senal: np.ndarray, fs: int) -> dict:
    hcqt, chromanet, recorte, sr_modelo, clases = _modelo()
    onda = torch.from_numpy(np.ascontiguousarray(senal, dtype=np.float32)).unsqueeze(0)
    if fs != sr_modelo:
        onda = torchaudio.functional.resample(onda, fs, sr_modelo)
    onda = onda / onda.abs().max().clamp_min(1e-9)
    duracion = onda.shape[1] / sr_modelo

    ventanas = _ventanas(onda, sr_modelo)
    if duracion > LARGO_DE_UNA_VEZ and ventanas:
        # En canciones largas, la transformada de toda la señal ocupa varios GB de memoria:
        # se usa el promedio de las ventanas (el modelo se entrenó con trozos de 15 s).
        pesos = [fin - inicio for inicio, fin, _ in ventanas]
        probs = np.average([p for _, _, p in ventanas], axis=0, weights=pesos)
    else:
        probs = _probabilidades(hcqt, chromanet, recorte, onda)
    orden = np.argsort(probs)[::-1]
    tonica, modo = clases[orden[0]]
    principal = _describir(tonica, modo, probs[orden[0]])

    rel = relativa(tonica, modo)
    idx_rel = clases.index(rel)
    alternativas = [{**_describir(*rel, probs[idx_rel]), "motivo": "relativa"}]
    for i in orden[1:3]:
        if i != idx_rel:
            alternativas.append({**_describir(*clases[i], probs[i]), "motivo": "segunda opción del modelo"})
            break

    return {
        "principal": principal,
        "confianza": None,  # se completa con evaluar_confianza() cuando están los acordes
        # Cuántas veces más probable es la primera opción que la segunda
        "ventaja": round(float(probs[orden[0]] / max(probs[orden[1]], 1e-6)), 2),
        "alternativas": alternativas,
        "por_tramos": _por_tramos(ventanas, duracion, clases, (tonica, modo)),
    }


# Perfiles tonales de Krumhansl y Kessler (1982): cuánto "pertenece" cada grado a la tonalidad
_KK_MAYOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MENOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def tonalidad_desde_acordes(acordes: list[tuple[float, float, str]]) -> tuple[int, str] | None:
    """Segundo método, independiente de S-KEY: deduce la tonalidad de las notas de los acordes."""
    import mir_eval

    perfil = np.zeros(12)
    for inicio, fin, etiqueta in acordes:
        if etiqueta in ("N", "X"):
            continue
        raiz, mapa, _ = mir_eval.chord.encode(etiqueta, reduce_extended_chords=True)
        if raiz < 0:
            continue
        notas = np.roll(mapa.astype(float), raiz)
        notas[raiz] += 1.0  # la fundamental pesa el doble
        perfil += (fin - inicio) * notas
    if np.ptp(perfil) == 0:  # sin acordes, o un perfil plano: no hay nada que correlacionar
        return None
    candidatas = [
        (float(np.corrcoef(perfil, np.roll(plantilla, tonica))[0, 1]), tonica, modo)
        for tonica in range(12)
        for modo, plantilla in (("mayor", _KK_MAYOR), ("menor", _KK_MENOR))
    ]
    _, tonica, modo = max(candidatas)
    return tonica, modo


def evaluar_confianza(ton: dict, desde_acordes: tuple[int, str] | None) -> None:
    """Combina la ventaja del modelo con el acuerdo del segundo método (modifica `ton`)."""
    p = ton["principal"]
    global_ = (p["tonica_pc"], p["modo"])
    if desde_acordes is None:
        acuerdo = None
    elif desde_acordes == global_:
        acuerdo = "igual"
    elif desde_acordes == relativa(*global_):
        acuerdo = "relativa"
    else:
        acuerdo = "distinta"

    ventaja = ton["ventaja"]
    if acuerdo is None:
        # Sin acordes (solo percusión, ruido, voz hablada...) la tonalidad no tiene sentido
        confianza = "baja"
    elif acuerdo == "igual" and ventaja >= 1.3:
        confianza = "alta"
    elif acuerdo == "igual" or (acuerdo == "relativa" and ventaja >= 1.5) or ventaja >= 2.5:
        confianza = "media"
    else:
        confianza = "baja"
    # Si más de la mitad de la canción suena en otra tonalidad, no puede ser "alta"
    tramos = ton["por_tramos"]
    if confianza == "alta" and tramos["acuerdo"] is not None and tramos["acuerdo"] < 0.5:
        confianza = "media"

    ton["confianza"] = confianza
    ton["segundo_metodo"] = (
        {"acuerdo": acuerdo, **nombre_tonalidad(*desde_acordes)} if desde_acordes else None
    )


def _ventanas(onda: torch.Tensor, sr: int) -> list[tuple[float, float, np.ndarray]]:
    """Probabilidades de S-KEY en ventanas de 30 s (cada 15 s): [(inicio, fin, probs), ...]."""
    hcqt, chromanet, recorte, _, _ = _modelo()
    n = onda.shape[1]
    largo, paso = int(VENTANA * sr), int(SALTO_VENTANA * sr)
    salida = []
    for ini in range(0, max(n - largo // 2, 1), paso):
        trozo = onda[:, ini : ini + largo]
        if trozo.shape[1] < largo // 2 or float(trozo.abs().max()) < 1e-3:
            continue
        trozo = trozo / trozo.abs().max()
        salida.append((ini / sr, min(ini + largo, n) / sr, _probabilidades(hcqt, chromanet, recorte, trozo)))
    return salida


def _por_tramos(ventanas: list, duracion: float, clases: list, global_: tuple[int, str]) -> dict:
    """Detecta posibles cambios de tonalidad a lo largo de la canción."""
    if duracion < VENTANA * 1.5:
        return {"tramos": [], "acuerdo": None, "cambios": []}

    rel = relativa(*global_)
    tramos = []
    for inicio, fin, probs in ventanas:
        i = int(np.argmax(probs))
        tonica, modo = clases[i]
        tramos.append(
            {
                "inicio": round(inicio, 1),
                "fin": round(fin, 1),
                "tonica_pc": tonica,
                "modo": modo,
                "probabilidad": round(float(probs[i]), 3),
                **nombre_tonalidad(tonica, modo),
            }
        )

    def misma(t):
        return (t["tonica_pc"], t["modo"]) in (global_, rel)

    acuerdo = sum(misma(t) for t in tramos) / len(tramos) if tramos else None

    # Cambio: al menos 3 ventanas seguidas (~60 s) en otra tonalidad que no sea la relativa
    cambios = []
    i = 0
    while i < len(tramos):
        if misma(tramos[i]):
            i += 1
            continue
        clave = (tramos[i]["tonica_pc"], tramos[i]["modo"])
        j = i
        while j + 1 < len(tramos) and (tramos[j + 1]["tonica_pc"], tramos[j + 1]["modo"]) == clave:
            j += 1
        if j - i + 1 >= 3:
            cambios.append(
                {k: tramos[i][k] for k in ("inicio", "tonica_pc", "modo", "latino", "americano")}
                | {"fin": tramos[j]["fin"]}
            )
        i = j + 1

    return {
        "tramos": tramos,
        "acuerdo": round(acuerdo, 2) if acuerdo is not None else None,
        "cambios": cambios,
    }


def estimar_afinacion(senal: np.ndarray, fs: int) -> dict:
    """Desvío respecto de La = 440 Hz, en cents (centésimos de semitono)."""
    trozo = senal[: fs * 90]  # alcanza con el primer minuto y medio
    desvio = float(librosa.estimate_tuning(y=trozo, sr=fs)) * 100
    aviso = None
    if abs(desvio) >= 25:
        direccion = "más aguda" if desvio > 0 else "más grave"
        aviso = (
            f"La grabación está {abs(desvio):.0f} cents {direccion} que la afinación estándar "
            "(La = 440 Hz). Con un desvío así, la tonalidad y los acordes pueden salir "
            "corridos medio tono."
        )
    return {"cents": round(desvio), "aviso": aviso}
