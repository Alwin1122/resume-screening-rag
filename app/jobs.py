from __future__ import annotations

import shutil
import threading
import uuid
from pathlib import Path

from app.config import INCOMING_DIR, MAX_ZIP_BYTES, ensure_dirs
from app.parsers import count_resumes, iter_resumes
from app.store import append_records, ingest_file

_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def start_upload_job(saved: list[tuple[str, Path]]) -> dict:
    ensure_dirs()
    total = 0
    for name, path in saved:
        if path.stat().st_size > MAX_ZIP_BYTES:
            raise ValueError("That zip is larger than 800 MB. Split it into smaller zips.")
        total += count_resumes(name, path=path)
    if not total:
        raise ValueError("No PDF, DOCX, or TXT resumes found.")

    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "total": total,
            "done": 0,
            "ok": 0,
            "failed": 0,
            "current": "Starting…",
            "errors": [],
        }
    thread = threading.Thread(target=_run, args=(job_id, saved), daemon=True)
    thread.start()
    return get_job(job_id)


def _run(job_id: str, saved: list[tuple[str, Path]]) -> None:
    pending: list[dict] = []
    try:
        for original, path in saved:
            for name, payload in iter_resumes(original, path=path):
                _patch(job_id, current=name)
                try:
                    pending.append(ingest_file(name, payload, save_index=False))
                    _bump(job_id, ok=True)
                except Exception as exc:
                    _bump(job_id, ok=False, error=f"{name}: {exc}")
                if len(pending) >= 20:
                    append_records(pending)
                    pending = []
        if pending:
            append_records(pending)
        _patch(job_id, status="done", current="Finished")
    except Exception as exc:
        if pending:
            append_records(pending)
        _patch(job_id, status="error", current=str(exc), error=str(exc))
    finally:
        for _, path in saved:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        folder = INCOMING_DIR / job_id
        shutil.rmtree(folder, ignore_errors=True)


def _bump(job_id: str, ok: bool, error: str | None = None) -> None:
    with _lock:
        job = _jobs[job_id]
        job["done"] += 1
        if ok:
            job["ok"] += 1
        else:
            job["failed"] += 1
        if error:
            job["errors"] = (job["errors"] + [error])[-15:]


def _patch(job_id: str, **fields) -> None:
    with _lock:
        job = _jobs[job_id]
        error = fields.pop("error", None)
        job.update(fields)
        if error:
            job["errors"] = (job["errors"] + [error])[-15:]
