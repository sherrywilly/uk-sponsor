from __future__ import annotations

import re
from collections.abc import Iterable

import tiktoken
from bs4 import BeautifulSoup

from .schemas import JDCompressed, JDExtractionResult

TECH_KEYWORDS = {
    "python",
    "django",
    "fastapi",
    "react",
    "typescript",
    "javascript",
    "aws",
    "gcp",
    "azure",
    "docker",
    "kubernetes",
    "terraform",
    "postgresql",
    "mysql",
    "redis",
    "celery",
    "graphql",
    "rest",
    "microservices",
    "ci/cd",
    "git",
    "linux",
    "nginx",
    "playwright",
}

REQ_HINTS = ("required", "must", "essential")
PREF_HINTS = ("preferred", "nice to have", "desirable")
SPONSORSHIP_BLOCKERS = (
    "no sponsorship",
    "no visa support",
    "must have right to work",
    "cannot provide sponsorship",
)


def _extract_text_lines(text: str) -> list[str]:
    return [line.strip(" -•\t") for line in text.splitlines() if line.strip()]


def _find_best_container(soup: BeautifulSoup):
    selectors = ["article", "main", "[class*='job-desc']", "[class*='description']", "[id*='job']"]
    for selector in selectors:
        node = soup.select_one(selector)
        if node and node.get_text(strip=True):
            return node
    return soup.body or soup


def _extract_seniority(text: str) -> str | None:
    years = re.findall(r"(\d{1,2})\+?\s+years", text, flags=re.IGNORECASE)
    if not years:
        return None
    max_years = max(int(year) for year in years)
    if max_years < 3:
        return "junior"
    if max_years < 6:
        return "mid"
    return "senior"


def _extract_role_type(text: str) -> str | None:
    low = text.lower()
    if "hybrid" in low:
        return "hybrid"
    if "remote" in low:
        return "remote"
    if "onsite" in low or "on-site" in low:
        return "onsite"
    return None


def _extract_skills(lines: Iterable[str], hints: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for line in lines:
        low = line.lower()
        if any(hint in low for hint in hints):
            out.append(line)
    return out[:20]


def _extract_tech_stack(text: str) -> list[str]:
    low = text.lower()
    found = [tech for tech in TECH_KEYWORDS if tech in low]
    return sorted(found)


def extract_jd(html: str) -> JDExtractionResult:
    soup = BeautifulSoup(html, "lxml")
    container = _find_best_container(soup)
    raw_text = re.sub(r"\s+", " ", container.get_text("\n", strip=True)).strip()
    lines = _extract_text_lines(container.get_text("\n", strip=True))

    sponsorship_flag = "blocked" if any(flag in raw_text.lower() for flag in SPONSORSHIP_BLOCKERS) else "ok"

    compressed = JDCompressed(
        required_skills=_extract_skills(lines, REQ_HINTS),
        preferred_skills=_extract_skills(lines, PREF_HINTS),
        tech_stack=_extract_tech_stack(raw_text),
        seniority=_extract_seniority(raw_text),
        sponsorship_flag=sponsorship_flag,
        role_type=_extract_role_type(raw_text),
    )

    compressed_text = compressed.model_dump_json()
    encoder = tiktoken.get_encoding("cl100k_base")
    token_count = len(encoder.encode(compressed_text))

    return JDExtractionResult(
        raw_text=raw_text,
        compressed=compressed,
        token_count=token_count,
        sponsorship_flag=sponsorship_flag,
    )
