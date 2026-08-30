from __future__ import annotations

import re

SKILLS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "golang",
    "rust", "ruby", "php", "swift", "kotlin", "scala", "r", "matlab", "sql",
    "html", "css", "react", "angular", "vue", "next.js", "node.js", "express",
    "django", "flask", "fastapi", "spring", "rails", ".net", "asp.net",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "keras",
    "nlp", "llm", "rag", "machine learning", "deep learning", "data science",
    "computer vision", "transformers", "huggingface", "langchain",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "ansible",
    "ci/cd", "jenkins", "github actions", "linux", "git", "graphql", "rest",
    "postgresql", "mysql", "mongodb", "redis", "elasticsearch", "snowflake",
    "spark", "hadoop", "airflow", "kafka", "tableau", "power bi", "excel",
    "figma", "photoshop", "illustrator", "ui/ux", "product management",
    "agile", "scrum", "jira", "salesforce", "hubspot", "seo", "sem",
    "android", "ios", "react native", "flutter", "unity",
    "communication", "leadership", "project management", "system design",
    "microservices", "devops", "sre", "cybersecurity", "networking",
    "accounting", "finance", "marketing", "content writing", "hr",
    "recruiting", "customer success", "operations", "supply chain",
]

SKILL_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "node": "node.js",
    "nextjs": "next.js",
    "reactjs": "react",
    "postgres": "postgresql",
    "k8s": "kubernetes",
    "ml": "machine learning",
    "dl": "deep learning",
    "tf": "tensorflow",
    "sklearn": "scikit-learn",
    "powerbi": "power bi",
    "ms excel": "excel",
}

_PATTERN = re.compile(
    r"\b("
    + "|".join(re.escape(s) for s in sorted(set(SKILLS + list(SKILL_ALIASES)), key=len, reverse=True))
    + r")\b",
    re.I,
)


def extract_skills(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in _PATTERN.finditer(text.lower()):
        raw = match.group(1).lower()
        canonical = SKILL_ALIASES.get(raw, raw)
        if canonical not in seen:
            seen.add(canonical)
            found.append(_display(canonical))
    return found


def _display(skill: str) -> str:
    specials = {
        "next.js": "Next.js",
        "node.js": "Node.js",
        "c++": "C++",
        "c#": "C#",
        ".net": ".NET",
        "asp.net": "ASP.NET",
        "ui/ux": "UI/UX",
        "ci/cd": "CI/CD",
        "nlp": "NLP",
        "llm": "LLM",
        "rag": "RAG",
        "aws": "AWS",
        "gcp": "GCP",
        "sql": "SQL",
        "html": "HTML",
        "css": "CSS",
        "ios": "iOS",
        "hr": "HR",
        "seo": "SEO",
        "sem": "SEM",
        "sre": "SRE",
        "fastapi": "FastAPI",
        "postgresql": "PostgreSQL",
        "pytorch": "PyTorch",
        "mongodb": "MongoDB",
        "graphql": "GraphQL",
        "devops": "DevOps",
        "typescript": "TypeScript",
        "javascript": "JavaScript",
    }
    if skill in specials:
        return specials[skill]
    return skill.title()


def skills_from_query(query: str) -> list[str]:
    return extract_skills(query)
