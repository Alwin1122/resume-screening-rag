from __future__ import annotations

import re

from app.config import CHUNK_OVERLAP, CHUNK_SIZE

SECTION_RE = re.compile(
    r"(?m)^(?:#{1,3}\s*)?("
    r"summary|objective|profile|experience|work experience|employment|"
    r"education|skills|technical skills|projects|certifications|"
    r"achievements|awards|publications|languages|interests"
    r")\s*:?\s*$",
    re.I,
)


def chunk_text(text: str) -> list[dict]:
    cleaned = text.strip()
    if not cleaned:
        return []

    sections = _split_sections(cleaned)
    chunks: list[dict] = []
    for section, body in sections:
        for piece in _window(body):
            chunks.append({"section": section, "text": piece})
    if not chunks:
        chunks = [{"section": "Resume", "text": cleaned[:CHUNK_SIZE]}]
    return chunks


def _split_sections(text: str) -> list[tuple[str, str]]:
    matches = list(SECTION_RE.finditer(text))
    if not matches:
        return [("Resume", text)]

    parts: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        lead = text[: matches[0].start()].strip()
        if lead:
            parts.append(("Header", lead))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        title = match.group(1).title()
        if body:
            parts.append((title, body))
    return parts or [("Resume", text)]


def _window(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            cut = text.rfind("\n", start + CHUNK_SIZE // 2, end)
            if cut == -1:
                cut = text.rfind(". ", start + CHUNK_SIZE // 2, end)
            if cut != -1:
                end = cut + 1
        piece = text[start:end].strip()
        if piece:
            pieces.append(piece)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return pieces
