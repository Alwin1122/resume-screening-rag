from __future__ import annotations

import re

ROLES = [
    {
        "title": "Frontend Engineer",
        "keywords": ["frontend", "front-end", "front end", "web designer", "ui developer"],
        "skills": {"html", "css", "javascript", "typescript", "react", "vue", "angular", "next.js", "ui/ux", "figma"},
    },
    {
        "title": "Backend Engineer",
        "keywords": ["backend", "back-end", "back end", "api engineer", "server"],
        "skills": {"python", "java", "node.js", "django", "flask", "fastapi", "spring", "sql", "postgresql", "mongodb", "redis", "rest"},
    },
    {
        "title": "Full Stack Engineer",
        "keywords": ["full stack", "fullstack", "full-stack"],
        "skills": {"javascript", "typescript", "react", "node.js", "python", "sql", "html", "css"},
    },
    {
        "title": "Data Scientist",
        "keywords": ["data scientist", "data science"],
        "skills": {"python", "machine learning", "pandas", "sql", "scikit-learn", "statistics", "tableau"},
    },
    {
        "title": "ML Engineer",
        "keywords": ["machine learning engineer", "ml engineer", "deep learning"],
        "skills": {"python", "pytorch", "tensorflow", "machine learning", "nlp", "llm", "rag", "docker"},
    },
    {
        "title": "DevOps / SRE",
        "keywords": ["devops", "sre", "site reliability"],
        "skills": {"aws", "docker", "kubernetes", "terraform", "ci/cd", "linux", "jenkins"},
    },
    {
        "title": "Product Manager",
        "keywords": ["product manager", "product management", "pm "],
        "skills": {"product management", "agile", "scrum", "jira", "sql", "figma"},
    },
    {
        "title": "UI / UX Designer",
        "keywords": ["ui/ux", "ux designer", "ui designer", "web designer", "graphic designer"],
        "skills": {"figma", "photoshop", "illustrator", "ui/ux", "css", "html"},
    },
    {
        "title": "Mobile Engineer",
        "keywords": ["android", "ios", "mobile engineer", "react native", "flutter"],
        "skills": {"android", "ios", "kotlin", "swift", "react native", "flutter"},
    },
    {
        "title": "QA Engineer",
        "keywords": ["qa engineer", "test engineer", "sdet", "quality assurance"],
        "skills": {"selenium", "cypress", "jira", "python", "javascript"},
    },
]


def predict_roles(text: str, skills: list[str] | None = None, top_n: int = 2) -> list[dict]:
    blob = (text or "").lower()
    have = {s.lower() for s in (skills or [])}
    scored = []
    for role in ROLES:
        title_hit = any(key in blob for key in role["keywords"])
        overlap = len(have & role["skills"])
        need = max(len(role["skills"]), 1)
        skill_score = overlap / min(need, 6)
        score = (0.55 if title_hit else 0.0) + 0.45 * min(skill_score, 1.0)
        if title_hit and overlap == 0:
            score = 0.62
        if score < 0.28:
            continue
        scored.append(
            {
                "title": role["title"],
                "confidence": round(min(score, 0.99), 2),
            }
        )
    scored.sort(key=lambda x: x["confidence"], reverse=True)
    return scored[:top_n]


def ensure_roles(record: dict) -> dict:
    if record.get("predicted_roles"):
        return record
    record["predicted_roles"] = predict_roles(
        record.get("preview") or "",
        record.get("skills") or [],
    )
    return record


def role_labels(record: dict) -> list[str]:
    return [r["title"] for r in (record.get("predicted_roles") or []) if r.get("title")]
