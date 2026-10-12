"""Servidor web local (solo escucha en 127.0.0.1: nada sale de tu PC)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .analisis import pipeline
from .analisis.audio import ErrorDeAudio

WEB = Path(__file__).parent / "web"
DATOS = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "analizador-musical"
CACHE = DATOS / "cache"
SUBIDAS = DATOS / "subidas"
TAMANO_MAXIMO = 1024**3  # 1 GB
MAXIMO_TRABAJOS = 30

log = logging.getLogger("analizador")

_trabajos: dict[str, dict] = {}
_candado = threading.Lock()
_ejecutor = ThreadPoolExecutor(max_workers=1)  # un análisis por vez: los modelos usan todo el CPU
_modelos_listos = threading.Event()


def _precargar() -> None:
    try:
        pipeline.precargar()
    except Exception:
        log.exception("No se pudieron cargar los modelos")
    finally:
        _modelos_listos.set()


@asynccontextmanager
async def _ciclo_de_vida(_app: FastAPI):
    CACHE.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(SUBIDAS, ignore_errors=True)  # restos de una sesión anterior
    SUBIDAS.mkdir(parents=True, exist_ok=True)
    _ejecutor.submit(_precargar)
    yield
    _ejecutor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Analizador musical", docs_url=None, redoc_url=None, lifespan=_ciclo_de_vida)
app.mount("/static", StaticFiles(directory=WEB), name="static")

MENSAJE_GRANDE = "El archivo es demasiado grande (máximo 1 GB)."


@app.middleware("http")
async def _limitar_tamano(request: Request, call_next):
    # Se rechaza antes de recibir el cuerpo: si no, el archivo entero se escribe en disco igual.
    largo = request.headers.get("content-length", "")
    if request.method == "POST" and largo.isdigit() and int(largo) > TAMANO_MAXIMO + (1 << 20):
        return JSONResponse({"detail": MENSAJE_GRANDE}, status_code=413)
    respuesta = await call_next(request)
    # Que el navegador siempre pregunte si hay una versión nueva de la página (si no, después
    # de actualizar la app puede seguir usando el app.js viejo que tenía guardado)
    respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta


@app.get("/")
def inicio():
    return FileResponse(WEB / "index.html")


def _registrar_trabajo(id_: str, **campos) -> None:
    with _candado:
        _trabajos[id_] = {"estado": "en_cola", "paso": "En espera", "progreso": 0.0, **campos}
        # Se descartan los más viejos, pero nunca uno que todavía está en cola o analizándose
        terminados = [k for k, t in _trabajos.items() if t["estado"] in ("listo", "error")]
        while len(_trabajos) > MAXIMO_TRABAJOS and terminados:
            _trabajos.pop(terminados.pop(0))


def _extension_segura(nombre: str) -> str:
    """'.MP4' -> '.mp4'; descarta caracteres que Windows no acepta (ffmpeg igual mira el contenido)."""
    return re.sub(r"[^a-z0-9.]", "", Path(nombre).suffix.lower())[:10]


def _actualizar(id_: str, **campos) -> None:
    with _candado:
        if id_ in _trabajos:
            _trabajos[id_].update(campos)


def _leer_cache(ruta: Path) -> dict | None:
    try:
        resultado = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return resultado if resultado.get("version") == pipeline.VERSION else None


@app.post("/api/analisis")
async def subir(archivo: UploadFile):
    nombre = Path(archivo.filename or "cancion").name or "cancion"
    id_ = uuid.uuid4().hex[:12]
    carpeta = SUBIDAS / id_
    # Nombre neutro en disco: evita problemas de ffmpeg con caracteres raros
    destino = carpeta / ("entrada" + _extension_segura(nombre))

    huella, total = hashlib.sha256(), 0
    try:
        carpeta.mkdir(parents=True, exist_ok=True)
        with open(destino, "wb") as f:
            while bloque := await archivo.read(1 << 20):
                total += len(bloque)
                if total > TAMANO_MAXIMO:
                    break
                huella.update(bloque)
                f.write(bloque)
    except OSError as e:
        shutil.rmtree(carpeta, ignore_errors=True)
        log.exception("No se pudo guardar la subida")
        raise HTTPException(500, f"No pude guardar el archivo en el disco: {e.strerror or e}") from e
    if total > TAMANO_MAXIMO:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise HTTPException(413, MENSAJE_GRANDE)
    if total == 0:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise HTTPException(400, "El archivo está vacío.")

    ruta_cache = CACHE / f"{huella.hexdigest()}.json"
    guardado = _leer_cache(ruta_cache)
    if guardado is not None:
        shutil.rmtree(carpeta, ignore_errors=True)
        guardado["archivo"]["nombre"] = nombre
        guardado["desde_cache"] = True
        _registrar_trabajo(id_, nombre=nombre, estado="listo", paso="Listo", progreso=1.0, resultado=guardado)
    else:
        _registrar_trabajo(id_, nombre=nombre)
        _ejecutor.submit(_analizar, id_, destino, nombre, ruta_cache)
    return {"id": id_}


def _analizar(id_: str, ruta: Path, nombre: str, ruta_cache: Path) -> None:
    def progreso(paso: str, fraccion: float) -> None:
        _actualizar(id_, estado="procesando", paso=paso, progreso=round(fraccion, 3))

    try:
        resultado = pipeline.analizar(ruta, progreso)
        resultado["archivo"]["nombre"] = nombre
        try:
            ruta_cache.write_text(json.dumps(resultado, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("No se pudo guardar el análisis en caché", exc_info=True)
        _actualizar(id_, estado="listo", paso="Listo", progreso=1.0, resultado=resultado)
    except ErrorDeAudio as e:
        _actualizar(id_, estado="error", error=str(e))
    except Exception as e:
        log.exception("Falló el análisis de %s", nombre)
        _actualizar(id_, estado="error", error=f"Error inesperado al analizar: {e}")
    finally:
        shutil.rmtree(ruta.parent, ignore_errors=True)


@app.get("/api/analisis/{id_}")
def estado(id_: str):
    with _candado:
        trabajo = dict(_trabajos.get(id_) or {})
    if not trabajo:
        raise HTTPException(404, "No existe ese análisis (¿se reinició el servidor?).")
    if trabajo["estado"] == "en_cola" and not _modelos_listos.is_set():
        trabajo["paso"] = "Cargando los modelos (la primera vez tarda un poco)"
    return trabajo
