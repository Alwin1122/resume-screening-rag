from __future__ import annotations

import re

from app.config import RETRIEVE_CHUNKS
from app.skills import extract_skills, skills_from_query
from app.store import get_collection, list_resumes

STOP = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has",
    "are", "was", "were", "will", "would", "should", "could", "their",
    "them", "they", "you", "your", "our", "who", "what", "when", "where",
    "which", "into", "about", "over", "under", "than", "then", "also",
    "plus", "more", "less", "very", "just", "able", "using", "used",
    "work", "role", "job", "candidate", "resume", "years", "year",
}


def build_query(payload: dict) -> str:
    parts = []
    if payload.get("role"):
        parts.append(f"Role: {payload['role']}")
    if payload.get("must_have"):
        parts.append(f"Must-have skills: {payload['must_have']}")
    if payload.get("nice_to_have"):
        parts.append(f"Nice-to-have skills: {payload['nice_to_have']}")
    if payload.get("experience"):
        parts.append(f"Experience: {payload['experience']}")
    if payload.get("location"):
        parts.append(f"Location: {payload['location']}")
    if payload.get("education"):
        parts.append(f"Education: {payload['education']}")
    if payload.get("notes"):
        parts.append(payload["notes"])
    query = "\n".join(p.strip() for p in parts if p and str(p).strip())
    return query or str(payload.get("query") or "").strip()


def search_resumes(payload: dict) -> dict:
    query = build_query(payload)
    if not query:
        raise ValueError("Describe the role or skills you want to match.")

    resumes = {r["id"]: r for r in list_resumes()}
    if not resumes:
        return {"query": query, "results": []}

    top_k = int(payload.get("top_k") or 8)
    min_score = float(payload.get("min_score") or 0)
    required = skills_from_query(
        " ".join(
            filter(
                None,
                [
                    payload.get("must_have", ""),
                    payload.get("role", ""),
                    payload.get("notes", ""),
                    query,
                ],
            )
        )
    )
    nice = skills_from_query(payload.get("nice_to_have") or "")

    collection = get_collection()
    n_results = min(RETRIEVE_CHUNKS, max(collection.count(), 1))
    raw = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )

    docs = raw.get("documents", [[]])[0]
    metas = raw.get("metadatas", [[]])[0]
    dists = raw.get("distances", [[]])[0]

    grouped: dict[str, dict] = {}
    for doc, meta, dist in zip(docs, metas, dists):
        rid = meta.get("resume_id")
        if rid not in resumes:
            continue
        similarity = max(0.0, 1.0 - float(dist))
        bucket = grouped.setdefault(
            rid,
            {"similarities": [], "snippets": []},
        )
        bucket["similarities"].append(similarity)
        if len(bucket["snippets"]) < 3:
            bucket["snippets"].append(
                {
                    "section": meta.get("section") or "Resume",
                    "text": _trim(doc),
                    "score": round(similarity, 3),
                }
            )

    query_terms = _keywords(query)
    ranked = []
    for rid, bucket in grouped.items():
        record = resumes[rid]
        sims = sorted(bucket["similarities"], reverse=True)
        semantic = 0.7 * sims[0] + 0.3 * (sum(sims[:3]) / min(len(sims), 3))
        resume_skills = record.get("skills") or []
        matched_must = _overlap(required, resume_skills)
        matched_nice = _overlap(nice, resume_skills)
        skill_score = _skill_score(required, nice, matched_must, matched_nice)
        keyword_score = _keyword_score(query_terms, record)
        if required and not matched_must:
            semantic *= 0.88

        final = 0.62 * semantic + 0.28 * skill_score + 0.10 * keyword_score
        if final < min_score:
            continue

        ranked.append(
            {
                **record,
                "score": round(final, 3),
                "semantic_score": round(semantic, 3),
                "skill_score": round(skill_score, 3),
                "matched_skills": matched_must + [s for s in matched_nice if s not in matched_must],
                "missing_skills": [s for s in required if s not in matched_must],
                "snippets": bucket["snippets"],
                "reasons": _reasons(
                    record, matched_must, matched_nice, required, semantic
                ),
            }
        )

    ranked.sort(key=lambda x: x["score"], reverse=True)
    from app.dedupe import collapse_duplicates

    unique = collapse_duplicates(ranked)
    return {
        "query": query,
        "required_skills": required,
        "results": unique[:top_k],
    }


def _overlap(wanted: list[str], have: list[str]) -> list[str]:
    have_l = {h.lower() for h in have}
    return [w for w in wanted if w.lower() in have_l]


def _skill_score(required, nice, matched_must, matched_nice) -> float:
    if not required and not nice:
        return 0.5
    must = len(matched_must) / len(required) if required else 1.0
    bonus = (len(matched_nice) / len(nice) * 0.25) if nice else 0.0
    return min(1.0, 0.75 * must + bonus + (0.25 if must == 1 and required else 0))


def _keywords(query: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z.+#-]{2,}", query.lower())
    return [w for w in words if w not in STOP]


def _keyword_score(terms: list[str], record: dict) -> float:
    if not terms:
        return 0.0
    blob = " ".join(
        [
            record.get("name", ""),
            record.get("preview", ""),
            " ".join(record.get("skills") or []),
            record.get("filename", ""),
        ]
    ).lower()
    hits = sum(1 for t in terms if t in blob)
    return hits / len(terms)


def _trim(text: str, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"


def _reasons(record, matched_must, matched_nice, required, semantic) -> list[str]:
    reasons = []
    if matched_must:
        reasons.append("Matches required skills: " + ", ".join(matched_must))
    if matched_nice:
        reasons.append("Also has: " + ", ".join(matched_nice))
    missing = [s for s in required if s not in matched_must]
    if missing:
        reasons.append("Not clearly listed: " + ", ".join(missing))
    if semantic >= 0.55:
        reasons.append("Resume language closely matches your preference.")
    elif semantic >= 0.4:
        reasons.append("Partial semantic overlap with the role description.")
    else:
        reasons.append("Weaker language match — review the snippets.")
    if record.get("email"):
        reasons.append(f"Contact: {record['email']}")
    return reasons
