from __future__ import annotations

import re

from app.parsers import EMAIL_RE, PHONE_RE

PLACEHOLDER_EMAILS = {
    "email@email.com",
    "xxx@gmail.com",
    "test@test.com",
    "name@email.com",
}

TITLE_WORDS = {
    "resume",
    "curriculum",
    "vitae",
    "profile",
    "contact",
    "objective",
    "summary",
    "director",
    "manager",
    "engineer",
    "specialist",
    "analyst",
    "developer",
    "designer",
    "consultant",
    "intern",
    "senior",
    "junior",
    "lead",
    "assistant",
    "associate",
    "officer",
    "president",
    "coordinator",
    "administrator",
    "executive",
    "candidate",
    "information",
    "technology",
    "quality",
    "assurance",
    "mobile",
    "backend",
    "frontend",
    "software",
    "of",
    "and",
    "the",
}


def identity_signature(name: str, text: str) -> str:
    return _identity_blob(f"{name} {text}")[:2500]


def collapse_duplicates(items: list[dict]) -> list[dict]:
    prepared = [_with_identity(item) for item in items]
    kept: list[dict] = []
    for item in prepared:
        twin = next((other for other in kept if _same_person(item, other)), None)
        if twin is None:
            kept.append(item)
            continue
        if _better(item, twin):
            _merge_into(item, twin)
            kept[kept.index(twin)] = item
        else:
            _merge_into(twin, item)
    return [_public(item) for item in kept]


def _with_identity(item: dict) -> dict:
    row = dict(item)
    raw = row.get("sig") or row.get("preview") or ""
    blob = _identity_blob(f"{row.get('name') or ''} {raw}")
    row["_name"] = _norm_name(row.get("name") or "")
    row["_name_tokens"] = _name_tokens(row.get("name") or "")
    row["_email"] = (row.get("email") or "").lower().strip()
    row["_phone"] = _phone_key(row.get("phone") or "")
    if not row["_phone"]:
        row["_phone"] = _phone_key(" ".join(PHONE_RE.findall(row.get("preview") or "")))
    row["_shingles"] = _shingles(blob)
    row["_words"] = _words(blob)
    row["_skills"] = {str(s).lower() for s in (row.get("skills") or [])}
    row.setdefault("also_emails", [])
    row.setdefault("also_phones", [])
    return row


def _same_person(left: dict, right: dict) -> bool:
    overlap = _jaccard(left["_shingles"], right["_shingles"])
    words = _jaccard(left["_words"], right["_words"])
    same_name = _names_match(left["_name"], right["_name"], left["_name_tokens"], right["_name_tokens"])
    same_email = _real_email(left["_email"]) and left["_email"] == right["_email"]
    same_phone = bool(left["_phone"] and left["_phone"] == right["_phone"])
    skills = _skill_overlap(left["_skills"], right["_skills"])

    # Same CV text, even if email or phone was changed.
    if overlap >= 0.34 or words >= 0.48:
        return True
    if same_name and (overlap >= 0.16 or words >= 0.22 or skills >= 0.7):
        return True
    if same_phone and (same_name or overlap >= 0.12 or words >= 0.18):
        return True
    if same_email and (same_name or overlap >= 0.12 or words >= 0.18):
        return True
    if skills >= 0.85 and same_name:
        return True
    return False


def _names_match(a: str, b: str, a_tokens: set[str], b_tokens: set[str]) -> bool:
    if a and b:
        if a == b:
            return True
        if len(a) >= 6 and (a in b or b in a):
            return True
    if not a_tokens or not b_tokens:
        return False
    if a_tokens == b_tokens or a_tokens <= b_tokens or b_tokens <= a_tokens:
        return True
    shared = a_tokens & b_tokens
    if len(shared) >= 2:
        return True
    if len(shared) == 1 and len(a_tokens) == 1 and len(b_tokens) == 1:
        return True
    return False


def _skill_overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    smaller = min(len(left), len(right))
    if smaller < 4:
        return 0.0
    return len(left & right) / smaller


def _better(left: dict, right: dict) -> bool:
    left_score = float(left.get("score") or left.get("fit") or 0)
    right_score = float(right.get("score") or right.get("fit") or 0)
    if left_score != right_score:
        return left_score > right_score
    return int(left.get("char_count") or 0) > int(right.get("char_count") or 0)


def _merge_into(keep: dict, other: dict) -> None:
    keep["also_emails"] = _unique(
        [
            keep.get("email"),
            other.get("email"),
            *(keep.get("also_emails") or []),
            *(other.get("also_emails") or []),
        ]
    )
    keep["also_phones"] = _unique(
        [
            keep.get("phone"),
            other.get("phone"),
            *(keep.get("also_phones") or []),
            *(other.get("also_phones") or []),
        ]
    )


def _unique(values: list) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _identity_blob(text: str) -> str:
    text = EMAIL_RE.sub(" ", text)
    text = PHONE_RE.sub(" ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.I)
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def _name_tokens(name: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{2,}", name.lower()) if w not in TITLE_WORDS}


def _phone_key(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) >= 10:
        return digits[-10:]
    if len(digits) >= 7:
        return digits[-7:]
    return ""


def _real_email(email: str) -> bool:
    return bool(email) and email not in PLACEHOLDER_EMAILS


def _words(blob: str) -> set[str]:
    return {w for w in blob.split() if len(w) >= 4}


def _shingles(blob: str, size: int = 12) -> set[str]:
    compact = blob.replace(" ", "")
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[i : i + size] for i in range(0, len(compact) - size + 1, 4)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _public(item: dict) -> dict:
    return {key: value for key, value in item.items() if not key.startswith("_")}
