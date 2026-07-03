from __future__ import annotations

import re


ATS_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "greenhouse": [re.compile(r"greenhouse\.io", re.I), re.compile(r"boards\.greenhouse", re.I)],
    "lever": [re.compile(r"lever\.co", re.I)],
    "workday": [re.compile(r"myworkdayjobs\.com", re.I), re.compile(r"workday", re.I)],
    "ashby": [re.compile(r"ashbyhq\.com", re.I), re.compile(r"jobs\.ashbyhq", re.I)],
    "smartrecruiters": [re.compile(r"smartrecruiters\.com", re.I)],
    "bamboohr": [re.compile(r"bamboohr\.com", re.I), re.compile(r"bamboohr", re.I)],
}


def detect_ats(*, url: str = "", html: str = "", text: str = "") -> str | None:
    corpus = "\n".join([url, html, text])
    for provider, patterns in ATS_PATTERNS.items():
        if any(p.search(corpus) for p in patterns):
            return provider
    return None
