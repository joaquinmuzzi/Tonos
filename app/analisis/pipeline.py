"""Une todos los análisis y arma el reporte (un dict listo para JSON)."""

from __future__ import annotations

import logging
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

import numpy as np

from . import acordes, periodicidad, ritmo, tonalidad
from .audio import obtener_audio
from .notacion import Ortografia, describir_acorde

VERSION = 5  # subirla invalida los análisis guardados en caché

Progreso = Callable[[str, float], None]


def precargar() -> None:
    """Carga los tres modelos en memoria (la primera vez descarga el de pulsos, ~77 MB)."""
    ritmo.precargar()
    tonalidad.precargar()
    acordes.precargar()
    # Algunas librerías configuran el log en modo INFO al importarse: lo bajamos a avisos.
    logging.getLogger().setLevel(logging.WARNING)


def analizar(ruta: Path, progreso: Progreso | None = None) -> dict:
    avisar = progreso or (lambda paso, fraccion: None)
    inicio = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="analizador-") as tmp:
        wav = Path(tmp) / "audio.wav"
        avisar("Extrayendo el audio", 0.02)
        senal, fs, pista = obtener_audio(ruta, wav)
        duracion = len(senal) / fs

        avisar("Buscando los pulsos y los primeros tiempos", 0.08)
        pulsos, primeros = ritmo.detectar_pulsos(senal, fs)
        pulsos, primeros, unificados = ritmo.unificar_pulsos(pulsos, primeros)
        envolvente = ritmo.envolvente_de_ataques(senal, fs)

        avisar("Calculando el tempo y el compás", 0.25)
        tempo = ritmo.analizar_tempo(pulsos, envolvente, fs)
        tempo["pulsos_unificados"] = unificados
        corregidos = unificados["quitados"] + unificados["agregados"]
        if corregidos >= 8:
            tempo["aviso"] = (
                f"En algunos tramos el detector marcó pulsos de más (el doble) o de menos: se "
                f"corrigieron {corregidos} pulsos para que la grilla quede pareja y se puedan "
                "contar los compases."
            )
        subdivision = ritmo.analizar_subdivision(pulsos, envolvente, fs)
        repeticion, espectro = periodicidad.analizar(senal, fs, pulsos, envolvente, ritmo.SALTO)
        compas = ritmo.analizar_compas(
            pulsos, primeros, subdivision, tempo.get("bpm"), tempo.get("confianza", "baja"), repeticion
        )
        del envolvente

        avisar("Buscando la tonalidad", 0.32)
        ton = tonalidad.detectar_tonalidad(senal, fs)
        afinacion = tonalidad.estimar_afinacion(senal, fs)

        avisar("Reconociendo los acordes", 0.45)
        crudos = acordes.detectar_acordes(
            wav,
            duracion,
            pulsos,
            progreso=lambda f: avisar("Reconociendo los acordes", 0.45 + 0.5 * f),
        )

        if compas["fuente"] == "primeros tiempos":
            # Compases mal cortados por un primer tiempo de más o de menos (3+1, 3+5...)
            primeros, rearmados = ritmo.regularizar_compases(pulsos, primeros, compas["pulsos_por_compas"])
            compas["compases_rearmados"] = rearmados
        elif compas["fuente"] == "periodicidad":
            # Los primeros tiempos del detector no sirven: se rearman con el compás nuevo,
            # donde cambian los acordes y la armonía
            avisar("Ubicando los compases", 0.96)
            cambios = periodicidad.cambios_de_acorde_por_pulso(pulsos, crudos)
            primeros, claridad = periodicidad.ubicar_compases(
                pulsos, compas["pulsos_por_compas"], espectro, fs, cambios
            )
            _completar_grilla(compas, claridad, tempo)
        del espectro

    avisar("Armando el reporte", 0.97)
    tonalidad.evaluar_confianza(ton, tonalidad.tonalidad_desde_acordes(crudos))
    principal = ton["principal"]
    orto = Ortografia(principal["tonica_pc"], principal["modo"])
    segmentos = [
        {"inicio": round(a, 3), "fin": round(b, 3), "etiqueta": e, **describir_acorde(e, orto)}
        for a, b, e in crudos
    ]
    lista_compases = ritmo.compases(pulsos, primeros, duracion)

    return {
        "version": VERSION,
        "archivo": {"nombre": ruta.name, "duracion": round(duracion, 2), "pista_de_audio": pista + 1},
        "segundos_de_analisis": round(time.perf_counter() - inicio, 1),
        "tempo": tempo,
        "compas": compas,
        "tonalidad": ton,
        "afinacion": afinacion,
        "acordes": {
            "segmentos": segmentos,
            "resumen": _resumen(segmentos, "latino", "americano"),
            "resumen_simple": _resumen(segmentos, "latino_simple", "americano_simple"),
        },
        "compases": _acordes_por_compas(lista_compases, segmentos, pulsos),
        "pulsos": [round(float(p), 3) for p in pulsos],
        "primeros_tiempos": [round(float(p), 3) for p in primeros],
    }


def _completar_grilla(compas: dict, claridad: float, tempo: dict) -> None:
    """Confianza y avisos de la grilla de compases rearmada por periodicidad."""
    compas["grilla_aproximada"] = claridad < periodicidad.CLARIDAD_FASE
    if claridad >= 2 * periodicidad.CLARIDAD_FASE and compas["confianza"] == "baja":
        # Los acordes cambian siempre en el mismo pulso del compás: la estructura es clara
        compas["confianza"] = ritmo.limitar_confianza("media", tempo.get("confianza", "baja"))
    if compas["grilla_aproximada"]:
        compas["avisos"].append(
            "No se pudo determinar con seguridad en qué pulso empieza cada compás: la grilla "
            "de compases es aproximada (puede estar corrida algunos pulsos)."
        )


def _resumen(segmentos: list[dict], clave_latina: str, clave_americana: str, maximo: int = 10) -> list[dict]:
    """Acordes más usados, por tiempo total que suenan."""
    total = defaultdict(float)
    nombres = {}
    for s in segmentos:
        if not s["es_acorde"]:
            continue
        total[s[clave_latina]] += s["fin"] - s["inicio"]
        nombres[s[clave_latina]] = s[clave_americana]
    suma = sum(total.values()) or 1.0
    orden = sorted(total.items(), key=lambda kv: kv[1], reverse=True)[:maximo]
    return [{"latino": k, "americano": nombres[k], "proporcion": round(v / suma, 3)} for k, v in orden]


def _acordes_por_compas(lista: list[dict], segmentos: list[dict], pulsos) -> list[dict]:
    """Para cada compás, los índices de los acordes que suenan en él (en orden)."""
    pulso_tipico = float(np.median(np.diff(pulsos))) if len(pulsos) > 1 else 0.5
    salida = []
    j = 0
    for c in lista:
        while j < len(segmentos) and segmentos[j]["fin"] <= c["inicio"]:
            j += 1
        indices = []
        k = j
        while k < len(segmentos) and segmentos[k]["inicio"] < c["fin"]:
            s = segmentos[k]
            solapamiento = min(s["fin"], c["fin"]) - max(s["inicio"], c["inicio"])
            # Se ignoran acordes que asoman menos de un tercio de pulso en el compás
            if solapamiento >= pulso_tipico / 3:
                indices.append(k)
            k += 1
        salida.append({**c, "acordes": indices})
    return salida
