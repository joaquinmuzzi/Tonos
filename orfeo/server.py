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
from .messages import message

WEB = Path(__file__).parent / "web"
# %LOCALAPPDATA%\orfeo on Windows (next to the installer's venv), ~/.cache/orfeo elsewhere
DATA_DIR = (
    Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    / "orfeo"
)
CACHE_DIR = DATA_DIR / "cache"
UPLOAD_DIR = DATA_DIR / "uploads"
MAX_UPLOAD_BYTES = 1024**3  # 1 GB
MAX_JOBS = 30

log = logging.getLogger("orfeo")

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1)  # one analysis at a time: the models use the whole CPU
_models_ready = threading.Event()


def _preload() -> None:
    try:
        pipeline.preload()
    except Exception:
        log.exception("Could not load the models")
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


app = FastAPI(title="orfeo", docs_url=None, redoc_url=None, lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")

TOO_LARGE = message("too_large", gigabytes=MAX_UPLOAD_BYTES // 1024**3)


@app.middleware("http")
async def _limit_body_size(request: Request, call_next):
    # Reject before receiving the body: otherwise the whole file is written to disk anyway.
    length = request.headers.get("content-length", "")
    if request.method == "POST" and length.isdigit() and int(length) > MAX_UPLOAD_BYTES + (1 << 20):
        return JSONResponse({"detail": TOO_LARGE}, status_code=413)
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
        _jobs[id_] = {"status": "queued", "step": "queued", "progress": 0.0, **fields}
        # Drop the oldest jobs, but never one that is still queued or being analyzed
        finished = [k for k, t in _jobs.items() if t["status"] in ("done", "error")]
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


@app.post("/api/analyses")
async def upload(file: UploadFile):
    name = Path(file.filename or "song").name or "song"
    id_ = uuid.uuid4().hex[:12]
    folder = UPLOAD_DIR / id_
    # Neutral file name on disk: avoids ffmpeg problems with unusual characters
    target = folder / ("input" + _safe_extension(name))

    hasher, total = hashlib.sha256(), 0
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            while block := await file.read(1 << 20):
                total += len(block)
                if total > MAX_UPLOAD_BYTES:
                    break
                hasher.update(block)
                f.write(block)
    except OSError as e:
        shutil.rmtree(folder, ignore_errors=True)
        log.exception("Could not save the upload")
        raise HTTPException(500, message("save_failed", detail=str(e.strerror or e))) from e
    if total > MAX_UPLOAD_BYTES:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(413, TOO_LARGE)
    if total == 0:
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(400, message("empty_file"))

    cache_path = CACHE_DIR / f"{hasher.hexdigest()}.json"
    cached = _read_cache(cache_path)
    if cached is not None:
        shutil.rmtree(folder, ignore_errors=True)
        cached["file"]["name"] = name
        cached["from_cache"] = True
        _register_job(id_, name=name, status="done", step="done", progress=1.0, result=cached)
    else:
        _register_job(id_, name=name)
        _executor.submit(_run_analysis, id_, target, name, cache_path)
    return {"id": id_}


def _run_analysis(id_: str, path: Path, name: str, cache_path: Path) -> None:
    def progress(step: str, fraction: float) -> None:
        _update_job(id_, status="running", step=step, progress=round(fraction, 3))

    try:
        result = pipeline.analyze(path, progress)
        result["file"]["name"] = name
        try:
            cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        except OSError:
            log.warning("Could not cache the analysis", exc_info=True)
        _update_job(id_, status="done", step="done", progress=1.0, result=result)
    except AudioError as e:
        _update_job(id_, status="error", error=e.message)
    except Exception as e:
        log.exception("The analysis of %s failed", name)
        _update_job(id_, status="error", error=message("unexpected_error", detail=str(e)))
    finally:
        shutil.rmtree(path.parent, ignore_errors=True)


@app.get("/api/analyses/{id_}")
def job_status(id_: str):
    """{"status": "queued" | "running" | "done" | "error", "step", "progress", "name",
    "result" (when done), "error" (a message, when it failed)}."""
    with _lock:
        job = dict(_jobs.get(id_) or {})
    if not job:
        raise HTTPException(404, message("job_not_found"))
    if job["status"] == "queued" and not _models_ready.is_set():
        job["step"] = "loading_models"
    return job
