from __future__ import annotations

import io
import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from app.chunker import chunk_text
from app.config import (
    CHROMA_DIR,
    COLLECTION_NAME,
    RESUMES_PATH,
    SHORTLIST_PATH,
    UPLOAD_DIR,
    ensure_dirs,
)
from app.dedupe import identity_signature
from app.parsers import extract_profile, parse_file
from app.roles import ensure_roles, predict_roles
from app.skills import extract_skills

_client = None
_collection = None


def get_collection():
    global _client, _collection
    ensure_dirs()
    if _collection is None:
        _client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=DefaultEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    ensure_dirs()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def list_resumes() -> list[dict]:
    items = _read_json(RESUMES_PATH, [])
    changed = False
    for item in items:
        if item.get("predicted_roles"):
            continue
        ensure_roles(item)
        changed = True
    if changed:
        save_resumes(items)
    return items


def save_resumes(items: list[dict]) -> None:
    _write_json(RESUMES_PATH, items)


def list_shortlist() -> list[dict]:
    return _read_json(SHORTLIST_PATH, [])


def save_shortlist(items: list[dict]) -> None:
    _write_json(SHORTLIST_PATH, items)


def ingest_file(filename: str, data: bytes, save_index: bool = True) -> dict:
    text = parse_file(filename, data)
    if len(text) < 40:
        raise ValueError(
            "Could not read text from this PDF. It may be a scan, image-only, or locked."
        )

    resume_id = uuid.uuid4().hex[:12]
    safe_name = Path(filename).name
    stored_path = UPLOAD_DIR / f"{resume_id}_{safe_name}"
    stored_path.write_bytes(data)

    profile = extract_profile(text, filename)
    skills = extract_skills(text)
    chunks = chunk_text(text)
    collection = get_collection()

    ids, documents, metadatas = [], [], []
    for i, chunk in enumerate(chunks):
        ids.append(f"{resume_id}_{i}")
        documents.append(chunk["text"])
        metadatas.append(
            {
                "resume_id": resume_id,
                "filename": safe_name,
                "name": profile["name"],
                "section": chunk["section"],
                "chunk_index": i,
            }
        )
    collection.add(ids=ids, documents=documents, metadatas=metadatas)

    record = {
        "id": resume_id,
        "filename": safe_name,
        "stored_as": stored_path.name,
        "name": profile["name"],
        "email": profile["email"],
        "phone": profile["phone"],
        "skills": skills,
        "predicted_roles": predict_roles(text, skills),
        "char_count": len(text),
        "chunk_count": len(chunks),
        "preview": text[:420].replace("\n", " ").strip(),
        "sig": identity_signature(profile["name"], text),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }
    if save_index:
        append_records([record])
    return record


def append_records(records: list[dict]) -> None:
    if not records:
        return
    items = _read_json(RESUMES_PATH, [])
    for record in reversed(records):
        items.insert(0, record)
    save_resumes(items)


def get_resume(resume_id: str) -> dict | None:
    for item in _read_json(RESUMES_PATH, []):
        if item["id"] == resume_id:
            return item
    return None


def read_resume_text(resume_id: str) -> str:
    item = get_resume(resume_id)
    if not item:
        raise FileNotFoundError("Resume not found")
    path = UPLOAD_DIR / item["stored_as"]
    if not path.exists():
        raise FileNotFoundError("Resume file missing from disk")
    return parse_file(item["filename"], path.read_bytes())


def delete_resume(resume_id: str) -> None:
    item = get_resume(resume_id)
    if not item:
        raise FileNotFoundError("Resume not found")

    collection = get_collection()
    collection.delete(where={"resume_id": resume_id})

    path = UPLOAD_DIR / item["stored_as"]
    if path.exists():
        path.unlink()

    save_resumes([r for r in list_resumes() if r["id"] != resume_id])
    save_shortlist([s for s in list_shortlist() if s["id"] != resume_id])


def add_to_shortlist(resume_id: str, note: str = "") -> dict:
    item = get_resume(resume_id)
    if not item:
        raise FileNotFoundError("Resume not found")
    shortlist = list_shortlist()
    existing = next((s for s in shortlist if s["id"] == resume_id), None)
    if existing:
        if note:
            existing["note"] = note
        save_shortlist(shortlist)
        return existing
    entry = {
        "id": item["id"],
        "name": item["name"],
        "filename": item["filename"],
        "email": item["email"],
        "skills": item.get("skills", []),
        "note": note,
        "added_at": datetime.now(timezone.utc).isoformat(),
    }
    shortlist.insert(0, entry)
    save_shortlist(shortlist)
    return entry


def remove_from_shortlist(resume_id: str) -> None:
    save_shortlist([s for s in list_shortlist() if s["id"] != resume_id])


def replace_shortlist(entries: list[dict]) -> list[dict]:
    cleaned = []
    for item in entries:
        resume = get_resume(item.get("id", ""))
        if not resume:
            continue
        cleaned.append(
            {
                "id": resume["id"],
                "name": resume["name"],
                "filename": resume["filename"],
                "stored_as": resume["stored_as"],
                "rank": item.get("rank"),
                "why": item.get("why", ""),
                "added_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    save_shortlist(cleaned)
    return cleaned


def zip_resumes(resume_ids: list[str]) -> bytes:
    buffer = io.BytesIO()
    used: set[str] = set()
    added = 0
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, resume_id in enumerate(resume_ids, 1):
            item = get_resume(resume_id)
            if not item:
                continue
            path = UPLOAD_DIR / item["stored_as"]
            if not path.exists():
                continue
            name = _zip_name(index, item["name"], item["filename"], used)
            archive.write(path, name)
            added += 1
    if not added:
        raise FileNotFoundError("No stored resume files found for this shortlist.")
    return buffer.getvalue()


def _zip_name(index: int, person: str, filename: str, used: set[str]) -> str:
    stem = re.sub(r"[^\w.\- ]+", "", f"{index:02d}_{person}_{filename}", flags=re.U)
    stem = stem.strip().replace(" ", "_") or f"{index:02d}_resume"
    name = stem
    count = 2
    while name.lower() in used:
        name = f"{stem.rsplit('.', 1)[0]}_{count}"
        if "." in stem:
            name = f"{name}.{stem.rsplit('.', 1)[-1]}"
        count += 1
    used.add(name.lower())
    return name
