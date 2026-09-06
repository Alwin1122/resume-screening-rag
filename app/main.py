from __future__ import annotations

from contextlib import asynccontextmanager

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import INCOMING_DIR, ROOT, ensure_dirs
from app.dedupe import collapse_duplicates
from app.jobs import cancel_job, get_job, start_upload_job
from app.llm import ask_groq
from app.store import (
    delete_resume,
    get_collection,
    list_resumes,
    list_shortlist,
    replace_shortlist,
    zip_resumes,
)

ensure_dirs()
STATIC = ROOT / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_collection()
    yield


app = FastAPI(title="Shortlist", version="1.0.0", lifespan=lifespan)


class AskBody(BaseModel):
    preference: str
    top_k: int | None = Field(default=None, ge=1, le=20)


class ZipBody(BaseModel):
    ids: list[str] = []


@app.get("/api/resumes")
def resumes() -> dict:
    items = collapse_duplicates(list_resumes())
    slim = [
        {
            "id": r["id"],
            "name": r["name"],
            "filename": r["filename"],
            "predicted_roles": r.get("predicted_roles") or [],
            "also_emails": r.get("also_emails") or [],
        }
        for r in items[:80]
    ]
    return {"total": len(items), "resumes": slim}


@app.post("/api/resumes")
async def upload(files: list[UploadFile] = File(...)) -> dict:
    ensure_dirs()
    job_id = uuid4().hex[:12]
    folder = INCOMING_DIR / job_id
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[tuple[str, Path]] = []
    try:
        for file in files:
            name = Path(file.filename or "resume.bin").name
            dest = folder / name
            dest.write_bytes(await file.read())
            if dest.stat().st_size == 0:
                raise ValueError(f"{name} is empty")
            saved.append((name, dest))
        return start_upload_job(saved, job_id=job_id)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/resumes/jobs/{job_id}")
def upload_job(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Upload job not found")
    return job


@app.post("/api/resumes/jobs/{job_id}/cancel")
def upload_job_cancel(job_id: str) -> dict:
    job = cancel_job(job_id)
    if not job:
        raise HTTPException(404, "Upload job not found")
    return job


@app.delete("/api/resumes/{resume_id}")
def resume_delete(resume_id: str) -> dict:
    try:
        delete_resume(resume_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return {"ok": True}


@app.post("/api/ask")
def ask(body: AskBody) -> dict:
    try:
        result = ask_groq(body.preference, body.top_k)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    replace_shortlist(result.get("list") or [])
    return result


@app.post("/api/shortlist/zip")
def shortlist_zip(body: ZipBody) -> Response:
    ids = body.ids or [item["id"] for item in list_shortlist()]
    if not ids:
        raise HTTPException(400, "No shortlisted resumes to download.")
    try:
        payload = zip_resumes(ids)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="shortlist-resumes.zip"'},
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
