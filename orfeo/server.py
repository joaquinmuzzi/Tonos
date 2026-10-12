"""Local web server (it only listens on 127.0.0.1: nothing leaves your computer)."""

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

from .analysis import pipeline
from .analysis.audio import AudioError

WEB = Path(__file__).parent / "web"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "analizador-musical"
CACHE_DIR = DATA_DIR / "cache"
UPLOAD_DIR = DATA_DIR / "subidas"
MAX_UPLOAD_BYTES = 1024**3  # 1 GB
MAX_JOBS = 30

log = logging.getLogger("analizador")

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1)  # one analysis at a time: the models use the whole CPU
_models_ready = threading.Event()


def _preload() -> None:
    try:
        pipeline.preload()
    except Exception:
        log.exception("No se pudieron cargar los modelos")
    finally:
        _models_ready.set()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)  # leftovers from a previous session
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    _executor.submit(_preload)
    yield
    _executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="Analizador musical", docs_url=None, redoc_url=None, lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")

TOO_LARGE_MESSAGE = "El archivo es demasiado grande (máximo 1 GB)."


@app.middleware("http")
async def _limit_body_size(request: Request, call_next):
    # Reject before receiving the body: otherwise the whole file is written to disk anyway.
    length = request.headers.get("content-length", "")
    if request.method == "POST" and length.isdigit() and int(length) > MAX_UPLOAD_BYTES + (1 << 20):
        return JSONResponse({"detail": TOO_LARGE_MESSAGE}, status_code=413)
    response = await call_next(request)
    # Make the browser always check for a newer version of the page (otherwise, after an
    # update, it may keep using the old app.js it had cached)
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


def _register_job(id_: str, **fields) -> None:
    with _lock:
        _jobs[id_] = {"estado": "en_cola", "paso": "En espera", "progreso": 0.0, **fields}
        # Drop the oldest jobs, but never one that is still queued or being analyzed
        finished = [k for k, t in _jobs.items() if t["estado"] in ("listo", "error")]
        while len(_jobs) > MAX_JOBS and finished:
            _jobs.pop(finished.pop(0))


def _safe_extension(name: str) -> str:
    """'.MP4' -> '.mp4'; drops characters Windows rejects (ffmpeg looks at the content anyway)."""
    return re.sub(r"[^a-z0-9.]", "", Path(name).suffix.lower())[:10]


def _update_job(id_: str, **fields) -> None:
    with _lock:
        if id_ in _jobs:
            _jobs[id_].update(fields)


def _read_cache(path: Path) -> dict | None:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return result if result.get("version") == pipeline.VERSION else None


@app.post("/api/analisis")
async def upload(archivo: UploadFile):
    name = Path(archivo.filename or "cancion").name or "cancion"
    id_ = uuid.uuid4().hex[:12]
    folder = UPLOAD_DIR / id_
    # Neutral file name on disk: avoids ffmpeg problems with unusual characters
    target = folder / ("entrada" + _safe_extension(name))

    hasher, total = hashlib.sha256(), 0
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            while block := await archivo.read(1 << 20):
                total += len(block)
                if total > MAX_UPLOAD_BYTES:
                    break
                hasher.update(block)
                f.write(block)
    except OSError as e:
        shutil.rmtree(folder, ignore_errors=True)
        log.exception("No se pudo guardar la subida")
        raise HTTPException(500, f"No pude guardar el archivo en el disco: {e.strerror or e}") from e
    if total > MAX_UPLOAD_BYTES:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(413, TOO_LARGE_MESSAGE)
    if total == 0:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(400, "El archivo está vacío.")

    cache_path = CACHE_DIR / f"{hasher.hexdigest()}.json"
    cached = _read_cache(cache_path)
    if cached is not None:
        shutil.rmtree(folder, ignore_errors=True)
        cached["archivo"]["nombre"] = name
        cached["desde_cache"] = True
        _register_job(id_, nombre=name, estado="listo", paso="Listo", progreso=1.0, resultado=cached)
    else:
        _register_job(id_, nombre=name)
        _executor.submit(_run_analysis, id_, target, name, cache_path)
    return {"id": id_}


def _run_analysis(id_: str, path: Path, name: str, cache_path: Path) -> None:
    def progress(step: str, fraction: float) -> None:
        _update_job(id_, estado="procesando", paso=step, progreso=round(fraction, 3))

    try:
        result = pipeline.analyze(path, progress)
        result["archivo"]["nombre"] = name
        try:
            cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("No se pudo guardar el análisis en caché", exc_info=True)
        _update_job(id_, estado="listo", paso="Listo", progreso=1.0, resultado=result)
    except AudioError as e:
        _update_job(id_, estado="error", error=str(e))
    except Exception as e:
        log.exception("Falló el análisis de %s", name)
        _update_job(id_, estado="error", error=f"Error inesperado al analizar: {e}")
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


@app.get("/api/analisis/{id_}")
def job_status(id_: str):
    with _lock:
        job = dict(_jobs.get(id_) or {})
    if not job:
        raise HTTPException(404, "No existe ese análisis (¿se reinició el servidor?).")
    if job["estado"] == "en_cola" and not _models_ready.is_set():
        job["paso"] = "Cargando los modelos (la primera vez tarda un poco)"
    return job
