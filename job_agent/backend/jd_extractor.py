from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import tiktoken
from bs4 import BeautifulSoup


TECH_KEYWORDS = {
    "python", "django", "flask", "fastapi", "java", "kotlin", "scala", "go", "rust",
    "react", "typescript", "javascript", "node", "aws", "gcp", "azure", "docker", "kubernetes",
    "terraform", "postgres", "mysql", "redis", "graphql", "celery", "airflow", "spark",
}

SPONSORSHIP_BLOCKERS = [
    "no sponsorship",
    "no visa support",
    "must have right to work",
    "cannot sponsor",
    "unable to sponsor",
]


@dataclass(slots=True)
class JDExtractionResult:
    raw_text: str
    compressed: dict[str, Any]
    token_count: int
    sponsorship_flag: str


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _extract_lines(text: str, patterns: list[str]) -> list[str]:
    lines = [line.strip(" -\t") for line in re.split(r"[\n\r\.]+", text) if line.strip()]
    hits = []
    for line in lines:
        lower = line.lower()
        if any(p in lower for p in patterns):
            hits.append(line)
    return hits[:15]


def _extract_seniority(text: str) -> str:
    years = re.findall(r"(\d+\+?)\s*(?:years|yrs)", text, flags=re.I)
    return years[0] if years else "unspecified"


def _extract_role_type(text: str) -> str:
    lower = text.lower()
    if "hybrid" in lower:
        return "hybrid"
    if "remote" in lower:
        return "remote"
    if "onsite" in lower or "on-site" in lower:
        return "onsite"
    return "unspecified"


def _extract_tech_stack(text: str) -> list[str]:
    found = {token.lower() for token in re.findall(r"[A-Za-z0-9\+#\.]+", text)}
    return sorted(k for k in TECH_KEYWORDS if k in found)


def extract_jd(html: str) -> JDExtractionResult:
    soup = BeautifulSoup(html, "lxml")
    container = (
        soup.find("article")
        or soup.find("main")
        or soup.select_one('[class*="job-desc"], [class*="description"], [id*="description"]')
        or soup.body
    )
    raw_text = _clean_text(container.get_text(" ", strip=True) if container else "")

    required = _extract_lines(raw_text, ["required", "must", "essential"])
    preferred = _extract_lines(raw_text, ["preferred", "nice to have", "bonus"])
    tech_stack = _extract_tech_stack(raw_text)
    seniority = _extract_seniority(raw_text)
    role_type = _extract_role_type(raw_text)
    sponsorship_flag = "blocked" if any(flag in raw_text.lower() for flag in SPONSORSHIP_BLOCKERS) else "ok"

    compressed = {
        "required_skills": required,
        "preferred_skills": preferred,
        "tech_stack": tech_stack,
        "seniority": seniority,
        "sponsorship_flag": sponsorship_flag,
        "role_type": role_type,
    }

    encoding = tiktoken.get_encoding("cl100k_base")
    token_count = len(encoding.encode(str(compressed)))

    return JDExtractionResult(
        raw_text=raw_text,
        compressed=compressed,
        token_count=token_count,
        sponsorship_flag=sponsorship_flag,
    )
