from __future__ import annotations

import re

from app.parsers import EMAIL_RE, PHONE_RE

PLACEHOLDER_EMAILS = {
    "email@email.com",
    "xxx@gmail.com",
    "test@test.com",
    "name@email.com",
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
            item["also_emails"] = _merge_contacts(item, twin)
            idx = kept.index(twin)
            kept[idx] = item
        else:
            twin["also_emails"] = _merge_contacts(twin, item)
    return [_public(item) for item in kept]


def _with_identity(item: dict) -> dict:
    row = dict(item)
    text = row.get("sig") or row.get("preview") or ""
    blob = text if row.get("sig") else _identity_blob(f"{row.get('name') or ''} {text}")
    row["_name"] = _norm_name(row.get("name") or "")
    row["_email"] = (row.get("email") or "").lower().strip()
    row["_phone"] = re.sub(r"\D", "", row.get("phone") or "")
    row["_shingles"] = _shingles(blob)
    row.setdefault("also_emails", [])
    return row


def _same_person(left: dict, right: dict) -> bool:
    overlap = _jaccard(left["_shingles"], right["_shingles"])
    same_name = _names_match(left["_name"], right["_name"])
    same_email = bool(left["_email"] and left["_email"] == right["_email"])
    real_email = left["_email"] not in PLACEHOLDER_EMAILS
    same_phone = bool(left["_phone"] and left["_phone"] == right["_phone"] and len(left["_phone"]) >= 10)

    if overlap >= 0.5:
        return True
    if same_name and overlap >= 0.22:
        return True
    if same_name and same_phone:
        return True
    if same_name and same_email and real_email:
        return True
    if same_email and real_email and overlap >= 0.18:
        return True
    return False


def _names_match(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) >= 6 and (a in b or b in a):
        return True
    return False


def _better(left: dict, right: dict) -> bool:
    left_score = float(left.get("score") or left.get("fit") or 0)
    right_score = float(right.get("score") or right.get("fit") or 0)
    if left_score != right_score:
        return left_score > right_score
    return int(left.get("char_count") or 0) > int(right.get("char_count") or 0)


def _merge_contacts(keep: dict, other: dict) -> list[str]:
    emails = []
    for value in [keep.get("email"), other.get("email"), *(keep.get("also_emails") or []), *(other.get("also_emails") or [])]:
        if value and value not in emails:
            emails.append(value)
    return emails


def _identity_blob(text: str) -> str:
    text = EMAIL_RE.sub(" ", text)
    text = PHONE_RE.sub(" ", text)
    text = re.sub(r"https?://\S+|www\.\S+", " ", text, flags=re.I)
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z]", "", name.lower())


def _shingles(blob: str, size: int = 14) -> set[str]:
    compact = blob.replace(" ", "")
    if len(compact) < size:
        return {compact} if compact else set()
    return {compact[i : i + size] for i in range(0, len(compact) - size + 1, 5)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _public(item: dict) -> dict:
    return {key: value for key, value in item.items() if not key.startswith("_")}
