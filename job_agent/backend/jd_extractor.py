from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bs4 import BeautifulSoup

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None

TECH_KEYWORDS = {
    "python", "django", "fastapi", "flask", "react", "typescript", "javascript", "node",
    "aws", "gcp", "azure", "docker", "kubernetes", "terraform", "postgresql", "mysql",
    "redis", "celery", "graphql", "rest", "ci/cd", "git", "linux",
}

SPONSORSHIP_BLOCK_PATTERNS = (
    "no sponsorship",
    "no visa support",
    "must have right to work",
    "unable to sponsor",
)


@dataclass(slots=True)
class JDExtraction:
    raw_text: str
    compressed: dict[str, Any]
    token_count: int
    sponsorship_flag: str


def extract_jd_from_html(html: str) -> JDExtraction:
    soup = BeautifulSoup(html, "lxml")
    container = (
        soup.find("article")
        or soup.select_one("[class*='job-desc']")
        or soup.find("main")
        or soup.body
        or soup
    )
    text = normalize_text(container.get_text("\n", strip=True))

    required = _extract_lines(text, ("required", "must", "essential"))
    preferred = _extract_lines(text, ("preferred", "nice to have", "desirable"))
    tech_stack = sorted({t for t in TECH_KEYWORDS if re.search(rf"\b{re.escape(t)}\b", text, re.I)})
    seniority = _extract_seniority(text)
    sponsorship_flag = "blocked" if any(p in text.lower() for p in SPONSORSHIP_BLOCK_PATTERNS) else "ok"
    role_type = _extract_role_type(text)

    compressed = {
        "required_skills": required[:20],
        "preferred_skills": preferred[:20],
        "tech_stack": tech_stack,
        "seniority": seniority,
        "sponsorship_flag": sponsorship_flag,
        "role_type": role_type,
    }

    token_count = count_tokens(text)
    return JDExtraction(raw_text=text, compressed=compressed, token_count=token_count, sponsorship_flag=sponsorship_flag)


def normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extract_lines(text: str, markers: tuple[str, ...]) -> list[str]:
    chunks = re.split(r"[\n\r\.\!\?;]", text)
    out: list[str] = []
    for chunk in chunks:
        low = chunk.lower()
        if any(m in low for m in markers):
            cleaned = chunk.strip()
            if cleaned:
                out.append(cleaned)
    return out


def _extract_seniority(text: str) -> str:
    years = re.findall(r"(\d+)\+?\s+years", text, flags=re.I)
    if not years:
        return "unspecified"
    max_year = max(int(y) for y in years)
    if max_year >= 8:
        return "senior"
    if max_year >= 4:
        return "mid"
    return "junior"


def _extract_role_type(text: str) -> str:
    low = text.lower()
    if "hybrid" in low:
        return "hybrid"
    if "remote" in low:
        return "remote"
    if "onsite" in low or "on-site" in low:
        return "onsite"
    return "unspecified"


def count_tokens(text: str) -> int:
    if tiktoken is None:
        return max(1, len(text) // 4)
    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))
