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

from .analysis import pipeline, separation
from .analysis.audio import AudioError
from .messages import message

WEB = Path(__file__).parent / "web"
# %LOCALAPPDATA%\tonos on Windows (next to the installer's venv), ~/.cache/tonos elsewhere;
# TONOS_DATA_DIR overrides it (the Docker image keeps it in a volume)
DATA_DIR = Path(
    os.environ.get("TONOS_DATA_DIR")
    or Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    / "tonos"
)
CACHE_DIR = DATA_DIR / "cache"
UPLOAD_DIR = DATA_DIR / "uploads"
STEMS_DIR = DATA_DIR / "stems"
MAX_STEM_SONGS = 10  # each song's stems take about 15 MB
MAX_UPLOAD_BYTES = 1024**3  # 1 GB
MAX_JOBS = 30

log = logging.getLogger("tonos")

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
    with _lock:
        for job in _jobs.values():
            if "cancel" in job:
                job["cancel"].set()
    _executor.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="tonos", docs_url=None, redoc_url=None, lifespan=_lifespan)
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


async def _save_upload(file: UploadFile) -> tuple[Path, str, str]:
    """Saves an uploaded file under UPLOAD_DIR. Returns (path, original name, SHA-256 of the content)."""
    name = Path(file.filename or "song").name or "song"
    folder = UPLOAD_DIR / uuid.uuid4().hex[:12]
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
    return target, name, hasher.hexdigest()


@app.post("/api/analyses")
async def upload(file: UploadFile):
    target, name, digest = await _save_upload(file)
    id_ = target.parent.name
    cache_path = CACHE_DIR / f"{digest}.json"
    cached = _read_cache(cache_path)
    if cached is not None:
        shutil.rmtree(target.parent, ignore_errors=True)
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
@app.get("/api/separations/{id_}")
def job_status(id_: str):
    """{"status": "queued" | "running" | "done" | "error", "step", "progress", "name",
    "result" (when done), "error" (a message, when it failed)}."""
    with _lock:
        job = {k: v for k, v in (_jobs.get(id_) or {}).items() if k != "cancel"}
    if not job:
        raise HTTPException(404, message("job_not_found"))
    if job["status"] == "queued" and not _models_ready.is_set():
        job["step"] = "loading_models"
    return job


# ---------------------------------------------------------------- stems (optional, issue #56)


def _stems_result(digest: str) -> dict:
    return {
        "stems": {stem: f"/stems/{digest}/{stem}.mp3" for stem in separation.STEMS},
        "peaks": f"/stems/{digest}/peaks.json",
    }


def _stems_ready(folder: Path) -> bool:
    return all((folder / f"{stem}.mp3").is_file() for stem in separation.STEMS)


def _prune_stems(keep: Path) -> None:
    """Keeps the stems of the MAX_STEM_SONGS most recently separated songs (they are large)."""
    folders = sorted(
        (f for f in STEMS_DIR.iterdir() if f.is_dir() and f != keep), key=lambda f: f.stat().st_mtime
    )
    for old in folders[: max(0, len(folders) - (MAX_STEM_SONGS - 1))]:
        shutil.rmtree(old, ignore_errors=True)


@app.post("/api/separations")
async def separate(file: UploadFile):
    """Separates a song into stems. The same file the analysis got: the browser sends it again."""
    target, name, digest = await _save_upload(file)
    id_ = target.parent.name
    folder = STEMS_DIR / digest
    if _stems_ready(folder):
        shutil.rmtree(target.parent, ignore_errors=True)
        folder.touch()  # recently used: pruned last
        _register_job(id_, name=name, status="done", step="done", progress=1.0, result=_stems_result(digest))
        return {"id": id_}
    with _lock:
        running = next(
            (
                k
                for k, job in _jobs.items()
                if job.get("digest") == digest
                and job["status"] in ("queued", "running")
                and not job["cancel"].is_set()
            ),
            None,
        )
    if running:
        shutil.rmtree(target.parent, ignore_errors=True)
        return {"id": running}
    _register_job(id_, name=name, digest=digest, cancel=threading.Event())
    _executor.submit(_run_separation, id_, target, name, digest)
    return {"id": id_}


@app.delete("/api/separations/{id_}")
def cancel_separation(id_: str):
    with _lock:
        job = _jobs.get(id_)
        if not job or "cancel" not in job:
            raise HTTPException(404, message("job_not_found"))
        job["cancel"].set()
        if job["status"] == "queued":
            job.update(status="error", error=message("separation_cancelled"))
    return {"id": id_}


def _run_separation(id_: str, path: Path, name: str, digest: str) -> None:
    with _lock:
        job = _jobs.get(id_)
    # A job dropped from the list while it waited can no longer be followed: treat it as cancelled
    cancel = job["cancel"] if job else threading.Event()
    if job is None:
        cancel.set()

    def progress(fraction: float) -> None:
        _update_job(id_, status="running", step="separating_tracks", progress=round(fraction, 3))

    folder = STEMS_DIR / digest
    partial = STEMS_DIR / f"{digest}.partial"
    try:
        if cancel.is_set():
            return
        if _stems_ready(folder):  # another job separated the same song meanwhile
            folder.touch()
            _update_job(id_, status="done", step="done", progress=1.0, result=_stems_result(digest))
            return
        progress(0.0)
        STEMS_DIR.mkdir(parents=True, exist_ok=True)
        separation.separate(path, partial, progress, cancel.is_set)
        shutil.rmtree(folder, ignore_errors=True)
        partial.rename(folder)
        _prune_stems(keep=folder)
        _update_job(id_, status="done", step="done", progress=1.0, result=_stems_result(digest))
    except separation.Cancelled:
        _update_job(id_, status="error", error=message("separation_cancelled"))
    except AudioError as e:
        _update_job(id_, status="error", error=e.message)
    except Exception as e:
        log.exception("The separation of %s failed", name)
        _update_job(id_, status="error", error=message("unexpected_error", detail=str(e)))
    finally:
        shutil.rmtree(partial, ignore_errors=True)
        shutil.rmtree(path.parent, ignore_errors=True)


@app.get("/stems/{digest}/{stem}.mp3")
def stem_file(digest: str, stem: str):
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or stem not in separation.STEMS:
        raise HTTPException(404)
    path = STEMS_DIR / digest / f"{stem}.mp3"
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/stems/{digest}/peaks.json")
def stem_peaks(digest: str):
    """Each track's waveform for the player (made from the MP3s for stems separated earlier)."""
    folder = STEMS_DIR / digest
    if not re.fullmatch(r"[0-9a-f]{64}", digest) or not _stems_ready(folder):
        raise HTTPException(404)
    path = folder / "peaks.json"
    if not path.is_file():
        path = separation.peaks_from_files(folder)
    return FileResponse(path, media_type="application/json")
