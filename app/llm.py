from __future__ import annotations

import importlib
import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from app import config as config_mod
from app.config import GROQ_MODELS, SETTINGS_PATH, ensure_dirs
from app.dedupe import collapse_duplicates
from app.matcher import search_resumes
from app.store import list_resumes, read_resume_text

load_dotenv()

SYSTEM = """You shortlist resumes from the given context only.
Follow the user's question exactly. Do not invent a job title or role
unless they named one. If they ask about a role, use predicted_roles
and the resume text. Never invent people, employers, or skills.
Treat near-duplicate resumes as one person (same name or almost the
same text, even if the email is different). Return distinct people only.
Return at most the requested number of people. Do not pad the list.
Return JSON:
{
  "summary": "one or two sentences answering the question",
  "list": [
    {
      "id": "resume_id from context",
      "rank": 1,
      "verdict": "strong | possible | weak",
      "fit": 87,
      "why": "2-3 sentences grounded in the resume and the question",
      "concerns": "gap or empty string"
    }
  ]
}
Sort best first. fit is 0-100.
"""

LIMIT_PATTERNS = (
    r"(?:top|best|first|only)\s+(\d+)",
    r"shortlist(?:\s+of)?\s+(\d+)",
    r"(\d+)\s+(?:candidates?|people|resumes?|profiles?)",
)


def groq_status() -> dict:
    key = get_groq_key()
    return {
        "configured": bool(key),
        "hint": _mask(key) if key else "",
    }


def get_groq_key() -> str:
    importlib.reload(config_mod)
    coded = (getattr(config_mod, "GROQ_API_KEY", "") or "").strip()
    if coded and coded != "gsk_your_key_here":
        return coded
    env = (os.environ.get("GROQ_API_KEY") or "").strip()
    if env:
        return env
    settings = _read_settings()
    return str(settings.get("groq_api_key") or "").strip()


def save_groq_key(key: str) -> dict:
    ensure_dirs()
    settings = _read_settings()
    cleaned = key.strip()
    if cleaned:
        settings["groq_api_key"] = cleaned
    else:
        settings.pop("groq_api_key", None)
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    return groq_status()


def parse_limit(text: str, requested: int | None = None) -> int:
    for pattern in LIMIT_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            return max(1, min(int(match.group(1)), 20))
    if requested is not None:
        return max(1, min(int(requested), 20))
    return 5


def _count_only(text: str) -> bool:
    cleaned = re.sub(
        r"(?:top|best|first|only|shortlist(?:\s+of)?|candidates?|people|"
        r"resumes?|profiles?|give me|show me|list|the|get|who|are|"
        r"strongest|best|pick|\d+)",
        " ",
        text,
        flags=re.I,
    )
    return len(re.sub(r"\W+", "", cleaned)) < 4


def ask_groq(preference: str, top_k: int | None = None) -> dict:
    preference = (preference or "").strip()
    if not preference:
        raise ValueError("Ask who you want from the uploaded resumes.")
    key = get_groq_key()
    if not key:
        raise RuntimeError(
            "Add your Groq API key in app/config.py (GROQ_API_KEY)."
        )

    limit = parse_limit(preference, top_k)
    pool = _unique_pool(preference, limit)
    retrieved = {"results": pool}
    if not retrieved["results"]:
        return {
            "preference": preference,
            "summary": "No resumes in the index matched that question.",
            "list": [],
            "model": None,
        }

    context = _context_block(retrieved["results"])
    payload = _complete(key, preference, context, limit)
    merged = _fill_unique(
        collapse_duplicates(_merge(payload, retrieved["results"], limit * 2)),
        retrieved["results"],
        limit,
    )
    for index, row in enumerate(merged, 1):
        row["rank"] = index
    return {
        "preference": preference,
        "summary": payload.get("summary") or "",
        "list": merged,
        "model": payload.get("_model"),
    }


def _unique_pool(preference: str, limit: int) -> list[dict]:
    if _count_only(preference):
        raw = list_resumes()
    else:
        pool_size = min(30, max(limit * 6, 12))
        raw = search_resumes({"query": preference, "top_k": pool_size})["results"]
        seen = {item["id"] for item in raw}
        for item in list_resumes():
            if item["id"] not in seen:
                raw.append(item)
    unique = collapse_duplicates(raw)
    return unique[: min(20, max(limit * 4, 8))]


def _fill_unique(picked: list[dict], pool: list[dict], limit: int) -> list[dict]:
    filled = list(picked)
    have = {row["id"] for row in filled}
    for record in pool:
        if len(filled) >= limit:
            break
        if record["id"] in have:
            continue
        trial = collapse_duplicates(filled + [_row(record, {}, 0)])
        if len(trial) > len(filled):
            filled = trial
            have = {row["id"] for row in filled}
    return filled[:limit]


def _complete(key: str, preference: str, context: str, limit: int) -> dict:
    client = Groq(api_key=key)
    user = (
        f"User question:\n{preference}\n\n"
        f"Return at most {limit} people. If they asked for {limit}, "
        f"return {limit} or fewer. Do not invent a role they did not name.\n\n"
        f"Resumes:\n{context}\n\n"
        "Return the JSON list now."
    )
    last_error = None
    for model in GROQ_MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or "{}"
            data = _parse_json(text)
            data["_model"] = model
            return data
        except Exception as exc:
            last_error = exc
            message = str(exc)
            if "401" in message or "invalid_api_key" in message.lower():
                raise RuntimeError("Groq rejected the API key. Check GROQ_API_KEY in app/config.py.") from exc
            continue
    raise RuntimeError(f"Groq could not rank the list: {last_error}")


def _context_block(results: list[dict]) -> str:
    parts = []
    for i, row in enumerate(results, 1):
        try:
            body = read_resume_text(row["id"])[:1800]
        except FileNotFoundError:
            body = row.get("preview") or ""
        snippets = " | ".join(
            f"{s.get('section')}: {s.get('text')}" for s in (row.get("snippets") or [])[:2]
        )
        parts.append(
            "\n".join(
                [
                    f"CANDIDATE {i}",
                    f"id: {row['id']}",
                    f"name: {row.get('name')}",
                    f"email: {row.get('email') or 'unknown'}",
                    f"also_emails: {', '.join(row.get('also_emails') or [])}",
                    f"predicted_roles: {', '.join(r['title'] for r in (row.get('predicted_roles') or []) if r.get('title'))}",
                    f"skills: {', '.join(row.get('skills') or [])}",
                    f"retrieval_score: {row.get('score')}",
                    f"matched_skills: {', '.join(row.get('matched_skills') or [])}",
                    f"missing_skills: {', '.join(row.get('missing_skills') or [])}",
                    f"snippets: {snippets}",
                    f"resume:\n{body}",
                ]
            )
        )
    return "\n\n----\n\n".join(parts)


def _merge(payload: dict, results: list[dict], limit: int) -> list[dict]:
    by_id = {r["id"]: r for r in results}
    by_name = {r.get("name", "").lower(): r for r in results}
    seen = set()
    ordered = []
    for item in payload.get("list") or []:
        record = by_id.get(item.get("id")) or by_name.get(str(item.get("name") or "").lower())
        if not record or record["id"] in seen:
            continue
        seen.add(record["id"])
        ordered.append(_row(record, item, len(ordered) + 1))
        if len(ordered) >= limit:
            return ordered
    for record in results:
        if len(ordered) >= limit:
            break
        if record["id"] not in seen:
            ordered.append(_row(record, {}, len(ordered) + 1))
    return ordered[:limit]


def _row(record: dict, item: dict, rank: int) -> dict:
    fit = item.get("fit")
    try:
        fit = max(0, min(100, int(round(float(fit)))))
    except (TypeError, ValueError):
        fit = int(round(float(record.get("score") or 0) * 100))
    return {
        **record,
        "rank": int(item.get("rank") or rank),
        "verdict": str(item.get("verdict") or "possible").lower(),
        "fit": fit,
        "why": str(item.get("why") or "Retrieved as a close language match."),
        "concerns": str(item.get("concerns") or ""),
    }


def _parse_json(text: str) -> dict:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("Model did not return JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("Model JSON was not an object")
    return data


def _read_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _mask(key: str) -> str:
    if len(key) <= 8:
        return "••••"
    return f"{key[:4]}…{key[-4:]}"
